import cv2


class CameraError(Exception):
    """
    Raised when the camera source configured in config.json
    ("camera") can't be understood or opened.
    """


def open_camera(camera_config):
    """
    Open a cv2.VideoCapture based on the "camera" section of
    config.json.

    camera_config["source"] selects between:
        "phone"  -> IP camera stream, built from
                    camera_config["phone"]["ip"/"port"/"path"]
        "webcam" -> local device, camera_config["webcam"]["device_index"]

    Raises CameraError (never returns an unopened capture) so
    callers can fail with a clear message instead of a bare
    cv2 error further down the line.
    """

    source = camera_config.get("source", "phone")

    if source == "phone":

        phone = camera_config["phone"]

        video_url = (
            f"http://{phone['ip']}:{phone['port']}{phone['path']}"
        )

        capture = cv2.VideoCapture(video_url)

    elif source == "webcam":

        device_index = camera_config.get(
            "webcam",
            {}
        ).get("device_index", 0)

        capture = cv2.VideoCapture(device_index)

    else:

        raise CameraError(
            f"Unknown camera.source '{source}' in config.json "
            f"(expected 'phone' or 'webcam')"
        )

    if not capture.isOpened():

        raise CameraError(
            f"Could not open camera (source={source})"
        )

    return capture
