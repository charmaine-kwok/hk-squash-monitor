# HK Squash Monitor

A lightweight Python automation project that monitors Hong Kong Squash league results, reconstructs individual player matchups, and sends Telegram notifications when match scores are published or changed.

It also provides on-demand Telegram commands for checking scores and viewing the latest league standings.

## Live Match Viewer

Individual player match results can be viewed here:

**https://charmaine-kwok.github.io/hk-squash-monitor/**

The web interface is powered by GitHub Pages and automatically reads the latest reconstructed player match data.

## Features

- Monitors multiple HK Squash divisions
- Detects newly published match results
- Detects corrections to existing results
- Ignores BYE fixtures
- Sends Telegram notifications when scores change
- Reconstructs individual player-vs-player matchups
- Uses player ranking points and registered team order to determine lineups
- Handles concession results (`CR`)
- Stores team results in `results.json`
- Stores reconstructed individual matches in `player_matches.json`
- Stores player history/state in `player_state.json`
- Publishes individual match results through GitHub Pages
- Provides `/checkscore` for an on-demand score check
- Provides `/standings` for the latest league standings
- Uses a Telegram webhook for immediate command handling
- Uses Cloudflare Workers for the Telegram webhook
- Uses GitHub Actions to run the Python monitoring scripts
- Uses cron-job.org for scheduled checks
- Centralizes league configuration in `config.py`

## Currently Monitored Leagues

- Division D15B
- Division L4

League IDs, season and year are configured in `config.py`.

Current season:

```text
2026–2027 Main League
```

## Architecture

```text
                         ┌─────────────────────┐
                         │      Telegram       │
                         └──────────┬──────────┘
                                    │
                         /start /help /checkscore
                                /standings
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Cloudflare Worker   │
                         │ Telegram Webhook    │
                         └──────────┬──────────┘
                                    │
                          repository_dispatch
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   GitHub Actions    │
                         └──────────┬──────────┘
                                    │
                  ┌─────────────────┴─────────────────┐
                  │                                   │
                  ▼                                   ▼
             monitor.py                          standings.py
                  │                                   │
                  ▼                                   ▼
       HK Squash results page              HK Squash standings page
                  │
                  ▼
          compare results.json
                  │
          ┌───────┴────────┐
          │                │
       no change        changed
          │                │
        silent             ▼
                    player_matches.py
                           │
                ┌──────────┼──────────┐
                │          │          │
                ▼          ▼          ▼
         player_matches  player_state  docs/
             .json          .json      player_matches.json
                │                        │
                │                        ▼
                │                 GitHub Pages UI
                │
                ▼
       Telegram notification
       with individual matches
```

Scheduled monitoring uses:

```text
cron-job.org
     │
     │ scheduled checks
     ▼
GitHub repository_dispatch
     │
     ▼
GitHub Actions
     │
     ▼
monitor.py
     │
     ├── results.json
     ├── player_matches.json
     ├── player_state.json
     └── docs/player_matches.json
```

## Telegram Commands

### `/start`

Displays information about the bot and available commands.

### `/help`

Displays the available commands.

### `/checkscore`

Immediately triggers a GitHub Action to check the latest HK Squash results.

Example:

```text
✅ Score check complete

Division D15B: 87 results pending
Division L4: 60 results pending

No new results since the previous check.
```

If a new result is found, the bot sends the team result together with reconstructed individual player matches where available.

Example:

```text
🚨 HK Squash result updated!

Division L4

Squashathon Ladies
vs
Kwai Tsing District Squash Club L4

Result: 2-2(3-0,2-3,3-0,0-3)

Individual matches:
1. Chung Wing Yin vs Chow Hoi Ying — 3-0
2. Yuen Wai Ting vs Yu Wing Tung — 2-3
3. Chak Wai Suen vs Tam Sum Yi — 3-0
4. Tsang Ka Lei Carrie vs Kwok Wai Yin — 0-3
```

### `/standings`

Fetches the latest standings for all configured divisions.

## Scheduled Monitoring

cron-job.org triggers the GitHub workflow using GitHub's `repository_dispatch` API.

The scheduled job:

1. Triggers the GitHub Action.
2. Runs `monitor.py`.
3. Downloads the latest HK Squash results.
4. Compares them against `results.json`.
5. Detects newly published or corrected scores.
6. Reconstructs individual player matchups.
7. Sends Telegram notifications when results change.
8. Updates `results.json`.
9. Updates `player_matches.json`.
10. Updates `player_state.json`.
11. Updates `docs/player_matches.json`.
12. Commits the latest data back to the repository.
13. GitHub Pages automatically serves the updated player match data.

## Result Change Detection

Each fixture is identified using:

```text
date | team1 | team2 | venue | time
```

Including the date prevents return fixtures involving the same teams, venue and time from overwriting earlier fixtures.

The monitor detects:

```text
blank result → published result
```

and:

```text
existing result → corrected result
```

## Individual Player Match Reconstruction

HK Squash publishes team results containing individual game scores, for example:

```text
2-2(3-0,2-3,3-0,0-3)
```

The project combines this with:

- registered team player order
- player ranking points
- previous player averages
- previous number of matches played
- the official divisional ranking points table

to reconstruct which players participated at each position.

Player order is treated as an ascending constraint.

For example, if selected players have registered orders:

```text
1, 3, 5, 7
```

they may play positions:

```text
1 → order 1
2 → order 3
3 → order 5
4 → order 7
```

but the order cannot reverse.

### Player average calculation

For later weeks, the expected new average is calculated using:

```text
(previous average × previous matches played + new match points)
÷
(previous matches played + 1)
```

This allows the monitor to identify which player participated even after multiple league matches.

### Blank points vs 0.00

The tracker distinguishes between:

```text
blank points
```

and:

```text
0.00 points
```

A blank value means no ranking score is recorded, while an explicit `0.00` can represent a player who participated and earned zero ranking points.

This distinction is important for identifying players at lower playing positions.

### Concessions

`CR` is treated as a concession resulting in an effective 3–0 win.

Example:

```text
4. Kwok Wai Yin — CR (3-0)
```

The original `CR` result is preserved in the stored data.

## Player Match Web Interface

The player match viewer is published through GitHub Pages:

**https://charmaine-kwok.github.io/hk-squash-monitor/**

The interface supports:

- division selection
- week selection
- team match results
- individual player-vs-player results
- concession results
- unresolved or partially reconstructed matches

The page reads:

```text
docs/player_matches.json
```

which is automatically generated whenever player match data changes.

## League Configuration

League information is stored in `config.py`.

Example:

```python
LEAGUES = {
    "D15B": {
        "id": "D00549",
        "year": "2026-2027",
        "season": "Squash",
        "pages_id": 25,
    },
    "L4": {
        "id": "D00542",
        "year": "2026-2027",
        "season": "Squash",
        "pages_id": 25,
    },
}
```

The application automatically generates the results, standings and player URLs from this configuration.

To monitor another league, add another entry to `LEAGUES`.

## Project Structure

```text
hk-squash-monitor/
├── .github/
│   └── workflows/
│       └── monitor.yml
├── docs/
│   ├── index.html
│   └── player_matches.json
├── config.py
├── monitor.py
├── player_matches.py
├── standings.py
├── results.json
├── player_matches.json
├── player_state.json
├── requirements.txt
├── .gitignore
└── README.md
```

## Technologies

- Python
- Requests
- Beautiful Soup
- Telegram Bot API
- Cloudflare Workers
- GitHub Actions
- GitHub REST API
- GitHub Pages
- cron-job.org

## Local Setup

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Create a local `.env` file:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

The `.env` file must not be committed to GitHub.

Run a score check locally:

```bash
python monitor.py
```

Run a standings check locally:

```bash
python standings.py
```

Reconstruct existing completed player matches:

```bash
python player_matches.py
```

Test the web interface locally:

```bash
python -m http.server 8000
```

Then open:

```text
http://localhost:8000/docs/
```

## GitHub Secrets

The GitHub Actions workflow uses:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

The Telegram webhook is hosted separately in Cloudflare Workers.

## Cloudflare Worker

The Cloudflare Worker receives Telegram webhook updates and handles lightweight commands.

Commands such as `/checkscore` and `/standings` trigger GitHub Actions through GitHub's `repository_dispatch` API.

Sensitive values such as the Telegram bot token and GitHub token are stored as Cloudflare Worker secrets rather than in the source code.

## Security

- Telegram bot tokens are stored in environment variables or GitHub Secrets.
- GitHub API tokens are stored as Cloudflare Worker secrets.
- `.env` is excluded from version control.
- No credentials are committed to the repository.

## Disclaimer

This is a personal automation project and is not affiliated with the Squash Association of Hong Kong, China.

Match and player information is derived from publicly available HK Squash league data.