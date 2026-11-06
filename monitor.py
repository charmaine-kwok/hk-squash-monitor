import json
import os

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from config import LEAGUES, results_url
from player_matches import (
    fixture_has_unresolved,
    mark_fixture_notified,
    process_result_updates,
    retry_unresolved_fixtures,
)

RESULTS_FILE = "results.json"

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BOT_COMMAND = os.getenv("BOT_COMMAND", "")


def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing.")
        return False

    url = f"https://api.telegram.org/" f"bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
        },
        timeout=20,
    )

    response.raise_for_status()
    return True


def get_matches(url):
    response = requests.get(
        url,
        timeout=45,
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    matches = {}

    current_week = ""
    current_date = ""

    elements = soup.find_all(
        [
            "div",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
        ]
    )

    for element in elements:
        text = element.get_text(
            " ",
            strip=True,
        )

        if text.lower().startswith("week ") and " - " in text:
            parts = text.split(
                " - ",
                1,
            )

            current_week = parts[0].strip()
            current_date = parts[1].strip()

            continue

        classes = element.get(
            "class",
            [],
        )

        if "results-schedules-list" not in classes:
            continue

        columns = element.find_all(
            "div",
            recursive=False,
        )

        if len(columns) != 6:
            continue

        team1 = columns[0].get_text(
            " ",
            strip=True,
        )

        team2 = columns[2].get_text(
            " ",
            strip=True,
        )

        venue = columns[3].get_text(
            " ",
            strip=True,
        )

        match_time = columns[4].get_text(
            " ",
            strip=True,
        )

        result = columns[5].get_text(
            " ",
            strip=True,
        )

        if team1.lower() == "team":
            continue

        if "[BYE]" in team1 or "[BYE]" in team2:
            continue

        match_id = (
            f"{current_date}|" f"{team1}|" f"{team2}|" f"{venue}|" f"{match_time}"
        )

        matches[match_id] = {
            "week": current_week,
            "date": current_date,
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

    with open(
        RESULTS_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def save_results(results):
    with open(
        RESULTS_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            results,
            file,
            indent=2,
            ensure_ascii=False,
        )


def check_for_updates(
    old_results,
    new_results,
):
    updates = []

    for (
        league_name,
        matches,
    ) in new_results.items():

        old_league = old_results.get(
            league_name,
            {},
        )

        for (
            match_id,
            match,
        ) in matches.items():

            new_result = match["result"]

            old_match = old_league.get(match_id)

            if old_match is None:
                continue

            old_result = old_match.get(
                "result",
                "",
            )

            if old_result == "" and new_result != "":
                updates.append(
                    {
                        "league": league_name,
                        "match_id": match_id,
                        **match,
                    }
                )

            elif old_result != "" and new_result != old_result:
                updates.append(
                    {
                        "league": league_name,
                        "match_id": match_id,
                        **match,
                        "old_result": old_result,
                    }
                )

    return updates


def build_check_summary(
    pending_counts,
    update_count=None,
):
    lines = [
        "✅ Score check complete",
        "",
    ]

    if update_count is not None:
        lines.extend(
            [
                ("New results found: " f"{update_count}"),
                "",
            ]
        )

    for (
        league_name,
        pending,
    ) in pending_counts.items():
        lines.append(f"Division " f"{league_name}: " f"{pending} " f"results pending")

    return lines


def add_individual_matches_to_message(
    message,
    fixture,
):
    if not fixture:
        return message

    individual_matches = fixture.get(
        "individual_matches",
        [],
    )

    if not individual_matches:
        return message

    message += "\n\nIndividual matches:"

    for match in individual_matches:
        position = match.get(
            "position",
            "?",
        )

        score = match.get(
            "score",
            "",
        )

        player1 = match.get("player1")

        player2 = match.get("player2")

        result_type = match.get("result_type")

        if result_type == "concession":
            if player1:
                message += f"\n{position}. " f"{player1} — " f"CR (3-0)"

            elif player2:
                message += f"\n{position}. " f"{player2} — " f"CR (3-0)"

            else:
                message += f"\n{position}. " f"CR (3-0)"

            continue

        if player1 and player2:
            message += f"\n{position}. " f"{player1} vs " f"{player2} — " f"{score}"

        elif player1:
            message += f"\n{position}. " f"{player1} vs " f"Unresolved — " f"{score}"

        elif player2:
            message += f"\n{position}. " f"Unresolved vs " f"{player2} — " f"{score}"

        else:
            message += f"\n{position}. " f"Players unresolved — " f"{score}"

    return message


def main():
    print("Checking HK Squash " "results...\n")

    previous_results = load_previous_results()

    current_results = {}
    pending_counts = {}

    for league_name in LEAGUES:
        url = results_url(league_name)

        print(f"Fetching Division " f"{league_name}...")

        matches = get_matches(url)

        current_results[league_name] = matches

        not_updated = sum(1 for match in matches.values() if match["result"] == "")

        pending_counts[league_name] = not_updated

        print(
            f"Division "
            f"{league_name}: "
            f"{len(matches)} matches, "
            f"{not_updated} results "
            f"not updated"
        )

    if not previous_results:
        print("\nNo previous " "results found.")

        print("Saving current results " "as baseline.")

        save_results(current_results)

        if BOT_COMMAND == "checkscore":
            lines = build_check_summary(pending_counts)

            lines.extend(
                [
                    "",
                    ("Baseline created. " "No previous " "results to compare."),
                ]
            )

            send_telegram_message("\n".join(lines))

        return

    updates = check_for_updates(
        previous_results,
        current_results,
    )

    individual_results = {}

    if updates:
        try:
            individual_results = process_result_updates(updates)

        except Exception as error:
            print("Player match " "reconstruction failed: " f"{error}")

            individual_results = {}

    if updates:
        print("\n🚨 NEW RESULT " "UPDATES!\n")

        for update in updates:
            print(
                f"Division "
                f'{update["league"]}: '
                f'{update["team1"]} vs '
                f'{update["team2"]}'
            )

            if "old_result" in update:
                print(f"Old: " f'{update["old_result"]}')

            print(f"New: " f'{update["result"]}')

            print()

            message = (
                "🚨 HK Squash result "
                "updated!\n\n"
                f"Division "
                f'{update["league"]}'
                "\n\n"
                f'{update["team1"]}'
                "\n"
                "vs\n"
                f'{update["team2"]}'
                "\n\n"
                f"Result: "
                f'{update["result"]}'
            )

            if "old_result" in update:
                message += "\nPrevious: " f'{update["old_result"]}'

            fixture = individual_results.get(
                (
                    update["league"],
                    update["match_id"],
                )
            )

            if fixture and not fixture_has_unresolved(fixture):
                message = add_individual_matches_to_message(
                    message,
                    fixture,
                )

                if send_telegram_message(message):
                    mark_fixture_notified(
                        update["league"],
                        update["match_id"],
                    )

                    print(
                        "Telegram "
                        "notification sent: "
                        f'{update["team1"]}'
                        " vs "
                        f'{update["team2"]}'
                    )

            else:
                print(
                    "Telegram notification "
                    "deferred: "
                    f'{update["team1"]}'
                    " vs "
                    f'{update["team2"]} '
                    "still has unresolved "
                    "players."
                )

        if BOT_COMMAND == "checkscore":
            lines = build_check_summary(
                pending_counts,
                update_count=len(updates),
            )

            send_telegram_message("\n".join(lines))

    else:
        print("\nNo new score updates.")

        if BOT_COMMAND == "checkscore":
            lines = build_check_summary(pending_counts)

            lines.extend(
                [
                    "",
                    ("No new results " "since the previous " "check."),
                ]
            )

            send_telegram_message("\n".join(lines))

    try:
        (
            retry_count,
            resolved_notifications,
        ) = retry_unresolved_fixtures(current_results)

        if retry_count:
            print(f"\nImproved " f"{retry_count} " f"unresolved " f"fixture(s).")

        for item in resolved_notifications:
            league_name = item["league"]

            match_id = item["match_id"]

            fixture = item["fixture"]

            message = (
                "🚨 HK Squash result "
                "updated!\n\n"
                f"Division "
                f"{league_name}\n\n"
                f'{fixture["team1"]}'
                "\n"
                "vs\n"
                f'{fixture["team2"]}'
                "\n\n"
                f"Result: "
                f'{fixture["team_result"]}'
            )

            message = add_individual_matches_to_message(
                message,
                fixture,
            )

            if send_telegram_message(message):
                mark_fixture_notified(
                    league_name,
                    match_id,
                )

                print(
                    "Telegram notification "
                    "sent: "
                    f'{fixture["team1"]}'
                    " vs "
                    f'{fixture["team2"]}'
                )

    except Exception as error:
        print("Unresolved match retry " "failed: " f"{error}")

    save_results(current_results)

    os.makedirs(
        "docs",
        exist_ok=True,
    )

    with open(
        "docs/schedule.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            current_results,
            file,
            indent=2,
            ensure_ascii=False,
        )


if __name__ == "__main__":
    main()
