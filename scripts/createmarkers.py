import os
import sys
import math

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config as config_loader
from src.card_assignments import build_card_assignments

cfg = config_loader.load_config()

aruco_dictionary_name = cfg.raw["camera"]["aruco_dictionary"]
dictionary = cv2.aruco.getPredefinedDictionary(
    getattr(cv2.aruco, aruco_dictionary_name)
)

# ============================================================
# A4 / PRINT SETTINGS
# ============================================================

DPI = 300

A4_W = int(8.27 * DPI)
A4_H = int(11.69 * DPI)

# Marker size: 30 mm
marker_size = int(30 / 25.4 * DPI)

# Markers per page
cols = 5
rows = 8
markers_per_page = cols * rows

# Marker IDs to generate - derived from config.json so this can never
# drift out of sync with what main.py actually assigns.
marker_ids = sorted(
    build_card_assignments(cfg.raw["cards"]).keys()
)

# ============================================================
# CALCULATE NUMBER OF PAGES
# ============================================================

num_pages = math.ceil(len(marker_ids) / markers_per_page)

print(f"Generating {len(marker_ids)} markers")
print(f"Pages required: {num_pages}")
print(f"Marker size: {marker_size}px (~30mm)")

# ============================================================
# GENERATE EACH PAGE
# ============================================================

for page in range(num_pages):

    page_ids = marker_ids[
        page * markers_per_page:
        (page + 1) * markers_per_page
    ]

    # White A4 page
    sheet = np.ones((A4_H, A4_W), dtype=np.uint8) * 255

    # Calculate spacing
    margin_x = (A4_W - cols * marker_size) // (cols + 1)
    margin_y = (A4_H - rows * marker_size) // (rows + 1)

    for position, marker_id in enumerate(page_ids):

        marker = cv2.aruco.generateImageMarker(
            dictionary,
            marker_id,
            marker_size
        )

        row = position // cols
        col = position % cols

        x = margin_x + col * (marker_size + margin_x)
        y = margin_y + row * (marker_size + margin_y)

        # Place marker
        sheet[
            y:y + marker_size,
            x:x + marker_size
        ] = marker

        # ----------------------------------------------------
        # ID LABEL
        # ----------------------------------------------------

        label = str(marker_id)

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.2
        thickness = 3

        text_size = cv2.getTextSize(
            label,
            font,
            font_scale,
            thickness
        )[0]

        text_x = x + (marker_size - text_size[0]) // 2
        text_y = y + marker_size + text_size[1] + 15

        cv2.putText(
            sheet,
            label,
            (text_x, text_y),
            font,
            font_scale,
            0,
            thickness,
            cv2.LINE_AA
        )

    # ========================================================
    # SAVE PAGE
    # ========================================================

    filename = f"aruco_{marker_ids[0]}_{marker_ids[-1]}_page{page + 1}.png"

    cv2.imwrite(filename, sheet)

    print(
        f"Saved {filename} "
        f"(markers {page_ids[0]}-{page_ids[-1]})"
    )

print("Done.")
