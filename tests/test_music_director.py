import pytest

from src.music_director import select_cue


@pytest.mark.parametrize(
    "coverage_percentage,expected_cue",
    [
        (0, "cue_1"),
        (32.9, "cue_1"),
        (33, "cue_2"),
        (50, "cue_2"),
        (65.9, "cue_2"),
        (66, "cue_3"),
        (99, "cue_3"),
        (100, "cue_3"),
    ],
)
def test_select_cue_boundaries(coverage_percentage, expected_cue):

    assert select_cue(coverage_percentage, cue_2_threshold=33, cue_3_threshold=66) == expected_cue
