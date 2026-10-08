import unittest
from html.parser import HTMLParser
import hashlib
import os
import re
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path
import wheel

DATA_FILE = Path(__file__).parent / "gamesdata.csv"
LIVE_CACHE_DIR = Path(tempfile.gettempdir()) / "game-picker-gamefaqs-test-cache"
LIVE_CACHE_TTL_SECONDS = 24 * 60 * 60
LIVE_REQUEST_DELAY_SECONDS = 2


class _GameTitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.titles = []
        self._current_tag = None
        self._current_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"title", "h1"}:
            self._current_tag = tag
            self._current_text = []
        elif tag == "meta":
            property_name = attrs.get("property", "").lower()
            name = attrs.get("name", "").lower()
            if property_name == "og:title" or name == "title":
                content = attrs.get("content")
                if content:
                    self.titles.append(content)

    def handle_endtag(self, tag):
        if tag == self._current_tag:
            title = " ".join("".join(self._current_text).split())
            if title:
                self.titles.append(title)
            self._current_tag = None
            self._current_text = []

    def handle_data(self, data):
        if self._current_tag:
            self._current_text.append(data)


def _normalize_title(title):
    title = re.sub(r"\s*(?:\||[-\u2013\u2014])\s*GameFAQs.*$", "", title, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", title.lower())


def _page_matches_game_title(html, expected_title):
    parser = _GameTitleParser()
    parser.feed(html)
    expected = _normalize_title(expected_title)
    return bool(expected) and any(
        _normalize_title(candidate) == expected for candidate in parser.titles
    )


def _cache_path(url):
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return LIVE_CACHE_DIR / f"{key}.html"


def _load_cached_page(url):
    path = _cache_path(url)
    try:
        if time.time() - path.stat().st_mtime > LIVE_CACHE_TTL_SECONDS:
            return None
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _cache_page(url, html):
    try:
        LIVE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(url).write_text(html, encoding="utf-8")
    except OSError as error:
        import warnings

        warnings.warn(f"Could not cache GameFAQs test response: {error}", RuntimeWarning)


def _retry_after(response):
    value = response.headers.get("Retry-After")
    if value and value.isdigit():
        return f"Retry-After: {value} seconds"
    return "Retry-After header was not provided"


class TestDatasetIDs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.games = wheel.load_games(str(DATA_FILE))

    def test_games_loaded(self):
        """Ensure the dataset is found and contains entries."""
        self.assertGreater(len(self.games), 0, "No games were loaded from dataset.")

    def test_no_missing_or_blank_ids(self):
        """Ensure every game has a non-empty, non-whitespace ID."""
        missing = [g.title for g in self.games if not g.game_id or not g.game_id.strip()]
        self.assertEqual(
            missing, [],
            f"Found {len(missing)} games with missing or empty IDs: {missing[:5]}"
        )

    def test_all_ids_are_numeric(self):
        """Ensure all present IDs consist purely of digits without crashing if an ID is missing."""
        non_numeric = [
            (g.title, g.game_id)
            for g in self.games
            if g.game_id is not None and not g.game_id.isdigit()
        ]
        self.assertEqual(
            non_numeric, [],
            f"Found {len(non_numeric)} games with non-numeric IDs: {non_numeric[:5]}"
        )

    def test_id_ranges_and_positivity(self):
        """Ensure present numeric IDs are positive numbers (> 0) without crashing on non-numeric/blank values."""
        invalid_numbers = [
            (g.title, g.game_id)
            for g in self.games
            if g.game_id is not None and g.game_id.isdigit() and int(g.game_id) <= 0
        ]
        self.assertEqual(
            invalid_numbers, [],
            f"Found {len(invalid_numbers)} games with non-positive IDs: {invalid_numbers[:5]}"
        )

    def test_all_games_generate_valid_gamefaqs_urls(self):
        """Ensure every (ID, platform, title) combination successfully produces a valid GameFAQs URL."""
        malformed = []
        url_pattern = re.compile(r"^https://gamefaqs\.gamespot\.com/([a-zA-Z0-9\-]+)/(\d+)-([a-zA-Z0-9\-]+)$")

        for g in self.games:
            url = wheel.build_gamefaqs_url(g)
            if not url or not url_pattern.match(url):
                malformed.append((g.title, g.game_id, g.platform, url))

        self.assertEqual(
            malformed, [],
            f"Found {len(malformed)} games generating invalid GameFAQs URLs: {malformed[:5]}"
        )

    def test_no_id_platform_collisions_across_different_titles(self):
        """Ensure the same (ID, platform) is never assigned to two completely different game titles."""
        seen = {}
        collisions = []

        for g in self.games:
            if not g.game_id:
                continue
            key = (g.game_id, g.platform)
            if key in seen and seen[key].lower() != g.title.lower():
                collisions.append((key, seen[key], g.title))
            seen[key] = g.title

        self.assertEqual(
            collisions, [],
            f"Found {len(collisions)} (ID, platform) collisions: {collisions[:5]}"
        )

    def test_live_title_match_requires_the_full_game_title(self):
        self.assertTrue(
            _page_matches_game_title(
                "<html><head><title>Super Mario Galaxy - GameFAQs</title></head></html>",
                "Super Mario Galaxy",
            )
        )
        self.assertFalse(
            _page_matches_game_title(
                "<html><head><title>Super Mario Galaxy 2 - GameFAQs</title></head></html>",
                "Super Mario Galaxy",
            )
        )

    def test_sample_ids_are_legitimate_on_gamefaqs(self):
        """Verify a small sample against GameFAQs, caching results and respecting rate limits.

        Skipped by default. Successful pages are cached locally for 24 hours to avoid
        repeat requests. On HTTP 429, stop requesting and skip after reporting prior
        failures; do not retry or attempt to work around the server's limit.
        Run with: RUN_LIVE_TESTS=1 python -m unittest test_ids.py
        """
        if not os.environ.get("RUN_LIVE_TESTS"):
            self.skipTest("Live GameFAQs network test skipped. Run with RUN_LIVE_TESTS=1 to enable.")

        if not self.games:
            return

        indices = [0, 100, 1000, 5000, 10000]
        sample = [self.games[i] for i in indices if i < len(self.games)]
        failed = []
        rate_limited = None
        network_requests = 0

        for g in sample:
            url = wheel.build_gamefaqs_url(g)
            self.assertIsNotNone(url, f"Failed to build URL for {g.title}")

            html = _load_cached_page(url)
            if html is None:
                if network_requests:
                    time.sleep(LIVE_REQUEST_DELAY_SECONDS)
                network_requests += 1
                req = wheel._gamefaqs_request(url)
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if resp.status != 200:
                            failed.append((g.title, g.game_id, f"HTTP {resp.status}"))
                            continue
                        html = wheel._decode_response(resp)
                    _cache_page(url, html)
                except urllib.error.HTTPError as error:
                    if error.code == 429:
                        rate_limited = _retry_after(error)
                        break
                    failed.append((g.title, g.game_id, f"HTTPError {error.code}"))
                    continue
                except (urllib.error.URLError, TimeoutError, OSError) as error:
                    failed.append((g.title, g.game_id, str(error)))
                    continue

            if not _page_matches_game_title(html, g.title):
                failed.append((g.title, g.game_id, "Page title did not exactly match game title"))

        self.assertEqual(
            failed, [],
            f"Sample ID verification on live GameFAQs failed: {failed}"
        )
        if rate_limited:
            self.skipTest(
                f"GameFAQs rate-limited the live test; stopped making requests. {rate_limited}"
            )


if __name__ == "__main__":
    unittest.main()
