# ufc-elo

Custom UFC Elo engine for pound-for-pound and divisional rankings, with GOAT case studies.

Scrapes every UFC bout from [ufcstats.com](http://ufcstats.com), replays fight history chronologically, and produces multi-dimensional Elo ratings — global pound-for-pound and per-division — with monthly snapshots for analysis and visualization.

For the full design rationale (carry-over rules, finish multipliers, loss penalty, Khabib vs Jones), see [docs/blog.md](docs/blog.md).

## Features

- **Fight database** — normalized fighter and fight records from 1993 to present
- **Multi-dimensional Elo** — parallel P4P and divisional ratings per fighter
- **Tunable model** — all constants in `config/config.json` (K-factor, loss penalty, result multipliers)
- **Historical snapshots** — forward-filled monthly time series for any point in time
- **Analysis notebook** — division and P4P timeline plots
- **P4P animation** — bar-chart-race MP4 of top-10 evolution since 2020
- **Weekly updates** — incremental scrape script with optional git commit/push

## Project structure

```
ufc-elo/
├── config/config.json       # Elo parameters
├── data/
│   ├── fighters.csv           # fighter IDs and names
│   ├── fights.csv             # bout results
│   └── historical_elo_snapshots.csv
├── docs/blog.md               # design write-up
├── notebooks/elo_analysis.ipynb
├── output/                    # generated MP4s (gitignored)
├── scripts/weekly_update.sh
└── src/
    ├── scrape_ufcstats.py
    ├── elo_engine.py
    └── generate_elo_animation.py
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`generate_elo_animation.py` requires [ffmpeg](https://ffmpeg.org/) on your PATH.

## Usage

Run all commands from the repository root.

### Scrape fight data

```bash
# Full historical backfill (~779 events, several hours)
python src/scrape_ufcstats.py --mode full

# Incremental update (page 1 only, stops at first known fight)
python src/scrape_ufcstats.py --mode incremental
```

### Compute Elo ratings

```bash
python src/elo_engine.py
```

Writes `data/historical_elo_snapshots.csv`. Re-run after changing `config/config.json` to recalculate the full history.

### Analyze and visualize

```bash
jupyter notebook notebooks/elo_analysis.ipynb
```

### Generate P4P animation

```bash
python src/generate_elo_animation.py
```

Output: `output/elo_evolution_2020.mp4`

### Weekly automated update

```bash
./scripts/weekly_update.sh
```

Incremental scrape, then commits and pushes `data/fighters.csv` and `data/fights.csv` if changed.

Cron example (Mondays at 6:00 AM):

```bash
0 6 * * 1 /path/to/ufc-elo/scripts/weekly_update.sh >> /path/to/ufc-elo/scrape.log 2>&1
```

## Model parameters

| Parameter | Default | Role |
|-----------|---------|------|
| `STARTING_ELO` | 1000 | Baseline for new fighters and division debuts |
| `BASE_K_FACTOR` | 32 | Rating movement per fight |
| `LOSS_MULTIPLIER` | 1.5 | Losses cost 1.5× what wins gain |
| `DEBUT_CARRY_OVER_PCT` | 0.90 | Cross-division reputation transfer (floor at 1000) |
| `RESULT_MULTIPLIERS` | 0.7–1.3 | Finish-quality scaling (KO/sub > decisions) |

## Data sources

Fight and fighter data from [ufcstats.com](http://ufcstats.com). Scraping uses a 1.5s delay between requests.

## License

Personal project — use and adapt as you like.
