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

BASE_URL = "https://www.hksquash.org.hk/public/leagues"


def results_url(league_name):
    config = LEAGUES[league_name]

    return (
        f"{BASE_URL}/results_schedules/"
        f"id/{config['id']}/"
        f"league/{config['season']}/"
        f"year/{config['year']}/"
        "pages_id/26.html"
    )


def standings_url(league_name):
    config = LEAGUES[league_name]

    return (
        f"{BASE_URL}/team_summery/"
        f"id/{config['id']}/"
        f"league/{config['season']}/"
        f"year/{config['year']}/"
        "pages_id/26.html"
    )