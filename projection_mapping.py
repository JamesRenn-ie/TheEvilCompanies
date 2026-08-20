import cv2
import numpy as np
from collections import deque
import time

# ============================================================
# CONFIGURATION
# ============================================================

PHONE_IP = "10.34.201.200"
VIDEO_URL = f"http://{PHONE_IP}:8080/video"

# Projector resolution
PROJECTOR_WIDTH = 1280
PROJECTOR_HEIGHT = 720

# Calibration marker IDs
CALIBRATION_IDS = [0, 1, 2, 3]

# ============================================================
# CARD CONFIGURATION
# ============================================================

NUM_TEAMS = 4

# Number of each card type PER TEAM.
#
# Change these values to change the number of cards.
#
# d = 10 per team
# a = 5 per team
# l = 5 per team
# b = 2 per team
# p = 2 per team
#
CARDS_PER_TEAM = {
    "d": 10,
    "a": 5,
    "l": 5,
    "b": 2,
    "p": 2,
}

# First ArUco ID used for cards.
# 0, 1, 2, 3 are reserved for calibration.
START_CARD_ID = 4

# Circle radius for cards
CIRCLE_RADIUS = 80

# Position smoothing
SMOOTHING_TIME = 0.1  # seconds

# How long to keep a card visible after detection is lost
MARKER_TIMEOUT = 0.5  # seconds


# ============================================================
# GENERATE CARD ASSIGNMENTS
# ============================================================

# Each physical ArUco marker gets assigned:
#
#   team
#   card type
#
# Example:
#
#   ArUco 4  -> Team 1, card d
#   ArUco 5  -> Team 1, card d
#   ...
#   ArUco 14 -> Team 1, card a
#
# The IDs are generated automatically from the configuration.

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


# All interactive marker IDs
INTERACTIVE_IDS = list(CARD_ASSIGNMENTS.keys())

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
    """
    Get the centre of an ArUco marker.
    """

    points = corners.reshape(4, 2)

    x = np.mean(points[:, 0])
    y = np.mean(points[:, 1])

    return np.array(
        [x, y],
        dtype=np.float32
    )


def calculate_homography(corners, ids):
    """
    Find the four calibration markers and calculate
    camera -> projector transformation.
    """

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

    # Need all four calibration markers
    if not all(
        marker_id in camera_points
        for marker_id in CALIBRATION_IDS
    ):
        return None

    # Camera coordinates
    src = np.array([
        camera_points[0],
        camera_points[1],
        camera_points[2],
        camera_points[3],
    ], dtype=np.float32)

    # Projector coordinates
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
    """
    Transform camera coordinate into projector coordinate.
    """

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
# MAIN LOOP
# ============================================================

while True:

    ret, frame = cap.read()

    if not ret:
        print("Failed to receive frame")
        break

    current_time = time.time()

    # --------------------------------------------------------
    # Detect ArUco markers
    # --------------------------------------------------------

    corners, ids, rejected = detector.detectMarkers(
        frame
    )

    # --------------------------------------------------------
    # BLUE BACKGROUND
    # --------------------------------------------------------

    projection = np.zeros(
        (
            PROJECTOR_HEIGHT,
            PROJECTOR_WIDTH,
            3
        ),
        dtype=np.uint8
    )

    projection[:] = (255, 0, 0)

    # --------------------------------------------------------
    # Process detections
    # --------------------------------------------------------

    if ids is not None:

        # Draw markers on camera preview
        aruco.drawDetectedMarkers(
            frame,
            corners,
            ids
        )

        # ----------------------------------------------------
        # Update calibration
        # ----------------------------------------------------

        new_H = calculate_homography(
            corners,
            ids
        )

        if new_H is not None:
            H = new_H

        # ----------------------------------------------------
        # Process cards
        # ----------------------------------------------------

        if H is not None:

            for marker_id, marker_corners in zip(
                ids,
                corners
            ):

                marker_id = int(marker_id)

                # Ignore anything that isn't one of our cards
                if marker_id not in cards:
                    continue

                card = cards[marker_id]

                # --------------------------------------------
                # Find camera position
                # --------------------------------------------

                camera_position = marker_center(
                    marker_corners
                )

                # --------------------------------------------
                # Convert to projector position
                # --------------------------------------------

                x, y = transform_point(
                    camera_position,
                    H
                )

                # --------------------------------------------
                # Add position to history
                # --------------------------------------------

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

                # Remove old positions
                while (
                    history
                    and current_time - history[0][0]
                    > SMOOTHING_TIME
                ):
                    history.popleft()

                # --------------------------------------------
                # Average recent positions
                # --------------------------------------------

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

                # --------------------------------------------
                # Update card state
                # --------------------------------------------

                card["position"] = (
                    avg_x,
                    avg_y
                )

                card["last_seen"] = current_time

                card["visible"] = True

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
    # DRAW CARDS
    # ========================================================

    if H is not None:

        for marker_id, card in cards.items():

            if not card["visible"]:
                continue

            # A cards are tracked but do not create circles
            if card["type"] == "a":
                continue

            position = card["position"]

            if position is None:
                continue

            x, y = position

            # --------------------------------------------
            # Black circle
            # --------------------------------------------

            cv2.circle(
                projection,
                (x, y),
                CIRCLE_RADIUS,
                (0, 0, 0),
                -1
            )

            # --------------------------------------------
            # Display card information
            # --------------------------------------------

            label = (
                f"T{card['team']} "
                f"{card['type']}"
            )

            cv2.putText(
                projection,
                label,
                (x - 35, y + 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )

    # ========================================================
    # CALCULATE BLUE REMOVED
    # ========================================================

    black_mask = cv2.inRange(
        projection,
        np.array([0, 0, 0]),
        np.array([0, 0, 0])
    )

    black_pixels = cv2.countNonZero(
        black_mask
    )

    total_pixels = (
        PROJECTOR_WIDTH
        * PROJECTOR_HEIGHT
    )

    percentage_removed = (
        black_pixels
        / total_pixels
        * 100
    )

    # ========================================================
    # DISPLAY OVERALL PERCENTAGE
    # ========================================================

    text = f"{percentage_removed:.1f}%"

    cv2.putText(
        projection,
        text,
        (30, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5,
        (255, 255, 255),
        3,
        cv2.LINE_AA
    )

    # ========================================================
    # DISPLAY CARD COUNTS
    # ========================================================

    # Count currently visible cards by team

    team_counts = {
        team: 0
        for team in range(1, NUM_TEAMS + 1)
    }

    for card in cards.values():

        if card["visible"]:
            team_counts[card["team"]] += 1

    # Display team counts
    y_position = 100

    for team in range(1, NUM_TEAMS + 1):

        text = (
            f"Team {team}: "
            f"{team_counts[team]} cards"
        )

        cv2.putText(
            projection,
            text,
            (30, y_position),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        y_position += 35

    # ========================================================
    # SHOW CAMERA
    # ========================================================

    cv2.imshow(
        "Camera",
        frame
    )

    # ========================================================
    # SHOW PROJECTION
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


# ============================================================
# CLEANUP
# ============================================================

cap.release()

cv2.destroyAllWindows()