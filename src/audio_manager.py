import os
import re
import glob
import random
import logging
import time

try:
    import pygame
except ImportError:
    pygame = None

from src.audio_ducking import compute_duck_until, compute_ducked_volume

logger = logging.getLogger("audio_manager")


# ============================================================
# SETTINGS
# ============================================================

SFX_FOLDER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sfx"
)

MUSIC_FOLDER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "music"
)

# Matches e.g. "lawyer_3.wav" -> event_type "lawyer"
FILENAME_PATTERN = re.compile(
    r"^([a-zA-Z]+)_(\d+)\.wav$",
    re.IGNORECASE
)

# ------------------------------------------------------------
# DEFAULT EVENT PRIORITY / VOLUME CONFIG
#
# priority: higher number = higher tier. When a sound of a given
#           tier plays, every tier <= its own priority gets cut
#           (stopped). Tiers ABOVE it are left alone.
# volume:   0.0 - 1.0
#
# These are only the fallback values used if nothing overrides
# them via configure(). The real values live in config.json
# ("audio.sfx") and are applied by main.py through configure()
# right after import - see the AudioManager.configure() docstring.
# ------------------------------------------------------------

DEFAULT_EVENT_CONFIG = {
    "datacenter":  {"priority": 1, "volume": 0.4},
    "activist":    {"priority": 1, "volume": 0.4},
    "lawyer":      {"priority": 1, "volume": 0.4},
    "billionaire": {"priority": 2, "volume": 0.7},
    "president":   {"priority": 3, "volume": 1.0},
}

# Fallback used when an event_type has sfx files but no entry
# in event_config (e.g. a dev drops in "newtype_1.wav" and
# hasn't configured it yet).
DEFAULT_PRIORITY = 1
DEFAULT_VOLUME = 0.5

# Total pygame mixer channels to allocate. Priority tiers get the
# first few reserved channels, one further reserved channel is
# dedicated to looping music (see MUSIC below), and the remainder
# stay free for future ambient/looping use.
DEFAULT_NUM_MIXER_CHANNELS = 16

# ------------------------------------------------------------
# MUSIC / DUCKING DEFAULTS
#
# music volume: if no explicit override is configured, music plays at
# the quietest configured sfx event volume, so it never overpowers any
# sfx tier. duck_multiplier/duck_fade_in_seconds control how far music
# ducks while an sfx plays and how quickly it fades back afterward -
# see src/audio_ducking.py for the actual envelope math.
# ------------------------------------------------------------

DEFAULT_DUCK_MULTIPLIER = 0.7
DEFAULT_DUCK_FADE_IN_SECONDS = 0.2


# ============================================================
# AUDIO MANAGER
# ============================================================

class AudioManager:

    def __init__(
        self,
        sfx_folder=SFX_FOLDER,
        music_folder=MUSIC_FOLDER,
        event_config=None,
        num_mixer_channels=None,
        default_priority=None,
        default_volume=None,
        music_volume_override=None,
        duck_multiplier=None,
        duck_fade_in_seconds=None
    ):

        self.sfx_folder = sfx_folder
        self.music_folder = music_folder
        self.event_config = event_config or DEFAULT_EVENT_CONFIG
        self.num_mixer_channels = (
            num_mixer_channels or DEFAULT_NUM_MIXER_CHANNELS
        )
        self.default_priority = (
            DEFAULT_PRIORITY
            if default_priority is None
            else default_priority
        )
        self.default_volume = (
            DEFAULT_VOLUME
            if default_volume is None
            else default_volume
        )
        self.music_volume_override = music_volume_override
        self.duck_multiplier = (
            DEFAULT_DUCK_MULTIPLIER
            if duck_multiplier is None
            else duck_multiplier
        )
        self.duck_fade_in_seconds = (
            DEFAULT_DUCK_FADE_IN_SECONDS
            if duck_fade_in_seconds is None
            else duck_fade_in_seconds
        )

        self.enabled = False

        self._library = {}            # event_type -> [filepaths]
        self._sound_cache = {}        # filepath -> pygame.mixer.Sound
        self._priority_channels = {}  # priority(int) -> pygame.mixer.Channel
        self._music_channel = None
        self._music_base_volume = self.default_volume
        self._music_current_volume = self.default_volume
        self._duck_until = 0.0

        self.init()

    # --------------------------------------------------------
    # CONFIGURE
    # --------------------------------------------------------

    def configure(
        self,
        event_config=None,
        num_mixer_channels=None,
        default_priority=None,
        default_volume=None,
        sfx_folder=None,
        music_folder=None,
        music_volume_override=None,
        duck_multiplier=None,
        duck_fade_in_seconds=None
    ):
        """
        Apply config.json-sourced settings (typically config.json's
        "audio.sfx" and "audio.music" sections) and re-run init() so
        mixer channels are re-reserved for the new priority tiers and
        sfx/ is re-scanned.

        Safe to call once at startup, right after
        `from src.audio_manager import audio`. Everything not
        passed keeps its current value.
        """

        if event_config is not None:
            self.event_config = event_config

        if num_mixer_channels is not None:
            self.num_mixer_channels = num_mixer_channels

        if default_priority is not None:
            self.default_priority = default_priority

        if default_volume is not None:
            self.default_volume = default_volume

        if sfx_folder is not None:
            self.sfx_folder = sfx_folder

        if music_folder is not None:
            self.music_folder = music_folder

        if music_volume_override is not None:
            self.music_volume_override = music_volume_override

        if duck_multiplier is not None:
            self.duck_multiplier = duck_multiplier

        if duck_fade_in_seconds is not None:
            self.duck_fade_in_seconds = duck_fade_in_seconds

        self.init()

    # --------------------------------------------------------
    # INIT
    # --------------------------------------------------------

    def init(self):
        """
        (Re-)initialise pygame.mixer, reserve one channel per
        distinct priority tier plus one dedicated music channel, and
        scan the sfx folder.

        Never raises - on any failure, self.enabled = False and
        every subsequent play() becomes a no-op.
        """

        if pygame is None:
            logger.warning(
                "audio_manager: pygame not importable, audio disabled"
            )
            self.enabled = False
            return

        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()

            distinct_priorities = sorted(
                set(
                    config.get("priority", self.default_priority)
                    for config in self.event_config.values()
                )
                | {self.default_priority}
            )

            # +1 reserved channel, disjoint from the sfx priority tiers,
            # dedicated to looping music - see play_music()/update().
            total_reserved = len(distinct_priorities) + 1

            self.num_mixer_channels = max(
                self.num_mixer_channels, total_reserved
            )

            pygame.mixer.set_num_channels(self.num_mixer_channels)
            pygame.mixer.set_reserved(total_reserved)

            self._priority_channels = {
                priority: pygame.mixer.Channel(index)
                for index, priority in enumerate(distinct_priorities)
            }

            self._music_channel = pygame.mixer.Channel(
                len(distinct_priorities)
            )

            if self.music_volume_override is not None:
                self._music_base_volume = self.music_volume_override
            elif self.event_config:
                self._music_base_volume = min(
                    config.get("volume", self.default_volume)
                    for config in self.event_config.values()
                )
            else:
                self._music_base_volume = self.default_volume

            self._music_current_volume = self._music_base_volume
            self._duck_until = 0.0

            self._scan_library()

            self.enabled = True

        except Exception as exc:

            logger.warning(
                f"audio_manager: mixer init failed, audio disabled ({exc})"
            )
            self.enabled = False

    # --------------------------------------------------------
    # RELOAD
    # --------------------------------------------------------

    def reload(self):
        """
        Re-scan sfx/ for new/removed files without restarting.
        """

        if not self.enabled:
            return

        try:
            self._scan_library()

        except Exception as exc:

            logger.warning(
                f"audio_manager: reload failed ({exc})"
            )

    # --------------------------------------------------------
    # SCAN LIBRARY
    # --------------------------------------------------------

    def _scan_library(self):

        library = {}

        if not os.path.isdir(self.sfx_folder):

            logger.warning(
                f"audio_manager: sfx folder not found: {self.sfx_folder}"
            )
            self._library = {}
            return

        for path in glob.glob(
            os.path.join(self.sfx_folder, "*.wav")
        ):

            match = FILENAME_PATTERN.match(
                os.path.basename(path)
            )

            if not match:
                continue

            event_type = match.group(1).lower()

            library.setdefault(
                event_type,
                []
            ).append(path)

        self._library = library

    # --------------------------------------------------------
    # LOAD SOUND (cached)
    # --------------------------------------------------------

    def _load_sound(self, filepath):

        if filepath in self._sound_cache:
            return self._sound_cache[filepath]

        try:
            sound = pygame.mixer.Sound(filepath)

        except Exception as exc:

            logger.warning(
                f"audio_manager: failed to load {filepath} ({exc})"
            )
            return None

        self._sound_cache[filepath] = sound

        return sound

    # --------------------------------------------------------
    # CHANNEL FOR PRIORITY
    # --------------------------------------------------------

    def _channel_for_priority(self, priority):

        channel = self._priority_channels.get(priority)

        if channel is not None:
            return channel

        return self._priority_channels.get(
            self.default_priority,
            next(iter(self._priority_channels.values()))
        )

    # --------------------------------------------------------
    # PLAY
    # --------------------------------------------------------

    def play(self, event_type, volume=None):
        """
        Play a random sfx file for event_type.

        Cutting rule: a sound cuts (stops) any currently playing
        sound whose priority tier is <= its own. It never blocks
        or delays itself because something higher-priority is
        already playing elsewhere - it always plays on its own
        tier's channel regardless of what else is active.
        """

        if not self.enabled:
            return

        try:
            files = self._library.get(event_type)

            if not files:

                logger.warning(
                    f"audio_manager: no sfx for event_type '{event_type}'"
                )
                return

            config = self.event_config.get(event_type, {})

            priority = config.get(
                "priority",
                self.default_priority
            )

            play_volume = (
                volume
                if volume is not None
                else config.get("volume", self.default_volume)
            )

            sound = self._load_sound(
                random.choice(files)
            )

            if sound is None:
                return

            for tier_priority, channel in self._priority_channels.items():

                if tier_priority <= priority:
                    channel.stop()

            target_channel = self._channel_for_priority(priority)

            sound.set_volume(play_volume)

            target_channel.play(sound)

            self._duck_until = compute_duck_until(
                self._duck_until,
                time.monotonic(),
                sound.get_length(),
            )

        except Exception as exc:

            logger.warning(
                f"audio_manager: play('{event_type}') failed ({exc})"
            )

    # --------------------------------------------------------
    # STOP ALL
    # --------------------------------------------------------

    def stop_all(self):

        if not self.enabled:
            return

        for channel in self._priority_channels.values():
            channel.stop()

    # --------------------------------------------------------
    # MUSIC
    # --------------------------------------------------------

    def play_music(self, name, loop=True):
        """
        Play music/<name>.wav on the dedicated music channel (a single
        literal filename, not a random pool like sfx event types).

        Instant cut: always stops whatever's currently on the music
        channel first, then starts the new track - no crossfade.
        """

        if not self.enabled:
            return

        try:
            path = os.path.join(self.music_folder, f"{name}.wav")

            sound = self._load_sound(path)

            if sound is None:
                return

            self._music_channel.stop()

            sound.set_volume(self._music_current_volume)

            self._music_channel.play(sound, loops=-1 if loop else 0)

        except Exception as exc:

            logger.warning(
                f"audio_manager: play_music('{name}') failed ({exc})"
            )

    def stop_music(self):

        if not self.enabled:
            return

        self._music_channel.stop()

    def is_music_playing(self):

        return self.enabled and self._music_channel.get_busy()

    def update(self, dt):
        """
        Call once per frame regardless of pause state, so the music
        duck/restore envelope keeps advancing. See src/audio_ducking.py.
        """

        if not self.enabled:
            return

        self._music_current_volume = compute_ducked_volume(
            self._music_current_volume,
            self._music_base_volume,
            self.duck_multiplier,
            self._duck_until,
            time.monotonic(),
            self.duck_fade_in_seconds,
            dt,
        )

        self._music_channel.set_volume(self._music_current_volume)


# ============================================================
# MODULE-LEVEL SINGLETON
#
# Both scripts just do `from src.audio_manager import audio` and
# call `audio.play("...")`. main.py additionally calls
# `audio.configure(...)` once at startup to apply config.json's
# "audio.sfx" values in place of the DEFAULT_* fallbacks above.
# ============================================================

audio = AudioManager()


# ============================================================
# FUTURE EXTENSIBILITY (not implemented yet - notes only)
#
# - Looped ambient/atmospheric sounds beyond music: would need another
#   disjoint channel (or set of channels) outside both the reserved
#   priority range AND the music channel, same play_ambient()/
#   stop_ambient() pattern the music channel now uses.
#
# - Music-driven scoring timer: just another event_config entry
#   (e.g. "scoring_tick") triggered from a one-line play() call
#   near the scoring loop in main.py. No changes needed here.
# ============================================================
