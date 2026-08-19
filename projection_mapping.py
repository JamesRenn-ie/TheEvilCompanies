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

# Interactive marker
INTERACTIVE_ID = 10

SMOOTHING_TIME = 0.5  # seconds

position_history = deque()
last_position = None


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

    return np.array([x, y], dtype=np.float32)


def calculate_homography(corners, ids):
    """
    Find the four calibration markers and calculate
    camera -> projector transformation.
    """

    camera_points = {}

    for marker_id, marker_corners in zip(ids, corners):

        marker_id = int(marker_id)

        if marker_id in CALIBRATION_IDS:
            camera_points[marker_id] = marker_center(
                marker_corners
            )

    # We need all four markers
    if not all(
        marker_id in camera_points
        for marker_id in CALIBRATION_IDS
    ):
        return None

    # Camera coordinates
    #
    # 0 = top-left
    # 1 = top-right
    # 2 = bottom-left
    # 3 = bottom-right

    src = np.array([
        camera_points[0],
        camera_points[1],
        camera_points[2],
        camera_points[3],
    ], dtype=np.float32)

    # Corresponding projector coordinates
    dst = np.array([
        [0, 0],
        [PROJECTOR_WIDTH - 1, 0],
        [0, PROJECTOR_HEIGHT - 1],
        [PROJECTOR_WIDTH - 1, PROJECTOR_HEIGHT - 1],
    ], dtype=np.float32)

    H, _ = cv2.findHomography(src, dst)

    return H


def transform_point(point, H):
    """
    Transform a camera coordinate into projector coordinates.
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

    # --------------------------------------------------------
    # Detect ArUco markers
    # --------------------------------------------------------

    corners, ids, rejected = detector.detectMarkers(frame)

    # --------------------------------------------------------
    # Create projection image
    # --------------------------------------------------------

    projection = np.zeros(
        (
            PROJECTOR_HEIGHT,
            PROJECTOR_WIDTH,
            3
        ),
        dtype=np.uint8
    )

    # --------------------------------------------------------
    # Draw detected markers on camera view
    # --------------------------------------------------------

    if ids is not None:

        aruco.drawDetectedMarkers(
            frame,
            corners,
            ids
        )

        # ----------------------------------------------------
        # Calculate calibration
        # ----------------------------------------------------

        new_H = calculate_homography(
            corners,
            ids
        )

        if new_H is not None:
            H = new_H

        # ----------------------------------------------------
        # Interactive marker
        # ----------------------------------------------------

        if H is not None:

            current_time = time.time()

            for marker_id, marker_corners in zip(ids, corners):

                marker_id = int(marker_id)

                if marker_id == INTERACTIVE_ID:

                    # Position in camera image
                    camera_position = marker_center(marker_corners)

                    # Convert to projector coordinates
                    x, y = transform_point(
                        camera_position,
                        H
                    )

                    # Add new position to history
                    position_history.append(
                        (current_time, x, y)
                    )

                    # Remove positions older than 0.5 seconds
                    while (
                        position_history
                        and current_time - position_history[0][0]
                        > SMOOTHING_TIME
                    ):
                        position_history.popleft()

                    # Average all recent positions
                    avg_x = int(
                        np.mean([
                            position[1]
                            for position in position_history
                        ])
                    )

                    avg_y = int(
                        np.mean([
                            position[2]
                            for position in position_history
                        ])
                    )

                    last_position = (avg_x, avg_y)

            # If marker wasn't detected this frame,
            # keep using the last known position.
            if last_position is not None:

                x, y = last_position

                cv2.circle(
                    projection,
                    (x, y),
                    80,
                    (0, 255, 0),
                    -1
                )

                cv2.circle(
                    projection,
                    (x, y),
                    30,
                    (255, 255, 255),
                    -1
                )

                cv2.line(
                    projection,
                    (x - 100, y),
                    (x + 100, y),
                    (255, 255, 255),
                    3
                )

                cv2.line(
                    projection,
                    (x, y - 100),
                    (x, y + 100),
                    (255, 255, 255),
                    3
                )
    # --------------------------------------------------------
    # Show camera
    # --------------------------------------------------------

    cv2.imshow(
        "Camera",
        frame
    )

    # --------------------------------------------------------
    # Show projector output
    # --------------------------------------------------------

    cv2.imshow(
        "Projection",
        projection
    )

    # --------------------------------------------------------
    # Keyboard
    # --------------------------------------------------------

    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):
        break


# ============================================================
# CLEANUP
# ============================================================

cap.release()

cv2.destroyAllWindows()