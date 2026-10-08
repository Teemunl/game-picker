import csv
import random
import argparse
import time
import sys
import re
import io
import gzip
import zlib
import ctypes
import urllib.parse
import urllib.request
import webbrowser

TRANSPARENT_COLOR = "#ff00ff"

try:
	import tkinter as tk
	from tkinter import messagebox
except Exception:
	tk = None

try:
	from PIL import Image, ImageTk
	PIL_AVAILABLE = True
except Exception:
	PIL_AVAILABLE = False


PLATFORM_GAMEFAQ_SLUGS = {
	"NS": "switch", "WII": "wii", "WIIU": "wii-u", "GC": "gamecube",
	"N64": "n64", "SNES": "snes", "GBA": "gba", "GB": "gb",
	"DS": "ds", "3DS": "3ds", "PS5": "ps5", "PS4": "ps4",
	"PS3": "ps3", "PS2": "ps2", "PS": "ps", "PSP": "psp",
	"VITA": "vita", "XONE": "xboxone", "X360": "xbox360",
	"XBOX": "xbox", "PC": "pc", "DC": "dreamcast", "XBL": "xboxlive",
}


def slugify_title(title):
	s = re.sub(r"['\"]", "", title.lower())
	return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def build_gamefaqs_url(game):
	if game and game.game_id and game.platform:
		slug = PLATFORM_GAMEFAQ_SLUGS.get(game.platform.upper(), game.platform.lower())
		return f"https://gamefaqs.gamespot.com/{slug}/{game.game_id}-{slugify_title(game.title)}"
	return None


class Game:
	def __init__(self, title, platform=None, game_id=None, year=None, avg_score=None, reviews=None, developer=None):
		self.title = title.strip()
		self.platform = platform.strip() if platform else None
		self.game_id = game_id.strip() if game_id else None
		self.year = year.strip() if year else None
		self.avg_score = avg_score.strip() if avg_score else None
		self.reviews = reviews.strip() if reviews else None
		self.developer = developer.strip() if developer else None

	def __str__(self):
		return self.title

	def display(self):
		if self.platform and self.year:
			return f"{self.title} ({self.platform}, {self.year})"
		if self.platform:
			return f"{self.title} ({self.platform})"
		return self.title

	def metadata_text(self):
		lines = []
		if self.platform:  lines.append(f"Platform: {self.platform}")
		if self.year:      lines.append(f"Year: {self.year}")
		if self.developer: lines.append(f"Developer: {self.developer}")
		if self.avg_score: lines.append(f"Score: {self.avg_score}")
		if self.reviews:   lines.append(f"Reviews: {self.reviews}")
		return "\n".join(lines) if lines else "No metadata available."


def _norm(header):
	return re.sub(r'[^a-z0-9]', '', header.lower().strip())


def load_games(path):
	COLS = {
		"title":    ({"title", "name", "gametitle", "game"}, 0),
		"id":       ({"id", "gameid", "gameid"}, None),
		"platform": ({"platform", "system", "console", "hardware"}, None),
		"year":     ({"year", "released", "release", "releaseyear"}, None),
		"avgscore": ({"avgscore", "score", "average", "avg"}, None),
		"reviews":  ({"reviews", "reviewcount", "review"}, None),
		"developer":({"developer", "dev", "studio"}, None),
	}
	games = []
	with open(path, encoding="utf-8", errors="replace") as f:
		reader = csv.reader(f)
		first = next(reader, None)
		if not first:
			return games
		headers = [_norm(h) for h in first]
		idx = {key: None for key in COLS}
		idx["title"] = 0
		for col_name, (aliases, _) in COLS.items():
			for i, h in enumerate(headers):
				if h in aliases:
					idx[col_name] = i
					break
		has_title_header = any(h in COLS["title"][0] for h in headers)
		if not has_title_header:
			games.append(Game(first[0].strip()))
		def _get(row, key):
			i = idx[key]
			return row[i].strip() if i is not None and len(row) > i else None
		for row in reader:
			if not row:
				continue
			title = _get(row, "title")
			if not title:
				continue
			games.append(Game(
				title,
				platform=_get(row, "platform"),
				game_id=_get(row, "id"),
				year=_get(row, "year"),
				avg_score=_get(row, "avgscore"),
				reviews=_get(row, "reviews"),
				developer=_get(row, "developer"),
			))
	return games


def open_game_link(game):
	url = build_gamefaqs_url(game) or f"https://www.google.com/search?q={urllib.parse.quote(game.title)}"
	webbrowser.open(url)


def make_draggable(widget):
	sx = sy = 0
	def on_press(e):
		nonlocal sx, sy
		sx, sy = e.x, e.y
	def on_drag(e):
		root = widget.winfo_toplevel()
		root.geometry(f"+{root.winfo_x() + e.x - sx}+{root.winfo_y() + e.y - sy}")
	widget.bind("<ButtonPress-1>", on_press)
	widget.bind("<B1-Motion>", on_drag)


def set_rounded_window(root, radius=20):
	if sys.platform != "win32":
		return
	def update_region(event=None):
		try:
			w, h = root.winfo_width(), root.winfo_height()
			if w > 0 and h > 0:
				hrgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius, radius)
				ctypes.windll.user32.SetWindowRgn(root.winfo_id(), hrgn, True)
		except Exception:
			pass
	root.bind("<Configure>", update_region)
	root.after(10, update_region)


def _gamefaqs_request(url, is_image=False, referer="https://gamefaqs.gamespot.com/"):
	headers = {
		'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
		'Accept-Language': 'en-US,en;q=0.9',
		'Referer': referer,
	}
	if is_image:
		headers.update({
			'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
			'Sec-Fetch-Dest': 'image',
			'Sec-Fetch-Mode': 'no-cors',
			'Sec-Fetch-Site': 'same-origin',
		})
	else:
		headers.update({
			'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
			'Accept-Encoding': 'gzip, deflate',
			'Upgrade-Insecure-Requests': '1',
			'Sec-Fetch-Dest': 'document',
			'Sec-Fetch-Mode': 'navigate',
			'Sec-Fetch-Site': 'same-origin',
			'Sec-Fetch-User': '?1',
			'Connection': 'close',
		})
	return urllib.request.Request(url, headers=headers)


def _decode_response(resp):
	raw = resp.read()
	enc = resp.getheader('Content-Encoding')
	if enc == 'gzip':    return gzip.decompress(raw).decode('utf-8', errors='replace')
	if enc == 'deflate': return zlib.decompress(raw).decode('utf-8', errors='replace')
	return raw.decode('utf-8', errors='replace')


def fetch_cover_image_url(page_url):
	if not page_url:
		return None
	try:
		with urllib.request.urlopen(_gamefaqs_request(page_url), timeout=10) as resp:
			html = _decode_response(resp)
		for pattern in (
			r'<div[^>]+class=["\']header_image["\'][^>]*style=["\']?[^"\'<]*background-image\s*:\s*url\(\s*([^)"\']+)\s*\)',
			r'"image"\s*:\s*"([^"\']+)"',
		):
			m = re.search(pattern, html, re.IGNORECASE)
			if m:
				return urllib.parse.urljoin(page_url, m.group(1).strip('\'"'))
	except Exception:
		pass
	return None


def load_poster(game, max_size=(200, 260)):
	if not PIL_AVAILABLE:
		return None
	page_url = build_gamefaqs_url(game)
	img_url = fetch_cover_image_url(page_url)
	if not img_url:
		return None
	# Prefer full-resolution front box art over tiny 100x140 thumbnail
	candidates = []
	if "_thumb" in img_url:
		candidates.append(img_url.replace("_thumb", "_front"))
	candidates.append(img_url)

	for candidate in candidates:
		try:
			req = _gamefaqs_request(candidate, is_image=True, referer=page_url or "https://gamefaqs.gamespot.com/")
			with urllib.request.urlopen(req, timeout=8) as resp:
				data = resp.read()
			img = Image.open(io.BytesIO(data))
			img.thumbnail(max_size, Image.LANCZOS)
			return ImageTk.PhotoImage(img)
		except Exception:
			continue
	return None


def console_spin(games, cycles=50, start_delay=0.01, end_delay=0.15):
	if not games:
		print("No games to pick from.")
		return
	total = len(games)
	target = random.randrange(total)
	indices = [(i * 7 + i) % total for i in range(cycles)]
	indices[-1] = target
	for i, idx in enumerate(indices):
		delay = start_delay + (end_delay - start_delay) * (i / (len(indices) - 1))
		sys.stdout.write('\r' + games[idx].display()[:80].ljust(80))
		sys.stdout.flush()
		time.sleep(delay)
	sel = games[target]
	print('\nSelected:', sel.display())
	if sel.platform or sel.year:
		if sel.platform: print('Platform:', sel.platform)
		if sel.year:     print('Year:', sel.year)
	return sel


def _add_hover(widget, normal_bg, hover_bg):
	widget.bind("<Enter>", lambda e: widget.config(bg=hover_bg))
	widget.bind("<Leave>", lambda e: widget.config(bg=normal_bg))


class WheelGUI:
	BG       = "#0d0d1a"
	PANEL    = "#12122a"
	ACCENT   = "#39ff14"
	DIM      = "#20a80a"
	BTN      = "#1a1a3a"
	SEP      = "#1e1e40"

	def __init__(self, root, games):
		self.root = root
		self.games = games
		self.poster_image = None
		self.spinning = False
		self.current = 0
		self.selected_game = None
		self.root.configure(bg=TRANSPARENT_COLOR)
		self._build_ui()

	def _build_ui(self):
		bg, panel, accent, dim, btn, sep = self.BG, self.PANEL, self.ACCENT, self.DIM, self.BTN, self.SEP

		frame = tk.Frame(self.root, bg=bg)
		frame.pack(padx=10, pady=10)

		# Title bar
		tbar = tk.Frame(frame, bg=panel)
		tbar.pack(fill='x')
		tk.Label(tbar, text="🎮  GAME RANDOMIZER", font=("Segoe UI", 11, "bold"), fg=accent, bg=panel).pack(side='left', padx=14, pady=8)
		tk.Label(tbar, text=f"{len(self.games)} games", font=("Segoe UI", 9), fg=dim, bg=panel).pack(side='left')
		self.close_btn = tk.Button(tbar, text="✕", command=self.root.destroy, bg=panel, fg="#888888",
			activebackground="#c0392b", activeforeground="white", bd=0, padx=10, pady=4,
			font=("Segoe UI", 10, "bold"), cursor="hand2")
		self.close_btn.pack(side='right', padx=4, pady=4)
		self.close_btn.bind("<Enter>", lambda e: self.close_btn.config(fg="white"))
		self.close_btn.bind("<Leave>", lambda e: self.close_btn.config(fg="#888888"))
		for w in (tbar, tbar.winfo_children()[0], tbar.winfo_children()[1]):
			make_draggable(w)

		tk.Frame(frame, bg=sep, height=1).pack(fill='x')

		# Spinning label
		self.label = tk.Label(frame, text="Press  Spin  to start",
			font=("Segoe UI", 18, "bold"), fg=accent, bg=bg, width=42, wraplength=620, pady=6)
		self.label.pack(padx=16, pady=(16, 8))

		# Buttons
		btn_row = tk.Frame(frame, bg=bg)
		btn_row.pack(pady=(0, 8))
		self.spin_btn = tk.Button(btn_row, text="⟳  Spin", command=self.start_spin,
			width=14, bg=btn, fg="white", activebackground=accent, activeforeground="#000",
			relief="flat", bd=0, padx=8, pady=6, font=("Segoe UI", 11, "bold"), cursor="hand2")
		self.spin_btn.grid(row=0, column=0, padx=6)
		self.link_btn = tk.Button(btn_row, text="🔗  Open Link", command=self.open_link,
			width=14, bg=btn, fg="white", activebackground="#2255cc", activeforeground="white",
			relief="flat", bd=0, padx=8, pady=6, font=("Segoe UI", 11), cursor="hand2")
		self.link_btn.grid(row=0, column=1, padx=6)
		_add_hover(self.spin_btn, btn, "#223322")
		_add_hover(self.link_btn, btn, "#1a1a40")

		# Result entry
		self.result_var = tk.StringVar()
		self.result_entry = tk.Entry(frame, textvariable=self.result_var,
			font=("Segoe UI", 13, "bold"), width=52, bg="#0e0e24", fg=accent,
			insertbackground=accent, relief="flat", bd=0,
			highlightthickness=1, highlightbackground=sep, highlightcolor=accent)
		self.result_entry.config(state='readonly', readonlybackground="#0e0e24")
		self.result_entry.pack(padx=16, pady=(0, 12), ipady=6)

		tk.Frame(frame, bg=sep, height=1).pack(fill='x', padx=16)

		# Info panel
		info = tk.Frame(frame, bg=panel)
		info.pack(padx=16, pady=12, fill='x')
		self.poster_label = tk.Label(info, bg="#0a0a1e", fg=dim, width=18, height=12,
			relief='flat', bd=0, text='No image', font=("Segoe UI", 9),
			highlightthickness=1, highlightbackground=sep)
		self.poster_label.pack(side='left', padx=(0, 14), pady=2)
		tk.Frame(info, bg=sep, width=1).pack(side='left', fill='y', pady=2)
		self.meta_label = tk.Label(info, text="No game selected.", justify='left', anchor='nw',
			font=("Segoe UI", 11), width=38, wraplength=310, bg=panel, fg="#cccccc", pady=4, padx=10)
		self.meta_label.pack(side='left', fill='both', expand=True)

		tk.Frame(frame, bg=sep, height=1).pack(fill='x')
		self.status_label = tk.Label(frame, text="Ready", font=("Segoe UI", 8),
			fg=dim, bg=panel, anchor='w', padx=12, pady=3)
		self.status_label.pack(fill='x')

	def open_link(self):
		if self.selected_game:
			open_game_link(self.selected_game)
		elif val := self.result_var.get():
			webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(val)}")

	def update_game_info(self, game):
		self.status_label.config(text="Loading image…")
		self.root.update_idletasks()
		self.poster_image = load_poster(game)
		if self.poster_image:
			self.poster_label.config(image=self.poster_image, text='', width=0, height=0)
		else:
			self.poster_label.config(image='', text='No image', width=18, height=12,
				bg='#0a0a1e', fg=self.ACCENT, anchor='center')
		self.meta_label.config(text=game.metadata_text(), fg="#cccccc")
		self.status_label.config(text=f"Selected: {game.display()}")

	def start_spin(self):
		if self.spinning:
			return
		self.spinning = True
		self.spin_btn.config(state=tk.DISABLED)
		self.status_label.config(text="Spinning…")
		total = len(self.games)
		cycles = random.randint(45, 60)
		target = random.randrange(total)
		indices = [(i * 5 + i) % total for i in range(cycles)]
		indices[-1] = target
		self._run_spin(indices, 0)

	def _run_spin(self, indices, i):
		self.current = indices[i]
		self.label.config(text=self.games[self.current].display())
		if i + 1 < len(indices):
			t = i / (len(indices) - 1)
			# Quadratic ease-out: rapid scrolling at start, smooth deceleration at end (~3-4s total)
			delay = int(15 + 175 * (t ** 2.2))
			self.root.after(delay, lambda: self._run_spin(indices, i + 1))
		else:
			self._finish()

	def _finish(self):
		sel = self.games[self.current]
		self.selected_game = sel
		self.update_game_info(sel)
		self.result_entry.config(state='normal')
		self.result_var.set(sel.display())
		self.result_entry.selection_range(0, 'end')
		self.result_entry.config(state='readonly')
		self.spin_btn.config(state=tk.NORMAL)
		self.spinning = False


def main():
	parser = argparse.ArgumentParser(description="Game randomizer wheel")
	parser.add_argument("--file", "-f", default="gamesdata.csv", help="Path to CSV file")
	parser.add_argument("--console", action="store_true", help="Console mode (no GUI)")
	args = parser.parse_args()

	games = load_games(args.file)
	if not games:
		print("No games loaded from:", args.file)
		return

	if args.console or tk is None:
		console_spin(games)
	else:
		root = tk.Tk()
		root.title("Game Randomizer")
		root.overrideredirect(True)
		root.configure(bg=TRANSPARENT_COLOR)
		if sys.platform == "win32":
			root.attributes("-transparentcolor", TRANSPARENT_COLOR)
		set_rounded_window(root, radius=20)
		WheelGUI(root, games)
		root.mainloop()


if __name__ == "__main__":
	main()
