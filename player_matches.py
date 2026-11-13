import json


import os


import re


import requests


from bs4 import BeautifulSoup


from config import players_url


from datetime import datetime

ROSTER_HISTORY_FILE = "roster_history.json"


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


def normalise_date(date_text):

    if not date_text:

        return None

    for fmt in (
        "%d/%m/%Y",
        "%Y-%m-%d",
    ):

        try:

            return datetime.strptime(
                date_text.strip(),
                fmt,
            ).strftime("%Y-%m-%d")

        except ValueError:

            pass

    return None


def find_effective_date(tokens):
    """

    Find an effective date in a section of

    HK Squash player-page text.



    HK Squash normally uses YYYY-MM-DD,

    but DD/MM/YYYY is also accepted.

    """

    date_pattern = r"(\d{4}-\d{1,2}-\d{1,2}" r"|\d{1,2}/\d{1,2}/\d{4})"

    for index, token in enumerate(tokens):

        text = token.strip()

        match = re.search(
            r"effective\s\*date\s\*:?\s\*" + date_pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:

            return normalise_date(match.group(1))

        if "effective date" in text.lower() and index + 1 < len(tokens):

            match = re.search(
                date_pattern,
                tokens[index + 1],
            )

            if match:

                return normalise_date(match.group(1))

    return None


def get_ranking_url(league_name):
    """Return the divisional ranking URL for a configured league."""
    return players_url(league_name).replace(
        "/players/",
        "/ranking/",
        1,
    )


def get_division_ranking(league_name, known_teams=None):
    """
    Fetch published divisional-ranking statistics.

    Each HK Squash ranking row is rendered as a
    ``div.ranking-content-list`` containing seven columns:

        position, player name, team, average points,
        total game points, games played, won, lost

    The position column may be blank. The ranking page does not publish
    HKS membership numbers, so rows are keyed by team name + exact player
    name and merged back into the roster returned by ``get_players()``.
    """
    response = requests.get(
        get_ranking_url(league_name),
        timeout=45,
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    known_teams = set(known_teams or [])
    ranking = {}

    for row in soup.select("div.ranking-content-list"):
        columns = row.find_all("div", recursive=False)

        # Normal player rows contain exactly 8 columns.  The NO DATA row
        # contains only one and is intentionally ignored.
        if len(columns) != 8:
            continue

        values = [column.get_text(" ", strip=True) for column in columns]

        player_name = values[1]
        team_name = values[2]
        average_text = values[3]
        total_points_text = values[4]
        games_text = values[5]
        won_text = values[6]
        lost_text = values[7]

        if not player_name or not team_name:
            continue

        if known_teams and team_name not in known_teams:
            continue

        try:
            games_played = int(games_text or 0)
            won = int(won_text or 0)
            lost = int(lost_text or 0)
        except ValueError:
            continue

        # HK Squash leaves average/total blank for players with 0 games.
        try:
            average = float(average_text) if average_text else None
            total_game_points = float(total_points_text) if total_points_text else 0.0
        except ValueError:
            continue

        if games_played < 0 or won < 0 or lost < 0:
            continue

        if won + lost != games_played:
            continue

        ranking.setdefault(team_name, {})[player_name] = {
            "average": average,
            "total_game_points": total_game_points,
            "games_played": games_played,
            "won": won,
            "lost": lost,
        }

    return ranking


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

        i += 2

        header_start = i

        # Find Points header while preserving

        # metadata between Team Name and Points.

        while (
            i < len(tokens)
            and tokens[i].lower() != "points"
            and tokens[i].lower() != "team name:"
        ):

            i += 1

        header_tokens = tokens[header_start:i]

        effective_date = find_effective_date(header_tokens)

        teams[team_name] = {
            "effective_date": effective_date,
            "players": {},
        }

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
                    r"-?\d+\.\d+",
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

    # Merge the divisional ranking page into the roster.
    # This gives us games played / total points / W-L evidence,
    # while the roster page remains the source of HKS number and order.
    try:
        ranking_stats = get_division_ranking(
            league_name,
            known_teams=teams.keys(),
        )
    except Exception as error:
        print(
            "Division ranking fetch failed for "
            f"{league_name}: {error}. "
            "Falling back to roster averages only."
        )
        ranking_stats = {}

    for team_name, team_data in teams.items():
        team_ranking = ranking_stats.get(team_name, {})

        for player in team_data.get("players", {}).values():
            published = team_ranking.get(player["name"])

            if not published:
                continue

            player["ranking_average"] = published["average"]
            player["total_game_points"] = published["total_game_points"]
            player["games_played"] = published["games_played"]
            player["won"] = published["won"]
            player["lost"] = published["lost"]

    merged_count = sum(
        1
        for team_data in teams.values()
        for player in team_data.get("players", {}).values()
        if player.get("games_played") is not None
    )
    print(
        f"Division {league_name}: merged ranking stats for "
        f"{merged_count} player(s)."
    )

    return teams


def save_roster_snapshot(
    league_name,
    league_players,
):

    history = load_json(ROSTER_HISTORY_FILE)

    history.setdefault(
        league_name,
        {},
    )

    changed = False

    for (
        team_name,
        team_data,
    ) in league_players.items():

        effective_date = team_data.get("effective_date")

        if not effective_date:

            print(
                "No effective date found for "
                f"{team_name}; "
                "roster snapshot skipped."
            )

            continue

        history[league_name].setdefault(
            team_name,
            {},
        )

        players = {}

        for (
            hks_no,
            player,
        ) in team_data.get(
            "players",
            {},
        ).items():

            # Snapshot membership/order only.

            # Points remain live data.

            players[str(hks_no)] = {
                "name": player["name"],
                "order": player["order"],
                "ranking": player.get("ranking"),
            }

        existing = history[league_name][team_name].get(effective_date)

        snapshot = {
            "players": players,
        }

        if existing != snapshot:

            history[league_name][team_name][effective_date] = snapshot

            changed = True

            print(
                "Saved roster snapshot: "
                f"{league_name} / "
                f"{team_name} / "
                f"{effective_date}"
            )

    if changed:

        save_json(
            ROSTER_HISTORY_FILE,
            history,
        )

    return history


def get_historical_team_players(
    league_name,
    team_name,
    match_date,
    live_league_players,
    roster_history,
):
    """



    Use the latest roster whose effective date



    is <= the match date.







    Historical roster supplies:



      - membership



      - registered order







    Live page supplies:



      - current points / average



    """

    match_date_normalised = normalise_date(match_date)

    if not match_date_normalised:

        return None

    snapshots = roster_history.get(league_name, {}).get(team_name, {})

    valid_dates = [
        effective_date
        for effective_date in snapshots
        if effective_date <= match_date_normalised
    ]

    if not valid_dates:

        print("No historical roster for " f"{team_name} on " f"{match_date}.")

        return None

    effective_date = max(valid_dates)

    snapshot = snapshots[effective_date]

    live_team = live_league_players.get(team_name, {})

    live_players = live_team.get("players", {})

    historical_players = {}

    for (
        hks_no,
        historical,
    ) in snapshot.get(
        "players",
        {},
    ).items():

        live = live_players.get(str(hks_no))

        historical_players[str(hks_no)] = {
            "name": historical["name"],
            "order": historical["order"],
            "ranking": historical.get("ranking"),
            # Latest live values from HK Squash.
            # Membership/order come from the historical snapshot,
            # but ranking statistics must remain live so the retry
            # resolver can detect who actually played.
            "points": (live.get("points") if live else None),
            "ranking_average": (live.get("ranking_average") if live else None),
            "total_game_points": (live.get("total_game_points") if live else None),
            "games_played": (live.get("games_played") if live else None),
            "won": (live.get("won") if live else None),
            "lost": (live.get("lost") if live else None),
        }

    print(
        "Using roster " f"{effective_date} for " f"{team_name} " f"(match {match_date})"
    )

    return historical_players


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







    The winning side receives "CR" and the conceding side receives







    None for that position.







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
    Return players compatible with this position/result.

    The roster-page average is still the mathematical compatibility
    check.  Divisional-ranking statistics add stronger participation
    evidence: an increase in games played is the strongest signal, and
    the corresponding total-game-points / W-L changes can corroborate it.
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

        if observed_points is None:
            continue

        observed_average = float(observed_points)
        old_player = team_state.get(str(hks_no), {})
        old_average = float(old_player.get("average", 0))
        matches_played = int(old_player.get("matches_played", 0))

        calculated_average = expected_average(
            old_average,
            matches_played,
            match_points,
        )

        if abs(observed_average - calculated_average) >= 0.011:
            continue

        ranking_evidence = 0

        published_games = player.get("games_played")
        previous_published_games = int(
            old_player.get(
                "published_games_played",
                matches_played,
            )
        )

        games_delta = None
        if published_games is not None:
            published_games = int(published_games)
            games_delta = published_games - previous_published_games

            # Exact +1 is direct evidence that this player appeared in
            # one newly published fixture since our previous known state.
            if games_delta == 1:
                ranking_evidence += 100

        published_total = player.get("total_game_points")
        previous_total = old_player.get("total_game_points")

        if previous_total is None and matches_played > 0:
            # Backward-compatible estimate for state files created before
            # total-game-points were stored.  Use a slightly wider tolerance
            # because the published average is rounded to two decimals.
            previous_total = old_average * matches_played

        points_delta = None
        if published_total is not None and previous_total is not None:
            published_total = float(published_total)
            previous_total = float(previous_total)
            points_delta = published_total - previous_total

            if games_delta == 1 and abs(points_delta - match_points) < 0.06:
                ranking_evidence += 25

        published_won = player.get("won")
        published_lost = player.get("lost")
        previous_won = old_player.get("won")
        previous_lost = old_player.get("lost")

        if (
            games_delta == 1
            and published_won is not None
            and published_lost is not None
            and previous_won is not None
            and previous_lost is not None
        ):
            left, right = [int(value) for value in effective_score.split("-", 1)]
            expected_win_delta = 1 if left > right else 0
            expected_loss_delta = 1 if left < right else 0

            if (
                int(published_won) - int(previous_won) == expected_win_delta
                and int(published_lost) - int(previous_lost) == expected_loss_delta
            ):
                ranking_evidence += 10

        # Existing average-change signal remains as a small fallback.
        if matches_played == 0:
            ranking_evidence += 2
        elif abs(observed_average - old_average) >= 0.011:
            ranking_evidence += 2

        candidates.append(
            {
                "hks_no": str(hks_no),
                "name": player["name"],
                "order": player["order"],
                "average": observed_average,
                "match_points": match_points,
                "matches_played_before": matches_played,
                "ranking_evidence": ranking_evidence,
                "published_games_played": published_games,
                "total_game_points": published_total,
                "won": published_won,
                "lost": published_lost,
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

    # Multiple mathematically valid lineups may remain.  Prefer lineups
    # with the strongest divisional-ranking participation evidence.
    best_evidence = max(
        sum(player.get("ranking_evidence", 0) for player in solution.values())
        for solution in solutions
    )

    if best_evidence > 0:
        solutions = [
            solution
            for solution in solutions
            if sum(player.get("ranking_evidence", 0) for player in solution.values())
            == best_evidence
        ]

        if len(solutions) == 1:
            return solutions[0]

    # Confirm only positions where every best solution agrees.
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
        "published_games_played": player.get(
            "published_games_played",
            player["matches_played_before"] + 1,
        ),
        "total_game_points": player.get("total_game_points"),
        "won": player.get("won"),
        "lost": player.get("lost"),
    }


def reconstruct_fixture(
    update,
    league_players,
    state,
    roster_history,
):

    league_name = update["league"]

    team1 = update["team1"]

    team2 = update["team2"]

    scores1, scores2 = resolve_cr_scores(update["result"])

    if not scores1 or not scores2:

        return None

    match_date = update.get("date")

    team1_players = get_historical_team_players(
        league_name,
        team1,
        match_date,
        league_players,
        roster_history,
    )

    team2_players = get_historical_team_players(
        league_name,
        team2,
        match_date,
        league_players,
        roster_history,
    )

    if team1_players is None:

        return None

    if team2_players is None:

        return None

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

            if record.get("player1") or record.get("player2"):

                record["status"] = "confirmed"

            else:

                record["status"] = "unresolved"

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

            record = {
                "position": position,
                "player1": (player1["name"] if player1 else None),
                "player2": (player2["name"] if player2 else None),
                "score": score1,
                "status": "unresolved",
            }

            if player1:

                record["player1_hks_no"] = player1["hks_no"]

            if player2:

                record["player2_hks_no"] = player2["hks_no"]

            individual_matches.append(record)

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
        "week": update.get(
            "week",
            "",
        ),
        "date": update.get(
            "date",
            "",
        ),
        "team1": team1,
        "team2": team2,
        "team_result": update["result"],
        "individual_matches": individual_matches,
        "notification_sent": False,
    }


def fixture_has_unresolved(
    fixture,
):

    for match in fixture.get(
        "individual_matches",
        [],
    ):

        if match.get("status") == "unresolved":

            return True

        if (
            match.get("result_type") == "concession"
            and not match.get("player1")
            and not match.get("player2")
        ):

            return True

    return False


def mark_fixture_notified(
    league_name,
    match_id,
):

    player_matches = load_json(PLAYER_MATCHES_FILE)

    fixture = player_matches.get(league_name, {}).get(match_id)

    if fixture is None:

        return

    fixture["notification_sent"] = True

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


def find_registered_player(
    players,
    player_name=None,
    hks_no=None,
):

    if hks_no:

        player = players.get(str(hks_no))

        if player:

            return {
                "hks_no": str(hks_no),
                **player,
            }

    if not player_name:

        return None

    matches = []

    for member_id, player in players.items():

        if player.get("name") == player_name:

            matches.append(
                {
                    "hks_no": str(member_id),
                    **player,
                }
            )

    if len(matches) == 1:

        return matches[0]

    return None


def solve_missing_positions(
    league_name,
    team_name,
    scores,
    players,
    state,
    individual_matches,
    side,
):
    """



    Retry only previously unresolved player slots.







    Existing identified players are fixed.







    Missing positions are allowed to remain unresolved.



    Among all valid possibilities, prefer solutions that



    resolve the maximum number of positions.







    A position is confirmed only when every best solution



    identifies the same player at that position.



    """

    player_key = "player1" if side == 1 else "player2"

    hks_key = "player1_hks_no" if side == 1 else "player2_hks_no"

    fixed = {}

    used_hks = set()

    # Existing known players are fixed.

    for match in individual_matches:

        position = match["position"]

        player_name = match.get(player_key)

        hks_no = match.get(hks_key)

        if not player_name:

            continue

        registered = find_registered_player(
            players,
            player_name=player_name,
            hks_no=hks_no,
        )

        # Current roster may have changed.

        # In that case we cannot safely infer

        # playing-order constraints.

        if registered is None:

            return {}

        fixed[position] = registered

        used_hks.add(registered["hks_no"])

    missing_positions = []

    candidates_by_position = {}

    for match in individual_matches:

        if match.get("status") != "unresolved":

            continue

        position = match["position"]

        # This side of the match is already known.

        if match.get(player_key):

            continue

        score = scores[position - 1]

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

        # Already-used players cannot appear again.

        candidates = [
            player for player in candidates if player["hks_no"] not in used_hks
        ]

        filtered = []

        for player in candidates:

            order = player["order"]

            valid = True

            # Must fit around all already-known

            # positions.

            for (
                fixed_position,
                fixed_player,
            ) in fixed.items():

                fixed_order = fixed_player["order"]

                if fixed_position < position and fixed_order >= order:

                    valid = False

                    break

                if fixed_position > position and fixed_order <= order:

                    valid = False

                    break

            if valid:

                filtered.append(player)

        missing_positions.append(position)

        candidates_by_position[position] = filtered

    if not missing_positions:

        return {}

    # Candidate objects already contain a position-aware ranking_evidence
    # score.  It strongly rewards a +1 published games-played change, then
    # corroborates that with total points and W-L changes.  If ranking data
    # is unavailable, the small average-change fallback still works.

    best_solutions = []

    best_score = (-1, -1)

    def record_solution(chosen):

        nonlocal best_score

        nonlocal best_solutions

        resolved_count = len(chosen)

        evidence_score = sum(
            player.get("ranking_evidence", 0) for player in chosen.values()
        )

        score = (
            resolved_count,
            evidence_score,
        )

        if score > best_score:

            best_score = score

            best_solutions = [chosen.copy()]

        elif score == best_score:

            best_solutions.append(chosen.copy())

    def backtrack(
        index,
        chosen,
        used,
    ):

        if index == len(missing_positions):

            record_solution(chosen)

            return

        position = missing_positions[index]

        # ---------------------------------

        # OPTION 1:

        # Leave this position unresolved.

        # ---------------------------------

        backtrack(
            index + 1,
            chosen,
            used,
        )

        # ---------------------------------

        # OPTION 2:

        # Try each possible player.

        # ---------------------------------

        for player in candidates_by_position[position]:

            hks_no = player["hks_no"]

            order = player["order"]

            if hks_no in used:

                continue

            valid = True

            # Check against previously chosen

            # unresolved positions.

            for (
                chosen_position,
                chosen_player,
            ) in chosen.items():

                chosen_order = chosen_player["order"]

                if chosen_position < position and chosen_order >= order:

                    valid = False

                    break

                if chosen_position > position and chosen_order <= order:

                    valid = False

                    break

            if not valid:

                continue

            chosen[position] = player

            used.add(hks_no)

            backtrack(
                index + 1,
                chosen,
                used,
            )

            used.remove(hks_no)

            del chosen[position]

    backtrack(
        0,
        {},
        set(used_hks),
    )

    if not best_solutions or best_score[0] <= 0:

        return {}

    confirmed = {}

    for position in missing_positions:

        players_for_position = [solution.get(position) for solution in best_solutions]

        # Some equally-good solution leaves this

        # position unresolved -> not safe to confirm.

        if any(player is None for player in players_for_position):

            continue

        hks_numbers = {player["hks_no"] for player in players_for_position}

        # Every best solution agrees.

        if len(hks_numbers) == 1:

            confirmed[position] = players_for_position[0]

    return confirmed


def retry_unresolved_fixtures(
    current_results,
):

    player_matches = load_json(PLAYER_MATCHES_FILE)

    state = load_json(PLAYER_STATE_FILE)

    roster_history = load_json(ROSTER_HISTORY_FILE)

    unresolved = []

    for league_name, fixtures in player_matches.items():

        for match_id, fixture in fixtures.items():

            if not fixture_has_unresolved(fixture):

                continue

            source_match = current_results.get(league_name, {}).get(match_id)

            if not source_match or not source_match.get("result"):

                continue

            unresolved.append(
                (
                    league_name,
                    match_id,
                    fixture,
                    source_match,
                )
            )

    if not unresolved:

        return 0, []

    leagues_needed = {item[0] for item in unresolved}

    league_players = {}

    for league_name in leagues_needed:

        print(f"Retrying unresolved " f"Division {league_name} " f"player matches...")

        league_players[league_name] = get_players(league_name)

        # Persist the currently published roster using its

        # effective date. This snapshot is used only for

        # membership/order; current points remain live.

        roster_history = save_roster_snapshot(
            league_name,
            league_players[league_name],
        )

    improved_count = 0

    resolved_for_notification = []

    for (
        league_name,
        match_id,
        fixture,
        source_match,
    ) in unresolved:

        live_players = league_players[league_name]

        team1 = fixture["team1"]

        team2 = fixture["team2"]

        match_date = fixture.get("date") or source_match.get("date")

        team1_players = get_historical_team_players(
            league_name,
            team1,
            match_date,
            live_players,
            roster_history,
        )

        team2_players = get_historical_team_players(
            league_name,
            team2,
            match_date,
            live_players,
            roster_history,
        )

        # If no roster effective on/before the match date

        # is available, do not fall back to today's order.

        if team1_players is None or team2_players is None:

            continue

        scores1, scores2 = resolve_cr_scores(source_match["result"])

        if not scores1 or not scores2:

            continue

        matches = fixture.get(
            "individual_matches",
            [],
        )

        resolved1 = solve_missing_positions(
            league_name,
            team1,
            scores1,
            team1_players,
            state,
            matches,
            side=1,
        )

        resolved2 = solve_missing_positions(
            league_name,
            team2,
            scores2,
            team2_players,
            state,
            matches,
            side=2,
        )

        fixture_improved = False

        for match in matches:

            position = match["position"]

            if not match.get("player1") and position in resolved1:

                player = resolved1[position]

                match["player1"] = player["name"]

                match["player1_hks_no"] = player["hks_no"]

                update_player_state(
                    state,
                    league_name,
                    team1,
                    player,
                )

                fixture_improved = True

            if not match.get("player2") and position in resolved2:

                player = resolved2[position]

                match["player2"] = player["name"]

                match["player2_hks_no"] = player["hks_no"]

                update_player_state(
                    state,
                    league_name,
                    team2,
                    player,
                )

                fixture_improved = True

            if match.get("result_type") == "concession" and (
                match.get("player1") or match.get("player2")
            ):

                match["status"] = "confirmed"

            elif (
                match.get("status") == "unresolved"
                and match.get("player1")
                and match.get("player2")
            ):

                match["status"] = "confirmed"

        if fixture_improved:

            improved_count += 1

            print(
                "Improved unresolved fixture: "
                f"{fixture['team1']} vs "
                f"{fixture['team2']}"
            )

            if not fixture_has_unresolved(fixture) and not fixture.get(
                "notification_sent",
                False,
            ):

                resolved_for_notification.append(
                    {
                        "league": league_name,
                        "match_id": match_id,
                        "fixture": fixture,
                    }
                )

    if improved_count:

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

    return (
        improved_count,
        resolved_for_notification,
    )


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

        roster_history = save_roster_snapshot(
            league_name,
            league_players[league_name],
        )

    reconstructed = {}

    for update in updates:

        league_name = update["league"]

        fixture = reconstruct_fixture(
            update,
            league_players[league_name],
            state,
            roster_history,
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


def rebuild_player_state_from_matches(
    player_matches,
):
    """
    Rebuild player_state.json entirely from
    confirmed fixtures in player_matches.json.

    player_matches.json is treated as the
    source of truth.
    """

    rebuilt = {}

    def add_player_result(
        league_name,
        team_name,
        hks_no,
        player_name,
        match_points,
    ):
        if not hks_no:
            return

        rebuilt.setdefault(
            league_name,
            {},
        )

        rebuilt[league_name].setdefault(
            team_name,
            {},
        )

        team_state = rebuilt[league_name][team_name]

        player_state = team_state.setdefault(
            str(hks_no),
            {
                "name": player_name,
                "total_points": 0.0,
                "matches_played": 0,
            },
        )

        player_state["total_points"] += float(match_points)

        player_state["matches_played"] += 1

    for (
        league_name,
        fixtures,
    ) in player_matches.items():

        sorted_fixtures = sorted(
            fixtures.values(),
            key=lambda fixture: (normalise_date(fixture.get("date")) or "9999-99-99"),
        )

        for fixture in sorted_fixtures:
            team1 = fixture.get("team1")
            team2 = fixture.get("team2")

            for match in fixture.get(
                "individual_matches",
                [],
            ):
                position = match.get("position")

                if position not in POINTS_TABLE:
                    continue

                result_type = match.get("result_type")

                # -------------------------
                # CONCESSION
                # -------------------------
                if result_type == "concession":
                    if match.get("player1"):
                        points = POINTS_TABLE[position]["3-0"]

                        add_player_result(
                            league_name,
                            team1,
                            match.get("player1_hks_no"),
                            match.get("player1"),
                            points,
                        )

                    elif match.get("player2"):
                        points = POINTS_TABLE[position]["3-0"]

                        add_player_result(
                            league_name,
                            team2,
                            match.get("player2_hks_no"),
                            match.get("player2"),
                            points,
                        )

                    continue

                # -------------------------
                # NORMAL MATCH
                # -------------------------
                score1 = match.get("score")

                if not score1 or score1 not in POINTS_TABLE[position]:
                    continue

                score2 = reverse_score(score1)

                player1 = match.get("player1")

                player2 = match.get("player2")

                if player1:
                    add_player_result(
                        league_name,
                        team1,
                        match.get("player1_hks_no"),
                        player1,
                        POINTS_TABLE[position][score1],
                    )

                if player2 and score2 in POINTS_TABLE[position]:
                    add_player_result(
                        league_name,
                        team2,
                        match.get("player2_hks_no"),
                        player2,
                        POINTS_TABLE[position][score2],
                    )

    # Convert internal totals into the
    # existing player_state.json format.
    final_state = {}

    for (
        league_name,
        teams,
    ) in rebuilt.items():

        final_state.setdefault(
            league_name,
            {},
        )

        for (
            team_name,
            players,
        ) in teams.items():

            final_state[league_name].setdefault(
                team_name,
                {},
            )

            for (
                hks_no,
                player,
            ) in players.items():

                matches_played = player["matches_played"]

                average = player["total_points"] / matches_played

                final_state[league_name][team_name][hks_no] = {
                    "name": player["name"],
                    "average": average,
                    "matches_played": matches_played,
                }

    return final_state


def rebuild_and_save_player_state():
    player_matches = load_json(PLAYER_MATCHES_FILE)

    state = rebuild_player_state_from_matches(player_matches)

    save_json(
        PLAYER_STATE_FILE,
        state,
    )

    print("Rebuilt player_state.json " "from player match history.")

    return state


def reopen_match_position(
    fixture,
    position,
    side,
):
    for match in fixture.get(
        "individual_matches",
        [],
    ):
        if match.get("position") != position:
            continue

        if side == 1:
            match["player1"] = None
            match.pop(
                "player1_hks_no",
                None,
            )

        else:
            match["player2"] = None
            match.pop(
                "player2_hks_no",
                None,
            )

        match["status"] = "unresolved"

        return True

    return False


def find_ranking_inconsistencies(
    league_name,
    player_matches,
    league_players,
):
    """
    Compare our reconstructed history with the
    current HK Squash divisional ranking.

    Return players whose reconstructed number of
    matches / total points differs from published
    values.
    """

    rebuilt = rebuild_player_state_from_matches(
        {league_name: player_matches.get(league_name, {})}
    )

    differences = []

    for team_name, team_data in league_players.items():
        reconstructed_team = rebuilt.get(league_name, {}).get(team_name, {})

        for hks_no, player in team_data.get(
            "players",
            {},
        ).items():
            published_games = player.get("games_played")

            published_total = player.get("total_game_points")

            if published_games is None:
                continue

            reconstructed = reconstructed_team.get(
                str(hks_no),
                {},
            )

            reconstructed_games = int(
                reconstructed.get(
                    "matches_played",
                    0,
                )
            )

            reconstructed_average = float(
                reconstructed.get(
                    "average",
                    0,
                )
            )

            reconstructed_total = reconstructed_average * reconstructed_games

            games_delta = int(published_games) - reconstructed_games

            points_delta = None

            if published_total is not None:
                points_delta = float(published_total) - reconstructed_total

            if games_delta != 0 or (
                points_delta is not None and abs(points_delta) >= 0.06
            ):
                differences.append(
                    {
                        "team": team_name,
                        "hks_no": str(hks_no),
                        "name": player["name"],
                        "published_games": int(published_games),
                        "reconstructed_games": reconstructed_games,
                        "games_delta": games_delta,
                        "published_total": published_total,
                        "reconstructed_total": reconstructed_total,
                        "points_delta": points_delta,
                    }
                )

    return differences


def audit_and_reopen_corrections(
    current_results,
):
    player_matches = load_json(PLAYER_MATCHES_FILE)

    changed = False

    for league_name in player_matches:
        league_players = get_players(league_name)

        differences = find_ranking_inconsistencies(
            league_name,
            player_matches,
            league_players,
        )

        if not differences:
            continue

        negative = [item for item in differences if item["games_delta"] == -1]

        positive = [item for item in differences if item["games_delta"] == 1]

        for old_player in negative:
            for new_player in positive:
                if old_player["team"] != new_player["team"]:
                    continue

                for (
                    match_id,
                    fixture,
                ) in player_matches[league_name].items():

                    team1 = fixture.get("team1")
                    team2 = fixture.get("team2")

                    for match in fixture.get(
                        "individual_matches",
                        [],
                    ):
                        position = match.get("position")

                        if position not in POINTS_TABLE:
                            continue

                        side = None
                        score = None

                        if (
                            team1 == old_player["team"]
                            and match.get("player1_hks_no") == old_player["hks_no"]
                        ):
                            side = 1
                            score = match.get("score")

                        elif (
                            team2 == old_player["team"]
                            and match.get("player2_hks_no") == old_player["hks_no"]
                        ):
                            side = 2

                            if match.get("result_type") == "concession":
                                score = "CR"
                            else:
                                score = reverse_score(match.get("score"))

                        if side is None or not score:
                            continue

                        effective_score = "3-0" if score == "CR" else score

                        if effective_score not in POINTS_TABLE[position]:
                            continue

                        expected_points = POINTS_TABLE[position][effective_score]

                        new_points_delta = new_player.get("points_delta")

                        old_points_delta = old_player.get("points_delta")

                        if new_points_delta is None or old_points_delta is None:
                            continue

                        if abs(new_points_delta - expected_points) >= 0.06:
                            continue

                        if abs(old_points_delta + expected_points) >= 0.06:
                            continue

                        if reopen_match_position(
                            fixture,
                            position,
                            side,
                        ):
                            print(
                                "Reopened historical "
                                "player assignment: "
                                f"{old_player['name']} "
                                "→ "
                                f"{new_player['name']} "
                                f"({fixture['team1']} "
                                "vs "
                                f"{fixture['team2']}, "
                                f"position {position})"
                            )

                            changed = True
                            break

                    if changed:
                        break

                if changed:
                    break

            if changed:
                break

        if changed:
            break

    if not changed:
        return False

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

    rebuild_and_save_player_state()

    return True


if __name__ == "__main__":

    bootstrap_week_1()
