from src.card_assignments import build_card_assignments


CARDS_CFG = {
    "num_teams": 4,
    "start_card_id": 4,
    "cards_per_team": {
        "d": 10,
        "a": 5,
        "l": 5,
        "b": 2,
        "p": 2,
    },
}


def test_id_range_has_no_gaps_and_starts_at_start_card_id():

    assignments = build_card_assignments(CARDS_CFG)

    ids = sorted(assignments.keys())

    assert ids[0] == CARDS_CFG["start_card_id"]
    assert ids == list(range(ids[0], ids[-1] + 1))


def test_total_count_matches_num_teams_times_cards_per_team():

    assignments = build_card_assignments(CARDS_CFG)

    expected_total = CARDS_CFG["num_teams"] * sum(
        CARDS_CFG["cards_per_team"].values()
    )

    assert len(assignments) == expected_total


def test_matches_main_py_style_generation_for_same_config():
    # Regression guard for the original bug: scripts/createmarkers.py used
    # to hardcode its own ID range (4..96) which drifted from what this
    # generator (and main.py) actually produce (4..99) for this config.

    assignments = build_card_assignments(CARDS_CFG)

    assert min(assignments) == 4
    assert max(assignments) == 99
    assert len(assignments) == 96
