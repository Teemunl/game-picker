# Game Randomizer Wheel

A borderless, dark-themed desktop app that randomly picks a game from a CSV list with games released from 1987 to 2019. Hit **Spin**, watch it scroll through your library with a smooth ease-out animation, and land on a random pick. Complete with cover art and metadata pulled from GameFAQs or your CSV.

## What it does

- Loads a game list from a CSV file (`gamesdata.csv` by default)
- Spins through the list with an animated scroll
- Displays the selected game's **title**, **platform**, **year**, **developer**, and **score**
- Fetches and shows the **cover image** from GameFAQs after picking (requires `id` + `platform` columns)
- **Open Link** button opens the game's GameFAQs page (or a Google search as fallback)
- Frameless, rounded window — drag it anywhere by the title bar

## Requirements

```
pip install pillow
```

Pillow is optional but needed for cover art. The app runs without it.

## Running

```powershell
python wheel.py
```

Or double-click **`wheel.bat`** to launch without a console window.

```powershell
# Use a different CSV file
python wheel.py --file mygames.csv

# Console-only mode (no GUI)
python wheel.py --console
```

## CSV format

The app auto-detects columns by header name. Supported headers:

| Column | Aliases | Description |
|---|---|---|
| `title` | `name`, `game` | Game title **(required)** |
| `id` | `gameid` | GameFAQs game ID — used to fetch cover art and build the page link |
| `platform` | `system`, `console` | Platform abbreviation (e.g. `NS`, `PS4`, `PC`) |
| `year` | `released`, `release` | Release year |
| `developer` | `dev`, `studio` | Developer name |
| `avg score` | `score`, `avg` | Average review score |
| `reviews` | `reviewcount` | Number of reviews |

After a game is picked, the app uses `id` + `platform` to construct the GameFAQs URL, then fetches the cover image from that page automatically. No image URLs are needed in the CSV.
