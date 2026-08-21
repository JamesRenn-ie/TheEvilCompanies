def select_cue(coverage_percentage, cue_2_threshold, cue_3_threshold):
    """
    Facilitated-mode cue selection: which music/cue_N.wav should be
    looping right now, purely as a function of current map coverage.

    Boundaries are inclusive on the upper side - coverage exactly equal
    to a threshold has already crossed into the next cue.
    """

    if coverage_percentage >= cue_3_threshold:
        return "cue_3"

    if coverage_percentage >= cue_2_threshold:
        return "cue_2"

    return "cue_1"
