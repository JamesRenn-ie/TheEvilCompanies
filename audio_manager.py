import os
import re
import glob
import random
import logging

try:
    import pygame
except ImportError:
    pygame = None

logger = logging.getLogger("audio_manager")


# ============================================================
# SETTINGS
# ============================================================

SFX_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "sfx"
)

# Matches e.g. "lawyer_3.wav" -> event_type "lawyer"
FILENAME_PATTERN = re.compile(
    r"^([a-zA-Z]+)_(\d+)\.wav$",
    re.IGNORECASE
)

# ------------------------------------------------------------
# EVENT PRIORITY / VOLUME CONFIG
#
# priority: higher number = higher tier. When a sound of a given
#           tier plays, every tier <= its own priority gets cut
#           (stopped). Tiers ABOVE it are left alone.
# volume:   0.0 - 1.0
#
# Add new event_types here as new sfx categories are introduced
# (ambient loops, timer/music cues, etc.) - no engine code changes
# needed elsewhere.
# ------------------------------------------------------------

EVENT_CONFIG = {
    "datacenter":  {"priority": 1, "volume": 0.4},
    "activist":    {"priority": 1, "volume": 0.4},
    "lawyer":      {"priority": 1, "volume": 0.4},
    "billionaire": {"priority": 2, "volume": 0.7},
    "president":   {"priority": 3, "volume": 1.0},
}

# Fallback used when an event_type has sfx files but no entry
# in EVENT_CONFIG (e.g. a dev drops in "newtype_1.wav" and
# hasn't configured it yet).
DEFAULT_PRIORITY = 1
DEFAULT_VOLUME = 0.5

# Total pygame mixer channels to allocate. Priority tiers get the
# first few reserved channels; the remainder stay free for future
# ambient/looping use (see README-style notes at the bottom).
NUM_MIXER_CHANNELS = 16


# ============================================================
# AUDIO MANAGER
# ============================================================

class AudioManager:

    def __init__(self, sfx_folder=SFX_FOLDER, event_config=None):

        self.sfx_folder = sfx_folder
        self.event_config = event_config or EVENT_CONFIG

        self.enabled = False

        self._library = {}            # event_type -> [filepaths]
        self._sound_cache = {}        # filepath -> pygame.mixer.Sound
        self._priority_channels = {}  # priority(int) -> pygame.mixer.Channel

        self.init()

    # --------------------------------------------------------
    # INIT
    # --------------------------------------------------------

    def init(self):
        """
        (Re-)initialise pygame.mixer, reserve one channel per
        distinct priority tier, and scan the sfx folder.

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

            pygame.mixer.set_num_channels(NUM_MIXER_CHANNELS)

            distinct_priorities = sorted(
                set(
                    config.get("priority", DEFAULT_PRIORITY)
                    for config in self.event_config.values()
                )
                | {DEFAULT_PRIORITY}
            )

            pygame.mixer.set_reserved(len(distinct_priorities))

            self._priority_channels = {
                priority: pygame.mixer.Channel(index)
                for index, priority in enumerate(distinct_priorities)
            }

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
            DEFAULT_PRIORITY,
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
                DEFAULT_PRIORITY
            )

            play_volume = (
                volume
                if volume is not None
                else config.get("volume", DEFAULT_VOLUME)
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


# ============================================================
# MODULE-LEVEL SINGLETON
#
# Both scripts just do `import audio_manager` and call
# `audio_manager.audio.play("...")`.
# ============================================================

audio = AudioManager()


# ============================================================
# FUTURE EXTENSIBILITY (not implemented yet - notes only)
#
# - Looped ambient/atmospheric sounds: add a disjoint
#   self._ambient_channels dict (channel indices outside the
#   reserved priority range) and play_ambient(name)/stop_ambient(name)
#   methods using channel.play(sound, loops=-1). Because it's a
#   separate channel set, play()'s cutting loop never touches it.
#
# - Music-driven scoring timer: just another EVENT_CONFIG entry
#   (e.g. "scoring_tick") triggered from a one-line play() call
#   near the scoring loop in projection_mapping.py. No changes
#   needed here.
# ============================================================
