"""
Pre-calibration camera check.

Shows a live annotated webcam preview next to a rolling pass/fail status
for pupil detection and lighting/glare, so the user can fix their camera
angle before starting calibration. Pressing space always continues to
calibration, even if the check hasn't passed.
"""

from collections import deque

import cv2
import tkinter as tk
import ttkbootstrap as ttk
from PIL import Image, ImageTk


class PreCheckScreen(tk.Frame):
    WINDOW_SIZE = 30
    MIN_SAMPLES = 15
    PUPIL_SUCCESS_THRESHOLD = 0.6
    GLARE_MAX_FRACTION = 0.3
    DARK_MIN_MEAN = 40

    def __init__(self, window, gazeObject, camObject, app, on_continue):
        self.window = window
        self.app = app
        self.gaze = gazeObject
        self.webcam = camObject
        self.on_continue = on_continue

        self.window.attributes("-fullscreen", True)

        ttk.Label(self.window, text="Camera check", style="BoldInfo.TLabel").place(
            x=100, y=50
        )
        self.status_label = ttk.Label(
            self.window, text="Checking...", style="ItalicInfo.TLabel"
        )
        self.status_label.place(x=100, y=100)
        ttk.Label(
            self.window,
            text="Center your face in the video below. Press space to start calibration.",
            style="Instructions.TLabel",
        ).place(x=100, y=150)

        self.video_label = tk.Label(self.window)
        self.video_label.place(relx=0.5, rely=0.6, anchor="center")

        self.window.bind("<space>", self.handle_space)
        self.window.bind("<Escape>", self.handle_escape)

        self.pupil_hits = deque(maxlen=self.WINDOW_SIZE)
        self.glare_hits = deque(maxlen=self.WINDOW_SIZE)
        self.dark_hits = deque(maxlen=self.WINDOW_SIZE)

        self.running = True
        self.update_frame()

    def update_frame(self):
        if not self.running:
            return

        ret, frame = self.webcam.read()
        if ret and frame is not None:
            self.gaze.refresh(frame)

            self.pupil_hits.append(self.gaze.pupils_located)
            stats = self.gaze.eye_brightness_stats()
            self.glare_hits.append(stats is not None and stats[1] > self.GLARE_MAX_FRACTION)
            self.dark_hits.append(stats is not None and stats[0] < self.DARK_MIN_MEAN)

            self.refresh_status()

            annotated = cv2.cvtColor(self.gaze.annotated_frame(), cv2.COLOR_BGR2RGB)
            image = Image.fromarray(annotated)
            image.thumbnail((480, 360))
            photo = ImageTk.PhotoImage(image=image)
            self.video_label.configure(image=photo)
            self.video_label.image = photo  # keep a reference, tkinter won't otherwise

        if self.running:
            self.window.after(30, self.update_frame)

    def refresh_status(self):
        if len(self.pupil_hits) < self.MIN_SAMPLES:
            self.status_label.configure(text="Checking...")
            return

        pupil_rate = sum(self.pupil_hits) / len(self.pupil_hits)
        glare_rate = sum(self.glare_hits) / len(self.glare_hits)
        dark_rate = sum(self.dark_hits) / len(self.dark_hits)

        problems = []
        if pupil_rate < self.PUPIL_SUCCESS_THRESHOLD:
            problems.append("Eyes not detected consistently, center your face in the video.")
        if glare_rate > 0.3:
            problems.append("Glare on your eyes, adjust lighting or camera angle.")
        if dark_rate > 0.3:
            problems.append("Too dark, add more light on your face.")

        if problems:
            self.status_label.configure(text=" ".join(problems) + " (press space to continue anyway)")
        else:
            self.status_label.configure(text="Looks good! Press space to start calibration.")

    def handle_space(self, event=None):
        self.running = False
        self.window.unbind("<space>")
        self.window.unbind("<Escape>")
        for widget in self.window.winfo_children():
            widget.destroy()
        self.on_continue()

    def handle_escape(self, event=None):
        self.running = False
        self.window.unbind("<space>")
        self.window.unbind("<Escape>")
        self.window.attributes("-fullscreen", False)
        self.window.destroy()
