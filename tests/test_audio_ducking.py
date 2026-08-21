import pytest

from src.audio_ducking import compute_duck_until, compute_ducked_volume


# ============================================================
# compute_duck_until
# ============================================================

def test_duck_until_extends_from_a_fresh_sfx():

    result = compute_duck_until(current_duck_until=0.0, now=10.0, sfx_duration_seconds=2.0)

    assert result == pytest.approx(12.0)


def test_duck_until_never_shortens_on_overlapping_shorter_sfx():

    # First sfx already pushed the window out to t=20.
    current = 20.0

    # A second, shorter sfx starts at t=15 and would only need until t=16.
    result = compute_duck_until(current_duck_until=current, now=15.0, sfx_duration_seconds=1.0)

    assert result == pytest.approx(20.0)


def test_duck_until_extends_on_overlapping_longer_sfx():

    current = 20.0

    # A longer sfx starts at t=19, needs until t=25.
    result = compute_duck_until(current_duck_until=current, now=19.0, sfx_duration_seconds=6.0)

    assert result == pytest.approx(25.0)


# ============================================================
# compute_ducked_volume
# ============================================================

def test_volume_snaps_down_instantly_while_ducked():

    result = compute_ducked_volume(
        current_volume=1.0,
        base_volume=1.0,
        duck_multiplier=0.7,
        duck_until=10.0,
        now=5.0,
        fade_in_seconds=0.2,
        dt=0.016,
    )

    assert result == pytest.approx(0.7)


def test_volume_ramps_back_up_linearly_after_duck_window_ends():

    base_volume = 1.0
    duck_multiplier = 0.7
    fade_in_seconds = 0.2

    # A small dt after the duck window ended, well short of a full fade-in.
    current = base_volume * duck_multiplier
    dt = 0.02

    result = compute_ducked_volume(
        current_volume=current,
        base_volume=base_volume,
        duck_multiplier=duck_multiplier,
        duck_until=10.0,
        now=10.1,
        fade_in_seconds=fade_in_seconds,
        dt=dt,
    )

    expected = current + base_volume * (dt / fade_in_seconds)

    assert result == pytest.approx(expected)


def test_volume_never_overshoots_base_volume_when_ramping():

    result = compute_ducked_volume(
        current_volume=0.99,
        base_volume=1.0,
        duck_multiplier=0.7,
        duck_until=10.0,
        now=20.0,
        fade_in_seconds=0.2,
        dt=1.0,
    )

    assert result == pytest.approx(1.0)


def test_zero_fade_in_seconds_restores_instantly():

    result = compute_ducked_volume(
        current_volume=0.7,
        base_volume=1.0,
        duck_multiplier=0.7,
        duck_until=10.0,
        now=10.1,
        fade_in_seconds=0.0,
        dt=0.016,
    )

    assert result == pytest.approx(1.0)
