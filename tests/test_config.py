import copy

import pytest

from src.config import Config, ConfigError


def make_valid_data(mode="static"):

    data = {
        "projector_profiles": [
            {
                "name": "test_profile",
                "width": 1280,
                "height": 720,
                "data_centre_radius": 80,
                "active": True,
            }
        ],
        "camera": {
            "aruco_dictionary": "DICT_6X6_250",
        },
        "cards": {
            "num_teams": 4,
        },
        "gameplay": {
            "mode": mode,
            "sequence_mode": "facilitated",
            "scoring_interval": 10.0,
            "stack_distance": 70,
            "marker_timeout": 0.15,
            "smoothing_time": 0.05,
            "target_fps": 30,
            "radius_growth_rate": 30,
            "min_radius": 10,
            "cue_2_threshold": 33,
            "cue_3_threshold": 66,
            "completion_percentage": 98,
        },
        "colours": {
            "team_rgb": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0]],
        },
    }

    return data


def test_fully_valid_static_config_loads_cleanly():

    config = Config(make_valid_data("static"), path="<test>")

    config.active_projector_profile()
    config.validate_gameplay()  # should not raise


def test_fully_valid_growth_config_loads_cleanly():

    config = Config(make_valid_data("growth"), path="<test>")

    config.validate_gameplay()  # should not raise


@pytest.mark.parametrize("mode", ["STATIC", "grow", "", None])
def test_invalid_mode_raises(mode):

    data = make_valid_data("static")
    data["gameplay"]["mode"] = mode

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


@pytest.mark.parametrize(
    "key,bad_value",
    [
        ("scoring_interval", 0),
        ("scoring_interval", -1),
        ("stack_distance", 0),
        ("marker_timeout", 0),
        ("target_fps", 0),
    ],
)
def test_non_positive_gameplay_values_raise(key, bad_value):

    data = make_valid_data("static")
    data["gameplay"][key] = bad_value

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


def test_negative_smoothing_time_raises():

    data = make_valid_data("static")
    data["gameplay"]["smoothing_time"] = -0.01

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


def test_zero_smoothing_time_is_allowed():

    data = make_valid_data("static")
    data["gameplay"]["smoothing_time"] = 0

    config = Config(data, path="<test>")

    config.validate_gameplay()  # should not raise


@pytest.mark.parametrize("key", ["radius_growth_rate", "min_radius"])
def test_growth_mode_requires_growth_only_keys(key):

    data = make_valid_data("growth")
    del data["gameplay"][key]

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


def test_growth_mode_requires_team_rgb_length_to_match_num_teams():

    data = make_valid_data("growth")
    data["colours"]["team_rgb"] = [[1, 0, 0]]  # only 1, but num_teams=4

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


def test_static_mode_does_not_require_team_rgb_by_default():

    data = make_valid_data("static")
    del data["colours"]["team_rgb"]  # team colours never render in static mode by default

    config = Config(data, path="<test>")

    config.validate_gameplay()  # should not raise


def test_team_colours_enabled_true_requires_team_rgb_even_in_static_mode():

    data = make_valid_data("static")
    data["colours"]["team_colours_enabled"] = True
    data["colours"]["team_rgb"] = [[1, 0, 0]]  # only 1, but num_teams=4

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


def test_team_colours_enabled_false_skips_team_rgb_check_in_growth_mode():

    data = make_valid_data("growth")
    data["colours"]["team_colours_enabled"] = False
    del data["colours"]["team_rgb"]  # forced off, so never rendered

    config = Config(data, path="<test>")

    config.validate_gameplay()  # should not raise


@pytest.mark.parametrize("bad_value", ["true", 1, 0, [], {}])
def test_team_colours_enabled_non_boolean_raises(bad_value):

    data = make_valid_data("static")
    data["colours"]["team_colours_enabled"] = bad_value

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


@pytest.mark.parametrize("key", ["width", "height", "data_centre_radius"])
def test_non_positive_profile_values_raise(key):

    data = make_valid_data("static")
    data["projector_profiles"][0][key] = 0

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


def test_missing_or_empty_aruco_dictionary_raises():

    data = make_valid_data("static")
    data["camera"]["aruco_dictionary"] = ""

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


# ============================================================
# gameplay.sequence_mode
# ============================================================

@pytest.mark.parametrize("sequence_mode", ["FACILITATED", "manual", "", None])
def test_invalid_sequence_mode_raises(sequence_mode):

    data = make_valid_data("static")
    data["gameplay"]["sequence_mode"] = sequence_mode

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


def test_sequence_mode_defaults_to_facilitated_when_absent():

    data = make_valid_data("static")
    del data["gameplay"]["sequence_mode"]

    config = Config(data, path="<test>")

    config.validate_gameplay()  # should not raise


# ============================================================
# gameplay.cue_2_threshold / cue_3_threshold / completion_percentage
# ============================================================

@pytest.mark.parametrize(
    "key", ["cue_2_threshold", "cue_3_threshold", "completion_percentage"]
)
def test_missing_threshold_raises(key):

    data = make_valid_data("static")
    del data["gameplay"][key]

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


@pytest.mark.parametrize(
    "key,bad_value",
    [
        ("cue_2_threshold", 0),
        ("cue_2_threshold", -5),
        ("cue_2_threshold", 101),
        ("completion_percentage", 0),
        ("completion_percentage", 150),
    ],
)
def test_threshold_out_of_range_raises(key, bad_value):

    data = make_valid_data("static")
    data["gameplay"][key] = bad_value

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


@pytest.mark.parametrize(
    "cue_2_threshold,cue_3_threshold,completion_percentage",
    [
        (66, 33, 98),   # cue_2 > cue_3
        (33, 98, 66),   # completion below cue_3
        (50, 50, 98),   # cue_2 == cue_3
        (33, 66, 66),   # cue_3 == completion
    ],
)
def test_thresholds_must_be_strictly_increasing(
    cue_2_threshold, cue_3_threshold, completion_percentage
):

    data = make_valid_data("static")
    data["gameplay"]["cue_2_threshold"] = cue_2_threshold
    data["gameplay"]["cue_3_threshold"] = cue_3_threshold
    data["gameplay"]["completion_percentage"] = completion_percentage

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


# ============================================================
# audio.music
# ============================================================

def test_audio_music_section_is_entirely_optional():

    data = make_valid_data("static")

    config = Config(data, path="<test>")

    config.validate_gameplay()  # should not raise - no "audio" key at all


def test_null_music_volume_is_allowed():

    data = make_valid_data("static")
    data["audio"] = {"music": {"volume": None}}

    config = Config(data, path="<test>")

    config.validate_gameplay()  # should not raise


@pytest.mark.parametrize("volume", [-0.1, 1.1])
def test_music_volume_out_of_range_raises(volume):

    data = make_valid_data("static")
    data["audio"] = {"music": {"volume": volume}}

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


@pytest.mark.parametrize("duck_multiplier", [0, -0.1, 1.1])
def test_duck_multiplier_out_of_range_raises(duck_multiplier):

    data = make_valid_data("static")
    data["audio"] = {"music": {"duck_multiplier": duck_multiplier}}

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


def test_negative_duck_fade_in_seconds_raises():

    data = make_valid_data("static")
    data["audio"] = {"music": {"duck_fade_in_seconds": -0.01}}

    config = Config(data, path="<test>")

    with pytest.raises(ConfigError):
        config.validate_gameplay()


def test_zero_duck_fade_in_seconds_is_allowed():

    data = make_valid_data("static")
    data["audio"] = {"music": {"duck_fade_in_seconds": 0}}

    config = Config(data, path="<test>")

    config.validate_gameplay()  # should not raise
