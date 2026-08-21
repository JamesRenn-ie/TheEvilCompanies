import pytest

from src.sequence import (
    AutomaticSequenceController,
    STATE_PRE_GAME,
    STATE_OPENING,
    STATE_RUNNING_1,
    STATE_SUSPENDED_END_1,
    STATE_RUNNING_2,
    STATE_SUSPENDED_END_2,
    STATE_RUNNING_3,
    STATE_GAME_OVER,
)


def make_controller():
    return AutomaticSequenceController(
        cue_2_threshold=33, cue_3_threshold=66, completion_percentage=98
    )


# ============================================================
# Full happy-path transition sequence
# ============================================================

def test_full_transition_sequence():

    controller = make_controller()

    assert controller.state == STATE_PRE_GAME
    assert controller.show_pregame_text

    controller.on_space_pressed()
    assert controller.state == STATE_OPENING
    assert controller.waiting_for_stinger
    assert not controller.should_grow

    controller.on_stinger_finished()
    assert controller.state == STATE_RUNNING_1
    assert controller.should_grow
    assert controller.should_score
    assert controller.should_play_sfx

    controller.update(coverage_percentage=10)
    assert controller.state == STATE_RUNNING_1  # below cue_2_threshold

    controller.update(coverage_percentage=33)
    assert controller.state == STATE_SUSPENDED_END_1
    assert controller.waiting_for_stinger
    assert not controller.should_grow

    controller.on_stinger_finished()
    assert controller.state == STATE_RUNNING_2

    controller.update(coverage_percentage=66)
    assert controller.state == STATE_SUSPENDED_END_2

    controller.on_stinger_finished()
    assert controller.state == STATE_RUNNING_3

    controller.update(coverage_percentage=98)
    assert controller.state == STATE_GAME_OVER
    assert controller.game_over
    assert not controller.should_grow
    assert not controller.should_score


# ============================================================
# Music commands
# ============================================================

def test_music_command_set_on_construction_is_stop():

    controller = make_controller()

    assert controller.pop_pending_music_command() == (None, False)


def test_music_command_is_one_shot():

    controller = make_controller()
    controller.pop_pending_music_command()

    controller.on_space_pressed()  # -> opening

    assert controller.pop_pending_music_command() == ("opening", False)
    assert controller.pop_pending_music_command() is None


@pytest.mark.parametrize(
    "advance_to_running_1,expected_command",
    [(True, ("cue_1", True))],
)
def test_running_state_music_loops(advance_to_running_1, expected_command):

    controller = make_controller()
    controller.on_space_pressed()
    controller.on_stinger_finished()

    assert controller.pop_pending_music_command() == expected_command


# ============================================================
# Manual pause (SPACE during running states only)
# ============================================================

def test_space_toggles_manual_pause_in_running_state():

    controller = make_controller()
    controller.on_space_pressed()
    controller.on_stinger_finished()

    assert not controller.manually_paused

    controller.on_space_pressed()
    assert controller.manually_paused
    assert controller.should_grow          # growth continues while manually paused
    assert not controller.should_score     # scoring stops while manually paused
    assert controller.should_play_sfx      # sfx still fire while manually paused

    controller.on_space_pressed()
    assert not controller.manually_paused


@pytest.mark.parametrize(
    "setup_state",
    [STATE_OPENING, STATE_SUSPENDED_END_1, STATE_SUSPENDED_END_2, STATE_GAME_OVER],
)
def test_space_is_noop_outside_pregame_and_running_states(setup_state):

    controller = make_controller()
    controller.state = setup_state
    controller.pop_pending_music_command()

    controller.on_space_pressed()

    assert controller.state == setup_state
    assert not controller.manually_paused
    assert controller.pop_pending_music_command() is None  # no transition happened


# ============================================================
# Reset
# ============================================================

@pytest.mark.parametrize(
    "setup_state",
    [
        STATE_OPENING,
        STATE_RUNNING_1,
        STATE_SUSPENDED_END_1,
        STATE_RUNNING_2,
        STATE_SUSPENDED_END_2,
        STATE_RUNNING_3,
        STATE_GAME_OVER,
    ],
)
def test_reset_returns_to_pregame_from_any_state(setup_state):

    controller = make_controller()
    controller.state = setup_state
    controller.manually_paused = True

    controller.on_reset_pressed()

    assert controller.state == STATE_PRE_GAME
    assert not controller.manually_paused
    assert controller.pop_pending_music_command() == (None, False)


# ============================================================
# on_stinger_finished no-ops outside stinger states
# ============================================================

@pytest.mark.parametrize(
    "setup_state", [STATE_PRE_GAME, STATE_RUNNING_1, STATE_RUNNING_2, STATE_RUNNING_3, STATE_GAME_OVER]
)
def test_stinger_finished_is_noop_outside_stinger_states(setup_state):

    controller = make_controller()
    controller.state = setup_state
    controller.pop_pending_music_command()

    controller.on_stinger_finished()

    assert controller.state == setup_state
    assert controller.pop_pending_music_command() is None


# ============================================================
# update() only reacts in running states
# ============================================================

@pytest.mark.parametrize(
    "setup_state",
    [STATE_PRE_GAME, STATE_OPENING, STATE_SUSPENDED_END_1, STATE_SUSPENDED_END_2, STATE_GAME_OVER],
)
def test_update_is_noop_outside_running_states(setup_state):

    controller = make_controller()
    controller.state = setup_state

    controller.update(coverage_percentage=100)

    assert controller.state == setup_state


# ============================================================
# show_paused_text
# ============================================================

def test_show_paused_text_true_during_stinger_and_manual_pause_but_not_running():

    controller = make_controller()
    controller.on_space_pressed()
    controller.on_stinger_finished()

    assert not controller.show_paused_text  # running, not manually paused

    controller.on_space_pressed()
    assert controller.show_paused_text  # running, but manually paused

    controller.on_space_pressed()  # unpause
    controller.state = STATE_SUSPENDED_END_1
    assert controller.show_paused_text  # stinger state
