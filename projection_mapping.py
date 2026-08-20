import cv2
import numpy as np
from collections import deque
import time
import threading

import pygame
import audio_manager

# ============================================================
# CONFIGURATION
# ============================================================

PHONE_IP = "10.34.201.200"
VIDEO_URL = f"http://{PHONE_IP}:8080/video"

PROJECTOR_WIDTH = 1280
PROJECTOR_HEIGHT = 720

CALIBRATION_IDS = [0, 1, 2, 3]

NUM_TEAMS = 4

CARDS_PER_TEAM = {
    "d": 20,
    "a": 10,
    "l": 10,
    "b": 3,
    "p": 1,
}

<<<<<<< HEAD
# ------------------------------------------------------------
# Map this script's short card-type codes to the sfx event_type
# names used by audio_manager (which match sfx/ filename prefixes).
# ------------------------------------------------------------
CARD_TYPE_TO_SFX_EVENT = {
    "d": "datacenter",
    "a": "activist",
    "l": "lawyer",
    "b": "billionaire",
    "p": "president",
}

# First ArUco ID used for cards
=======
>>>>>>> ff94f56a5e9c2f33587ab69e9180e78cb64d91f3
START_CARD_ID = 4

CIRCLE_RADIUS = 80

# Lower values = less latency
SMOOTHING_TIME = 0.05

# Lower values = less delay when a marker disappears
MARKER_TIMEOUT = 0.15

SCORING_INTERVAL = 10.0


# ============================================================
# GENERATE CARD ASSIGNMENTS
# ============================================================

CARD_ASSIGNMENTS = {}

marker_id = START_CARD_ID

for team in range(1, NUM_TEAMS + 1):

    for card_type, quantity in CARDS_PER_TEAM.items():

        for _ in range(quantity):

            CARD_ASSIGNMENTS[marker_id] = {
                "team": team,
                "type": card_type,
            }

            marker_id += 1


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
print()


# ============================================================
# CARD TRACKING STATE
# ============================================================

cards = {
    marker_id: {
        "team": data["team"],
        "type": data["type"],
        "position": None,
        "last_seen": None,
        "visible": False,
    }
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


# ============================================================
# GAME STATE
# ============================================================

game_paused = False

next_scoring_time = (
    time.time()
    + SCORING_INTERVAL
)


# ============================================================
# ARUCO SETUP
# ============================================================

aruco = cv2.aruco

dictionary = aruco.getPredefinedDictionary(
    aruco.DICT_6X6_250
)

parameters = aruco.DetectorParameters()

detector = aruco.ArucoDetector(
    dictionary,
    parameters
)


# ============================================================
# CAMERA
# ============================================================

cap = cv2.VideoCapture(VIDEO_URL)

if not cap.isOpened():
    print("Could not connect to camera")
    exit()

print("Connected to camera")


# ============================================================
# LATEST-FRAME CAMERA THREAD
# ============================================================

latest_frame = None
frame_lock = threading.Lock()
camera_running = True


def camera_reader():

    global latest_frame
    global camera_running

    while camera_running:

        ret, frame = cap.read()

        if not ret:
            print("Camera frame read failed")
            time.sleep(0.01)
            continue

        # Replace the old frame immediately.
        # We NEVER build up a queue of frames.
        with frame_lock:
            latest_frame = frame


camera_thread = threading.Thread(
    target=camera_reader,
    daemon=True
)

camera_thread.start()


# ============================================================
# GET NEWEST FRAME
# ============================================================

def get_latest_frame():

    global latest_frame

    with frame_lock:

        if latest_frame is None:
            return None

        # Copy so the camera thread can immediately
        # replace the frame while we process this one.
        return latest_frame.copy()


# ============================================================
# PROJECTOR WINDOW
# ============================================================

cv2.namedWindow(
    "Projection",
    cv2.WINDOW_NORMAL
)

cv2.resizeWindow(
    "Projection",
    PROJECTOR_WIDTH,
    PROJECTOR_HEIGHT
)


# ============================================================
# HOMOGRAPHY
# ============================================================

H = None


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
        camera_points[0],
        camera_points[1],
        camera_points[2],
        camera_points[3],
    ], dtype=np.float32)

    dst = np.array([
        [0, 0],
        [PROJECTOR_WIDTH - 1, 0],
        [0, PROJECTOR_HEIGHT - 1],
        [PROJECTOR_WIDTH - 1, PROJECTOR_HEIGHT - 1],
    ], dtype=np.float32)

    H, _ = cv2.findHomography(
        src,
        dst
    )

    return H


def transform_point(point, H):

    point = np.array(
        [[point]],
        dtype=np.float32
    )

    transformed = cv2.perspectiveTransform(
        point,
        H
    )

    x, y = transformed[0][0]

    return int(x), int(y)


# ============================================================
# SCORING
# ============================================================

def score_visible_cards():

    points_awarded = {
        team: 0
        for team in range(1, NUM_TEAMS + 1)
    }

    for card in cards.values():

        if card["type"] == "a":
            continue

        if not card["visible"]:
            continue

        team = card["team"]

        scores[team] += 1
        points_awarded[team] += 1

    return points_awarded


# ============================================================
# MAIN LOOP
# ============================================================

while True:

    # ========================================================
    # GET NEWEST AVAILABLE FRAME
    # ========================================================

    frame = get_latest_frame()

    if frame is None:

        time.sleep(0.001)
        continue

    current_time = time.time()

    # ========================================================
    # DETECT ARUCO MARKERS
    # ========================================================

    corners, ids, rejected = detector.detectMarkers(
        frame
    )

    # ========================================================
    # BLUE BACKGROUND
    # ========================================================

    projection = np.zeros(
        (
            PROJECTOR_HEIGHT,
            PROJECTOR_WIDTH,
            3
        ),
        dtype=np.uint8
    )

    projection[:] = (255, 0, 0)

    # ========================================================
    # PROCESS DETECTIONS
    # ========================================================

    if ids is not None:

        aruco.drawDetectedMarkers(
            frame,
            corners,
            ids
        )

        # ----------------------------------------------------
        # ONLY CALCULATE HOMOGRAPHY UNTIL IT EXISTS
        # ----------------------------------------------------

        if H is None:

            new_H = calculate_homography(
                corners,
                ids
            )

            if new_H is not None:
                H = new_H
                print("Calibration complete")

        # ----------------------------------------------------
        # TRACK CARDS
        # ----------------------------------------------------

        if H is not None:

            for marker_id, marker_corners in zip(
                ids,
                corners
            ):

                marker_id = int(marker_id)

                if marker_id not in cards:
                    continue

                card = cards[marker_id]

<<<<<<< HEAD
                was_visible = card["visible"]

                # Camera position
=======
>>>>>>> ff94f56a5e9c2f33587ab69e9180e78cb64d91f3
                camera_position = marker_center(
                    marker_corners
                )

                x, y = transform_point(
                    camera_position,
                    H
                )

                history = position_histories[
                    marker_id
                ]

                history.append(
                    (
                        current_time,
                        x,
                        y
                    )
                )

                while (
                    history
                    and current_time - history[0][0]
                    > SMOOTHING_TIME
                ):
                    history.popleft()

                avg_x = int(
                    np.mean([
                        position[1]
                        for position in history
                    ])
                )

                avg_y = int(
                    np.mean([
                        position[2]
                        for position in history
                    ])
                )

                card["position"] = (
                    avg_x,
                    avg_y
                )

                card["last_seen"] = current_time
                card["visible"] = True

                if not was_visible:

                    audio_manager.audio.play(
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
    # SCORING
    # ========================================================

    if not game_paused:

        while current_time >= next_scoring_time:

            points_awarded = score_visible_cards()

            print("\n--- SCORING ---")

            for team in range(1, NUM_TEAMS + 1):

                print(
                    f"Team {team}: "
                    f"+{points_awarded[team]} "
                    f"(total {scores[team]})"
                )

            next_scoring_time += SCORING_INTERVAL

    # ========================================================
    # DRAW CARDS
    # ========================================================

    if H is not None:

        for marker_id, card in cards.items():

            if not card["visible"]:
                continue

            if card["type"] == "a":
                continue

            position = card["position"]

            if position is None:
                continue

            x, y = position

            cv2.circle(
                projection,
                (x, y),
                CIRCLE_RADIUS,
                (0, 0, 0),
                -1
            )

    # ========================================================
    # TIMER
    # ========================================================

    if game_paused:

        timer_text = "PAUSED"

    else:

        time_remaining = max(
            0,
            next_scoring_time - current_time
        )

        timer_text = f"{time_remaining:.1f}"

    cv2.putText(
        projection,
        timer_text,
        (30, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5,
        (255, 255, 255),
        3,
        cv2.LINE_AA
    )

    # ========================================================
    # DISPLAY SCORES
    # ========================================================

    y_position = 110

    for team in range(1, NUM_TEAMS + 1):

        text = (
            f"Team {team}: "
            f"{scores[team]}"
        )

        cv2.putText(
            projection,
            text,
            (30, y_position),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        y_position += 45

    # ========================================================
    # CAMERA PREVIEW
    # ========================================================

    cv2.imshow(
        "Camera",
        frame
    )

    # ========================================================
    # PROJECTOR
    # ========================================================

    cv2.imshow(
        "Projection",
        projection
    )

    # ========================================================
    # KEYBOARD
    # ========================================================

    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):
        break

    elif key == ord(" "):

        if game_paused:

            game_paused = False

            next_scoring_time = (
                time.time()
                + SCORING_INTERVAL
            )

            print("Game resumed")

        else:

            game_paused = True

            print("Game paused")

    elif key == ord("r"):

        for team in range(1, NUM_TEAMS + 1):
            scores[team] = 0

        next_scoring_time = (
            time.time()
            + SCORING_INTERVAL
        )

        print("Scores reset")


# ============================================================
# CLEANUP
# ============================================================

camera_running = False

camera_thread.join(timeout=1)

cap.release()

cv2.destroyAllWindows()