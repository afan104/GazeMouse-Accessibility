"""
Demonstration of the GazeTracking library.
Check the README.md for complete documentation.
"""

import cv2
from GazeTracking.gaze_tracking import GazeTracking
import tkinter as tk
import ttkbootstrap as ttk
import threading
import pyautogui
import numpy as np
import time


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
            (0.5, 0.05),  # Top-left corner
            (0.5, 0.25),
            (0.5, 0.5),  # Center
            (0.5, 0.75),
            (0.5, 0.95),  # Top-right corner
            (0.05, 0.5),  # Bottom-left corner
            (0.25, 0.5),
            (0.5, 0.5),
            (0.75, 0.5),
            (0.95, 0.5),  # Bottom-right corner
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

                left_pupil = self.gaze.pupil_left_coords()
                right_pupil = self.gaze.pupil_right_coords()

                if (
                    left_pupil
                    and right_pupil
                    and self.currentPosition < len(self.dotPositions)
                ):
                    # Record the average gaze position
                    avgGaze = [
                        (left_pupil[0] + right_pupil[0]) / 2,
                        (left_pupil[1] + right_pupil[1]) / 2,
                    ]
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

    # dotPositions is a cross: indices 5-9 vary in x (y held at center),
    # indices 0-4 vary in y (x held at center). Fitting each axis against
    # only its own varying dots keeps head-movement noise from the other
    # axis's dots out of the fit.
    X_FIT_DOTS = [5, 6, 7, 8, 9]
    Y_FIT_DOTS = [0, 1, 2, 3, 4]

    def _axis_fit_data(self, dot_indices, grid_size, eye_index, pixel_index):
        """Builds (eye_positions, pixel_targets) for one axis, using only
        the dots whose target actually varies along that axis."""
        eye_values = []
        pixel_values = []
        for i in dot_indices:
            target = int(self.dotPositions[i][pixel_index] * grid_size)
            for sample in self.eyeData[i]:
                eye_values.append(sample[eye_index])
                pixel_values.append(target)
        return np.array(eye_values), np.array(pixel_values)

    def calculateFunctionGrid(self):
        # setup grid
        gridWidth = self.screenWidth // self.cellWidth
        gridHeight = self.screenHeight // self.cellHeight

        x_eye, x_pixel = self._axis_fit_data(self.X_FIT_DOTS, gridWidth, eye_index=0, pixel_index=0)
        y_eye, y_pixel = self._axis_fit_data(self.Y_FIT_DOTS, gridHeight, eye_index=1, pixel_index=1)

        # calculate polyfit
        self.app.xcoeff = np.polyfit(x_eye, x_pixel, 2)
        self.app.ycoeff = np.polyfit(y_eye, y_pixel, 2)

        # the range actually seen during calibration, so MouseController
        # can clamp live readings and avoid extrapolating past it
        self.app.xEyeRange = (float(x_eye.min()), float(x_eye.max()))
        self.app.yEyeRange = (float(y_eye.min()), float(y_eye.max()))
        print(x_eye)
        print(y_eye)
        print(x_pixel)
        print(y_pixel)
        print(f"{self.app.xcoeff}, {self.app.ycoeff}")
