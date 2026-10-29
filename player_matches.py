import json
import os
import re
import requests
from bs4 import BeautifulSoup
from config import players_url

RESULTS_FILE = "results.json"

PLAYER_MATCHES_FILE = "player_matches.json"

PLAYER_STATE_FILE = "player_state.json"

# Official HK Squash divisional ranking points

POINTS_TABLE = {
    1: {
        "3-0": 27,
        "3-1": 24,
        "3-2": 21,
        "2-3": 18,
        "1-3": 15,
        "0-3": 12,
    },
    2: {
        "3-0": 24,
        "3-1": 21,
        "3-2": 18,
        "2-3": 15,
        "1-3": 12,
        "0-3": 9,
    },
    3: {
        "3-0": 21,
        "3-1": 18,
        "3-2": 15,
        "2-3": 12,
        "1-3": 9,
        "0-3": 6,
    },
    4: {
        "3-0": 18,
        "3-1": 15,
        "3-2": 12,
        "2-3": 9,
        "1-3": 6,
        "0-3": 3,
    },
    5: {
        "3-0": 15,
        "3-1": 12,
        "3-2": 9,
        "2-3": 6,
        "1-3": 3,
        "0-3": 0,
    },
}


def load_json(path):

    if not os.path.exists(path):

        return {}

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


def save_json(path, data):

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


def get_players(league_name):

    response = requests.get(
        players_url(league_name),
        timeout=45,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    tokens = list(soup.stripped_strings)

    teams = {}

    i = 0

    while i < len(tokens):

        if tokens[i].lower() != "team name:":

            i += 1

            continue

        if i + 1 >= len(tokens):

            break

        team_name = tokens[i + 1]

        teams[team_name] = {"players": {}}

        i += 2

        # Find Points header

        while (
            i < len(tokens)
            and tokens[i].lower() != "points"
            and tokens[i].lower() != "team name:"
        ):

            i += 1

        if i >= len(tokens) or tokens[i].lower() == "team name:":

            continue

        i += 1

        # Parse player rows

        while i < len(tokens) and tokens[i].lower() != "team name:":

            if not tokens[i].isdigit():

                i += 1

                continue

            order = int(tokens[i])

            if i + 3 >= len(tokens):

                break

            hks_no = tokens[i + 1]

            player_name = tokens[i + 2]

            ranking = tokens[i + 3]

            if not hks_no.isdigit():

                i += 1

                continue

            if not player_name or player_name.isdigit():

                i += 1

                continue

            # None = no points value shown / has not played

            # 0.0 = explicit 0.00 shown / played and earned zero points

            points = None

            next_index = i + 4

            if next_index < len(tokens):

                possible_points = tokens[next_index]

                if re.fullmatch(
                    r"-?\d+**\\.**\d+",
                    possible_points,
                ):

                    points = float(possible_points)

                    next_index += 1

            teams[team_name]["players"][hks_no] = {
                "order": order,
                "name": player_name,
                "ranking": ranking,
                "points": points,
            }

            i = next_index

    return teams


def extract_individual_scores(result):

    if "(" not in result or ")" not in result:

        return []

    inside = result.split(
        "(",
        1,
    )[1].rsplit(
        ")",
        1,
    )[0]

    return [score.strip() for score in inside.split(",")]


def reverse_score(score):

    if not score:

        return None

    if score == "CR":

        return None

    if "-" not in score:

        return score

    left, right = score.split(
        "-",
        1,
    )

    return f"{right}-{left}"


def resolve_cr_scores(result):
    """

    Convert the result into separate score lists for team1 and team2.


    ``CR`` by itself does not identify which side conceded. Infer the

    concession winner from the overall team score and the non-CR matches.

    The winning side receives ``"CR"`` and the conceding side receives

    ``None`` for that position.

    """

    scores = extract_individual_scores(result)

    if not scores:

        return [], []

    team_score_text = result.split("(", 1)[0].strip()

    try:

        team1_total, team2_total = [
            int(value.strip()) for value in team_score_text.split("-", 1)
        ]

    except (TypeError, ValueError):

        return [], []

    team1_known_wins = 0

    team2_known_wins = 0

    for score in scores:

        if score == "CR":

            continue

        if "-" not in score:

            continue

        try:

            left, right = [int(value.strip()) for value in score.split("-", 1)]

        except ValueError:

            continue

        if left > right:

            team1_known_wins += 1

        elif right > left:

            team2_known_wins += 1

    team1_cr_wins = team1_total - team1_known_wins

    team2_cr_wins = team2_total - team2_known_wins

    cr_count = sum(1 for score in scores if score == "CR")

    # Sanity check: all CR positions should be explained by the team score.

    if (
        team1_cr_wins < 0
        or team2_cr_wins < 0
        or team1_cr_wins + team2_cr_wins != cr_count
    ):

        return [], []

    scores1 = []

    scores2 = []

    team1_cr_remaining = team1_cr_wins

    team2_cr_remaining = team2_cr_wins

    for score in scores:

        if score != "CR":

            scores1.append(score)

            scores2.append(reverse_score(score))

            continue

        if team1_cr_remaining > 0:

            scores1.append("CR")

            scores2.append(None)

            team1_cr_remaining -= 1

            continue

        if team2_cr_remaining > 0:

            scores1.append(None)

            scores2.append("CR")

            team2_cr_remaining -= 1

            continue

        # Should not be reached after the sanity check above.

        scores1.append(None)

        scores2.append(None)

    return scores1, scores2


def expected_average(
    old_average,
    matches_played,
    match_points,
):

    total_before = old_average * matches_played

    return (total_before + match_points) / (matches_played + 1)


def build_candidates_for_position(
    league_name,
    team_name,
    position,
    score,
    players,
    state,
):
    """


    Return all players whose current average


    is compatible with this position/result.


    """

    if score is None:

        return []

    effective_score = "3-0" if score == "CR" else score

    if position not in POINTS_TABLE or effective_score not in POINTS_TABLE[position]:

        return []

    match_points = POINTS_TABLE[position][effective_score]

    team_state = state.get(league_name, {}).get(team_name, {})

    candidates = []

    for hks_no, player in players.items():

        observed_points = player.get("points")

        # Blank points means the player has no

        # recorded result yet, so they cannot

        # be a candidate for this completed match.

        if observed_points is None:

            continue

        observed_average = float(observed_points)

        old_player = team_state.get(
            hks_no,
            {},
        )

        old_average = float(
            old_player.get(
                "average",
                0,
            )
        )

        matches_played = int(
            old_player.get(
                "matches_played",
                0,
            )
        )

        calculated_average = expected_average(
            old_average,
            matches_played,
            match_points,
        )

        if abs(observed_average - calculated_average) < 0.011:

            candidates.append(
                {
                    "hks_no": hks_no,
                    "name": player["name"],
                    "order": player["order"],
                    "average": observed_average,
                    "match_points": match_points,
                    "matches_played_before": matches_played,
                }
            )

    return candidates


def solve_team_lineup(
    league_name,
    team_name,
    scores,
    players,
    state,
):
    """


    Find all valid ascending-order lineups.

    Important rule:

    registered player order must remain ascending.

    Example:

    valid:

        order 1 -> position 1

        order 3 -> position 2

        order 5 -> position 3


    invalid:

        order 3 -> position 1

        order 2 -> position 2

    If multiple complete lineups are possible,

    a position is confirmed only when every valid

    lineup contains the same player there.

    """

    playable_positions = []

    candidates_by_position = {}

    for position, score in enumerate(
        scores,
        start=1,
    ):

        # None means this team had no opponent/player

        # at this position, e.g. losing side of CR.

        if score is None:

            continue

        candidates = build_candidates_for_position(
            league_name,
            team_name,
            position,
            score,
            players,
            state,
        )

        playable_positions.append(position)

        candidates_by_position[position] = candidates

    solutions = []

    def backtrack(
        index,
        chosen,
        used_hks,
        last_order,
    ):

        if index == len(playable_positions):

            solutions.append(chosen.copy())

            return

        position = playable_positions[index]

        candidates = candidates_by_position.get(
            position,
            [],
        )

        for player in candidates:

            if player["hks_no"] in used_hks:

                continue

            # Hard rule:

            # player registered order must increase

            # as playing position increases.

            if player["order"] <= last_order:

                continue

            chosen[position] = player

            used_hks.add(player["hks_no"])

            backtrack(
                index + 1,
                chosen,
                used_hks,
                player["order"],
            )

            used_hks.remove(player["hks_no"])

            del chosen[position]

    backtrack(
        0,
        {},
        set(),
        -1,
    )

    if not solutions:

        return {}

    # Only one possible full lineup:

    # everything is confirmed.

    if len(solutions) == 1:

        return solutions[0]

    # Multiple possible lineups.

    # Confirm only positions where every

    # valid lineup uses the same player.

    confirmed = {}

    for position in playable_positions:

        players_for_position = []

        for solution in solutions:

            player = solution.get(position)

            if player:

                players_for_position.append(player)

        if not players_for_position:

            continue

        # Every valid lineup must contain

        # a player at this position.

        if len(players_for_position) != len(solutions):

            continue

        hks_numbers = {player["hks_no"] for player in players_for_position}

        # Same exact player across

        # every possible lineup.

        if len(hks_numbers) == 1:

            confirmed[position] = players_for_position[0]

    return confirmed


def update_player_state(
    state,
    league_name,
    team_name,
    player,
):

    state.setdefault(
        league_name,
        {},
    )

    state[league_name].setdefault(
        team_name,
        {},
    )

    state[league_name][team_name][player["hks_no"]] = {
        "name": player["name"],
        "average": player["average"],
        "matches_played": player["matches_played_before"] + 1,
    }


def reconstruct_fixture(
    update,
    league_players,
    state,
):

    league_name = update["league"]

    team1 = update["team1"]

    team2 = update["team2"]

    scores1, scores2 = resolve_cr_scores(update["result"])

    if not scores1 or not scores2:

        return None

    if team1 not in league_players:

        return None

    if team2 not in league_players:

        return None

    team1_players = league_players[team1]["players"]

    team2_players = league_players[team2]["players"]

    lineup1 = solve_team_lineup(
        league_name,
        team1,
        scores1,
        team1_players,
        state,
    )

    lineup2 = solve_team_lineup(
        league_name,
        team2,
        scores2,
        team2_players,
        state,
    )

    individual_matches = []

    for position, score1 in enumerate(
        scores1,
        start=1,
    ):

        score2 = scores2[position - 1]

        player1 = lineup1.get(position) if lineup1 else None

        player2 = lineup2.get(position) if lineup2 else None

        # --------------------

        # CR / CONCESSION

        # --------------------

        if score1 == "CR" or score2 == "CR":

            team1_won_cr = score1 == "CR"

            record = {
                "position": position,
                "score": "CR",
                "effective_score": "3-0",
                "result_type": "concession",
            }

            if team1_won_cr:

                record["player1"] = player1["name"] if player1 else None

                if player1:

                    record["player1_hks_no"] = player1["hks_no"]

                record["player2"] = None

            else:

                record["player1"] = None

                record["player2"] = player2["name"] if player2 else None

                if player2:

                    record["player2_hks_no"] = player2["hks_no"]

            individual_matches.append(record)

            continue

        # --------------------

        # NORMAL MATCH

        # --------------------

        if player1 is not None and player2 is not None:

            individual_matches.append(
                {
                    "position": position,
                    "player1": player1["name"],
                    "player1_hks_no": player1["hks_no"],
                    "player2": player2["name"],
                    "player2_hks_no": player2["hks_no"],
                    "score": score1,
                    "status": "confirmed",
                }
            )

        else:

            individual_matches.append(
                {
                    "position": position,
                    "player1": (player1["name"] if player1 else None),
                    "player2": (player2["name"] if player2 else None),
                    "score": score1,
                    "status": "unresolved",
                }
            )

    # Update state only for players that were actually confirmed.

    if lineup1:

        for player in lineup1.values():

            update_player_state(
                state,
                league_name,
                team1,
                player,
            )

    if lineup2:

        for player in lineup2.values():

            update_player_state(
                state,
                league_name,
                team2,
                player,
            )

    return {
        "week": update.get("week", ""),
        "date": update.get("date", ""),
        "team1": team1,
        "team2": team2,
        "team_result": update["result"],
        "individual_matches": individual_matches,
    }


def process_result_updates(
    updates,
):

    if not updates:

        return {}

    player_matches = load_json(PLAYER_MATCHES_FILE)

    state = load_json(PLAYER_STATE_FILE)

    leagues_needed = {update["league"] for update in updates}

    league_players = {}

    for league_name in leagues_needed:

        print(f"Fetching Division " f"{league_name} " f"player data...")

        league_players[league_name] = get_players(league_name)

    reconstructed = {}

    for update in updates:

        league_name = update["league"]

        fixture = reconstruct_fixture(
            update,
            league_players[league_name],
            state,
        )

        if fixture is None:

            continue

        match_id = update["match_id"]

        player_matches.setdefault(
            league_name,
            {},
        )

        player_matches[league_name][match_id] = fixture

        reconstructed[
            (
                league_name,
                match_id,
            )
        ] = fixture

    save_json(
        PLAYER_MATCHES_FILE,
        player_matches,
    )

    os.makedirs(
        "docs",
        exist_ok=True,
    )

    save_json(
        "docs/player_matches.json",
        player_matches,
    )

    save_json(
        PLAYER_STATE_FILE,
        state,
    )

    return reconstructed


def bootstrap_week_1():

    if os.path.exists(PLAYER_STATE_FILE):

        print("player_state.json " "already exists.")

        print("Bootstrap cancelled " "to avoid duplicating " "player history.")

        return

    results = load_json(RESULTS_FILE)

    updates = []

    for (
        league_name,
        matches,
    ) in results.items():

        for (
            match_id,
            match,
        ) in matches.items():

            if not match.get("result"):

                continue

            updates.append(
                {
                    "league": league_name,
                    "match_id": match_id,
                    **match,
                }
            )

    if not updates:

        print("No completed fixtures found.")

        return

    print(f"Reconstructing " f"{len(updates)} " f"completed fixtures...")

    reconstructed = process_result_updates(updates)

    print(f"Saved " f"{len(reconstructed)} " f"fixture records.")


if __name__ == "__main__":

    bootstrap_week_1()
