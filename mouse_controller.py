import time

import cv2
import pyautogui
import numpy as np

from one_euro_filter import OneEuroFilter
from median_filter import MedianFilter


class MouseController:
    def __init__(
        self,
        xcoeffs,
        ycoeffs,
        gaze,
        webcam,
        cellWidth,
        cellHeight,
        screenWidth,
        screenHeight,
        xEyeRange=None,
        yEyeRange=None,
    ):
        self.xcoeffs = xcoeffs
        self.ycoeffs = ycoeffs
        self.gaze = gaze
        self.webcam = webcam

        # the pupil-position range seen during calibration; readings are
        # clamped to this before interpolating, as an extra guard on top
        # of the NearestNDInterpolator fallback in _evaluateSurface
        self.xEyeRange = xEyeRange
        self.yEyeRange = yEyeRange

        self.cellWidth = cellWidth
        self.cellHeight = cellHeight
        self.screenWidth = screenWidth
        self.screenHeight = screenHeight

        self.gridWidth = screenWidth // cellWidth
        self.gridHeight = screenHeight // cellHeight

        # Median filter first: rejects single-frame outlier spikes (a
        # blink, a momentary detection glitch) that the One Euro Filter
        # alone would treat as fast deliberate movement and smooth less,
        # not more -- that's what caused the cursor to jump toward a
        # spike and slowly decay back instead of just ignoring it.
        self._xMedian = MedianFilter(window=3)
        self._yMedian = MedianFilter(window=3)

        # One Euro Filter: smooths heavily when the gaze signal is nearly
        # still (jitter), and less as it speeds up (avoids lag on
        # deliberate moves). beta controls how much cutoff increases with
        # speed -- tune here based on how it feels in practice.
        self._xFilter = OneEuroFilter(min_cutoff=0.15, beta=1.0)
        self._yFilter = OneEuroFilter(min_cutoff=0.15, beta=1.0)

        self.startController()

    def startController(self):
        windowName = "Eye Tracking (ESC to stop, SPACE to click)"
        controlMouse = True
        while controlMouse:
            # We get a new frame from the webcam
            ret, frame = self.webcam.read()
            if not ret or frame is None:
                break

            # We send this frame to GazeTracking to analyze it
            self.gaze.refresh(frame)

            # Show a live preview; this also gives cv2.waitKey below an
            # actual window to read key presses from.
            cv2.imshow(windowName, self.gaze.annotated_frame())
            key = cv2.waitKey(1)
            if key == 27:  # ESC
                break
            elif key == 32:  # SPACE
                pyautogui.click()

            # Get normalized gaze ratios (0.0-1.0, robust to head position)
            if self.gaze.pupils_located:
                eyegaze = [self.gaze.horizontal_ratio(), self.gaze.vertical_ratio()]
                smoothedAvg = self.smooth(eyegaze)
                eyeX = self._clampToRange(smoothedAvg[0], self.xEyeRange)
                eyeY = self._clampToRange(smoothedAvg[1], self.yEyeRange)
                xPixel = (
                    np.clip(
                        int(self._evaluateSurface(self.xcoeffs, eyeX, eyeY)),
                        0,
                        self.gridWidth - 1,
                    )
                    * self.cellWidth
                    + self.cellWidth / 2
                )
                yPixel = (
                    np.clip(
                        int(self._evaluateSurface(self.ycoeffs, eyeX, eyeY)),
                        0,
                        self.gridHeight - 1,
                    )
                    * self.cellHeight
                    + self.cellHeight / 2
                )
                try:
                    pyautogui.moveTo(xPixel, yPixel)  # move to point on screen
                except pyautogui.FailSafeException:
                    # Our own targets are always inset from the screen edge
                    # (never an exact corner), so this means the real cursor
                    # was already at a corner when we tried to move it --
                    # most likely the user grabbed their physical mouse or
                    # trackpad. Treat that the same as pressing Escape:
                    # relinquish control instead of crashing the app.
                    print("Fail-safe corner touched, stopping mouse control.")
                    break

        self.webcam.release()
        cv2.destroyAllWindows()

    def _clampToRange(self, value, valueRange):
        if valueRange is None:
            return value
        return np.clip(value, valueRange[0], valueRange[1])

    def _evaluateSurface(self, interpolators, x, y):
        """Evaluates the piecewise-linear scattered interpolation from
        calculateFunctionGrid: interpolators is (LinearNDInterpolator,
        NearestNDInterpolator), the second used as a fallback when (x, y)
        falls outside the convex hull of the calibration points, where
        LinearNDInterpolator returns NaN."""
        linear, nearest = interpolators
        value = linear(x, y)
        if np.isnan(value):
            value = nearest(x, y)
        return float(value)

    def smooth(self, eyeGaze):
        medianX = self._xMedian.filter(eyeGaze[0])
        medianY = self._yMedian.filter(eyeGaze[1])
        timestamp = time.time()
        return [
            self._xFilter.filter(medianX, timestamp),
            self._yFilter.filter(medianY, timestamp),
        ]


# # GRAVITATE MOUSE TOWARD CLICKABLE ITEMS (NOT INTEGRATED)
#     # launch google
#     mainGoogle = 'https://www.google.com/'
#     driver = webdriver.Chrome()
#     driver.maximize_window()
#     driver.get(mainGoogle)

#     scannedElements = getClickableElements(driver )
#     scanFlag = False
#     xPixel, yPixel = weight_elements(xPixel, yPixel, scannedElements)

# def getClickableElements(driver):
#     # Get all button and anchor (link) elements
#     buttons = driver.find_elements(By.CSS_SELECTOR, 'button, a')
#     searchbars= driver.find_elements(By.NAME, 'q')
#     buttons.extend(searchbars)
#     elements = []
#     for button in buttons:
#         if button.is_displayed():  # Only consider visible buttons
#             location = button.location  # Get the top-left coordinates of the element
#             size = button.size  # Get the width and height of the element

#             # Calculate the center coordinates
#             center_x = location['x'] + size['width'] / 2
#             center_y = location['y'] + size['height'] / 2
#             elements.append([center_x, center_y])

#             print(f"Clickable element: {button.text}, Center: ({center_x}, {center_y})")
#     return elements


# def calculate_distance(point1, point2):
#     return np.sqrt((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2)

# # Function to weight elements by proximity
# def weight_elements(gaze_x, gaze_y, elements, snap_threshold=120, weight_exponent=6):
#     gaze_point = (gaze_x, gaze_y)
#     distances = []

#     for index, element in enumerate(elements):
#         dist = calculate_distance(gaze_point, element)
#         distances.append((index, dist))

#     # Sort clickable elements by distance from gaze point
#     distances = sorted(distances, key=lambda tup: tup[1])

#     # Apply weights based on proximity
#     total_weight = 0
#     weighted_position = np.array([0.0, 0.0])

#     for element, distance in distances:
#         if distance < snap_threshold:
#             weight = (snap_threshold - distance) ** weight_exponent
#             weighted_position += np.array(elements[element]) * weight
#             total_weight += weight

#     # Return weighted average position if within threshold
#     if total_weight > 0:
#         return weighted_position / total_weight
#     else:
#         return gaze_point  # Return original gaze point if no snapping
