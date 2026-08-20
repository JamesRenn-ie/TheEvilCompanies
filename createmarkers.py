import cv2
import numpy as np

dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)

# A4 at 300 DPI
DPI = 300
A4_W = int(8.27 * DPI)
A4_H = int(11.69 * DPI)

# Marker size: 30 mm
marker_size = int(30 / 25.4 * DPI)

cols = 5
rows = 8

# Calculate equal spacing
margin_x = (A4_W - cols * marker_size) // (cols + 1)
margin_y = (A4_H - rows * marker_size) // (rows + 1)

sheet = np.ones((A4_H, A4_W), dtype=np.uint8) * 255

for marker_id in range(40):
    marker = cv2.aruco.generateImageMarker(
        dictionary,
        marker_id,
        marker_size
    )

    row = marker_id // cols
    col = marker_id % cols

    x = margin_x + col * (marker_size + margin_x)
    y = margin_y + row * (marker_size + margin_y)

    sheet[y:y + marker_size, x:x + marker_size] = marker

cv2.imwrite("aruco_40_a4.png", sheet)

print("Saved aruco_40_a4.png")
print(f"Marker size: {marker_size}px (~30mm)")