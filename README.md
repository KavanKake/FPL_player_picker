# FPL Player Picker

A small Flask web app that recommends **Fantasy Premier League** players for a given budget and position, using live data from the official FPL API.

## Features

- **Best now** – ranks players by current form and points per game (z-score normalised).
- **Best for future** – estimates an expected score for each player over their next 3 fixtures, based on:
  - the player's form (falls back to points per game),
  - the team's goals scored/conceded over the last 5 matches,
  - the opponent's recent form,
  - the official Fixture Difficulty Rating (FDR).
- **Minimum minutes filter** (default 180) – leaves out players with too little playing time, so one good cameo doesn't top the list.
- Player photos, a highlighted top pick and the next four alternatives.
- Responsive layout that works on desktop and mobile.

## Getting started

Requires Python 3.9+.

```bash
git clone <repo-url>
cd FPLPlayerpic

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python fpl.py
```

Open <http://127.0.0.1:5000> in your browser.

## How to use

1. Enter your max price in £m (e.g. `7.5`).
2. Optionally adjust the minimum minutes played (default 180, set to 0 to include everyone).
3. Choose a position: GK, DEF, MID or FWD.
4. Click **Best now** for in-form picks, or **Best for future** to factor in upcoming fixtures.

## How the scoring works

### Best now

```
score = z(form) + z(points_per_game)
```

Both values are standardised within the filtered player pool (same position, within budget), so they contribute equally.

### Best for future

For each of the player's next 3 fixtures:

| Position   | Fixture score                                            |
|------------|----------------------------------------------------------|
| MID / FWD  | `form × (team goals scored / opp. goals conceded) × FDR factor` |
| GK / DEF   | `form × (1 / opp. goals scored) × FDR factor`            |

`FDR factor = (6 − FDR) / 5`, so an FDR of 1 gives 1.0 and an FDR of 5 gives 0.2. The expected score is the average across the fixtures.

> These are simple heuristics – a fun starting point, not a guarantee of points.

## Project structure

```
FPLPlayerpic/
├── fpl.py              # Flask app, data fetching and scoring logic
├── templates/
│   └── index.html      # Page template (Jinja2)
├── static/
│   └── style.css       # Styling
└── requirements.txt
```

## Data source

- `https://fantasy.premierleague.com/api/bootstrap-static/` – players, teams, positions
- `https://fantasy.premierleague.com/api/fixtures/` – fixtures and results
- Player photos from the Premier League CDN

This project is not affiliated with or endorsed by the Premier League.
