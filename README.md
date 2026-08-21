# TheEvilCompanies

Project for Make Shift Camp 2026.

A projected board game: teams place ArUco-marker cards on a physical
surface, a camera watches the board, and `main.py` projects a live
land/water map back onto it based on which cards are where.

## Running the game

```bash
python main.py
```

`main.py` reads `config.json` from the repository root at startup. A
malformed or invalid config fails immediately with a clear error
(see `src/config.py`), rather than partway through the game.

## Controls

| Key     | Effect |
|---------|--------|
| `SPACE` | Facilitated mode: pause/resume the game. Automatic mode: starts the game from the pre-game screen; once running, pauses/resumes it the same way. |
| `R`     | Facilitated mode: reset scores and card ownership, game keeps running/paused as it was. Automatic mode: send the game all the way back to the pre-game "Everything's Computer" screen. |
| `C`     | Recalibrate: forget the current camera-to-projector homography and show "WAITING FOR CALIBRATION" until all `camera.calibration_ids` are seen together again. Cards keep tracking with the old homography for up to `marker_timeout` seconds, then stop until recalibration completes. Use this any time the camera or projector has moved. |
| `Q`     | Quit. |

## config.json reference

### `projector_profiles`

A list of named output resolutions; exactly one entry must have
`"active": true` - that's the profile used for this run. Swap which
one is active to switch resolution/rig without touching anything
else.

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Label only, printed at startup. |
| `width`, `height` | int > 0 | Projector/display resolution in pixels. |
| `data_centre_radius` | int > 0 | Starting radius (px) of a Data Centre's circle before any growth-mode changes. |
| `active` | bool | Exactly one profile must be `true`. |

### `camera`

| Field | Type | Meaning |
|---|---|---|
| `source` | `"phone"` \| `"webcam"` | Which capture backend to use. |
| `phone.ip`, `phone.port`, `phone.path` | string/int/string | Used when `source: "phone"` - builds the IP-camera stream URL `http://{ip}:{port}{path}` (e.g. an IP Webcam Android app). |
| `webcam.device_index` | int | Used when `source: "webcam"` - the OpenCV device index for a locally-attached camera. |
| `calibration_ids` | list of 4 ints | ArUco marker IDs at the board's four calibration corners, used to compute the camera→projector homography. |
| `homography_recompute_every_frame` | bool | If `false` (default), the homography is computed once and reused. If `true`, it's recomputed every frame the calibration markers are visible (useful if the camera/projector can move mid-game, costs a little CPU). |
| `aruco_dictionary` | string | Must name a real OpenCV constant, e.g. `"DICT_6X6_250"` - passed to `cv2.aruco.<name>`. An unrecognised name fails at startup. |

### `cards`

Defines how physical ArUco marker IDs map to (team, card type) pairs.
See `src/card_assignments.py` - marker IDs are assigned sequentially
starting at `start_card_id`, team 1 first, in `cards_per_team`'s key
order, then team 2, and so on. `scripts/createmarkers.py` uses the
exact same logic, so the two can never drift apart.

| Field | Type | Meaning |
|---|---|---|
| `num_teams` | int | Number of teams playing. |
| `start_card_id` | int | First ArUco marker ID used for a gameplay card (IDs below this are typically reserved for calibration markers). |
| `cards_per_team` | object | How many of each card type each team gets. Keys are single-letter card-type codes: `d` = Data Centre, `a` = Activist, `l` = Lawyer, `b` = Billionaire, `p` = President. |

### `gameplay`

| Field | Type | Meaning |
|---|---|---|
| `mode` | `"static"` \| `"growth"` | `"static"`: a Data Centre's circle never changes size; land ownership is just "is a Data Centre here". `"growth"`: Data Centre circles grow/shrink over time based on same-team clusters and Activist/Lawyer blocking (see `update_growth_radii` in `src/gameplay.py`), and land is coloured per-team. |
| `sequence_mode` | `"facilitated"` \| `"automatic"` | Which top-level game flow runs - see **Sequence modes & music** below. |
| `stack_distance` | number > 0 | Max pixel distance between two visible cards for them to count as "stacked" (touching/interacting) with each other. |
| `smoothing_time` | number >= 0 | Seconds of recent marker-position history averaged together per card, to smooth out camera jitter. `0` disables smoothing. |
| `marker_timeout` | number > 0 | Seconds a card can go undetected before it's treated as no longer visible. |
| `scoring_interval` | number > 0 | Seconds between each scoring tick. |
| `target_fps` | number > 0 | Target frame rate for the main loop/display. |
| `radius_growth_rate` | number > 0 | Growth-mode only. Base px/second a single, isolated Data Centre's radius grows by. |
| `min_radius` | number > 0 | Growth-mode only. Floor a shrinking Data Centre's radius can never go below. |
| `cue_2_threshold` | 0 < number <= 100 | Map land-coverage percentage at which music switches from `cue_1` to `cue_2` (facilitated mode), or at which automatic mode's `end_1.wav` stinger triggers. Must be less than `cue_3_threshold`. |
| `cue_3_threshold` | 0 < number <= 100 | Coverage percentage for the `cue_2` → `cue_3` switch (facilitated), or the `end_2.wav` stinger (automatic). Must be less than `completion_percentage`. |
| `completion_percentage` | 0 < number <= 100 | Coverage percentage that ends the round: facilitated mode auto-pauses the game (and, in growth mode, awards the area bonus) at this point; automatic mode plays `end_final.wav` and enters its game-over state. |

`radius_growth_rate`/`min_radius` are required only when `mode` is
`"growth"`. `cue_2_threshold`, `cue_3_threshold`, and
`completion_percentage` are always required and must satisfy
`cue_2_threshold < cue_3_threshold < completion_percentage`.

### `colours`

| Field | Type | Meaning |
|---|---|---|
| `water_rgb`, `land_rgb` | `[r, g, b]` (0-255) | Base colours for water/land, used whenever team colours (below) aren't in effect. |
| `team_colours_enabled` | `true` / `false` / `null` | Whether a Data Centre's land renders in its owning team's `team_rgb` colour instead of the flat `land_rgb`. `null` (default) preserves the original behaviour: on in growth mode, off in static mode. `true`/`false` forces it on/off regardless of `gameplay.mode`. |
| `team_rgb` | list of `[r, g, b]` | Required (and validated) only when team colours will actually render under the resolution above. One colour per team, in team order (team 1 first); length must exactly equal `cards.num_teams`. |

### `audio.sfx`

Sound effects live in `sfx/*.wav`, named `<event_type>_<n>.wav` (e.g.
`lawyer_3.wav`); when a card of that type first becomes visible, a
random file for its event type plays. Event types map from card-type
letters via `CARD_TYPE_TO_SFX_EVENT` in `main.py`: `d`→`datacenter`,
`a`→`activist`, `l`→`lawyer`, `b`→`billionaire`, `p`→`president`.

| Field | Type | Meaning |
|---|---|---|
| `num_mixer_channels` | int | Total pygame mixer channels reserved. Must be large enough for every distinct priority tier plus one more for music (bumped up automatically if too small). |
| `default_priority` | int | Priority tier used for any event type not listed in `events`. |
| `default_volume` | 0.0-1.0 | Volume used for any event type not listed in `events`. |
| `events.<type>.priority` | int | Higher number = higher tier. Playing a sound stops any other currently-playing sfx whose tier is `<=` its own; higher tiers are left alone. |
| `events.<type>.volume` | 0.0-1.0 | Playback volume for that event type. |

### `audio.music`

Music lives in `music/*.wav` as fixed, literal filenames (not a
random pool like sfx): `cue_1.wav`, `cue_2.wav`, `cue_3.wav` (looping
cues), and `opening.wav`, `end_1.wav`, `end_2.wav`, `end_final.wav`
(one-shot stingers, played once, no loop). Music plays on its own
dedicated mixer channel, separate from every sfx priority tier, so it
is never stopped by an sfx playing - it only ducks (see below).

| Field | Type | Meaning |
|---|---|---|
| `volume` | `null` \| 0.0-1.0 | `null` (recommended): music's base volume auto-derives from the quietest configured `audio.sfx.events[*].volume`, so it never overpowers any sfx. A number pins an explicit volume instead. |
| `duck_multiplier` | 0.0 (exclusive)-1.0 | While any sfx is playing, music volume drops to `base_volume * duck_multiplier`. Default `0.7` (i.e. music drops to 70% of normal). |
| `duck_fade_in_seconds` | number >= 0 | Once the sfx finishes, how many seconds it takes for music to linearly fade back up to full volume. Default `0.2` (200ms - fast and subtle). `0` restores instantly. |

### `debug`

| Field | Type | Meaning |
|---|---|---|
| `show_marker_positions` | bool | Draw a small circle at every visible card's tracked position, plus each Data Centre's live radius, directly on the projected output. |
| `show_camera_preview` | bool | Open a separate OpenCV window showing the raw camera feed with detected markers outlined - handy for aiming/focusing the camera, not part of the projected game view. |

## Sequence modes & music

`gameplay.sequence_mode` picks one of two top-level flows. Both use
the exact same `cue_2_threshold` / `cue_3_threshold` /
`completion_percentage` values from `gameplay`, measured as the
percentage of the map's pixels currently land (see
`compute_coverage_percentage` in `src/gameplay.py`).

### `facilitated` (default)

The classic flow: the game runs continuously from the moment it
starts. `SPACE` pauses/resumes it manually at any time; `R` resets
scores and card ownership without changing anything else. Music
tracks coverage continuously and switches instantly (no crossfade)
between:

- below `cue_2_threshold`: `cue_1.wav` loops
- between `cue_2_threshold` and `cue_3_threshold`: `cue_2.wav` loops
- above `cue_3_threshold`: `cue_3.wav` loops

Once coverage reaches `completion_percentage`, the game automatically
pauses (identical to a manual SPACE pause - it can be resumed) so
scores can be read out. In growth mode, this is also the moment the
final area bonus (each team's currently-owned pixel area, added to
their score once) is awarded.

### `automatic`

A scripted, self-driving flow intended to run without a facilitator
touching pause/resume mid-round:

1. **Pre-game**: on startup, the map/score HUD is visible with
   "Everything's Computer" centered on top. Card tracking runs, but
   scoring and (in growth mode) Data Centre growth are frozen.
2. Press `SPACE` → **Opening**: `opening.wav` plays once. Still
   frozen (no scoring, no growth) - cards are tracked and drawn at
   their current radius, but nothing changes size or counts up.
3. When `opening.wav` finishes → **Running (cue_1)**: growth and
   scoring resume normally, `cue_1.wav` loops.
4. At `cue_2_threshold` coverage → frozen again while `end_1.wav`
   plays once.
5. On completion → **Running (cue_2)**: resumes, `cue_2.wav` loops.
6. At `cue_3_threshold` coverage → frozen while `end_2.wav` plays.
7. On completion → **Running (cue_3)**: resumes, `cue_3.wav` loops.
8. At `completion_percentage` coverage → **Game over**: frozen, the
   growth-mode area bonus is awarded, `end_final.wav` plays once,
   and the game then stays paused - this is a terminal state until
   reset.

During any "Running" phase, `SPACE` still works as a manual
pause/resume toggle (mirroring facilitated mode - growth continues
while manually paused, only scoring stops). Outside of the running
phases, `SPACE` only does one thing - starting the game from the
pre-game screen; pressed during the opening/end_1/end_2/game-over
frozen states, it's a no-op, since those only advance automatically,
never manually. Card sfx (Data Centre/Activist/Lawyer/Billionaire/
President sounds) are suppressed during every frozen state (pre-game,
opening, end_1, end_2, game over) and play normally otherwise,
including while manually paused.

`R` sends the game back to the pre-game screen from any state,
stopping whatever music was playing.
