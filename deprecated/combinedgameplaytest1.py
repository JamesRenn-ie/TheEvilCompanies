import cv2
import numpy as np
from collections import deque
import time
import pygame


# ============================================================
# CONFIGURATION
# ============================================================

PHONE_IP = "10.34.201.200"
VIDEO_URL = f"http://{PHONE_IP}:8080/video"

# ------------------------------------------------------------
# PROJECTOR
# ------------------------------------------------------------

PROJECTOR_WIDTH = 1280
PROJECTOR_HEIGHT = 720

# If your projector is actually 1920x1080, use:
#
# PROJECTOR_WIDTH = 1920
# PROJECTOR_HEIGHT = 1080


# ------------------------------------------------------------
# CALIBRATION MARKERS
# ------------------------------------------------------------

CALIBRATION_IDS = [0, 1, 2, 3]


# ============================================================
# CARD CONFIGURATION
# ============================================================

NUM_TEAMS = 4

CARDS_PER_TEAM = {
    "d": 10,   # Data Centre
    "a": 5,    # Activist
    "l": 5,    # Lawyer

    # These are still detected but don't affect the map
    "b": 2,
    "p": 2,
}

START_CARD_ID = 4


# ============================================================
# GAME SETTINGS
# ============================================================

# Radius of a Data Centre's effect
CIRCLE_RADIUS = 80

# How close cards need to be to count as "on top of"
# each other.
STACK_DISTANCE = 70

# Position smoothing
SMOOTHING_TIME = 0.2

# How long a card remains detected after the camera
# temporarily loses it.
MARKER_TIMEOUT = 0.5


# ============================================================
# MAP COLOURS
# ============================================================

WATER_COLOUR = np.array(
    [20, 110, 180],
    dtype=np.float32
)

LAND_COLOUR = np.array(
    [85, 160, 80],
    dtype=np.float32
)


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


INTERACTIVE_IDS = list(
    CARD_ASSIGNMENTS.keys()
)


# ============================================================
# PRINT CARD ASSIGNMENTS
# ============================================================

print()
print("Card assignments:")
print("-----------------")

for marker_id, card in CARD_ASSIGNMENTS.items():

    print(
        f"ArUco {marker_id:3d} "
        f"-> Team {card['team']} "
        f"Card {card['type']}"
    )

print()
print(
    f"Total cards: {len(CARD_ASSIGNMENTS)}"
)
print()


# ============================================================
# CARD TRACKING
# ============================================================

cards = {
    marker_id: {
        "team": data["team"],
        "type": data["type"],
        "position": None,
        "last_seen": None,
        "visible": False,
    }

    for marker_id, data
    in CARD_ASSIGNMENTS.items()
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

cap = cv2.VideoCapture(
    VIDEO_URL
)

if not cap.isOpened():

    print(
        "Could not connect to camera"
    )

    exit()

print(
    "Connected to camera"
)


# ============================================================
# HOMOGRAPHY
# ============================================================

H = None


def marker_center(corners):

    points = corners.reshape(
        4,
        2
    )

    x = np.mean(
        points[:, 0]
    )

    y = np.mean(
        points[:, 1]
    )

    return np.array(
        [x, y],
        dtype=np.float32
    )


def calculate_homography(
    corners,
    ids
):

    camera_points = {}

    for marker_id, marker_corners in zip(
        ids,
        corners
    ):

        marker_id = int(
            marker_id
        )

        if marker_id in CALIBRATION_IDS:

            camera_points[
                marker_id
            ] = marker_center(
                marker_corners
            )

    if not all(
        marker_id in camera_points
        for marker_id in CALIBRATION_IDS
    ):

        return None

    src = np.array(
        [
            camera_points[0],
            camera_points[1],
            camera_points[2],
            camera_points[3],
        ],
        dtype=np.float32
    )

    dst = np.array(
        [
            [0, 0],

            [
                PROJECTOR_WIDTH - 1,
                0
            ],

            [
                0,
                PROJECTOR_HEIGHT - 1
            ],

            [
                PROJECTOR_WIDTH - 1,
                PROJECTOR_HEIGHT - 1
            ],
        ],
        dtype=np.float32
    )

    H, _ = cv2.findHomography(
        src,
        dst
    )

    return H


def transform_point(
    point,
    H
):

    point = np.array(
        [[point]],
        dtype=np.float32
    )

    transformed = cv2.perspectiveTransform(
        point,
        H
    )

    x, y = transformed[0][0]

    return (
        int(x),
        int(y)
    )


# ============================================================
# MAP ENGINE
# ============================================================

class MapEngine:

    def __init__(self):

        self.width = PROJECTOR_WIDTH
        self.height = PROJECTOR_HEIGHT

        # ----------------------------------------------------
        # MAP STATE
        # ----------------------------------------------------
        #
        # 0 = water
        # 1 = land
        #
        # The map is rebuilt every frame from the cards.
        #

        self.land_mask = np.zeros(
            (
                self.height,
                self.width
            ),
            dtype=np.uint8
        )

    # ========================================================
    # CLEAR MAP
    # ========================================================

    def clear(self):

        self.land_mask.fill(0)

    # ========================================================
    # APPLY CIRCLE
    # ========================================================

    def apply_circle(
        self,
        x,
        y,
        radius,
        terrain
    ):

        x = int(x)
        y = int(y)
        radius = int(radius)

        # Keep calculation inside map
        x_min = max(
            0,
            x - radius
        )

        x_max = min(
            self.width,
            x + radius + 1
        )

        y_min = max(
            0,
            y - radius
        )

        y_max = min(
            self.height,
            y + radius + 1
        )

        yy, xx = np.ogrid[
            y_min:y_max,
            x_min:x_max
        ]

        distance_squared = (
            (xx - x) ** 2
            +
            (yy - y) ** 2
        )

        circle = (
            distance_squared
            <= radius ** 2
        )

        self.land_mask[
            y_min:y_max,
            x_min:x_max
        ][circle] = terrain

    # ========================================================
    # RENDER
    # ========================================================

    def render(self):

        # ----------------------------------------------------
        # SMOOTH THE MASK
        # ----------------------------------------------------
        #
        # This gives the coast a soft/anti-aliased edge.
        #

        mask_float = (
            self.land_mask.astype(
                np.float32
            )
            * 255
        )

        smooth_mask = cv2.GaussianBlur(
            mask_float,
            (0, 0),
            sigmaX=2.0
        )

        alpha = (
            smooth_mask / 255.0
        )

        # ----------------------------------------------------
        # CREATE RGB IMAGE
        # ----------------------------------------------------

        image = (
            WATER_COLOUR[None, None, :]
            * (1 - alpha[:, :, None])
            +
            LAND_COLOUR[None, None, :]
            * alpha[:, :, None]
        )

        image = np.clip(
            image,
            0,
            255
        ).astype(
            np.uint8
        )

        # NumPy -> Pygame

        surface = pygame.surfarray.make_surface(
            image.swapaxes(0, 1)
        )

        return surface


# ============================================================
# STACK DETECTION
# ============================================================

def find_stacks():

    """
    Find groups of cards which are physically on top
    of each other.

    Cards within STACK_DISTANCE pixels are treated as
    one stack.
    """

    visible_cards = [
        card
        for card in cards.values()
        if card["visible"]
        and card["position"] is not None
    ]

    stacks = []

    unused = set(
        id(card)
        for card in visible_cards
    )

    card_lookup = {
        id(card): card
        for card in visible_cards
    }

    while unused:

        first_id = next(
            iter(unused)
        )

        first_card = card_lookup[
            first_id
        ]

        stack = [
            first_card
        ]

        unused.remove(
            first_id
        )

        changed = True

        while changed:

            changed = False

            for candidate_id in list(
                unused
            ):

                candidate = card_lookup[
                    candidate_id
                ]

                # Compare against every card
                # already in the stack.

                for stack_card in stack:

                    x1, y1 = (
                        stack_card["position"]
                    )

                    x2, y2 = (
                        candidate["position"]
                    )

                    distance = np.hypot(
                        x2 - x1,
                        y2 - y1
                    )

                    if (
                        distance
                        <= STACK_DISTANCE
                    ):

                        stack.append(
                            candidate
                        )

                        unused.remove(
                            candidate_id
                        )

                        changed = True

                        break

        stacks.append(
            stack
        )

    return stacks


# ============================================================
# APPLY GAME RULES
# ============================================================

def rebuild_map(
    map_engine
):

    """
    Completely rebuild the map from the cards currently
    visible.

    Rules:

        Data Centre
            -> removes water

        Data Centre + Activist
            -> water comes back

        Data Centre + Activist + Lawyer
            -> water removed again
    """

    # Start with a completely empty ocean.

    map_engine.clear()

    stacks = find_stacks()

    for stack in stacks:

        card_types = [
            card["type"]
            for card in stack
        ]

        # ----------------------------------------------------
        # Find Data Centres
        # ----------------------------------------------------

        data_centres = [
            card
            for card in stack
            if card["type"] == "d"
        ]

        # No Data Centre = no map effect

        if not data_centres:
            continue

        has_activist = (
            "a"
            in card_types
        )

        has_lawyer = (
            "l"
            in card_types
        )

        # ----------------------------------------------------
        # APPLY EACH DATA CENTRE
        # ----------------------------------------------------

        for data_centre in data_centres:

            x, y = data_centre["position"]

            # ------------------------------------------------
            # DATA CENTRE + ACTIVIST + LAWYER
            # ------------------------------------------------
            #
            # Lawyer undoes the activist.
            #

            if (
                has_activist
                and has_lawyer
            ):

                map_engine.apply_circle(
                    x,
                    y,
                    CIRCLE_RADIUS,
                    terrain=1
                )

            # ------------------------------------------------
            # DATA CENTRE + ACTIVIST
            # ------------------------------------------------
            #
            # Activist restores water.
            #

            elif has_activist:

                map_engine.apply_circle(
                    x,
                    y,
                    CIRCLE_RADIUS,
                    terrain=0
                )

            # ------------------------------------------------
            # DATA CENTRE ALONE
            # ------------------------------------------------
            #
            # Data Centre removes water.
            #

            else:

                map_engine.apply_circle(
                    x,
                    y,
                    CIRCLE_RADIUS,
                    terrain=1
                )


# ============================================================
# PYGAME
# ============================================================

pygame.init()

pygame.display.set_caption(
    "Projected Board Game"
)

screen = pygame.display.set_mode(
    (
        PROJECTOR_WIDTH,
        PROJECTOR_HEIGHT
    )
)

clock = pygame.time.Clock()

map_engine = MapEngine()


# ============================================================
# MAIN LOOP
# ============================================================

while True:

    # ========================================================
    # EVENTS
    # ========================================================

    for event in pygame.event.get():

        if event.type == pygame.QUIT:

            cap.release()

            pygame.quit()

            cv2.destroyAllWindows()

            exit()

        elif event.type == pygame.KEYDOWN:

            # Q = quit
            if event.key == pygame.K_q:

                cap.release()

                pygame.quit()

                cv2.destroyAllWindows()

                exit()


    # ========================================================
    # CAMERA FRAME
    # ========================================================

    ret, frame = cap.read()

    if not ret:

        print(
            "Failed to receive frame"
        )

        break

    current_time = time.time()


    # ========================================================
    # ARUCO DETECTION
    # ========================================================

    corners, ids, rejected = (
        detector.detectMarkers(
            frame
        )
    )


    # ========================================================
    # UPDATE HOMOGRAPHY
    # ========================================================

    if ids is not None:

        new_H = calculate_homography(
            corners,
            ids
        )

        if new_H is not None:

            H = new_H


    # ========================================================
    # PROCESS CARDS
    # ========================================================

    if (
        ids is not None
        and H is not None
    ):

        for marker_id, marker_corners in zip(
            ids,
            corners
        ):

            marker_id = int(
                marker_id
            )

            # Ignore calibration markers
            if marker_id in CALIBRATION_IDS:
                continue

            # Ignore unknown markers
            if marker_id not in cards:
                continue

            card = cards[
                marker_id
            ]

            # ------------------------------------------------
            # CAMERA POSITION
            # ------------------------------------------------

            camera_position = marker_center(
                marker_corners
            )

            # ------------------------------------------------
            # CAMERA → PROJECTOR
            # ------------------------------------------------

            x, y = transform_point(
                camera_position,
                H
            )

            # ------------------------------------------------
            # SMOOTH POSITION
            # ------------------------------------------------

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
                and
                current_time
                - history[0][0]
                > SMOOTHING_TIME
            ):

                history.popleft()

            avg_x = int(
                np.mean(
                    [
                        p[1]
                        for p in history
                    ]
                )
            )

            avg_y = int(
                np.mean(
                    [
                        p[2]
                        for p in history
                    ]
                )
            )

            # ------------------------------------------------
            # UPDATE CARD
            # ------------------------------------------------

            card["position"] = (
                avg_x,
                avg_y
            )

            card["last_seen"] = (
                current_time
            )

            card["visible"] = True


    # ========================================================
    # UPDATE CARD VISIBILITY
    # ========================================================

    for marker_id, card in cards.items():

        if card["last_seen"] is None:

            card["visible"] = False

            continue

        if (
            current_time
            - card["last_seen"]
            > MARKER_TIMEOUT
        ):

            card["visible"] = False


    # ========================================================
    # REBUILD MAP
    # ========================================================

    rebuild_map(
        map_engine
    )


    # ========================================================
    # RENDER MAP
    # ========================================================

    map_surface = map_engine.render()

    screen.blit(
        map_surface,
        (0, 0)
    )


    # ========================================================
    # DEBUG: DRAW DETECTED CARD POSITIONS
    # ========================================================
    #
    # IMPORTANT:
    # These are just temporary debug markers.
    # Remove this section when projecting onto the table.
    #

    for marker_id, card in cards.items():

        if not card["visible"]:
            continue

        if card["position"] is None:
            continue

        x, y = card["position"]

        # Data Centre
        if card["type"] == "d":

            pygame.draw.circle(
                screen,
                (255, 255, 255),
                (x, y),
                8
            )

            pygame.draw.circle(
                screen,
                (255, 255, 255),
                (x, y),
                CIRCLE_RADIUS,
                2
            )

        # Activist
        elif card["type"] == "a":

            pygame.draw.circle(
                screen,
                (255, 255, 0),
                (x, y),
                6
            )

        # Lawyer
        elif card["type"] == "l":

            pygame.draw.circle(
                screen,
                (255, 0, 255),
                (x, y),
                6
            )


    # ========================================================
    # FLIP DISPLAY
    # ========================================================

    pygame.display.flip()

    clock.tick(30)


# ============================================================
# CLEANUP
# ============================================================

cap.release()

pygame.quit()

cv2.destroyAllWindows()
