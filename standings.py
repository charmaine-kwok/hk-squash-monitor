import os

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from config import LEAGUES, standings_url


load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
        },
        timeout=20,
    )

    response.raise_for_status()


def get_standings(url):
    response = requests.get(url, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    standings = []

    rows = soup.select("div.teamSummary-content-list")

    for row in rows:
        columns = row.find_all("div", recursive=False)

        if len(columns) != 5:
            continue

        team = columns[0].get_text(" ", strip=True)
        played = columns[1].get_text(" ", strip=True)
        won = columns[2].get_text(" ", strip=True)
        lost = columns[3].get_text(" ", strip=True)
        points = columns[4].get_text(" ", strip=True)

        # Skip header row
        if team == "" and played.lower() == "played":
            continue

        try:
            standings.append({
                "team": team,
                "played": int(played),
                "won": int(won),
                "lost": int(lost),
                "points": int(points),
            })
        except ValueError:
            continue

    standings.sort(
        key=lambda team: team["points"],
        reverse=True
    )

    return standings


def format_standings(league_name, standings):
    lines = [
        f"🏆 Division {league_name} Standings",
        "",
    ]

    for position, team in enumerate(standings, start=1):
        lines.append(
            f"{position}. {team['team']} — "
            f"{team['points']} pts "
            f"({team['played']}P "
            f"{team['won']}W "
            f"{team['lost']}L)"
        )

    return "\n".join(lines)


def main():
    messages = []

    for league_name in LEAGUES:
        url = standings_url(league_name)

        print(
            f"Fetching Division {league_name} standings..."
        )

        try:
            standings = get_standings(url)

            if not standings:
                messages.append(
                    f"⚠️ Could not read Division "
                    f"{league_name} standings."
                )
                continue

            messages.append(
                format_standings(
                    league_name,
                    standings
                )
            )

        except requests.RequestException as error:
            print(
                f"Failed to fetch Division "
                f"{league_name}: {error}"
            )

            messages.append(
                f"⚠️ Failed to fetch Division "
                f"{league_name} standings."
            )

    if not messages:
        send_telegram_message(
            "⚠️ No standings could be retrieved."
        )
        return

    send_telegram_message(
        "\n\n".join(messages)
    )


if __name__ == "__main__":
    main()