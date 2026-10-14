LEAGUES = {
    "L4": {
        "id": "D00549",
        "year": "2026-2027",
        "season": "Squash",
        "pages_id": 25,
    },
    "D15B": {
        "id": "D00542",
        "year": "2026-2027",
        "season": "Squash",
        "pages_id": 25,
    },
}

BASE_URL = "https://www.hksquash.org.hk/public/leagues"


def results_url(league_name):
    config = LEAGUES[league_name]

    return (
        f"{BASE_URL}/results_schedules/"
        f"id/{config['id']}/"
        f"league/{config['season']}/"
        f"year/{config['year']}/"
        f"pages_id/{config['pages_id']}.html"
    )


def standings_url(league_name):
    config = LEAGUES[league_name]

    return (
        f"{BASE_URL}/team_summery/"
        f"id/{config['id']}/"
        f"league/{config['season']}/"
        f"year/{config['year']}/"
        f"pages_id/{config['pages_id']}.html"
    )