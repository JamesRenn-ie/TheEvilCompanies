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

# Interactive markers
# Every marker from 4 onwards will create a black circle.
INTERACTIVE_IDS = list(range(4, 12))

# Circle radius
CIRCLE_RADIUS = 80

# Position smoothing
SMOOTHING_TIME = 0.2  # seconds

# How long to keep a marker visible after detection is lost
MARKER_TIMEOUT = 0.5  # seconds


# ============================================================
# POSITION TRACKING
# ============================================================

position_histories = {
    marker_id: deque()
    for marker_id in INTERACTIVE_IDS
}

last_positions = {
    marker_id: None
    for marker_id in INTERACTIVE_IDS
}

last_detection_times = {
    marker_id: None
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

    # OpenCV uses BGR.
    # (255, 0, 0) = blue.

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
        # Track interactive markers
        # ----------------------------------------------------

        if H is not None:

            for marker_id, marker_corners in zip(
                ids,
                corners
            ):

                marker_id = int(marker_id)

                # Ignore calibration markers
                if marker_id not in INTERACTIVE_IDS:
                    continue

                # Camera position
                camera_position = marker_center(
                    marker_corners
                )

                # Convert to projector position
                x, y = transform_point(
                    camera_position,
                    H
                )

                # Add position to history
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

                # Average recent positions
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

                # Save position
                last_positions[marker_id] = (
                    avg_x,
                    avg_y
                )

                last_detection_times[marker_id] = (
                    current_time
                )

    # ========================================================
    # DRAW BLACK CIRCLES
    # ========================================================

    if H is not None:

        for marker_id in INTERACTIVE_IDS:

            position = last_positions[marker_id]

            last_detection = (
                last_detection_times[marker_id]
            )

            # Marker has never been detected
            if position is None:
                continue

            # Marker has disappeared
            if (
                last_detection is None
                or current_time - last_detection
                > MARKER_TIMEOUT
            ):
                continue

            x, y = position

            # Black circle
            cv2.circle(
                projection,
                (x, y),
                CIRCLE_RADIUS,
                (0, 0, 0),
                -1
            )

    # ========================================================
    # CALCULATE BLUE REMOVED
    # ========================================================

    # Black pixels are pixels where all BGR values are zero.

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
    # DISPLAY PERCENTAGE
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