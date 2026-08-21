import json
import os


DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config.json"
)


class ConfigError(Exception):
    """
    Raised when config.json is missing, malformed, or fails
    validation (e.g. zero or multiple active projector_profiles).
    """


class Config:

    def __init__(self, data, path):

        self._data = data
        self.path = path

    @property
    def raw(self):

        return self._data

    # --------------------------------------------------------
    # PROJECTOR PROFILE
    # --------------------------------------------------------

    def active_projector_profile(self):
        """
        Return the single projector_profiles entry with
        "active": true. Raises ConfigError if zero or more
        than one profile is marked active.
        """

        profiles = self._data.get("projector_profiles", [])

        active = [
            profile
            for profile in profiles
            if profile.get("active") is True
        ]

        if len(active) == 0:

            raise ConfigError(
                f"config.json ({self.path}): no entry in "
                f"\"projector_profiles\" has \"active\": true. "
                f"Exactly one profile must be active."
            )

        if len(active) > 1:

            names = ", ".join(
                profile.get("name", "<unnamed>")
                for profile in active
            )

            raise ConfigError(
                f"config.json ({self.path}): multiple projector_profiles "
                f"are marked active ({names}). Exactly one profile "
                f"must be active."
            )

        return active[0]

    # --------------------------------------------------------
    # GAMEPLAY / COLOURS VALIDATION
    # --------------------------------------------------------

    def validate_gameplay(self):
        """
        Validate "gameplay" and "colours" values that are trusted
        unchecked elsewhere (main.py indexes them directly). Raises
        ConfigError with a specific message on the first problem found.
        """

        gameplay = self._data.get("gameplay", {})

        mode = gameplay.get("mode", "static")

        if mode not in ("static", "growth"):
            raise ConfigError(
                f"config.json ({self.path}): gameplay.mode must be "
                f"\"static\" or \"growth\", got {mode!r}."
            )

        sequence_mode = gameplay.get("sequence_mode", "facilitated")

        if sequence_mode not in ("facilitated", "automatic"):
            raise ConfigError(
                f"config.json ({self.path}): gameplay.sequence_mode must be "
                f"\"facilitated\" or \"automatic\", got {sequence_mode!r}."
            )

        def require_positive(key, allow_zero=False):

            value = gameplay.get(key)

            if value is None:
                raise ConfigError(
                    f"config.json ({self.path}): gameplay.{key} is required."
                )

            if allow_zero:
                if value < 0:
                    raise ConfigError(
                        f"config.json ({self.path}): gameplay.{key} must "
                        f"be >= 0, got {value}."
                    )
            else:
                if value <= 0:
                    raise ConfigError(
                        f"config.json ({self.path}): gameplay.{key} must "
                        f"be > 0, got {value}."
                    )

        def require_percentage(key):

            value = gameplay.get(key)

            if value is None:
                raise ConfigError(
                    f"config.json ({self.path}): gameplay.{key} is required."
                )

            if not (0 < value <= 100):
                raise ConfigError(
                    f"config.json ({self.path}): gameplay.{key} must be "
                    f"> 0 and <= 100, got {value}."
                )

        require_positive("scoring_interval")
        require_positive("stack_distance")
        require_positive("marker_timeout")
        require_positive("smoothing_time", allow_zero=True)
        require_positive("target_fps")

        require_percentage("cue_2_threshold")
        require_percentage("cue_3_threshold")
        require_percentage("completion_percentage")

        cue_2_threshold = gameplay["cue_2_threshold"]
        cue_3_threshold = gameplay["cue_3_threshold"]
        completion_percentage = gameplay["completion_percentage"]

        if not (cue_2_threshold < cue_3_threshold < completion_percentage):
            raise ConfigError(
                f"config.json ({self.path}): gameplay.cue_2_threshold "
                f"({cue_2_threshold}) < gameplay.cue_3_threshold "
                f"({cue_3_threshold}) < gameplay.completion_percentage "
                f"({completion_percentage}) must all hold."
            )

        if mode == "growth":

            require_positive("radius_growth_rate")
            require_positive("min_radius")

            num_teams = self._data.get("cards", {}).get("num_teams")
            team_rgb = self._data.get("colours", {}).get("team_rgb", [])

            if len(team_rgb) != num_teams:
                raise ConfigError(
                    f"config.json ({self.path}): gameplay.mode is "
                    f"\"growth\", so colours.team_rgb must have exactly "
                    f"one entry per team (cards.num_teams={num_teams}), "
                    f"got {len(team_rgb)}."
                )

        profile = self.active_projector_profile()

        for key in ("width", "height", "data_centre_radius"):

            if profile.get(key, 0) <= 0:
                raise ConfigError(
                    f"config.json ({self.path}): active projector "
                    f"profile {profile.get('name', '<unnamed>')!r} must "
                    f"have {key} > 0, got {profile.get(key)}."
                )

        aruco_dictionary = self._data.get("camera", {}).get("aruco_dictionary")

        if not aruco_dictionary or not isinstance(aruco_dictionary, str):
            raise ConfigError(
                f"config.json ({self.path}): camera.aruco_dictionary must "
                f"be a non-empty string (e.g. \"DICT_6X6_250\")."
            )

        music_cfg = self._data.get("audio", {}).get("music", {})

        music_volume = music_cfg.get("volume")

        if music_volume is not None and not (0.0 <= music_volume <= 1.0):
            raise ConfigError(
                f"config.json ({self.path}): audio.music.volume must be "
                f"null or between 0.0 and 1.0, got {music_volume}."
            )

        duck_multiplier = music_cfg.get("duck_multiplier", 0.7)

        if not (0.0 < duck_multiplier <= 1.0):
            raise ConfigError(
                f"config.json ({self.path}): audio.music.duck_multiplier "
                f"must be > 0.0 and <= 1.0, got {duck_multiplier}."
            )

        duck_fade_in_seconds = music_cfg.get("duck_fade_in_seconds", 0.2)

        if duck_fade_in_seconds < 0:
            raise ConfigError(
                f"config.json ({self.path}): audio.music.duck_fade_in_seconds "
                f"must be >= 0, got {duck_fade_in_seconds}."
            )


# ============================================================
# LOAD
# ============================================================

def load_config(path=None):
    """
    Load and validate config.json. Raises ConfigError if the
    file is missing, isn't valid JSON, or fails validation
    (checked eagerly here so a bad config fails at startup,
    not on first use deep inside the game loop).
    """

    path = path or DEFAULT_CONFIG_PATH

    if not os.path.isfile(path):

        raise ConfigError(
            f"config.json not found at {path}"
        )

    try:

        with open(path, "r", encoding="utf-8") as config_file:
            data = json.load(config_file)

    except json.JSONDecodeError as exc:

        raise ConfigError(
            f"config.json at {path} is not valid JSON: {exc}"
        ) from exc

    config = Config(data, path)

    # Validate eagerly, so a bad config fails at startup, not deep
    # inside the game loop.
    config.active_projector_profile()
    config.validate_gameplay()

    return config
