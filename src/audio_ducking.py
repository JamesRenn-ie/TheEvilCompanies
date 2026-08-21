def compute_duck_until(current_duck_until, now, sfx_duration_seconds):
    """
    Extend the music-ducking window to cover a newly-started sfx.

    Never shortens the window - if several sfx overlap, each one just
    pushes duck_until further out, so music stays ducked until the
    LAST overlapping sfx finishes.
    """

    return max(current_duck_until, now + sfx_duration_seconds)


def compute_ducked_volume(
    current_volume,
    base_volume,
    duck_multiplier,
    duck_until,
    now,
    fade_in_seconds,
    dt,
):
    """
    One frame-step of the music duck/restore envelope.

    While `now < duck_until`, the target volume snaps instantly down to
    `base_volume * duck_multiplier` (an sfx just started or is still
    playing - no reason to delay ducking). Once the window ends, volume
    ramps linearly back up to `base_volume` over `fade_in_seconds`.
    """

    ducked_volume = base_volume * duck_multiplier

    if now < duck_until:
        return ducked_volume

    if fade_in_seconds <= 0:
        return base_volume

    step = base_volume * (dt / fade_in_seconds)

    return min(base_volume, current_volume + step)
