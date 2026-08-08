import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from calibrate_frame import CalibrateScreen
from precheck_frame import PreCheckScreen
from mouse_controller import MouseController
import pyautogui
import cv2
from iris_gaze_tracking import IrisGazeTracking
import numpy as np


class EyeTrackingApp(tk.Tk):
    def __init__(self, root, gaze, webcam, theme="morph"):
        self.root = root
        self.gaze = gaze
        self.webcam = webcam
        self.root.geometry("800x600")
        self.root.title("Eye Tracking App")

        self.xcoeff, self.ycoeff = None, None
        self.xEyeRange, self.yEyeRange = None, None

        # Define styles
        self.style = ttk.Style(theme=theme)
        self.style.configure("Title.TLabel", font=("Helvetica", 24, "bold"))
        self.style.configure("Subtitle.TLabel", font=("Helvetica", 14))
        self.style.configure("Instructions.TLabel", font=("Helvetica", 14, "italic"))
        self.style.configure(
            "BoldInfo.TLabel",
            font=("Helvetica", 24, "bold"),
            background="#d9edf7",
            foreground="#31708f",
            padding=10,
        )
        self.style.configure(
            "ItalicInfo.TLabel",
            font=("Helvetica", 24, "italic"),
            background="#d9edf7",
            foreground="#31708f",
            padding=10,
        )

        # Initialize the home screen
        self.init_home_screen()

        # Keybinds
        self.root.bind("<space>", self.calibration_screen)

    def init_home_screen(self):
        # Add labels to the home screen
        ttk.Label(self.root, text="Welcome to Eye TrackPad", style="Title.TLabel").pack(
            pady=28
        )
        ttk.Label(self.root, text="Start Calibration", style="Subtitle.TLabel").pack(
            pady=(100, 5)
        )
        ttk.Label(
            self.root, text="Press space bar to start.", style="Instructions.TLabel"
        ).pack(pady=5)

    def calibration_screen(self, event=None):
        # Clear the screen
        for widget in self.root.winfo_children():
            widget.destroy()
        # Check camera angle/lighting before calibration
        PreCheckScreen(self.root, self.gaze, self.webcam, self, self.start_calibration)

    def start_calibration(self):
        # Clear the screen
        for widget in self.root.winfo_children():
            widget.destroy()
        # Instantiate the Calibrate class
        CalibrateScreen(self.root, self.gaze, self.webcam, 20, 20, self)

    # get xcoeff and ycoeff from CalibrateScreen
    def get_coeffs(self):
        return self.xcoeff, self.ycoeff

    # get the calibrated eye-position ranges from CalibrateScreen
    def get_eye_ranges(self):
        return self.xEyeRange, self.yEyeRange


if __name__ == "__main__":
    cellWidth = 20
    cellHeight = 20
    screenWidth = pyautogui.size()[0]
    screenHeight = pyautogui.size()[1]

    gaze = IrisGazeTracking()
    webcam = cv2.VideoCapture(0)

    root = tk.Tk()
    app = EyeTrackingApp(root, gaze, webcam)
    root.mainloop()
    xcoeff, ycoeff = app.get_coeffs()
    xEyeRange, yEyeRange = app.get_eye_ranges()

    # Start tracking
    if np.all(xcoeff is not None) and np.all(ycoeff is not None):
        app = MouseController(
            xcoeff,
            ycoeff,
            gaze,
            webcam,
            cellWidth,
            cellHeight,
            screenWidth,
            screenHeight,
            xEyeRange,
            yEyeRange,
        )

    webcam.release()
    cv2.destroyAllWindows()
