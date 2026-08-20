import pygame
import math
import numpy as np


# ============================================================
# SETTINGS
# ============================================================

WIDTH = 1920
HEIGHT = 1080

FPS = 60

# How close cards need to be to be considered stacked
STACK_DISTANCE = 70

# Visual size of the simulated cards
CARD_WIDTH = 150
CARD_HEIGHT = 210

# Effect radius of a Data Centre
DATA_CENTRE_RADIUS = 180

# ------------------------------------------------------------
# COLOURS
# ------------------------------------------------------------

WATER = (20, 110, 180)
LAND = (85, 160, 80)

DATA_CENTRE_COLOUR = (180, 80, 70)
ACTIVIST_COLOUR = (70, 150, 90)
LAWYER_COLOUR = (80, 100, 180)

WHITE = (255, 255, 255)
BLACK = (20, 20, 20)

GRID_COLOUR = (255, 255, 255)


# ============================================================
# CARD
# ============================================================

class Card:

    def __init__(
        self,
        card_id,
        card_type,
        x,
        y
    ):

        self.id = card_id
        self.type = card_type

        self.x = x
        self.y = y

        self.selected = False

    def position(self):

        return (
            self.x,
            self.y
        )


# ============================================================
# MAP ENGINE
# ============================================================

class MapEngine:

    def __init__(self):

        # 0 = water
        # 1 = land

        self.land_mask = np.zeros(
            (
                HEIGHT,
                WIDTH
            ),
            dtype=np.uint8
        )

        self.screen = pygame.display.set_mode(
            (
                WIDTH,
                HEIGHT
            )
        )

        pygame.display.set_caption(
            "Board Game Prototype"
        )

        self.clock = pygame.time.Clock()

    # --------------------------------------------------------
    # RESET
    # --------------------------------------------------------

    def clear(self):

        self.land_mask.fill(0)

    # --------------------------------------------------------
    # APPLY CIRCLE
    # --------------------------------------------------------

    def apply_circle(
        self,
        x,
        y,
        radius,
        terrain
    ):

        """
        terrain:
            0 = water
            1 = land
        """

        x_min = max(
            0,
            int(x - radius)
        )

        x_max = min(
            WIDTH,
            int(x + radius + 1)
        )

        y_min = max(
            0,
            int(y - radius)
        )

        y_max = min(
            HEIGHT,
            int(y + radius + 1)
        )

        yy, xx = np.ogrid[
            y_min:y_max,
            x_min:x_max
        ]

        distance_squared = (
            (xx - x) ** 2 +
            (yy - y) ** 2
        )

        circle = (
            distance_squared <= radius ** 2
        )

        self.land_mask[
            y_min:y_max,
            x_min:x_max
        ][circle] = terrain

    # --------------------------------------------------------
    # RENDER
    # --------------------------------------------------------

    def render(self):

        image = np.empty(
            (
                HEIGHT,
                WIDTH,
                3
            ),
            dtype=np.uint8
        )

        # Start with ocean
        image[:, :] = WATER

        # Draw land
        image[
            self.land_mask == 1
        ] = LAND

        surface = pygame.surfarray.make_surface(
            image.swapaxes(0, 1)
        )

        return surface


# ============================================================
# GAME
# ============================================================

class Game:

    def __init__(self):

        self.map = MapEngine()

        self.cards = []

        self.next_card_id = 1

        # Currently dragged card
        self.dragging_card = None

        self.drag_offset_x = 0
        self.drag_offset_y = 0

        # Font
        self.font = pygame.font.SysFont(
            "Arial",
            28
        )

        self.small_font = pygame.font.SysFont(
            "Arial",
            20
        )

    # ========================================================
    # ADD CARD
    # ========================================================

    def add_card(
        self,
        card_type,
        x,
        y
    ):

        card = Card(
            self.next_card_id,
            card_type,
            x,
            y
        )

        self.cards.append(card)

        self.next_card_id += 1

        return card

    # ========================================================
    # REMOVE CARD
    # ========================================================

    def remove_card(
        self,
        card
    ):

        if card in self.cards:
            self.cards.remove(card)

    # ========================================================
    # FIND CARD UNDER MOUSE
    # ========================================================

    def find_card(
        self,
        x,
        y
    ):

        # Reverse order means cards later in the list
        # are considered visually on top.

        for card in reversed(self.cards):

            if (
                abs(card.x - x)
                < CARD_WIDTH / 2
                and
                abs(card.y - y)
                < CARD_HEIGHT / 2
            ):

                return card

        return None

    # ========================================================
    # FIND STACKS
    # ========================================================

    def find_stacks(self):

        """
        Groups cards which are close enough to be
        considered physically stacked.

        Returns a list of lists.
        """

        stacks = []

        unused = set(
            self.cards
        )

        while unused:

            starting_card = next(
                iter(unused)
            )

            stack = [
                starting_card
            ]

            unused.remove(
                starting_card
            )

            changed = True

            while changed:

                changed = False

                for card in list(unused):

                    for stack_card in stack:

                        distance = math.hypot(
                            card.x - stack_card.x,
                            card.y - stack_card.y
                        )

                        if distance <= STACK_DISTANCE:

                            stack.append(card)

                            unused.remove(card)

                            changed = True

                            break

            stacks.append(stack)

        return stacks

    # ========================================================
    # CALCULATE MAP
    # ========================================================

    def rebuild_map(self):

        """
        Rebuild the entire map from the current cards.

        This is deliberately recalculated from scratch.

        Therefore moving/removing cards automatically
        updates the map correctly.
        """

        self.map.clear()

        stacks = self.find_stacks()

        for stack in stacks:

            self.apply_stack(
                stack
            )

    # ========================================================
    # APPLY A STACK
    # ========================================================

    def apply_stack(
        self,
        stack
    ):

        """
        Determine what a stack of cards does.

        Rules:

        Data Centre
            -> remove water

        Data Centre + Activist
            -> restore water

        Data Centre + Activist + Lawyer
            -> remove water again
        """

        # ----------------------------------------------------
        # Find card types
        # ----------------------------------------------------

        card_types = [
            card.type
            for card in stack
        ]

        # ----------------------------------------------------
        # Must contain a Data Centre
        # ----------------------------------------------------

        if "data_centre" not in card_types:

            return

        # ----------------------------------------------------
        # Find Data Centre
        # ----------------------------------------------------

        data_centre = next(
            card
            for card in stack
            if card.type == "data_centre"
        )

        # ----------------------------------------------------
        # Check for Activist
        # ----------------------------------------------------

        has_activist = (
            "activist"
            in card_types
        )

        # ----------------------------------------------------
        # Check for Lawyer
        # ----------------------------------------------------

        has_lawyer = (
            "lawyer"
            in card_types
        )

        # ----------------------------------------------------
        # DATA CENTRE + ACTIVIST + LAWYER
        # ----------------------------------------------------

        if has_activist and has_lawyer:

            self.map.apply_circle(
                data_centre.x,
                data_centre.y,
                DATA_CENTRE_RADIUS,
                terrain=1
            )

        # ----------------------------------------------------
        # DATA CENTRE + ACTIVIST
        # ----------------------------------------------------

        elif has_activist:

            self.map.apply_circle(
                data_centre.x,
                data_centre.y,
                DATA_CENTRE_RADIUS,
                terrain=0
            )

        # ----------------------------------------------------
        # DATA CENTRE ONLY
        # ----------------------------------------------------

        else:

            self.map.apply_circle(
                data_centre.x,
                data_centre.y,
                DATA_CENTRE_RADIUS,
                terrain=1
            )

    # ========================================================
    # DRAW CARDS
    # ========================================================

    def draw_cards(
        self,
        screen
    ):

        for card in self.cards:

            # -----------------------------------------------
            # Card colour
            # -----------------------------------------------

            if card.type == "data_centre":

                colour = DATA_CENTRE_COLOUR
                label = "DATA CENTRE"

            elif card.type == "activist":

                colour = ACTIVIST_COLOUR
                label = "ACTIVIST"

            elif card.type == "lawyer":

                colour = LAWYER_COLOUR
                label = "LAWYER"

            else:

                colour = WHITE
                label = "UNKNOWN"

            # -----------------------------------------------
            # Card rectangle
            # -----------------------------------------------

            rect = pygame.Rect(
                0,
                0,
                CARD_WIDTH,
                CARD_HEIGHT
            )

            rect.center = (
                card.x,
                card.y
            )

            pygame.draw.rect(
                screen,
                colour,
                rect,
                border_radius=12
            )

            # -----------------------------------------------
            # Selection border
            # -----------------------------------------------

            if card.selected:

                pygame.draw.rect(
                    screen,
                    WHITE,
                    rect,
                    width=5,
                    border_radius=12
                )

            # -----------------------------------------------
            # Label
            # -----------------------------------------------

            text = self.small_font.render(
                label,
                True,
                WHITE
            )

            text_rect = text.get_rect(
                center=(
                    card.x,
                    card.y
                )
            )

            screen.blit(
                text,
                text_rect
            )

            # -----------------------------------------------
            # Card ID
            # -----------------------------------------------

            id_text = self.small_font.render(
                f"ID: {card.id}",
                True,
                WHITE
            )

            id_rect = id_text.get_rect(
                center=(
                    card.x,
                    card.y + 35
                )
            )

            screen.blit(
                id_text,
                id_rect
            )

    # ========================================================
    # DRAW STACK INFORMATION
    # ========================================================

    def draw_stack_info(
        self,
        screen
    ):

        stacks = self.find_stacks()

        y = 20

        for stack in stacks:

            if len(stack) <= 1:
                continue

            types = [
                card.type.replace(
                    "_",
                    " "
                )
                for card in stack
            ]

            text = (
                "STACK: "
                + " + ".join(types)
            )

            surface = self.small_font.render(
                text,
                True,
                WHITE
            )

            screen.blit(
                surface,
                (
                    20,
                    y
                )
            )

            y += 25

    # ========================================================
    # DRAW INSTRUCTIONS
    # ========================================================

    def draw_instructions(
        self,
        screen
    ):

        instructions = [
            "D = Data Centre",
            "A = Activist",
            "L = Lawyer",
            "Left click = select / drag",
            "Right click = delete",
            "R = reset",
            "ESC = quit"
        ]

        y = HEIGHT - (
            len(instructions) * 25
        ) - 20

        for instruction in instructions:

            text = self.small_font.render(
                instruction,
                True,
                WHITE
            )

            screen.blit(
                text,
                (
                    20,
                    y
                )
            )

            y += 25


# ============================================================
# INITIALISE
# ============================================================

pygame.init()

game = Game()

running = True


# ============================================================
# MAIN LOOP
# ============================================================

while running:

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------

    for event in pygame.event.get():

        # ----------------------------------------------------
        # QUIT
        # ----------------------------------------------------

        if event.type == pygame.QUIT:

            running = False

        # ----------------------------------------------------
        # KEYBOARD
        # ----------------------------------------------------

        elif event.type == pygame.KEYDOWN:

            if event.key == pygame.K_ESCAPE:

                running = False

            elif event.key == pygame.K_r:

                game.cards.clear()

                game.next_card_id = 1

                game.dragging_card = None

                game.map.clear()

            # -----------------------------------------------
            # CREATE DATA CENTRE
            # -----------------------------------------------

            elif event.key == pygame.K_d:

                mouse_x, mouse_y = pygame.mouse.get_pos()

                game.add_card(
                    "data_centre",
                    mouse_x,
                    mouse_y
                )

            # -----------------------------------------------
            # CREATE ACTIVIST
            # -----------------------------------------------

            elif event.key == pygame.K_a:

                mouse_x, mouse_y = pygame.mouse.get_pos()

                game.add_card(
                    "activist",
                    mouse_x,
                    mouse_y
                )

            # -----------------------------------------------
            # CREATE LAWYER
            # -----------------------------------------------

            elif event.key == pygame.K_l:

                mouse_x, mouse_y = pygame.mouse.get_pos()

                game.add_card(
                    "lawyer",
                    mouse_x,
                    mouse_y
                )

        # ----------------------------------------------------
        # MOUSE BUTTON DOWN
        # ----------------------------------------------------

        elif event.type == pygame.MOUSEBUTTONDOWN:

            mouse_x, mouse_y = pygame.mouse.get_pos()

            # -----------------------------------------------
            # RIGHT CLICK = DELETE
            # -----------------------------------------------

            if event.button == 3:

                card = game.find_card(
                    mouse_x,
                    mouse_y
                )

                if card:

                    game.remove_card(
                        card
                    )

            # -----------------------------------------------
            # LEFT CLICK = START DRAG
            # -----------------------------------------------

            elif event.button == 1:

                card = game.find_card(
                    mouse_x,
                    mouse_y
                )

                if card:

                    # Deselect everything
                    for c in game.cards:
                        c.selected = False

                    card.selected = True

                    game.dragging_card = card

                    game.drag_offset_x = (
                        card.x - mouse_x
                    )

                    game.drag_offset_y = (
                        card.y - mouse_y
                    )

        # ----------------------------------------------------
        # MOUSE BUTTON UP
        # ----------------------------------------------------

        elif event.type == pygame.MOUSEBUTTONUP:

            if event.button == 1:

                game.dragging_card = None

    # --------------------------------------------------------
    # DRAG CARD
    # --------------------------------------------------------

    if game.dragging_card:

        mouse_x, mouse_y = pygame.mouse.get_pos()

        game.dragging_card.x = (
            mouse_x +
            game.drag_offset_x
        )

        game.dragging_card.y = (
            mouse_y +
            game.drag_offset_y
        )

    # --------------------------------------------------------
    # REBUILD MAP
    # --------------------------------------------------------

    game.rebuild_map()

    # --------------------------------------------------------
    # RENDER MAP
    # --------------------------------------------------------

    map_image = game.map.render()

    game.map.screen.blit(
        map_image,
        (0, 0)
    )

    # --------------------------------------------------------
    # DRAW CARDS
    # --------------------------------------------------------

    game.draw_cards(
        game.map.screen
    )

    # --------------------------------------------------------
    # DRAW INFORMATION
    # --------------------------------------------------------

    game.draw_stack_info(
        game.map.screen
    )

    game.draw_instructions(
        game.map.screen
    )

    # --------------------------------------------------------
    # UPDATE DISPLAY
    # --------------------------------------------------------

    pygame.display.flip()

    game.map.clock.tick(FPS)


pygame.quit()
