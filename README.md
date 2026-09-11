# HK Squash Monitor

A lightweight Python automation project that monitors Hong Kong Squash league results and sends Telegram notifications when match scores are published or changed.

It also provides on-demand Telegram commands for checking scores and viewing the latest league standings.

## Features

* Monitors multiple HK Squash divisions
* Detects newly published match results
* Detects corrections to existing results
* Ignores BYE fixtures
* Sends Telegram notifications when scores change
* Stores the latest result state in `results.json`
* Provides `/checkscore` for an on-demand score check
* Provides `/standings` for the latest league standings
* Uses a Telegram webhook for immediate command handling
* Uses Cloudflare Workers for the Telegram webhook
* Uses GitHub Actions to run the Python monitoring scripts
* Uses cron-job.org for scheduled checks
* Centralizes league configuration in `config.py`

## Currently Monitored Leagues

* Division 9A
* Division 9C

League IDs, season and year are configured in `config.py`.

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
        ┌────────┴────────┐
        │                 │
     no change         changed
        │                 │
      silent       Telegram notification
                          │
                          ▼
                  update results.json
```

Scheduled monitoring uses a separate path:

```text
cron-job.org
      │
      │ every 15 minutes
      │ Monday–Friday, 09:00–18:00 HKT
      ▼
GitHub repository_dispatch
      │
      ▼
GitHub Actions
      │
      ▼
monitor.py
```



## Telegram Commands

### `/start`

Displays information about the bot and available commands.

### `/help`

Displays the available commands.

### `/checkscore`

Immediately triggers a GitHub Action to check the latest HK Squash results.

Example response:

```text
✅ Score check complete

Division 9A: 11 results pending
Division 9C: 8 results pending

No new results since the previous check.
```

If new results are found, the bot also sends the newly published scores.

### `/standings`

Fetches the latest standings for all configured divisions.

Example:

```text
🏆 Division 9A Standings

1. M&M Squash — 31 pts (9P 8W 1L)
2. I am fine thank you and you — 29 pts (8P 8W 0L)
3. Hong Kong Racketlon Association D9 — 20 pts (9P 5W 4L)
...
```

## Scheduled Monitoring

cron-job.org triggers the GitHub workflow periodically using GitHub's `repository_dispatch` API.

The current schedule is intended to monitor league updates during weekday daytime hours.

The scheduled job:

1. Triggers the GitHub Action.
2. Runs `monitor.py`.
3. Downloads the latest results.
4. Compares them against `results.json`.
5. Sends Telegram notifications only when results change.
6. Updates and commits `results.json`.

## Result Change Detection

Each fixture is identified using:

```text
team1 | team2 | venue | time
```

The monitor detects:

```text
blank result → published result
```

and:

```text
existing result → corrected result
```

Example notification:

```text
🚨 HK Squash result updated!

Division 9C

SQUASH SCAM CLUB
vs
Unity Squash 3

Result: 2-1(3-0,1-3,3-0)
```

## League Configuration

League information is stored in `config.py`.

Example:

```python
LEAGUES = {
    "9A": {
        "id": "D00516",
        "year": 2026,
        "season": "Summer",
    },
    "9C": {
        "id": "D00518",
        "year": 2026,
        "season": "Summer",
    },
}
```

The application automatically generates both the results and standings URLs from this configuration.

To add another league, add another entry to `LEAGUES`.

## Project Structure

```text
hk-squash-monitor/
├── .github/
│   └── workflows/
│       └── monitor.yml
├── config.py
├── monitor.py
├── standings.py
├── results.json
├── requirements.txt
├── .gitignore
└── README.md
```

## Technologies

* Python
* Requests
* Beautiful Soup
* Telegram Bot API
* Cloudflare Workers
* GitHub Actions
* GitHub REST API
* cron-job.org

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

## GitHub Secrets

The GitHub Actions workflow uses:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

The Telegram webhook is hosted separately in Cloudflare Workers.

## Cloudflare Worker

The Cloudflare Worker receives Telegram webhook updates and handles lightweight commands directly.

Commands such as `/checkscore` and `/standings` trigger GitHub Actions through the GitHub `repository_dispatch` API.

Sensitive values such as the Telegram bot token and GitHub token are stored as Cloudflare Worker secrets rather than in the source code.

## Security

* Telegram bot tokens are stored in environment variables/secrets.
* GitHub API tokens are stored as Cloudflare Worker secrets.
* `.env` is excluded from version control.
* No credentials are committed to the repository.

## Disclaimer

This is a personal automation project and is not affiliated with the Squash Association of Hong Kong, China.
