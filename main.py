import cv2
import numpy as np
from collections import deque
import time
import threading

import pygame

from src import config as config_loader
from src import camera
from src.audio_manager import audio
from src.card_assignments import build_card_assignments
from src.gameplay import (
    MapEngine,
    find_stacks,
    apply_billionaire_steals,
    apply_president_claims,
    update_growth_radii,
    rebuild_map,
    score_visible_cards,
    check_area_bonus,
    compute_coverage_percentage,
)
from src.music_director import select_cue
from src.sequence import AutomaticSequenceController


# ============================================================
# CONFIG
# ============================================================

cfg = config_loader.load_config()

profile = cfg.active_projector_profile()

PROJECTOR_WIDTH = profile["width"]
PROJECTOR_HEIGHT = profile["height"]
CIRCLE_RADIUS = profile["data_centre_radius"]

print(f"Using projector profile: {profile['name']}")

camera_cfg = cfg.raw["camera"]

CALIBRATION_IDS = camera_cfg["calibration_ids"]
HOMOGRAPHY_RECOMPUTE_EVERY_FRAME = camera_cfg.get(
    "homography_recompute_every_frame",
    False
)

cards_cfg = cfg.raw["cards"]

NUM_TEAMS = cards_cfg["num_teams"]

gameplay_cfg = cfg.raw["gameplay"]

GAME_MODE = gameplay_cfg.get("mode", "static")
SEQUENCE_MODE = gameplay_cfg.get("sequence_mode", "facilitated")
STACK_DISTANCE = gameplay_cfg["stack_distance"]
SMOOTHING_TIME = gameplay_cfg["smoothing_time"]
MARKER_TIMEOUT = gameplay_cfg["marker_timeout"]
SCORING_INTERVAL = gameplay_cfg["scoring_interval"]
TARGET_FPS = gameplay_cfg["target_fps"]
RADIUS_GROWTH_RATE = gameplay_cfg["radius_growth_rate"]
MIN_RADIUS = gameplay_cfg["min_radius"]
CUE_2_THRESHOLD = gameplay_cfg["cue_2_threshold"]
CUE_3_THRESHOLD = gameplay_cfg["cue_3_threshold"]
COMPLETION_PERCENTAGE = gameplay_cfg["completion_percentage"]

colours_cfg = cfg.raw["colours"]

# RGB - consumed directly by pygame (the final map image is
# converted straight to a pygame surface, never through cv2.imshow).
WATER_COLOUR = colours_cfg["water_rgb"]
LAND_COLOUR = colours_cfg["land_rgb"]
TEAM_COLOURS = colours_cfg.get("team_rgb", [])

debug_cfg = cfg.raw["debug"]

DEBUG_SHOW_MARKER_POSITIONS = debug_cfg["show_marker_positions"]
DEBUG_SHOW_CAMERA_PREVIEW = debug_cfg["show_camera_preview"]

audio_sfx_cfg = cfg.raw["audio"]["sfx"]
audio_music_cfg = cfg.raw["audio"].get("music", {})

audio.configure(
    event_config=audio_sfx_cfg["events"],
    num_mixer_channels=audio_sfx_cfg["num_mixer_channels"],
    default_priority=audio_sfx_cfg["default_priority"],
    default_volume=audio_sfx_cfg["default_volume"],
    music_volume_override=audio_music_cfg.get("volume"),
    duck_multiplier=audio_music_cfg.get("duck_multiplier"),
    duck_fade_in_seconds=audio_music_cfg.get("duck_fade_in_seconds"),
)


# ============================================================
# CARD TYPE -> SFX EVENT
# ============================================================

CARD_TYPE_TO_SFX_EVENT = {
    "d": "datacenter",
    "a": "activist",
    "l": "lawyer",
    "b": "billionaire",
    "p": "president",
}


# ============================================================
# GENERATE CARD ASSIGNMENTS
# ============================================================

CARD_ASSIGNMENTS = build_card_assignments(cards_cfg)

INTERACTIVE_IDS = list(CARD_ASSIGNMENTS.keys())


# ============================================================
# PRINT CARD ASSIGNMENTS
# ============================================================

print("\nCard assignments:")
print("-----------------")

for marker_id, card in CARD_ASSIGNMENTS.items():

    print(
        f"ArUco {marker_id:3d} "
        f"-> Team {card['team']} "
        f"Card {card['type']}"
    )

print()
print(f"Total cards: {len(CARD_ASSIGNMENTS)}")
print(f"Game mode: {GAME_MODE}")
print()


# ============================================================
# CARD TRACKING STATE
# ============================================================

def make_card_state(marker_id, data):

    return {
        "id": marker_id,
        "team": data["team"],
        "type": data["type"],
        "position": None,
        "last_seen": None,
        "visible": False,
        "owner_team": data["team"],
        "locked": False,
        "radius": CIRCLE_RADIUS,
    }


cards = {
    marker_id: make_card_state(marker_id, data)
    for marker_id, data in CARD_ASSIGNMENTS.items()
}


# ============================================================
# POSITION HISTORIES
# ============================================================

position_histories = {
    marker_id: deque()
    for marker_id in INTERACTIVE_IDS
}


# ============================================================
# SCORES
# ============================================================

scores = {
    team: 0
    for team in range(1, NUM_TEAMS + 1)
}

bonus_awarded = False
completion_pause_triggered = False  # facilitated mode only


def reset_game_state():

    global bonus_awarded
    global completion_pause_triggered

    for team in range(1, NUM_TEAMS + 1):
        scores[team] = 0

    for marker_id, card in cards.items():

        card["owner_team"] = card["team"]
        card["locked"] = False
        card["radius"] = CIRCLE_RADIUS

    bonus_awarded = False
    completion_pause_triggered = False


# ============================================================
# GAME STATE
# ============================================================

game_paused = False

# facilitated mode: which cue is currently looping, so we only call
# audio.play_music() on an actual change, not every frame.
current_music_cue = None

sequence_controller = (
    AutomaticSequenceController(
        CUE_2_THRESHOLD, CUE_3_THRESHOLD, COMPLETION_PERCENTAGE
    )
    if SEQUENCE_MODE == "automatic"
    else None
)

next_scoring_time = (
    time.time()
    + SCORING_INTERVAL
)

last_frame_time = time.time()


# ============================================================
# ARUCO SETUP
# ============================================================

aruco = cv2.aruco

aruco_dictionary_name = camera_cfg["aruco_dictionary"]

try:
    aruco_dictionary_id = getattr(aruco, aruco_dictionary_name)

except AttributeError:

    print(
        f"Unknown camera.aruco_dictionary {aruco_dictionary_name!r} "
        f"(expected something like \"DICT_6X6_250\")"
    )
    exit(1)

dictionary = aruco.getPredefinedDictionary(
    aruco_dictionary_id
)

parameters = aruco.DetectorParameters()

detector = aruco.ArucoDetector(
    dictionary,
    parameters
)


# ============================================================
# CAMERA
# ============================================================

try:
    cap = camera.open_camera(camera_cfg)

except camera.CameraError as exc:

    print(f"Could not connect to camera: {exc}")
    exit(1)

print(f"Connected to camera (source={camera_cfg.get('source', 'phone')})")


# ============================================================
# LATEST-FRAME CAMERA THREAD
# ============================================================

latest_frame = None
frame_lock = threading.Lock()
camera_running = True
camera_connected = True

CAMERA_FAILURE_BACKOFF_START = 0.01
CAMERA_FAILURE_BACKOFF_MAX = 1.0
CAMERA_FAILURE_DISCONNECT_THRESHOLD = 30


def camera_reader():

    global latest_frame
    global camera_running
    global camera_connected

    backoff = CAMERA_FAILURE_BACKOFF_START
    consecutive_failures = 0

    while camera_running:

        ret, frame = cap.read()

        if not ret:

            consecutive_failures += 1

            if consecutive_failures >= CAMERA_FAILURE_DISCONNECT_THRESHOLD:

                with frame_lock:
                    camera_connected = False

            print("Camera frame read failed")

            time.sleep(backoff)

            backoff = min(CAMERA_FAILURE_BACKOFF_MAX, backoff * 2)

            continue

        consecutive_failures = 0
        backoff = CAMERA_FAILURE_BACKOFF_START

        # Replace the old frame immediately.
        # We NEVER build up a queue of frames.
        with frame_lock:
            latest_frame = frame
            camera_connected = True


camera_thread = threading.Thread(
    target=camera_reader,
    daemon=True
)

camera_thread.start()


def apply_pending_music_command():
    """
    Pop and apply sequence_controller's pending music command, if any.
    A `name` of None means "stop the current track". No-op if nothing
    is pending (already consumed this frame).
    """

    music_command = sequence_controller.pop_pending_music_command()

    if music_command is None:
        return

    name, loop = music_command

    if name is None:
        audio.stop_music()
    else:
        audio.play_music(name, loop=loop)


def resync_scoring_deadline(now):
    """
    Fast-forward next_scoring_time past `now` in whole SCORING_INTERVAL
    steps, without awarding points for any skipped ticks.

    Used when resuming from a manual pause: the music track is never
    stopped by a pause, so its chimes keep sounding on their original
    schedule. Snapping the deadline to "now + SCORING_INTERVAL" would
    pull the on-screen countdown out of phase with those chimes: this
    keeps it phase-locked to whenever the track actually started
    instead, while still avoiding a burst of catch-up scoring ticks if
    the pause lasted longer than one interval.
    """

    global next_scoring_time

    while next_scoring_time <= now:
        next_scoring_time += SCORING_INTERVAL


def get_latest_frame():

    global latest_frame

    with frame_lock:

        if latest_frame is None:
            return None

        # Copy so the camera thread can immediately
        # replace the frame while we process this one.
        return latest_frame.copy()


def is_camera_connected():

    with frame_lock:
        return camera_connected


# ============================================================
# CAMERA PREVIEW WINDOW (debug only)
# ============================================================

if DEBUG_SHOW_CAMERA_PREVIEW:

    cv2.namedWindow(
        "Camera",
        cv2.WINDOW_NORMAL
    )


# ============================================================
# HOMOGRAPHY
# ============================================================

H = None

# Marker IDs we've already warned about once (neither a calibration ID
# nor a card ID) - printed once each rather than every frame, since a
# stray/misprinted marker would otherwise spam the console.
unrecognized_marker_ids_warned = set()


def marker_center(corners):

    points = corners.reshape(4, 2)

    x = np.mean(points[:, 0])
    y = np.mean(points[:, 1])

    return np.array(
        [x, y],
        dtype=np.float32
    )


def calculate_homography(corners, ids):

    camera_points = {}

    for marker_id, marker_corners in zip(
        ids,
        corners
    ):

        marker_id = int(marker_id)

        if marker_id in CALIBRATION_IDS:

            camera_points[marker_id] = marker_center(
                marker_corners
            )

    if not all(
        marker_id in camera_points
        for marker_id in CALIBRATION_IDS
    ):
        return None

    src = np.array([
        camera_points[CALIBRATION_IDS[0]],
        camera_points[CALIBRATION_IDS[1]],
        camera_points[CALIBRATION_IDS[2]],
        camera_points[CALIBRATION_IDS[3]],
    ], dtype=np.float32)

    dst = np.array([
        [0, 0],
        [PROJECTOR_WIDTH - 1, 0],
        [0, PROJECTOR_HEIGHT - 1],
        [PROJECTOR_WIDTH - 1, PROJECTOR_HEIGHT - 1],
    ], dtype=np.float32)

    homography, _ = cv2.findHomography(
        src,
        dst
    )

    return homography


def transform_point(point, homography):

    point = np.array(
        [[point]],
        dtype=np.float32
    )

    transformed = cv2.perspectiveTransform(
        point,
        homography
    )

    x, y = transformed[0][0]

    return int(x), int(y)


# ============================================================
# PYGAME
# ============================================================

pygame.init()
pygame.font.init()

pygame.display.set_caption("Projected Board Game")

screen = pygame.display.set_mode(
    (PROJECTOR_WIDTH, PROJECTOR_HEIGHT)
)

clock = pygame.time.Clock()

map_engine = MapEngine(
    PROJECTOR_WIDTH,
    PROJECTOR_HEIGHT,
    WATER_COLOUR,
    LAND_COLOUR,
    mode=GAME_MODE,
    team_colours=TEAM_COLOURS,
)

timer_font = pygame.font.SysFont(None, 48)
score_font = pygame.font.SysFont(None, 36)
pregame_font = pygame.font.SysFont(None, 80)


# ============================================================
# MAIN LOOP
# ============================================================

running = True

while running:

    # ========================================================
    # GET NEWEST AVAILABLE FRAME
    # ========================================================

    frame = get_latest_frame()

    if frame is None:

        time.sleep(0.001)
        continue

    current_time = time.time()

    dt = current_time - last_frame_time
    last_frame_time = current_time

    audio.update(dt)

    # ========================================================
    # INPUT
    # ========================================================

    for event in pygame.event.get():

        if event.type == pygame.QUIT:

            running = False

        elif event.type == pygame.KEYDOWN:

            if event.key == pygame.K_q:

                running = False

            elif event.key == pygame.K_SPACE:

                if SEQUENCE_MODE == "automatic":

                    sequence_controller.on_space_pressed()

                    if sequence_controller.should_score:

                        # Resuming, not (re-)starting the track - stay
                        # phase-locked to its original start time.
                        resync_scoring_deadline(time.time())

                    print(f"Automatic mode: SPACE ({sequence_controller.state})")

                elif game_paused:

                    game_paused = False

                    # Resuming, not (re-)starting the track - stay
                    # phase-locked to its original start time.
                    resync_scoring_deadline(time.time())

                    print("Game resumed")

                else:

                    game_paused = True

                    print("Game paused")

            elif event.key == pygame.K_c:

                H = None

                print("Recalibrating - show all calibration markers to the camera")

            elif event.key == pygame.K_r:

                reset_game_state()

                next_scoring_time = (
                    time.time()
                    + SCORING_INTERVAL
                )

                if SEQUENCE_MODE == "automatic":

                    sequence_controller.on_reset_pressed()
                    audio.stop_music()

                else:

                    # Force the facilitated cue-selection block below to
                    # treat this as a fresh track start (not just a
                    # continuation) so the timer resync stays tied to
                    # when the music actually restarts.
                    audio.stop_music()
                    current_music_cue = None

                print("Game reset")

    if not running:
        break

    # ========================================================
    # DETECT ARUCO MARKERS
    # ========================================================

    corners, ids, rejected = detector.detectMarkers(frame)

    if ids is not None:

        aruco.drawDetectedMarkers(
            frame,
            corners,
            ids
        )

        # ----------------------------------------------------
        # HOMOGRAPHY
        # ----------------------------------------------------

        should_recompute = (
            H is None
            or HOMOGRAPHY_RECOMPUTE_EVERY_FRAME
        )

        if should_recompute:

            new_H = calculate_homography(corners, ids)

            if new_H is not None:

                if H is None:
                    print("Calibration complete")

                H = new_H

        # ----------------------------------------------------
        # TRACK CARDS
        # ----------------------------------------------------

        if H is not None:

            for marker_id, marker_corners in zip(ids, corners):

                marker_id = int(marker_id)

                if marker_id in CALIBRATION_IDS:
                    continue

                if marker_id not in cards:

                    if marker_id not in unrecognized_marker_ids_warned:

                        unrecognized_marker_ids_warned.add(marker_id)

                        print(
                            f"ArUco {marker_id} detected but is not a "
                            f"calibration ID or an assigned card ID - "
                            f"it will never affect the game "
                            f"(see Card assignments above)"
                        )

                    continue

                card = cards[marker_id]

                was_visible = card["visible"]

                camera_position = marker_center(marker_corners)

                x, y = transform_point(camera_position, H)

                history = position_histories[marker_id]

                history.append((current_time, x, y))

                while (
                    history
                    and current_time - history[0][0]
                    > SMOOTHING_TIME
                ):
                    history.popleft()

                avg_x = int(np.mean([p[1] for p in history]))
                avg_y = int(np.mean([p[2] for p in history]))

                card["position"] = (avg_x, avg_y)
                card["last_seen"] = current_time
                card["visible"] = True

                should_play_sfx = (
                    sequence_controller.should_play_sfx
                    if SEQUENCE_MODE == "automatic"
                    else True
                )

                if not was_visible and should_play_sfx:

                    audio.play(
                        CARD_TYPE_TO_SFX_EVENT.get(
                            card["type"],
                            card["type"]
                        )
                    )

    # ========================================================
    # UPDATE CARD VISIBILITY
    # ========================================================

    for marker_id, card in cards.items():

        if card["last_seen"] is None:

            card["visible"] = False
            continue

        if (
            current_time - card["last_seen"]
            > MARKER_TIMEOUT
        ):

            card["visible"] = False

    # ========================================================
    # APPLY GAME RULES
    # ========================================================

    stacks = find_stacks(cards, STACK_DISTANCE)

    should_grow = (
        sequence_controller.should_grow
        if SEQUENCE_MODE == "automatic"
        else True
    )

    if GAME_MODE == "growth" and should_grow:
        update_growth_radii(dt, stacks, cards, RADIUS_GROWTH_RATE, MIN_RADIUS)

    apply_billionaire_steals(stacks)

    visible_data_centres = [
        card
        for card in cards.values()
        if card["type"] == "d" and card["visible"]
    ]

    apply_president_claims(stacks, visible_data_centres, GAME_MODE)

    # ========================================================
    # SCORING
    # ========================================================

    should_score = (
        sequence_controller.should_score
        if SEQUENCE_MODE == "automatic"
        else not game_paused
    )

    if should_score:

        while current_time >= next_scoring_time:

            points_awarded = score_visible_cards(
                cards, scores, NUM_TEAMS, GAME_MODE, stacks
            )

            print("\n--- SCORING ---")

            for team in range(1, NUM_TEAMS + 1):

                print(
                    f"Team {team}: "
                    f"+{points_awarded[team]} "
                    f"(total {scores[team]})"
                )

            next_scoring_time += SCORING_INTERVAL

    # ========================================================
    # REBUILD + RENDER MAP
    # ========================================================

    rebuild_map(map_engine, stacks)

    coverage_percentage = compute_coverage_percentage(map_engine.land_mask)

    if GAME_MODE == "growth":
        bonus_awarded = check_area_bonus(
            map_engine, scores, NUM_TEAMS, bonus_awarded,
            threshold_percentage=COMPLETION_PERCENTAGE,
        )

    map_surface = map_engine.render()

    screen.blit(map_surface, (0, 0))

    # ========================================================
    # SEQUENCE MODE / MUSIC
    # ========================================================

    if SEQUENCE_MODE == "automatic":

        was_running = sequence_controller.should_grow

        # Apply any transition that happened elsewhere this frame (e.g.
        # SPACE/R in the INPUT section above) BEFORE checking whether
        # the current track has finished - otherwise a track that was
        # only just started this same frame would still read as "not
        # playing yet" and immediately skip its own stinger state.
        apply_pending_music_command()

        if (
            sequence_controller.waiting_for_stinger
            and not audio.is_music_playing()
        ):
            sequence_controller.on_stinger_finished()

        sequence_controller.update(coverage_percentage)

        apply_pending_music_command()

        if not was_running and sequence_controller.should_grow:

            # A running phase was just (re-)entered after a freeze -
            # don't let next_scoring_time have gone stale, or scoring
            # would fire a burst of catch-up ticks the instant it resumes.
            next_scoring_time = current_time + SCORING_INTERVAL

    else:

        target_cue = select_cue(
            coverage_percentage, CUE_2_THRESHOLD, CUE_3_THRESHOLD
        )

        if target_cue != current_music_cue:

            audio.play_music(target_cue, loop=True)
            current_music_cue = target_cue

            # The new cue restarts from sample 0 this exact frame -
            # resync the countdown to it so it starts exactly when the
            # music starts, instead of drifting from whenever the
            # *previous* cue (or the script itself) happened to start.
            next_scoring_time = current_time + SCORING_INTERVAL

        if (
            not completion_pause_triggered
            and coverage_percentage >= COMPLETION_PERCENTAGE
        ):

            game_paused = True
            completion_pause_triggered = True

            print("Completion threshold reached - game auto-paused")

    # ========================================================
    # DEBUG: DRAW DETECTED CARD POSITIONS
    # ========================================================

    if DEBUG_SHOW_MARKER_POSITIONS:

        for marker_id, card in cards.items():

            if not card["visible"]:
                continue

            if card["position"] is None:
                continue

            x, y = card["position"]

            if card["type"] == "d":

                pygame.draw.circle(
                    screen, (255, 255, 255), (x, y), 8
                )

                pygame.draw.circle(
                    screen, (255, 255, 255), (x, y), int(card["radius"]), 2
                )

            elif card["type"] == "a":

                pygame.draw.circle(
                    screen, (255, 255, 0), (x, y), 6
                )

            elif card["type"] == "l":

                pygame.draw.circle(
                    screen, (255, 0, 255), (x, y), 6
                )

    # ========================================================
    # TIMER / SCORE TEXT
    # ========================================================

    if SEQUENCE_MODE == "automatic" and sequence_controller.show_pregame_text:

        pregame_surface = pregame_font.render(
            "Everything's Computer", True, (255, 255, 255)
        )

        screen.blit(
            pregame_surface,
            (
                (PROJECTOR_WIDTH - pregame_surface.get_width()) // 2,
                (PROJECTOR_HEIGHT - pregame_surface.get_height()) // 2,
            )
        )

    else:

        is_paused = (
            sequence_controller.show_paused_text
            if SEQUENCE_MODE == "automatic"
            else game_paused
        )

        if is_paused:

            timer_text = "PAUSED"

        else:

            time_remaining = max(0, next_scoring_time - current_time)

            timer_text = f"{time_remaining:.1f}"

        timer_surface = timer_font.render(
            timer_text, True, (255, 255, 255)
        )

        screen.blit(timer_surface, (30, 20))

    y_position = 80

    for team in range(1, NUM_TEAMS + 1):

        score_surface = score_font.render(
            f"Team {team}: {scores[team]}",
            True,
            (255, 255, 255)
        )

        screen.blit(score_surface, (30, y_position))

        y_position += 40

    if not is_camera_connected():

        disconnected_surface = timer_font.render(
            "CAMERA DISCONNECTED", True, (255, 60, 60)
        )

        screen.blit(
            disconnected_surface,
            (
                (PROJECTOR_WIDTH - disconnected_surface.get_width()) // 2,
                20
            )
        )

    elif H is None:

        # No card is ever tracked (so no Data Centre radius, or
        # anything else, is ever drawn) until all of
        # camera.calibration_ids have been seen in the same frame -
        # make that state visible instead of silently doing nothing.

        calibrating_surface = timer_font.render(
            "WAITING FOR CALIBRATION", True, (255, 200, 60)
        )

        screen.blit(
            calibrating_surface,
            (
                (PROJECTOR_WIDTH - calibrating_surface.get_width()) // 2,
                20
            )
        )

    # ========================================================
    # FLIP DISPLAY / CAMERA PREVIEW
    # ========================================================

    pygame.display.flip()

    if DEBUG_SHOW_CAMERA_PREVIEW:

        cv2.imshow("Camera", frame)
        cv2.waitKey(1)

    clock.tick(TARGET_FPS)


# ============================================================
# CLEANUP
# ============================================================

camera_running = False

camera_thread.join(timeout=1)

cap.release()

pygame.quit()

cv2.destroyAllWindows()
