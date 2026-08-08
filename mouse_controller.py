import cv2
from GazeTracking.gaze_tracking import GazeTracking
import pyautogui
import numpy as np


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
        # clamped to this before the fit is evaluated, since the fit was
        # only ever validated inside this range and a quadratic can blow
        # up fast just outside it
        self.xEyeRange = xEyeRange
        self.yEyeRange = yEyeRange

        self.cellWidth = cellWidth
        self.cellHeight = cellHeight
        self.screenWidth = screenWidth
        self.screenHeight = screenHeight

        self.gridWidth = screenWidth // cellWidth
        self.gridHeight = screenHeight // cellHeight

        # Moving average
        self.xDataFrame = []
        self.yDataFrame = []
        self.avgFrames = 3

        self.startController()

    def startController(self):
        windowName = "Eye Tracking (press ESC to stop)"
        controlMouse = True
        while controlMouse:
            # We get a new frame from the webcam
            ret, frame = self.webcam.read()
            if not ret or frame is None:
                break

            # We send this frame to GazeTracking to analyze it
            self.gaze.refresh(frame)

            # Show a live preview; this also gives cv2.waitKey below an
            # actual window to read the ESC key press from.
            cv2.imshow(windowName, self.gaze.annotated_frame())
            if cv2.waitKey(1) == 27:
                break

            # Get normalized gaze ratios (0.0-1.0, robust to head position)
            if self.gaze.pupils_located:
                eyegaze = [self.gaze.horizontal_ratio(), self.gaze.vertical_ratio()]
                smoothedAvg = self.movingAverage(eyegaze)
                eyeX = self._clampToRange(smoothedAvg[0], self.xEyeRange)
                eyeY = self._clampToRange(smoothedAvg[1], self.yEyeRange)
                xPixel = (
                    np.clip(
                        int(
                            self.xcoeffs[0] * eyeX**2
                            + self.xcoeffs[1] * eyeX
                            + self.xcoeffs[2]
                        ),
                        0,
                        self.gridWidth - 1,
                    )
                    * self.cellWidth
                    + self.cellWidth / 2
                )
                yPixel = (
                    np.clip(
                        int(
                            self.ycoeffs[0] * eyeY**2
                            + self.ycoeffs[1] * eyeY
                            + self.ycoeffs[2]
                        ),
                        0,
                        self.gridHeight - 1,
                    )
                    * self.cellHeight
                    + self.cellWidth / 2
                )
                pyautogui.moveTo(xPixel, yPixel)  # move to point on screen

        self.webcam.release()
        cv2.destroyAllWindows()

    def _clampToRange(self, value, valueRange):
        if valueRange is None:
            return value
        return np.clip(value, valueRange[0], valueRange[1])

    def movingAverage(self, eyeGaze):
        self.xDataFrame.append(eyeGaze[0])
        if len(self.xDataFrame) > self.avgFrames:
            self.xDataFrame.pop(0)
        self.yDataFrame.append(eyeGaze[1])
        if len(self.yDataFrame) > self.avgFrames:
            self.yDataFrame.pop(0)
        return [np.mean(self.xDataFrame), np.mean(self.yDataFrame)]


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
