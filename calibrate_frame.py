import cv2
import tkinter as tk
import ttkbootstrap as ttk
import threading
import pyautogui
import numpy as np
import time
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator


class CalibrateScreen(tk.Frame):
    def __init__(self, window, gazeObject, camObject, cellWidth, cellHeight, app):
        self.window = window
        self.window.attributes("-fullscreen", True)
        self.app = app

        # Create a full-screen canvas
        self.canvas = tk.Canvas(window, bg="white", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Keybinds
        self.window.bind("<space>", self.dot_on)
        self.window.bind("<Escape>", self.handle_escape)

        # screen size info
        self.width = window.winfo_screenwidth()
        self.height = window.winfo_screenheight()

        # Tranformation Function Paramters
        self.cellWidth = cellWidth
        self.cellHeight = cellHeight
        self.screenWidth = pyautogui.size()[0]
        self.screenHeight = pyautogui.size()[1]
        self.xcoeffs = 0
        self.ycoeffs = 0

        # Instructions message
        self.display_instructions()

        # Corner dots information
        self.dotSize = 20
        self.currentPosition = 0
        self.dotPositions = [
            (0.05, 0.05),  # Top-left
            (0.5, 0.05),  # Top-center
            (0.95, 0.05),  # Top-right
            (0.05, 0.5),  # Center-left
            (0.5, 0.5),  # Center
            (0.95, 0.5),  # Center-right
            (0.05, 0.95),  # Bottom-left
            (0.5, 0.95),  # Bottom-center
            (0.95, 0.95),  # Bottom-right
        ]
        self.eyeData = [[] for _ in range(len(self.dotPositions))]
        self.dotShowing = False
        self.initialize_dots_as_circles()

        # Initialize gaze tracking
        self.gaze = gazeObject
        self.webcam = camObject

        # Create a thread to track the gaze
        self.collectData = False
        self.calibrate = True
        self.gazeThread = threading.Thread(target=self.track_gaze, daemon=False)
        self.gazeThread.start()
        self.lock = threading.Lock()
        self.failCollection = 0

        # Timing variables
        self.timeDelay = 500
        self.timeCollection = 3000

    def display_instructions(self):
        """
        Displays instructions to look at red dot.
        Creates a color changing block to indicate progress.
        """
        labelTop = ttk.Label(
            self.app.root,
            text="Look at the red dot until it turns green.",
            style="BoldInfo.TLabel",
        )
        labelTop.place(x=100, y=50)
        labelBottom = ttk.Label(
            self.app.root,
            text="Press space to continue.                           ",
            style="ItalicInfo.TLabel",
        )
        labelBottom.place(x=100, y=100)

    def create_dot(self, corner_index, fill, outline=""):
        """
        Creates a dot at the specified location (corner_index) on the screen with
        the specified fill and outline.
        """
        corner = self.dotPositions[corner_index]
        x = self.width * corner[0]
        y = self.height * corner[1]
        self.canvas.create_oval(
            x - self.dotSize / 2,
            y - self.dotSize / 2,
            x + self.dotSize / 2,
            y + self.dotSize / 2,
            fill=fill,
            outline=outline,
            tags="dot",
        )

    def initialize_dots_as_circles(self):
        """
        Initializes the dots as circles on the screen.
        The first dot is red, and the rest are empty circles.
        """
        # first dot is red
        self.create_dot(0, fill="red")

        # other dots empty circles
        for i in range(1, len(self.dotPositions)):
            self.create_dot(i, fill="", outline="black")

    def dot_on(self, event=None):
        """
        Starts measuring at current dot and signals for gaze tracking.
        """
        if self.currentPosition == len(self.dotPositions):
            self.window.unbind("<space>")
            return
        # current position on the screen
        x = self.width * self.dotPositions[self.currentPosition][0]
        y = self.height * self.dotPositions[self.currentPosition][1]

        # Make dot yellow and start gaze tracking collection
        self.create_dot(self.currentPosition, fill="yellow")
        self.collectData = True

        self.dotShowing = True  # turns on gaze tracking
        self.window.after(2000, self.dot_off)

    def dot_off(self, event=None):
        """
        After 2 seconds, turns off measuring at dot and stops gaze tracking.
        Changes dot to green color and next dot to red color.
        """
        with self.lock:
            if len(self.eyeData[self.currentPosition]) > 5:
                self.collectData = False
                self.failCollection = 0

                self.currentPosition += 1
                self.dotShowing = False  # turns off gaze tracking
                self.create_dot(self.currentPosition - 1, fill="green")

                # make next one red
                if self.currentPosition != len(self.dotPositions):
                    self.create_dot(self.currentPosition, fill="red")
                else:
                    self.calibrate = False
                    self.canvas.update_idletasks()  # render the green dot before we close
                    self.window.after(400, self.finish_calibration)
            elif self.failCollection < 10:
                print("not enough data collected, waiting...")
                self.failCollection += 1
                self.window.after(500, self.dot_off)
            else:
                print("Not enough data collected for this dot. Retrying, press space to try again.")
                self.collectData = False
                self.dotShowing = False
                self.failCollection = 0
                self.eyeData[self.currentPosition] = []
                self.create_dot(self.currentPosition, fill="red")

    def finish_calibration(self):
        self.window.attributes("-fullscreen", False)
        self.window.destroy()
        self.exit_fullscreen()

    def handle_escape(self, event=None):
        """Aborts calibration early without computing coefficients from partial data."""
        self.calibrate = False
        self.collectData = False
        self.window.unbind("<space>")
        self.window.unbind("<Escape>")
        self.window.attributes("-fullscreen", False)
        self.window.destroy()

    def track_gaze(self):
        """
        Tracks the gaze of the user and records the pupil position data.
        """

        while self.calibrate:
            if self.collectData:
                ret, frame = self.webcam.read()
                if not ret or frame is None:
                    print("Error getting frames.")
                    self.calibrate = False
                    self.window.attributes("-fullscreen", False)
                    self.window.destroy()
                    self.webcam.release()
                    cv2.destroyAllWindows()
                    self.exit_fullscreen()
                    break
                self.gaze.refresh(frame)

                if self.gaze.pupils_located and self.currentPosition < len(
                    self.dotPositions
                ):
                    # Record the normalized gaze ratios (0.0-1.0, robust to
                    # head position) instead of raw pupil pixel coordinates
                    avgGaze = [self.gaze.horizontal_ratio(), self.gaze.vertical_ratio()]
                    with self.lock:
                        self.eyeData[self.currentPosition].append(avgGaze)
            else:
                time.sleep(0.1)
        print("done")

    def exit_fullscreen(self, event=None):
        # mappingfunction
        if self.failCollection == 0:
            # code for calculating coefficients....

            self.calculateFunctionGrid()

        # stop thread
        self.calibrate = False
        # if self.gazeThread.is_alive():
        #     self.gazeThread.join()

    # dots are drawn inset from the screen edge (0.05-0.95, not 0.0-1.0) so
    # they're fully visible during calibration. The fit targets are rescaled
    # so the outermost dots still teach the true screen edge, not a point
    # 5% short of it -- otherwise, once live readings are clamped to the
    # calibrated range, the cursor can never reach the actual edge.
    DOT_MARGIN = 0.05

    def _rescale(self, fraction):
        span = 1 - 2 * self.DOT_MARGIN
        return (fraction - self.DOT_MARGIN) / span

    def calculateFunctionGrid(self):
        """Maps gaze ratios (horizontal_ratio, vertical_ratio) to screen
        position using piecewise-linear scattered interpolation
        (scipy.interpolate.LinearNDInterpolator) over the 9 calibration
        dots' mean ratio readings, instead of fitting a parametric
        polynomial surface.

        A parametric quadratic surface was tried first (6-term, then a
        full 9-term biquadratic tensor basis) and rejected: the real
        per-dot ratio data is tight and low-noise (std ~0.01-0.02), but the
        9-point system is severely ill-conditioned (condition number in
        the millions) even for a matched 9-parameter basis, so any exact
        or near-exact fit at the calibration points oscillated wildly
        *between* them -- verified this produced predictions wildly
        outside the valid screen range at points a person would actually
        look at during normal use, not just at extreme corners.
        LinearNDInterpolator (Delaunay triangulation + linear
        interpolation) is exact at all 9 calibration points by
        construction and mathematically cannot overshoot between them,
        since each interpolated value is a weighted average of its
        triangle's three vertices."""
        gridWidth = self.screenWidth // self.cellWidth
        gridHeight = self.screenHeight // self.cellHeight

        dotRatios, dotTargetsX, dotTargetsY = [], [], []
        print(f"gridWidth={gridWidth}, gridHeight={gridHeight}")
        for i, (xFrac, yFrac) in enumerate(self.dotPositions):
            pixelX = int(self._rescale(xFrac) * gridWidth)
            pixelY = int(self._rescale(yFrac) * gridHeight)
            dotRatioX = [sample[0] for sample in self.eyeData[i]]
            dotRatioY = [sample[1] for sample in self.eyeData[i]]
            if not dotRatioX:
                continue
            meanX, meanY = float(np.mean(dotRatioX)), float(np.mean(dotRatioY))
            print(
                f"dot {i} @ screen({xFrac},{yFrac}) -> target({pixelX},{pixelY}): "
                f"n={len(dotRatioX)} "
                f"ratioX mean={meanX:.3f} std={np.std(dotRatioX):.3f} "
                f"ratioY mean={meanY:.3f} std={np.std(dotRatioY):.3f}"
            )
            dotRatios.append((meanX, meanY))
            dotTargetsX.append(pixelX)
            dotTargetsY.append(pixelY)

        points = np.array(dotRatios)
        self.app.xcoeff = (
            LinearNDInterpolator(points, np.array(dotTargetsX, dtype=float)),
            NearestNDInterpolator(points, np.array(dotTargetsX, dtype=float)),
        )
        self.app.ycoeff = (
            LinearNDInterpolator(points, np.array(dotTargetsY, dtype=float)),
            NearestNDInterpolator(points, np.array(dotTargetsY, dtype=float)),
        )

        # the range actually seen during calibration, so MouseController
        # can clamp live readings and avoid extrapolating past it
        self.app.xEyeRange = (float(points[:, 0].min()), float(points[:, 0].max()))
        self.app.yEyeRange = (float(points[:, 1].min()), float(points[:, 1].max()))
        print(f"ratioX range: {self.app.xEyeRange}, ratioY range: {self.app.yEyeRange}")
