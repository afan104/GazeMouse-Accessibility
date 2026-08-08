"""
Iris-based gaze tracking using MediaPipe Face Mesh's iris landmarks.

Exposes the same interface as GazeTracking.gaze_tracking.GazeTracking
(refresh, pupils_located, horizontal_ratio, vertical_ratio,
annotated_frame), so it's a drop-in replacement in calibrate_frame.py,
mouse_controller.py, and app.py. Unlike the dlib+Haar cascade pipeline,
MediaPipe gives a real iris-center landmark directly (no threshold+centroid
step), which is both more precise and more stable frame to frame.
"""

import cv2
import mediapipe as mp
import numpy as np


class IrisGazeTracking:
    # landmark indices from MediaPipe Face Mesh with refine_landmarks=True
    # (adds 10 iris landmarks, indices 468-477, to the base 468-point mesh)
    RIGHT_EYE = {"iris": 468, "outer": 33, "inner": 133, "top": 159, "bottom": 145}
    LEFT_EYE = {"iris": 473, "outer": 263, "inner": 362, "top": 386, "bottom": 374}

    def __init__(self):
        self._face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.frame = None
        self._landmarks = None

    def refresh(self, frame):
        """Refreshes the frame and re-runs face mesh detection.

        Arguments:
            frame (numpy.ndarray): The frame to analyze
        """
        self.frame = frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._face_mesh.process(rgb)
        if results.multi_face_landmarks:
            self._landmarks = results.multi_face_landmarks[0].landmark
        else:
            self._landmarks = None

    @property
    def pupils_located(self):
        """Check that a face (and therefore both irises) was detected"""
        return self._landmarks is not None

    def _eye_ratios(self, eye):
        """Returns (horizontal_ratio, vertical_ratio) for one eye: the
        iris center's position within the eye-corner bounding box,
        0.0-1.0 in each direction."""
        lm = self._landmarks
        iris = lm[eye["iris"]]
        outer = lm[eye["outer"]]
        inner = lm[eye["inner"]]
        top = lm[eye["top"]]
        bottom = lm[eye["bottom"]]

        x_min, x_max = sorted([outer.x, inner.x])
        y_min, y_max = sorted([top.y, bottom.y])

        h_ratio = (iris.x - x_min) / (x_max - x_min) if x_max > x_min else 0.5
        v_ratio = (iris.y - y_min) / (y_max - y_min) if y_max > y_min else 0.5
        return h_ratio, v_ratio

    def horizontal_ratio(self):
        """Average horizontal iris position across both eyes, 0.0-1.0"""
        if not self.pupils_located:
            return None
        hLeft, _ = self._eye_ratios(self.LEFT_EYE)
        hRight, _ = self._eye_ratios(self.RIGHT_EYE)
        return (hLeft + hRight) / 2

    def vertical_ratio(self):
        """Average vertical iris position across both eyes, 0.0-1.0"""
        if not self.pupils_located:
            return None
        _, vLeft = self._eye_ratios(self.LEFT_EYE)
        _, vRight = self._eye_ratios(self.RIGHT_EYE)
        return (vLeft + vRight) / 2

    def eye_brightness_stats(self):
        """Returns (mean_brightness, glare_fraction) across both eye
        regions in the current frame, or None if no face is detected.
        Used by PreCheckScreen for the lighting/glare check."""
        if not self.pupils_located or self.frame is None:
            return None

        gray = cv2.cvtColor(self.frame, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape[:2]

        means, glare_fractions = [], []
        for eye in (self.LEFT_EYE, self.RIGHT_EYE):
            xs = [self._landmarks[eye[k]].x for k in ("outer", "inner", "top", "bottom")]
            ys = [self._landmarks[eye[k]].y for k in ("outer", "inner", "top", "bottom")]
            x1, x2 = int(min(xs) * width), int(max(xs) * width)
            y1, y2 = int(min(ys) * height), int(max(ys) * height)
            region = gray[y1:y2, x1:x2]
            if region.size == 0:
                continue
            means.append(float(np.mean(region)))
            glare_fractions.append(float(np.mean(region > 245)))

        if not means:
            return None
        return sum(means) / len(means), max(glare_fractions)

    def annotated_frame(self):
        """Returns the main frame with the detected iris centers marked"""
        frame = self.frame.copy()
        if self.pupils_located:
            height, width = frame.shape[:2]
            for eye in (self.LEFT_EYE, self.RIGHT_EYE):
                iris = self._landmarks[eye["iris"]]
                x, y = int(iris.x * width), int(iris.y * height)
                cv2.circle(frame, (x, y), 3, (0, 255, 0), -1)
        return frame
