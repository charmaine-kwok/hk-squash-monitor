# HK Squash Monitor

A lightweight Python monitor for Hong Kong Squash league results.

The script periodically checks selected league result pages, compares them against previously saved results, and sends a Telegram notification whenever a new score is published or an existing score changes.

## Features

* Monitors multiple HK Squash divisions
* Detects newly published match results
* Detects changes or corrections to existing results
* Ignores BYE fixtures
* Sends Telegram notifications only when a result changes
* Stores the latest known results in `results.json`
* Runs automatically through GitHub Actions
* Can be triggered externally using `repository_dispatch`

## Currently Monitored Leagues

* Division 9A
* Division 9C

League pages are provided by the Squash Association of Hong Kong, China.

## How It Works

```text
cron-job.org
      ↓
GitHub repository_dispatch
      ↓
GitHub Actions
      ↓
monitor.py
      ↓
HK Squash results pages
      ↓
compare with results.json
      ↓
 ┌───────────────┴───────────────┐
 │                               │
No change                    Result changed
 │                               │
Do nothing                Send Telegram alert
                                 ↓
                        Update results.json
```

## Example Notification

```text
🚨 HK Squash result updated!

Division 9C

SQUASH SCAM CLUB
vs
Unity Squash 3

Result: 2-1(3-0,1-3,3-0)
```

## Project Structure

```text
hk-squash-monitor/
├── .github/
│   └── workflows/
│       └── monitor.yml
├── monitor.py
├── requirements.txt
├── results.json
└── .gitignore
```

## Setup

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

Create a local `.env` file:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

The `.env` file should not be committed to the repository.

Run the monitor locally:

```bash
python monitor.py
```

## Automation

The GitHub Actions workflow supports:

* manual execution with `workflow_dispatch`
* external execution with `repository_dispatch`

The external event type is:

```text
check-squash-results
```

An external scheduler such as cron-job.org can trigger the workflow periodically using the GitHub REST API.

## Result State

`results.json` contains the most recently observed match results.

On each run:

1. Current results are fetched from the HK Squash website.
2. They are compared with `results.json`.
3. New or changed results trigger a Telegram notification.
4. `results.json` is updated with the latest state.

## Tech Stack

* Python
* Requests
* Beautiful Soup
* Telegram Bot API
* GitHub Actions
* cron-job.org

## Disclaimer

This is a personal automation project and is not affiliated with the Squash Association of Hong Kong, China.
