"""Detect a prominent face and track its position for vertical background framing."""

from __future__ import annotations

import logging
import math
from pathlib import Path


def track_face_centers(
    video_path: str | Path,
    start: float,
    end: float,
    sample_interval: float = 1.5,
) -> list[tuple[float, float]]:
    """Return smoothed (clip-relative time, normalized horizontal face center) samples."""
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError(
            "Face-aware framing requires OpenCV. Install it with "
            '`py -m pip install -e ".[framing]"`.'
        ) from error

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV could not open video for face tracking: {video_path}")

    detector = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    )
    if detector.empty():
        capture.release()
        raise RuntimeError("OpenCV's frontal-face detection model could not be loaded.")

    duration = end - start
    sample_times = []
    current_time = 0.0
    while current_time < duration:
        sample_times.append(current_time)
        current_time += sample_interval
    if not sample_times or sample_times[-1] != duration:
        sample_times.append(duration)

    samples = []
    previous_center = 0.5
    previous_rect = None
    found_face = False
    try:
        for relative_time in sample_times:
            capture.set(cv2.CAP_PROP_POS_MSEC, (start + relative_time) * 1000)
            success, frame = capture.read()
            if not success or frame is None:
                samples.append((relative_time, previous_center))
                continue

            frame_height, frame_width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            scale = min(1.0, 1280 / frame_width)
            if scale < 1.0:
                gray = cv2.resize(
                    gray,
                    (round(frame_width * scale), round(frame_height * scale)),
                )
            faces = detector.detectMultiScale(
                gray,
                scaleFactor=1.08,
                minNeighbors=3,
                minSize=(24, 24),
            )
            if len(faces):
                selected = _select_face(faces, previous_rect)
                x, y, width, height = selected
                center = float(
                    min(1.0, max(0.0, (x + width / 2) / gray.shape[1]))
                )
                previous_center = previous_center * 0.55 + center * 0.45
                previous_rect = selected
                found_face = True
            samples.append((relative_time, previous_center))
    finally:
        capture.release()

    if not found_face:
        logging.warning(
            "No face was detected in %s; using centered blurred background framing.",
            video_path,
        )
    return samples


def _select_face(faces, previous_rect):
    if previous_rect is None:
        return max(faces, key=lambda face: face[2] * face[3])

    previous_x, previous_y, previous_width, previous_height = previous_rect
    previous_center_x = previous_x + previous_width / 2
    previous_center_y = previous_y + previous_height / 2
    previous_area = previous_width * previous_height

    def score(face):
        x, y, width, height = face
        center_x = x + width / 2
        center_y = y + height / 2
        distance = math.hypot(
            center_x - previous_center_x,
            center_y - previous_center_y,
        )
        area_penalty = abs(math.log(max(width * height, 1) / max(previous_area, 1)))
        return distance + area_penalty * 12

    return min(faces, key=score)
