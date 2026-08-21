import numpy as np
import pytest

from src.gameplay import (
    MapEngine,
    compute_stack_flags,
    circles_touch,
    find_stacks,
    apply_billionaire_steals,
    apply_president_claims,
    update_growth_radii,
    score_visible_cards,
    check_area_bonus,
    compute_coverage_percentage,
)


def make_card(marker_id, card_type, team, position=(0, 0), radius=80,
              visible=True, owner_team=None, locked=False):

    return {
        "id": marker_id,
        "type": card_type,
        "team": team,
        "owner_team": team if owner_team is None else owner_team,
        "position": position,
        "visible": visible,
        "locked": locked,
        "radius": radius,
        "last_seen": 0.0,
    }


# ============================================================
# find_stacks
# ============================================================

def test_find_stacks_groups_nearby_cards():

    cards = {
        1: make_card(1, "d", 1, position=(100, 100)),
        2: make_card(2, "a", 1, position=(110, 100)),
        3: make_card(3, "d", 2, position=(500, 500)),
    }

    stacks = find_stacks(cards, stack_distance=70)

    stack_sizes = sorted(len(stack) for stack in stacks)

    assert stack_sizes == [1, 2]


def test_find_stacks_does_not_group_far_cards():

    cards = {
        1: make_card(1, "d", 1, position=(0, 0)),
        2: make_card(2, "d", 1, position=(1000, 1000)),
    }

    stacks = find_stacks(cards, stack_distance=70)

    assert len(stacks) == 2


def test_find_stacks_ignores_invisible_cards():

    cards = {
        1: make_card(1, "d", 1, position=(0, 0), visible=True),
        2: make_card(2, "a", 1, position=(0, 0), visible=False),
    }

    stacks = find_stacks(cards, stack_distance=70)

    assert len(stacks) == 1
    assert len(stacks[0]) == 1


# ============================================================
# compute_stack_flags
# ============================================================

@pytest.mark.parametrize(
    "types,expected_blocked",
    [
        (["d"], False),
        (["d", "a"], True),
        (["d", "a", "l"], False),
        (["d", "l"], False),
    ],
)
def test_compute_stack_flags_blocked(types, expected_blocked):

    stack = [make_card(i, t, 1) for i, t in enumerate(types)]

    data_centres, billionaires, presidents, blocked = compute_stack_flags(stack)

    assert blocked is expected_blocked
    assert len(data_centres) == types.count("d")
    assert len(billionaires) == types.count("b")
    assert len(presidents) == types.count("p")


# ============================================================
# apply_billionaire_steals
# ============================================================

def test_billionaire_steals_unprotected_datacentre_from_other_team():

    dc = make_card(1, "d", team=1, owner_team=1)
    billionaire = make_card(2, "b", team=2)

    stacks = [[dc, billionaire]]

    apply_billionaire_steals(stacks)

    assert dc["owner_team"] == 2
    assert dc["locked"] is False


def test_billionaire_does_not_steal_own_team_datacentre():

    dc = make_card(1, "d", team=1, owner_team=1)
    billionaire = make_card(2, "b", team=1)

    apply_billionaire_steals([[dc, billionaire]])

    assert dc["owner_team"] == 1


def test_billionaire_cannot_steal_locked_datacentre():

    dc = make_card(1, "d", team=1, owner_team=1, locked=True)
    billionaire = make_card(2, "b", team=2)

    apply_billionaire_steals([[dc, billionaire]])

    assert dc["owner_team"] == 1


def test_billionaire_cannot_steal_blocked_datacentre():

    dc = make_card(1, "d", team=1, owner_team=1)
    activist = make_card(2, "a", team=1)
    billionaire = make_card(3, "b", team=2)

    apply_billionaire_steals([[dc, activist, billionaire]])

    assert dc["owner_team"] == 1


def test_billionaire_steal_is_idempotent_on_repeat_calls():

    dc = make_card(1, "d", team=1, owner_team=1)
    billionaire = make_card(2, "b", team=2)

    stacks = [[dc, billionaire]]

    apply_billionaire_steals(stacks)
    first_owner = dc["owner_team"]

    apply_billionaire_steals(stacks)  # simulate a second frame, still stacked
    second_owner = dc["owner_team"]

    assert first_owner == second_owner == 2


# ============================================================
# apply_president_claims
# ============================================================

def test_president_claims_any_datacentre_ignoring_block_and_lock():

    dc = make_card(1, "d", team=1, owner_team=1, locked=True)
    activist = make_card(2, "a", team=1)
    president = make_card(3, "p", team=3)

    apply_president_claims([[dc, activist, president]], [dc], game_mode="static")

    assert dc["owner_team"] == 3
    assert dc["locked"] is True


def test_president_claim_one_hop_only_in_growth_mode():
    # Chain A - B - C: A touches B, B touches C, A does NOT touch C.
    # President stacked with A should also claim B, but NOT C.

    a = make_card(1, "d", team=1, position=(0, 0), radius=50)
    b = make_card(2, "d", team=1, position=(90, 0), radius=50)   # touches a (dist 90 <= 100)
    c = make_card(3, "d", team=1, position=(180, 0), radius=50)  # touches b (dist 90 <= 100)

    assert circles_touch(a, b)
    assert circles_touch(b, c)
    assert not circles_touch(a, c)  # dist 180 > 100

    president = make_card(4, "p", team=9, position=(0, 0))

    stacks = [[a, president]]
    visible_dcs = [a, b, c]

    apply_president_claims(stacks, visible_dcs, game_mode="growth")

    assert a["owner_team"] == 9
    assert b["owner_team"] == 9
    assert c["owner_team"] != 9


def test_president_claim_does_not_extend_in_static_mode():

    a = make_card(1, "d", team=1, position=(0, 0), radius=50)
    b = make_card(2, "d", team=1, position=(90, 0), radius=50)

    president = make_card(3, "p", team=9, position=(0, 0))

    stacks = [[a, president]]
    visible_dcs = [a, b]

    apply_president_claims(stacks, visible_dcs, game_mode="static")

    assert a["owner_team"] == 9
    assert b["owner_team"] == 1


# ============================================================
# update_growth_radii
# ============================================================

def test_isolated_datacentre_grows_at_base_rate():

    dc = make_card(1, "d", team=1, position=(0, 0), radius=80)

    cards = {1: dc}

    update_growth_radii(dt=1.0, stacks=[], cards=cards, growth_rate=10, min_radius=10)

    assert dc["radius"] == pytest.approx(90.0)


def test_three_touching_same_team_datacentres_grow_at_triple_rate():

    a = make_card(1, "d", team=1, position=(0, 0), radius=50)
    b = make_card(2, "d", team=1, position=(90, 0), radius=50)
    c = make_card(3, "d", team=1, position=(180, 0), radius=50)

    cards = {1: a, 2: b, 3: c}

    update_growth_radii(dt=1.0, stacks=[], cards=cards, growth_rate=10, min_radius=10)

    assert a["radius"] == pytest.approx(80.0)
    assert b["radius"] == pytest.approx(80.0)
    assert c["radius"] == pytest.approx(80.0)


def test_third_party_wedge_invalidates_same_team_edge():
    # a and c are same team and would touch directly, but b (a DIFFERENT
    # team, sitting geometrically between them) touches both - this
    # should invalidate the a-c edge, leaving both at N=1.

    a = make_card(1, "d", team=1, position=(0, 0), radius=60)
    b = make_card(2, "d", team=2, position=(60, 0), radius=60)
    c = make_card(3, "d", team=1, position=(120, 0), radius=60)

    assert circles_touch(a, c)  # would touch directly (dist 120 <= 120)

    cards = {1: a, 2: b, 3: c}

    update_growth_radii(dt=1.0, stacks=[], cards=cards, growth_rate=10, min_radius=10)

    # a and c should each grow as an isolated node (N=1), NOT as a pair (N=2),
    # because b sits between them.
    assert a["radius"] == pytest.approx(70.0)
    assert c["radius"] == pytest.approx(70.0)


def test_blocked_datacentre_shrinks_and_does_not_inflate_neighbours():

    a = make_card(1, "d", team=1, position=(0, 0), radius=50)
    b = make_card(2, "d", team=1, position=(90, 0), radius=50)
    blocked_dc = make_card(3, "d", team=1, position=(180, 0), radius=50)
    activist = make_card(4, "a", team=1, position=(180, 0))

    cards = {1: a, 2: b, 3: blocked_dc}

    # blocked_dc is in a stack with an (unlawyered) activist -> blocked.
    stacks = [[blocked_dc, activist]]

    update_growth_radii(dt=1.0, stacks=stacks, cards=cards, growth_rate=10, min_radius=10)

    # a/b form their own real 2-cluster; blocked_dc must NOT count toward it.
    assert a["radius"] == pytest.approx(70.0)  # N=2 -> +20
    assert b["radius"] == pytest.approx(70.0)

    # blocked_dc's hypothetical N: touches b (real, unblocked) which is
    # itself part of a 2-node component -> n_hypothetical = 1 + 2 = 3
    # shrink = -2 * 3 * 10 * 1.0 = -60 -> 50 - 60 = -10, floored at 10.
    assert blocked_dc["radius"] == pytest.approx(10.0)


def test_shrink_never_crosses_min_radius_floor():

    dc = make_card(1, "d", team=1, position=(0, 0), radius=12)
    activist = make_card(2, "a", team=1, position=(0, 0))

    cards = {1: dc}
    stacks = [[dc, activist]]

    update_growth_radii(dt=5.0, stacks=stacks, cards=cards, growth_rate=100, min_radius=10)

    assert dc["radius"] == 10


# ============================================================
# score_visible_cards
# ============================================================

def test_static_mode_scores_blocked_datacentre_unconditionally():

    dc = make_card(1, "d", team=1, owner_team=1)
    activist = make_card(2, "a", team=1)

    cards = {1: dc, 2: activist}
    scores = {1: 0}

    stacks = [[dc, activist]]

    points = score_visible_cards(cards, scores, num_teams=1, game_mode="static", stacks=stacks)

    assert points[1] == 1  # dc scores; activist type is always excluded
    assert scores[1] == 1


def test_growth_mode_blocked_datacentre_scores_zero():

    dc = make_card(1, "d", team=1, owner_team=1)
    activist = make_card(2, "a", team=1)

    cards = {1: dc, 2: activist}
    scores = {1: 0}

    stacks = [[dc, activist]]

    points = score_visible_cards(cards, scores, num_teams=1, game_mode="growth", stacks=stacks)

    assert points[1] == 0
    assert scores[1] == 0


def test_scoring_uses_owner_team_not_printed_team():

    dc = make_card(1, "d", team=1, owner_team=2)  # stolen by team 2

    cards = {1: dc}
    scores = {1: 0, 2: 0}

    points = score_visible_cards(cards, scores, num_teams=2, game_mode="static", stacks=[])

    assert points[2] == 1
    assert points[1] == 0


# ============================================================
# check_area_bonus
# ============================================================

def test_area_bonus_does_not_fire_while_water_remains():

    engine = MapEngine(10, 10, water_colour=[0, 0, 255], land_colour=[0, 255, 0])
    engine.land_mask[:] = 1
    engine.land_mask[0, 0] = 0  # one water pixel remains

    scores = {1: 0}

    result = check_area_bonus(engine, scores, num_teams=1, bonus_awarded=False)

    assert result is False
    assert scores[1] == 0


def test_area_bonus_fires_once_at_full_coverage_and_latches():

    engine = MapEngine(10, 10, water_colour=[0, 0, 255], land_colour=[0, 255, 0])
    engine.land_mask[:] = 1  # fully covered, all owned by team 1

    scores = {1: 0}

    result = check_area_bonus(engine, scores, num_teams=1, bonus_awarded=False)

    assert result is True
    assert scores[1] == 100  # 10x10 fully owned

    # Second call: already latched, must not award again even if state unchanged.
    result_again = check_area_bonus(engine, scores, num_teams=1, bonus_awarded=True)

    assert result_again is True
    assert scores[1] == 100


# ============================================================
# compute_coverage_percentage
# ============================================================

def test_coverage_percentage_all_water_is_zero():

    engine = MapEngine(10, 10, water_colour=[0, 0, 255], land_colour=[0, 255, 0])

    assert compute_coverage_percentage(engine.land_mask) == pytest.approx(0.0)


def test_coverage_percentage_all_land_is_100():

    engine = MapEngine(10, 10, water_colour=[0, 0, 255], land_colour=[0, 255, 0])
    engine.land_mask[:] = 1

    assert compute_coverage_percentage(engine.land_mask) == pytest.approx(100.0)


def test_coverage_percentage_half_land_is_50():

    engine = MapEngine(10, 10, water_colour=[0, 0, 255], land_colour=[0, 255, 0])
    engine.land_mask[:5, :] = 1

    assert compute_coverage_percentage(engine.land_mask) == pytest.approx(50.0)


# ============================================================
# check_area_bonus with a configurable threshold
# ============================================================

def test_area_bonus_does_not_fire_below_threshold():

    engine = MapEngine(10, 10, water_colour=[0, 0, 255], land_colour=[0, 255, 0])
    engine.land_mask[:8, :] = 1  # 80% land

    scores = {1: 0}

    result = check_area_bonus(
        engine, scores, num_teams=1, bonus_awarded=False, threshold_percentage=90.0
    )

    assert result is False
    assert scores[1] == 0


def test_area_bonus_fires_at_configured_threshold_without_full_coverage():

    engine = MapEngine(10, 10, water_colour=[0, 0, 255], land_colour=[0, 255, 0])
    engine.land_mask[:9, :] = 1  # 90% land, all team 1

    scores = {1: 0}

    result = check_area_bonus(
        engine, scores, num_teams=1, bonus_awarded=False, threshold_percentage=90.0
    )

    assert result is True
    assert scores[1] == 90
