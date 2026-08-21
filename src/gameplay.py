import math

import cv2
import numpy as np
import pygame


# ============================================================
# STACK FLAGS
# ============================================================

def compute_stack_flags(stack):
    """
    Classify a single proximity-grouped stack of cards (see find_stacks).

    Returns (data_centres, billionaires, presidents, blocked), where
    `blocked` is the "unlawyered Activist present" condition that turns
    a Data Centre's terrain back to water.
    """

    data_centres = [card for card in stack if card["type"] == "d"]
    billionaires = [card for card in stack if card["type"] == "b"]
    presidents = [card for card in stack if card["type"] == "p"]

    has_activist = any(card["type"] == "a" for card in stack)
    has_lawyer = any(card["type"] == "l" for card in stack)

    blocked = has_activist and not has_lawyer

    return data_centres, billionaires, presidents, blocked


def circles_touch(card_a, card_b):
    """True if two cards' current circles intersect or are tangent."""

    x1, y1 = card_a["position"]
    x2, y2 = card_b["position"]

    distance = math.hypot(x2 - x1, y2 - y1)

    return distance <= card_a["radius"] + card_b["radius"]


# ============================================================
# STACK DETECTION
# ============================================================

def find_stacks(cards, stack_distance):
    """
    Find groups of currently-visible cards which are physically on top
    of each other. Cards within `stack_distance` pixels of any other
    card already in a group are treated as one stack.
    """

    visible_cards = [
        card
        for card in cards.values()
        if card["visible"] and card["position"] is not None
    ]

    stacks = []

    unused = set(id(card) for card in visible_cards)
    card_lookup = {id(card): card for card in visible_cards}

    while unused:

        first_id = next(iter(unused))
        first_card = card_lookup[first_id]

        stack = [first_card]
        unused.remove(first_id)

        changed = True

        while changed:

            changed = False

            for candidate_id in list(unused):

                candidate = card_lookup[candidate_id]

                for stack_card in stack:

                    x1, y1 = stack_card["position"]
                    x2, y2 = candidate["position"]

                    distance = np.hypot(x2 - x1, y2 - y1)

                    if distance <= stack_distance:

                        stack.append(candidate)
                        unused.remove(candidate_id)
                        changed = True
                        break

        stacks.append(stack)

    return stacks


# ============================================================
# BILLIONAIRE / PRESIDENT EFFECTS
# ============================================================

def apply_billionaire_steals(stacks):
    """
    A Billionaire stacked with an unlocked Data Centre owned by a
    different team steals it (owner_team = billionaire's team) and
    marks it billionaire_reactivated, so an unlawyered Activist in the
    same stack no longer blocks it (see rebuild_map/update_growth_radii/
    score_visible_cards, which all check this flag). Not locked - stays
    normally contestable afterward.

    billionaire_reactivated is a persistent flag, not re-derived fresh
    every frame, because a successful steal makes owner_team equal the
    Billionaire's own team immediately - re-deriving "different team"
    live every frame would only ever be true for the single frame the
    steal happens, then flip back to blocked next frame even though the
    Billionaire is still physically there. Instead it stays True for as
    long as a Billionaire belonging to the Data Centre's (now-matching)
    owning team remains in the stack, and only resets to False once no
    such Billionaire remains - at which point an unlawyered Activist
    resumes blocking it.

    Safe to call every frame: once a Data Centre's owner_team already
    matches the Billionaire's team, stealing is a no-op - but
    billionaire_reactivated is independently re-derived every frame
    from presence, per the persistence rule above.
    """

    for stack in stacks:

        data_centres, billionaires, _, _ = compute_stack_flags(stack)

        if not data_centres:
            continue

        stolen_this_frame = set()

        for billionaire in billionaires:

            for data_centre in data_centres:

                if data_centre["locked"]:
                    continue

                if data_centre["owner_team"] == billionaire["team"]:
                    continue

                data_centre["owner_team"] = billionaire["team"]
                stolen_this_frame.add(data_centre["id"])

        for data_centre in data_centres:

            if data_centre["locked"]:
                data_centre["billionaire_reactivated"] = False

            elif data_centre["id"] in stolen_this_frame:
                data_centre["billionaire_reactivated"] = True

            elif any(
                billionaire["team"] == data_centre["owner_team"]
                for billionaire in billionaires
            ):
                pass  # a Billionaire of the matching team is still here - keep prior state

            else:
                data_centre["billionaire_reactivated"] = False


def _claim(data_centre, team):

    data_centre["owner_team"] = team
    data_centre["locked"] = True


def apply_president_claims(stacks, visible_data_centres, game_mode):
    """
    A President stacked with ANY Data Centre (ignoring its current lock
    or blocked state) claims it: owner_team = president's team,
    locked = True, permanently immune to Activist/Lawyer/Billionoire
    while it stays visible.

    In growth mode, the claim also extends one hop to every OTHER
    visible Data Centre whose circle directly touches the targeted one,
    regardless of that neighbour's team/lock/block state - but does not
    cascade further (a neighbour's neighbour is not claimed unless it
    also independently touches the originally targeted Data Centre).
    """

    for stack in stacks:

        data_centres, _, presidents, _ = compute_stack_flags(stack)

        if not data_centres or not presidents:
            continue

        for president in presidents:

            for data_centre in data_centres:

                _claim(data_centre, president["team"])

                if game_mode != "growth":
                    continue

                for other in visible_data_centres:

                    if other is data_centre:
                        continue

                    if circles_touch(data_centre, other):
                        _claim(other, president["team"])


# ============================================================
# GROWTH-MODE RADIUS SIMULATION
# ============================================================

def update_growth_radii(dt, stacks, cards, growth_rate, min_radius):
    """
    Growth mode only. Each visible Data Centre's radius changes over
    real elapsed time `dt` (seconds):

    - Unblocked Data Centres grow at `N * growth_rate` px/sec, where N
      is the size of the connected component of same-owner_team,
      unblocked, currently-touching Data Centres it belongs to. Two
      same-team Data Centres are connected unless some THIRD visible
      Data Centre (any team/block state) touches both of them, which
      invalidates the direct connection.
    - Blocked Data Centres (unlawyered Activist present) never count
      toward another Data Centre's component, but shrink at
      `2 * N_hypothetical * growth_rate` px/sec, where N_hypothetical is
      the component size it WOULD have if it were unblocked - computed
      fresh every frame so the shrink rate naturally declines as the
      circle separates from its former cluster. Floored at min_radius.
    - A locked (President-claimed) or billionaire_reactivated Data
      Centre is exempt from all of the above even if its stack would
      otherwise be blocked: it grows/holds like a normal unblocked Data
      Centre, resuming from whatever radius it currently has.
    """

    visible_dcs = [
        card
        for card in cards.values()
        if card["type"] == "d" and card["visible"]
    ]

    if not visible_dcs:
        return

    blocked_ids = set()

    for stack in stacks:

        data_centres, _, _, blocked = compute_stack_flags(stack)

        if not blocked:
            continue

        for dc in data_centres:

            if dc["locked"] or dc.get("billionaire_reactivated", False):
                continue

            blocked_ids.add(dc["id"])

    def touches(card_a, card_b):
        return circles_touch(card_a, card_b)

    def blocked_by_third(card_a, card_b):

        for other in visible_dcs:

            if other["id"] in (card_a["id"], card_b["id"]):
                continue

            if touches(card_a, other) and touches(card_b, other):
                return True

        return False

    # --- Real graph: unblocked Data Centres only ---

    unblocked = [dc for dc in visible_dcs if dc["id"] not in blocked_ids]

    adjacency = {dc["id"]: [] for dc in unblocked}

    for i, card_a in enumerate(unblocked):

        for card_b in unblocked[i + 1:]:

            if card_a["owner_team"] != card_b["owner_team"]:
                continue

            if not touches(card_a, card_b):
                continue

            if blocked_by_third(card_a, card_b):
                continue

            adjacency[card_a["id"]].append(card_b["id"])
            adjacency[card_b["id"]].append(card_a["id"])

    component_id_of = {}
    component_size = {}

    visited = set()
    next_component_id = 0

    for card in unblocked:

        if card["id"] in visited:
            continue

        members = []
        queue = [card["id"]]
        visited.add(card["id"])

        while queue:

            node = queue.pop()
            members.append(node)

            for neighbour in adjacency[node]:

                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(neighbour)

        for node in members:
            component_id_of[node] = next_component_id

        component_size[next_component_id] = len(members)
        next_component_id += 1

    deltas = {}

    for card in unblocked:

        size = component_size[component_id_of[card["id"]]]
        deltas[card["id"]] = size * growth_rate * dt

    # --- Blocked Data Centres: hypothetical N against real unblocked
    #     neighbours only. Must never feed back into `adjacency`/
    #     `component_size` above, or a blocked card would incorrectly
    #     inflate other cards' real growth rate.

    for card in visible_dcs:

        if card["id"] not in blocked_ids:
            continue

        touched_components = set()

        for other in unblocked:

            if other["owner_team"] != card["owner_team"]:
                continue

            if not touches(card, other):
                continue

            if blocked_by_third(card, other):
                continue

            touched_components.add(component_id_of[other["id"]])

        n_hypothetical = 1 + sum(
            component_size[component_id] for component_id in touched_components
        )

        deltas[card["id"]] = -2 * n_hypothetical * growth_rate * dt

    for card in visible_dcs:

        delta = deltas.get(card["id"], 0.0)

        card["radius"] = max(min_radius, card["radius"] + delta)


# ============================================================
# TERRAIN RESOLUTION
# ============================================================

def rebuild_map(map_engine, stacks):
    """
    Completely rebuild the map from the cards currently visible.

    Rules (both modes):
        Data Centre alone, or Data Centre + Activist + Lawyer -> land
        Data Centre + Activist (no Lawyer)                    -> water
        A locked Data Centre (President-claimed) is always land,
        immune to the above. A billionaire_reactivated Data Centre
        (see apply_billionaire_steals) is also land despite the block,
        for as long as that flag holds.

    Stacks are processed in a deterministic order (lowest marker ID
    first) rather than find_stacks()'s arbitrary set-iteration order,
    so that in growth mode, where two different teams' circles can
    overlap, the "last one painted wins that pixel" tie-break is
    stable frame-to-frame instead of flickering.
    """

    map_engine.clear()

    ordered_stacks = sorted(
        stacks,
        key=lambda stack: min(card["id"] for card in stack),
    )

    for stack in ordered_stacks:

        data_centres, _, _, blocked = compute_stack_flags(stack)

        for data_centre in data_centres:

            x, y = data_centre["position"]

            terrain = 1 if (
                data_centre["locked"]
                or not blocked
                or data_centre.get("billionaire_reactivated", False)
            ) else 0

            map_engine.apply_circle(
                x, y,
                data_centre["radius"],
                terrain=terrain,
                team=data_centre["owner_team"],
            )


# ============================================================
# SCORING
# ============================================================

def score_visible_cards(cards, scores, num_teams, game_mode, stacks):

    blocked_dc_ids = set()

    if game_mode == "growth":

        for stack in stacks:

            data_centres, _, _, blocked = compute_stack_flags(stack)

            if not blocked:
                continue

            for dc in data_centres:

                if dc["locked"] or dc.get("billionaire_reactivated", False):
                    continue

                blocked_dc_ids.add(dc["id"])

    points_awarded = {team: 0 for team in range(1, num_teams + 1)}

    for card in cards.values():

        if card["type"] == "a":
            continue

        if not card["visible"]:
            continue

        if (
            game_mode == "growth"
            and card["type"] == "d"
            and card["id"] in blocked_dc_ids
        ):
            continue

        team = card["owner_team"]

        scores[team] += 1
        points_awarded[team] += 1

    return points_awarded


# ============================================================
# MAP COVERAGE
# ============================================================

def compute_coverage_percentage(land_mask):
    """
    Percentage (0-100) of the map's pixels that are land (nonzero).
    Works identically for static masks (any nonzero = land) and growth
    masks (nonzero team ID = land) - only nonzero-ness matters.
    """

    return 100.0 * np.count_nonzero(land_mask) / land_mask.size


# ============================================================
# END-OF-GAME AREA BONUS (growth mode only)
# ============================================================

def check_area_bonus(
    map_engine, scores, num_teams, bonus_awarded, threshold_percentage=100.0
):
    """
    The first frame the map's land coverage reaches `threshold_percentage`,
    add each team's currently-owned pixel area to their score once.
    Returns the new value of `bonus_awarded` (the caller owns this flag
    so it can be reset alongside scores on a game reset).
    """

    if bonus_awarded:
        return True

    if compute_coverage_percentage(map_engine.land_mask) < threshold_percentage:
        return False

    for team in range(1, num_teams + 1):

        area = int(np.count_nonzero(map_engine.land_mask == team))

        scores[team] += area

        print(f"Area bonus: Team {team} +{area}")

    return True


# ============================================================
# MAP ENGINE
# ============================================================

class MapEngine:
    """
    Holds the land/water mask and renders it to a pygame surface.

    `land_mask` stores, per pixel, 0 for water or a team ID (1..N) for
    land owned by that team. In "static" mode, rendering only cares
    whether a pixel is land at all (any nonzero value) and paints it
    with a single flat land colour, exactly as before this feature was
    added. In "growth" mode, each team's land is blurred and composited
    separately so players can see whose land is whose.
    """

    def __init__(
        self,
        width,
        height,
        water_colour,
        land_colour,
        mode="static",
        team_colours=None,
        team_colours_enabled=None,
    ):
        """
        team_colours_enabled controls whether Data Centre land renders
        in its owning team's colour instead of the flat `land_colour`:
        None (default) - on in growth mode, off in static mode (the
        original, mode-tied behaviour). True/False - always on/off,
        regardless of `mode`.
        """

        self.width = width
        self.height = height

        self.water_colour = np.array(water_colour, dtype=np.float32)
        self.land_colour = np.array(land_colour, dtype=np.float32)

        self.mode = mode
        self.team_colours = (
            [np.array(colour, dtype=np.float32) for colour in team_colours]
            if team_colours
            else []
        )
        self.team_colours_enabled = team_colours_enabled

        self.land_mask = np.zeros((self.height, self.width), dtype=np.uint8)

    def clear(self):

        self.land_mask.fill(0)

    def apply_circle(self, x, y, radius, terrain, team=0):

        x = int(x)
        y = int(y)
        radius = max(0, int(round(radius)))

        fill_value = int(team) if terrain == 1 else 0

        x_min = max(0, x - radius)
        x_max = min(self.width, x + radius + 1)

        y_min = max(0, y - radius)
        y_max = min(self.height, y + radius + 1)

        if x_min >= x_max or y_min >= y_max:
            return

        yy, xx = np.ogrid[y_min:y_max, x_min:x_max]

        distance_squared = (xx - x) ** 2 + (yy - y) ** 2

        circle = distance_squared <= radius ** 2

        self.land_mask[y_min:y_max, x_min:x_max][circle] = fill_value

    def _blur_alpha(self, binary_mask):

        mask_float = binary_mask.astype(np.float32) * 255

        smooth_mask = cv2.GaussianBlur(mask_float, (0, 0), sigmaX=2.0)

        return smooth_mask / 255.0

    def render(self):

        use_team_colours = (
            self.team_colours_enabled
            if self.team_colours_enabled is not None
            else self.mode == "growth"
        )

        if use_team_colours and self.team_colours:

            image = np.tile(
                self.water_colour[None, None, :],
                (self.height, self.width, 1),
            )

            for team_index, team_colour in enumerate(self.team_colours, start=1):

                alpha = self._blur_alpha(self.land_mask == team_index)

                image = (
                    image * (1 - alpha[:, :, None])
                    + team_colour[None, None, :] * alpha[:, :, None]
                )

        else:

            alpha = self._blur_alpha(self.land_mask > 0)

            image = (
                self.water_colour[None, None, :] * (1 - alpha[:, :, None])
                + self.land_colour[None, None, :] * alpha[:, :, None]
            )

        image = np.clip(image, 0, 255).astype(np.uint8)

        return pygame.surfarray.make_surface(image.swapaxes(0, 1))
