import json
import os

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from config import LEAGUES, results_url


RESULTS_FILE = "results.json"

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BOT_COMMAND = os.getenv("BOT_COMMAND", "")


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


def get_matches(url):
    response = requests.get(url, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    matches = {}

    rows = soup.select("div.results-schedules-list")

    for row in rows:
        columns = row.find_all("div", recursive=False)

        if len(columns) != 6:
            continue

        team1 = columns[0].get_text(" ", strip=True)
        team2 = columns[2].get_text(" ", strip=True)
        venue = columns[3].get_text(" ", strip=True)
        match_time = columns[4].get_text(" ", strip=True)
        result = columns[5].get_text(" ", strip=True)

        # Skip header row
        if team1.lower() == "team":
            continue

        # Ignore BYE fixtures
        if "[BYE]" in team1 or "[BYE]" in team2:
            continue

        # Unique ID for the fixture
        match_id = f"{team1}|{team2}|{venue}|{match_time}"

        matches[match_id] = {
            "team1": team1,
            "team2": team2,
            "venue": venue,
            "time": match_time,
            "result": result,
        }

    return matches


def load_previous_results():
    if not os.path.exists(RESULTS_FILE):
        return {}

    with open(RESULTS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_results(results):
    with open(RESULTS_FILE, "w", encoding="utf-8") as file:
        json.dump(
            results,
            file,
            indent=2,
            ensure_ascii=False,
        )


def check_for_updates(old_results, new_results):
    updates = []

    for league_name, matches in new_results.items():
        old_league = old_results.get(league_name, {})

        for match_id, match in matches.items():
            new_result = match["result"]

            old_match = old_league.get(match_id)

            # New fixture not present in old baseline
            if old_match is None:
                continue

            old_result = old_match.get("result", "")

            # Blank result -> newly published result
            if old_result == "" and new_result != "":
                updates.append({
                    "league": league_name,
                    **match,
                })

            # Existing result -> corrected/changed result
            elif (
                old_result != ""
                and new_result != old_result
            ):
                updates.append({
                    "league": league_name,
                    **match,
                    "old_result": old_result,
                })

    return updates


def build_check_summary(pending_counts, update_count=None):
    lines = [
        "✅ Score check complete",
        "",
    ]

    if update_count is not None:
        lines.extend([
            f"New results found: {update_count}",
            "",
        ])

    for league_name, pending in pending_counts.items():
        lines.append(
            f"Division {league_name}: "
            f"{pending} results pending"
        )

    return lines


def main():
    print("Checking HK Squash results...\n")

    previous_results = load_previous_results()

    current_results = {}
    pending_counts = {}

    # Fetch every configured league once
    for league_name in LEAGUES:
        url = results_url(league_name)

        print(f"Fetching Division {league_name}...")

        matches = get_matches(url)

        current_results[league_name] = matches

        not_updated = sum(
            1
            for match in matches.values()
            if match["result"] == ""
        )

        pending_counts[league_name] = not_updated

        print(
            f"Division {league_name}: "
            f"{len(matches)} matches, "
            f"{not_updated} results not updated"
        )

    # First ever run
    if not previous_results:
        print("\nNo previous results found.")
        print("Saving current results as baseline.")

        save_results(current_results)

        if BOT_COMMAND == "checkscore":
            lines = build_check_summary(
                pending_counts
            )

            lines.extend([
                "",
                "Baseline created. "
                "No previous results to compare.",
            ])

            send_telegram_message(
                "\n".join(lines)
            )

        return

    updates = check_for_updates(
        previous_results,
        current_results,
    )

    if updates:
        print("\n🚨 NEW RESULT UPDATES!\n")

        for update in updates:
            print(
                f'Division {update["league"]}: '
                f'{update["team1"]} vs '
                f'{update["team2"]}'
            )

            if "old_result" in update:
                print(
                    f'Old: {update["old_result"]}'
                )

            print(
                f'New: {update["result"]}'
            )
            print()

            message = (
                "🚨 HK Squash result updated!\n\n"
                f'Division {update["league"]}\n\n'
                f'{update["team1"]}\n'
                "vs\n"
                f'{update["team2"]}\n\n'
                f'Result: {update["result"]}'
            )

            if "old_result" in update:
                message += (
                    f'\nPrevious: '
                    f'{update["old_result"]}'
                )

            send_telegram_message(message)

        # /checkscore should always give a completion response
        if BOT_COMMAND == "checkscore":
            lines = build_check_summary(
                pending_counts,
                update_count=len(updates),
            )

            send_telegram_message(
                "\n".join(lines)
            )

    else:
        print("\nNo new score updates.")

        # Scheduled checks stay silent.
        # Explicit /checkscore gets a response.
        if BOT_COMMAND == "checkscore":
            lines = build_check_summary(
                pending_counts
            )

            lines.extend([
                "",
                "No new results since "
                "the previous check.",
            ])

            send_telegram_message(
                "\n".join(lines)
            )

    # Always update baseline after a successful check
    save_results(current_results)


if __name__ == "__main__":
    main()