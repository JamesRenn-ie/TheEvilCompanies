import cv2
import numpy as np

dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)

marker_size = 500
border = 50
markers_per_row = 4
markers_per_column = 3

sheet_width = markers_per_row * (marker_size + border) + border
sheet_height = markers_per_column * (marker_size + border) + border

sheet = np.ones((sheet_height, sheet_width), dtype=np.uint8) * 255

for i in range(markers_per_row * markers_per_column):
    marker = cv2.aruco.generateImageMarker(
        dictionary,
        i,
        marker_size
    )

    row = i // markers_per_row
    col = i % markers_per_row

    x = border + col * (marker_size + border)
    y = border + row * (marker_size + border)

    sheet[y:y+marker_size, x:x+marker_size] = marker

cv2.imwrite("aruco_markers.png", sheet)

print("Saved aruco_markers.png")