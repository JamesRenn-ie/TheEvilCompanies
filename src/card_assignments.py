def build_card_assignments(cards_cfg):
    """
    cards_cfg = cfg.raw["cards"].

    Sequentially assigns ArUco marker IDs to (team, type) pairs, starting
    at cards_cfg["start_card_id"], iterating teams 1..num_teams and, for
    each team, iterating cards_cfg["cards_per_team"] in dict order.

    Returns marker_id -> {"team": int, "type": str}.

    This is the single source of truth for marker ID assignment - main.py
    and scripts/createmarkers.py both call this so they can never drift
    out of sync with each other or with config.json.
    """

    num_teams = cards_cfg["num_teams"]
    start_card_id = cards_cfg["start_card_id"]
    cards_per_team = cards_cfg["cards_per_team"]

    assignments = {}

    marker_id = start_card_id

    for team in range(1, num_teams + 1):

        for card_type, quantity in cards_per_team.items():

            for _ in range(quantity):

                assignments[marker_id] = {
                    "team": team,
                    "type": card_type,
                }

                marker_id += 1

    return assignments
