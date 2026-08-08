# Changelog

Record of bugs found and fixes made while getting the app running and improving
calibration accuracy. Each entry explains the problem observed, the root cause,
and the fix, so the reasoning is still clear later even if the symptom isn't
fresh in memory.

## Getting the app running

**requirements.txt was UTF-16 with a BOM.** `pip install -r requirements.txt`
couldn't parse the file. Converted it to plain UTF-8.

**GazeTracking submodule was never initialized.** The `GazeTracking/` directory
existed but was empty, since `.gitmodules` was committed but the submodule
content wasn't checked out. Fixed by running `git submodule update --init`.

**Python 3.12 broke dependency installs.** The pinned versions (`numpy==1.23.5`,
`dlib==19.24.2`) don't have prebuilt wheels for 3.12. Used a Python 3.11 venv
instead, where every dependency installed cleanly, `dlib` included.

## Calibration flow

**Calibration aborted entirely if one dot failed.** In `calibrate_frame.py`,
`dot_off()` required more than 5 gaze samples per dot within ~2.5s (with a few
retries). If that failed 10 times in a row, it printed "Failed calibration"
and tore down the whole calibration window and webcam, forcing a full restart.
Changed the failure branch to reset just that dot's data and turn it back to
red, so pressing space retries the same dot instead of restarting from
scratch.

**No way to escape fullscreen calibration.** Once the auto-abort-on-failure
path above was removed, there was no way out of the fullscreen calibration
window short of force-quitting the process. Bound `<Escape>` in both
`CalibrateScreen` and `PreCheckScreen` to cleanly stop the gaze thread, exit
fullscreen, and destroy the window without computing coefficients from
incomplete data.

**Escape did nothing during actual mouse control.** The bindings above only
apply while the tkinter calibration windows are alive. Once calibration
finishes, `MouseController.startController()` takes over with its own loop
that checks `cv2.waitKey(1) == 27` for Escape -- but that only reads keyboard
input from an OpenCV window, and the app never called `cv2.imshow()`, so
there was no window for it to read from. Escape was dead code from the start
during mouse control. Fixed by showing a live annotated preview via
`cv2.imshow()` during mouse control, which gives the existing `waitKey` check
an actual window to read from.

**Last calibration dot never visibly turned green.** `dot_off()` drew the
final dot green and called `window.destroy()` in the same function call,
before Tkinter had a chance to render the change. Added `canvas.update_idletasks()`
plus a 400ms delay before closing so the green dot is actually visible.

**Added a pre-calibration camera check (`precheck_frame.py`).** New
`PreCheckScreen` shows a live annotated webcam feed next to a rolling
pass/fail status covering pupil-detection rate, glare, and darkness in the
eye region. Warns but doesn't block calibration, so a marginal setup can
still proceed if the user chooses to.

**Removed noisy per-frame debug print.** `track_gaze()` called
`print(self.eyeData)` on every collected sample, flooding the terminal and
making everything else hard to read.

## Gaze-to-mouse mapping accuracy

These were the hardest to track down, and they compounded: fixing one often
exposed the next.

**Cursor jumped to the left edge of the screen.** In
`calculateFunctionGrid()`, the line `y_eye = x_eye = data[:, 1]` is a chained
assignment: Python assigns the same value (the eye's *y*-coordinate data) to
both `y_eye` and `x_eye`, silently overwriting the correct `x_eye = data[:, 0]`
set on the line above. So the horizontal mapping was fit against vertical eye
movement instead of horizontal. Split it into two separate assignments.

**Fit was polluted by the wrong dots.** `dotPositions` is a cross layout, not
a grid: 5 dots vary in x with y held at center, and a different 5 vary in y
with x held at center (despite comments in the code calling them "corners").
`calculateFunctionGrid()` pooled all 10 dots into a single x-fit and a single
y-fit, so for the x-fit, the 5 dots that only vary in *y* contributed samples
whose x-position had incidentally drifted from head movement while their
x-pixel target stayed fixed -- pure noise, and it dominated the fit since it
outnumbered the real horizontal signal 2-to-1. Split the fit so each axis
uses only the dots where its own target actually varies
(`X_FIT_DOTS = [5,6,7,8,9]`, `Y_FIT_DOTS = [0,1,2,3,4]`).

**Cursor got stuck at a screen edge (right, then bottom, then bottom-left).**
The calibrated pupil-position range was very narrow (tens of pixels across
the whole screen). A quadratic fit over that narrow a domain is steep just
outside it: evaluating a few pixels past the calibrated range produced
predictions far outside the valid grid, which `np.clip()` then pinned to a
screen edge. Any detector jitter or drift past the calibrated range got
slammed to that edge and stayed there. Fixed two ways:
1. `CalibrateScreen` now records the min/max eye position seen per axis
   during calibration; `MouseController` clamps live readings to that range
   *before* evaluating the polynomial, so noise past the calibrated range
   can no longer cause runaway extrapolation.
2. Switched calibration and live tracking from raw pupil pixel coordinates
   (`pupil_left_coords()` / `pupil_right_coords()`) to GazeTracking's
   `horizontal_ratio()` / `vertical_ratio()`. Raw pixel coordinates conflate
   head-position drift with actual eye movement and only spanned ~20-65px
   across the whole screen. The ratio methods normalize pupil position
   within the detected eye region (0.0-1.0), specifically designed to strip
   out head position and eye-region-size variation. Verified with synthetic
   data that this widens the working range to roughly the full 0.0-1.0 scale
   instead of a 20-65px sliver -- the same absolute jitter now moves the
   cursor proportionally much less.

**Cursor could reach all four corners but stopped short of the actual edges.**
A side effect of the clamp fix above. `dotPositions` draws the outermost dots
at 0.05/0.95 screen-fraction, not 0.0/1.0, so they render fully on screen
instead of being clipped at the boundary. But `calculateFunctionGrid` used
that same 0.05/0.95 fraction directly as the fit *target*, so the mapping
only ever learned "this eye reading = 95% of the way to the edge." Before the
clamp fix, the polynomial could extrapolate a bit past that to reach the true
edge (messily -- see the stuck-at-an-edge bugs above); after clamping live
readings to the calibrated range, that extrapolation was no longer possible,
so the cursor topped out at ~95% of the way to every edge. Fixed by rescaling
the fit targets so the outermost dot (still drawn inset, for visibility) is
taught as the true edge (grid index 0 or max), not 95% of the way there.

## Still open

- **Still some jitter.** Expected, given this is visible-spectrum webcam
  pupil tracking rather than an IR-based or deep-learning gaze model; the
  3-frame moving average in `MouseController.movingAverage` already smooths
  some of it. Increasing `avgFrames` would smooth further at the cost of
  more lag. Not addressed yet -- ask if you want it tuned.
- **`dotPositions` is a cross, not a grid.** The x-fit only ever sees eye
  positions from looking left/right through screen-center, and the y-fit
  only sees up/down through center. A proper corner/grid layout would give
  a true 2D calibration instead of two independent 1D ones. Not yet
  addressed.
- **Dependabot flagged 31 vulnerabilities** (1 critical, 20 high, 9 moderate,
  1 low) in dependencies. See
  `https://github.com/afan104/GazeMouse-Accessibility/security/dependabot`.
  Deferred by request.
