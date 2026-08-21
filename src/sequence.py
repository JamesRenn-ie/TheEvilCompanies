"""
Automatic-mode game flow state machine.

Pure and pygame-free: main.py drives this with input events, elapsed
coverage percentage, and "did the current stinger finish playing"
notifications, and reads back what it should do (grow/score/play sfx
this frame, what music command to issue, what text to show) via
properties. See README.md for the full flow description.
"""

STATE_PRE_GAME = "pre_game"
STATE_OPENING = "opening"
STATE_RUNNING_1 = "running_1"
STATE_SUSPENDED_END_1 = "suspended_end_1"
STATE_RUNNING_2 = "running_2"
STATE_SUSPENDED_END_2 = "suspended_end_2"
STATE_RUNNING_3 = "running_3"
STATE_GAME_OVER = "game_over"

RUNNING_STATES = (STATE_RUNNING_1, STATE_RUNNING_2, STATE_RUNNING_3)
STINGER_STATES = (STATE_OPENING, STATE_SUSPENDED_END_1, STATE_SUSPENDED_END_2)

# state -> (music track name or None, loop)
# None means "stop whatever music is playing" rather than "play a track
# called None".
_MUSIC_FOR_STATE = {
    STATE_PRE_GAME: (None, False),
    STATE_OPENING: ("opening", False),
    STATE_RUNNING_1: ("cue_1", True),
    STATE_SUSPENDED_END_1: ("end_1", False),
    STATE_RUNNING_2: ("cue_2", True),
    STATE_SUSPENDED_END_2: ("end_2", False),
    STATE_RUNNING_3: ("cue_3", True),
    STATE_GAME_OVER: ("end_final", False),
}


class AutomaticSequenceController:

    def __init__(self, cue_2_threshold, cue_3_threshold, completion_percentage):

        self.cue_2_threshold = cue_2_threshold
        self.cue_3_threshold = cue_3_threshold
        self.completion_percentage = completion_percentage

        self.state = STATE_PRE_GAME
        self.manually_paused = False

        self._pending_music_command = _MUSIC_FOR_STATE[self.state]

    # --------------------------------------------------------
    # TRANSITIONS
    # --------------------------------------------------------

    def _enter(self, new_state):

        self.state = new_state
        self.manually_paused = False
        self._pending_music_command = _MUSIC_FOR_STATE[new_state]

    def on_space_pressed(self):
        """
        pre_game -> opening (the "press to start" trigger).
        Any running_* state: toggle manual pause/resume, exactly like
        facilitated mode's SPACE handling.
        Stinger states and game_over: no-op, not manually skippable.
        """

        if self.state == STATE_PRE_GAME:

            self._enter(STATE_OPENING)

        elif self.state in RUNNING_STATES:

            self.manually_paused = not self.manually_paused

    def on_reset_pressed(self):
        """R always sends the game back to the pre-game screen."""

        self._enter(STATE_PRE_GAME)

    def on_stinger_finished(self):
        """
        Called once the currently-playing stinger track has stopped.
        Advances out of opening/suspended_end_1/suspended_end_2 into the
        next running phase. No-op in every other state.
        """

        if self.state == STATE_OPENING:

            self._enter(STATE_RUNNING_1)

        elif self.state == STATE_SUSPENDED_END_1:

            self._enter(STATE_RUNNING_2)

        elif self.state == STATE_SUSPENDED_END_2:

            self._enter(STATE_RUNNING_3)

    def update(self, coverage_percentage):
        """
        Called every frame with the current map coverage percentage.
        Only running_* states react - crossing the relevant threshold
        advances into the next suspended/game-over state.
        """

        if self.state == STATE_RUNNING_1:

            if coverage_percentage >= self.cue_2_threshold:
                self._enter(STATE_SUSPENDED_END_1)

        elif self.state == STATE_RUNNING_2:

            if coverage_percentage >= self.cue_3_threshold:
                self._enter(STATE_SUSPENDED_END_2)

        elif self.state == STATE_RUNNING_3:

            if coverage_percentage >= self.completion_percentage:
                self._enter(STATE_GAME_OVER)

    def pop_pending_music_command(self):
        """
        Returns the (name, loop) music command set by the most recent
        state transition, or None if it's already been consumed. `name`
        of None means "stop the current music track".
        """

        command = self._pending_music_command
        self._pending_music_command = None

        return command

    # --------------------------------------------------------
    # PROPERTIES
    # --------------------------------------------------------

    @property
    def waiting_for_stinger(self):
        return self.state in STINGER_STATES

    @property
    def should_grow(self):
        return self.state in RUNNING_STATES

    @property
    def should_score(self):
        return self.should_grow and not self.manually_paused

    @property
    def should_play_sfx(self):
        return self.should_grow

    @property
    def show_pregame_text(self):
        return self.state == STATE_PRE_GAME

    @property
    def show_paused_text(self):
        return self.manually_paused or self.state not in RUNNING_STATES

    @property
    def game_over(self):
        return self.state == STATE_GAME_OVER
