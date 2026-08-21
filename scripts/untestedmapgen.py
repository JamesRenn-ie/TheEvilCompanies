import pygame
import math
import random

# ============================================================
# CONFIGURATION
# ============================================================

SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# Internal rendering resolution.
# Rendering the map at a lower resolution and scaling it up
# creates naturally smooth coastlines.
MAP_WIDTH = 480
MAP_HEIGHT = 270

FPS = 60

# Initial brush size in internal pixels
INITIAL_BRUSH_SIZE = 22
MIN_BRUSH_SIZE = 5
MAX_BRUSH_SIZE = 80

# ============================================================
# INITIALISE PYGAME
# ============================================================

pygame.init()

screen = pygame.display.set_mode(
    (SCREEN_WIDTH, SCREEN_HEIGHT)
)

pygame.display.set_caption("Projected Board Game Prototype")

clock = pygame.time.Clock()

# ============================================================
# COLOURS
# ============================================================

WATER_COLOUR = (20, 105, 170)
WATER_LIGHT = (30, 125, 190)
WATER_DARK = (10, 80, 145)

LAND_COLOUR = (83, 155, 78)
LAND_LIGHT = (105, 175, 88)
LAND_DARK = (60, 125, 65)

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# ============================================================
# LAND MASK
# ============================================================

# This surface stores the actual state of the board.
#
# Black  = water
# White  = land
#
# Keeping this separate from the graphics is important.
# Later your ArUco/game logic can modify this mask directly.

land_mask = pygame.Surface(
    (MAP_WIDTH, MAP_HEIGHT),
    pygame.SRCALPHA
)

land_mask.fill((0, 0, 0, 0))


# ============================================================
# OPTIONAL INITIAL ISLAND
# ============================================================

def create_initial_island():
    """
    Creates a small starting island.

    Delete/comment this function call if you want
    the game to start as 100% ocean.
    """

    pygame.draw.circle(
        land_mask,
        (255, 255, 255, 255),
        (MAP_WIDTH // 2, MAP_HEIGHT // 2),
        35
    )

    pygame.draw.circle(
        land_mask,
        (255, 255, 255, 255),
        (MAP_WIDTH // 2 + 30, MAP_HEIGHT // 2 - 10),
        28
    )

    pygame.draw.circle(
        land_mask,
        (255, 255, 255, 255),
        (MAP_WIDTH // 2 - 30, MAP_HEIGHT // 2 + 15),
        25
    )


# Start with a small island.
create_initial_island()

# ============================================================
# BRUSH
# ============================================================

brush_size = INITIAL_BRUSH_SIZE


def add_land(x, y, radius):
    """
    Add land to the map.

    Because we're drawing circles rather than squares,
    the coastline is naturally rounded.
    """

    pygame.draw.circle(
        land_mask,
        (255, 255, 255, 255),
        (x, y),
        radius
    )


def remove_land(x, y, radius):
    """
    Remove land and reveal water.
    """

    pygame.draw.circle(
        land_mask,
        (0, 0, 0, 0),
        (x, y),
        radius
    )


# ============================================================
# MAP COORDINATE CONVERSION
# ============================================================

def screen_to_map(mouse_x, mouse_y):
    """
    Convert 1920x1080 screen coordinates into
    the internal 480x270 map coordinates.
    """

    map_x = int(
        mouse_x * MAP_WIDTH / SCREEN_WIDTH
    )

    map_y = int(
        mouse_y * MAP_HEIGHT / SCREEN_HEIGHT
    )

    return map_x, map_y


def map_to_screen(map_x, map_y):
    """
    Convert internal map coordinates back to
    projector/screen coordinates.
    """

    screen_x = int(
        map_x * SCREEN_WIDTH / MAP_WIDTH
    )

    screen_y = int(
        map_y * SCREEN_HEIGHT / MAP_HEIGHT
    )

    return screen_x, screen_y


# ============================================================
# WATER TEXTURE
# ============================================================

# Create a subtle animated water texture at the internal
# rendering resolution.

water_surface = pygame.Surface(
    (MAP_WIDTH, MAP_HEIGHT)
)


def draw_water(time):
    """
    Draws a simple animated ocean.

    This can later be replaced with a proper water texture
    or shader.
    """

    water_surface.fill(WATER_COLOUR)

    # Draw subtle wave lines
    for y in range(0, MAP_HEIGHT, 12):

        offset = math.sin(
            time * 0.001 + y * 0.05
        ) * 8

        for x in range(-20, MAP_WIDTH + 20, 40):

            start_x = x + offset

            pygame.draw.arc(
                water_surface,
                WATER_LIGHT,
                (
                    int(start_x),
                    y,
                    30,
                    10
                ),
                math.pi,
                math.pi * 2,
                1
            )


# ============================================================
# LAND TEXTURE
# ============================================================

land_surface = pygame.Surface(
    (MAP_WIDTH, MAP_HEIGHT),
    pygame.SRCALPHA
)


def draw_land():
    """
    Creates the visible land layer from the land mask.
    """

    land_surface.fill((0, 0, 0, 0))

    # Base land colour
    land_surface.fill(
        (*LAND_COLOUR, 255),
        special_flags=pygame.BLEND_RGBA_MIN
    )

    # Apply the mask.
    #
    # The mask determines where land is visible.
    land_surface.blit(
        land_mask,
        (0, 0),
        special_flags=pygame.BLEND_RGBA_MULT
    )


# ============================================================
# LAND DETAIL
# ============================================================

def draw_land_details(surface):
    """
    Adds a few simple visual details to land.
    These are purely decorative.
    """

    # We don't want thousands of objects every frame,
    # so keep the decoration subtle.

    random.seed(42)

    for _ in range(100):

        x = random.randint(
            0,
            MAP_WIDTH - 1
        )

        y = random.randint(
            0,
            MAP_HEIGHT - 1
        )

        # Check whether this point is land.
        pixel = land_mask.get_at((x, y))

        if pixel.a > 128:

            pygame.draw.circle(
                surface,
                LAND_LIGHT,
                (x, y),
                1
            )


# ============================================================
# SMOOTH MAP RENDERING
# ============================================================

def render_map(time):
    """
    Creates the final map image.

    The map is rendered internally at 480x270 and then
    smoothly scaled to 1920x1080.

    This is what gives the land coastline a softer appearance.
    """

    draw_water(time)

    draw_land()

    # Composite the land over the ocean.
    combined = water_surface.copy()

    combined.blit(
        land_surface,
        (0, 0)
    )

    draw_land_details(combined)

    # Scale to projector resolution.
    final_map = pygame.transform.smoothscale(
        combined,
        (SCREEN_WIDTH, SCREEN_HEIGHT)
    )

    return final_map


# ============================================================
# HUD
# ============================================================

font = pygame.font.SysFont(
    "Arial",
    24
)


def draw_hud():
    """
    Displays controls in the corner.
    """

    text = (
        f"LEFT CLICK: Land   "
        f"RIGHT CLICK: Water   "
        f"Scroll: Brush Size   "
        f"R: Reset   "
        f"F: Fullscreen   "
        f"Brush: {brush_size}"
    )

    text_surface = font.render(
        text,
        True,
        WHITE
    )

    # Transparent background
    background = pygame.Surface(
        (
            text_surface.get_width() + 20,
            text_surface.get_height() + 12
        ),
        pygame.SRCALPHA
    )

    background.fill(
        (0, 0, 0, 150)
    )

    screen.blit(
        background,
        (15, 15)
    )

    screen.blit(
        text_surface,
        (25, 21)
    )


# ============================================================
# RESET
# ============================================================

def reset_board():
    """
    Reset the map to entirely water.
    """

    land_mask.fill(
        (0, 0, 0, 0)
    )


# ============================================================
# MAIN LOOP
# ============================================================

running = True
fullscreen = False

while running:

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------

    for event in pygame.event.get():

        if event.type == pygame.QUIT:
            running = False

        # Keyboard
        elif event.type == pygame.KEYDOWN:

            if event.key == pygame.K_ESCAPE:
                running = False

            elif event.key == pygame.K_r:
                reset_board()

            elif event.key == pygame.K_f:

                fullscreen = not fullscreen

                if fullscreen:
                    screen = pygame.display.set_mode(
                        (SCREEN_WIDTH, SCREEN_HEIGHT),
                        pygame.FULLSCREEN
                    )
                else:
                    screen = pygame.display.set_mode(
                        (SCREEN_WIDTH, SCREEN_HEIGHT)
                    )

        # Mouse wheel
        elif event.type == pygame.MOUSEWHEEL:

            brush_size += event.y * 3

            brush_size = max(
                MIN_BRUSH_SIZE,
                min(
                    MAX_BRUSH_SIZE,
                    brush_size
                )
            )

    # --------------------------------------------------------
    # MOUSE INPUT
    # --------------------------------------------------------

    mouse_buttons = pygame.mouse.get_pressed()

    mouse_x, mouse_y = pygame.mouse.get_pos()

    map_x, map_y = screen_to_map(
        mouse_x,
        mouse_y
    )

    # LEFT CLICK = ADD LAND
    if mouse_buttons[0]:

        add_land(
            map_x,
            map_y,
            brush_size
        )

    # RIGHT CLICK = REMOVE LAND
    elif mouse_buttons[2]:

        remove_land(
            map_x,
            map_y,
            brush_size
        )

    # --------------------------------------------------------
    # RENDER
    # --------------------------------------------------------

    current_time = pygame.time.get_ticks()

    final_map = render_map(
        current_time
    )

    screen.blit(
        final_map,
        (0, 0)
    )

    draw_hud()

    pygame.display.flip()

    clock.tick(FPS)


pygame.quit()
