         

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

**Couldn't reach top-right or bottom-left.** Two compounding causes:

1. `vertical_ratio()` was noticeably noisier at extreme upward gaze than
   anywhere else -- grouping the top calibration dot's samples showed a
   0.30-0.61 spread, nearly half the entire calibration's dynamic range,
   versus 0.1-0.2 for every other dot. Likely the upper eyelid partially
   covering the visible pupil/iris when looking up, a known limitation of
   visible-spectrum (non-IR) webcam pupil tracking, not a code bug.
2. The deeper issue: `dotPositions` was a cross (5 dots vary in x, 5 vary in
   y), and x/y were fit completely independently (see the axis-separated
   fit above). That assumes gaze decomposes additively into independent
   horizontal and vertical components -- so true diagonal positions like
   top-right were never actually measured during calibration, only assumed
   from combining the separate x and y fits. If that assumption doesn't
   hold (plausible, especially combined with #1's noise at the top), any
   diagonal corner is wrong even though each axis looks fine on its own.

Fixed by replacing the cross with a real 3x3 grid (all 4 corners + edge
midpoints + center), and replacing the two independent quadratic fits with
a single bivariate quadratic surface (basis: `1, x, y, x^2, y^2, x*y`) fit
via least squares for both `x_pixel` and `y_pixel`. Every dot, corners
included, now directly contributes to both outputs, so diagonal gaze is
directly calibrated rather than assumed. Verified with synthetic data
(including a deliberately injected nonlinear x/y coupling term) that the
surface fit correctly reproduces diagonal corners that the old independent
fits structurally couldn't represent.

## MediaPipe iris tracking rework (branch: `mediapipe-iris-tracking`)

The fixes above got calibration and mapping correct given the input signal
available, but the input signal itself (dlib + Haar cascade pupil detection)
has a real ceiling: coarse threshold-and-centroid pupil localization, no
head-pose awareness, visible-spectrum only. The goal for this branch: push
eye-tracking as far as it can go, rather than defaulting to a head-tracking
input model (a different, more robust approach for other reasons -- see the
design discussion in the branch history for the tradeoffs; this repo commits
to eye tracking specifically).

**Replaced dlib+Haar pupil detection with MediaPipe iris landmarks.**
`iris_gaze_tracking.py` wraps MediaPipe Face Mesh (`refine_landmarks=True`,
which adds real iris-center landmarks, not just eyelid contour points) and
exposes the same interface as the old `GazeTracking` class
(`refresh`/`pupils_located`/`horizontal_ratio`/`vertical_ratio`/`annotated_frame`),
so `calibrate_frame.py` and `mouse_controller.py` needed no logic changes,
only `app.py`'s instantiation swapped. Ratios are computed as the iris
center's position within each eye's corner-to-corner bounding box (landmarks
33/133/159/145 for the right eye, 263/362/386/374 for the left; iris
centers at 468/473), averaged across both eyes. Pinned `mediapipe==0.10.14`
specifically -- 1.0.0 removed the `solutions.face_mesh` API in favor of a
Tasks API that needs a separately downloaded model file, unneeded complexity
here.

**PreCheckScreen broke under the new tracker.** Its glare/darkness check
reached into `gaze.eye_left`/`gaze.eye_right`, internals specific to the old
`GazeTracking` class's isolated-eye-crop objects, which `IrisGazeTracking`
doesn't have. Moved that logic into the tracker interface itself
(`eye_brightness_stats()`), so `PreCheckScreen` no longer needs to know which
tracker implementation is behind `self.gaze`.

**Jitter: replaced the flat moving average with a One Euro Filter.** The
old 3-frame average weighted all samples equally and couldn't adapt to how
fast the signal was moving -- a fixed tradeoff between jitter and lag. Added
`one_euro_filter.py`, implementing the 1-euro filter (Casiez, Roussel,
Vogel, CHI 2012), the standard adaptive filter for noisy pointing signals:
heavy smoothing when the signal is nearly still, progressively less as it
speeds up. Verified with synthetic data: at-rest jitter (std 0.02) reduced
to std 0.0064 with the initial parameters (`min_cutoff=1.0, beta=0.5`).

**Real calibration produced huge, unstable fit coefficients (magnitudes in
the thousands).** This directly explained two symptoms reported after
testing: the cursor still jittered noticeably despite the new filter, and it
had trouble reaching the right edge specifically (while top-left/bottom-left
worked). Root cause: with only 9 calibration dots feeding a 6-parameter
quadratic surface, and a real MediaPipe ratio range likely narrower than the
idealized 0-1 scale, the surface's basis columns (`1, x, y, x^2, y^2, x*y`)
become nearly collinear, so plain least-squares produces a wildly
oscillating fit that's exactly correct at the 9 training points but
erratic everywhere else -- and any residual filter noise gets massively
amplified by those huge coefficients before it ever reaches the cursor.

Fixed two ways:

1. Added ridge regularization to the surface fit (`RIDGE_ALPHA = 0.1`).
   Tested alpha values from 0.001 to 20 against synthetic narrow-range data:
   0.1 cuts peak coefficient magnitude by roughly half to two-thirds while
   keeping corner/edge predictions within ~5% of the true target -- higher
   alpha reduces coefficients further but starts meaningfully hurting
   accuracy at the calibration points themselves.
2. Increased the One Euro Filter's baseline smoothing
   (`min_cutoff: 1.0 -> 0.15`, `beta: 0.5 -> 1.0`), verified this gives
   roughly 3x more at-rest smoothing while tracking fast deliberate moves
   just as well.

Retested live: jitter improved a lot (user reported "pretty happy with it"),
but a new pattern emerged -- confident, accurate control on the left side,
but top-right and bottom-right still unreachable, then on a further test
only the top-left corner was reliably reachable at all.

**Root cause: the polynomial surface fit was the wrong model, not just
poorly regularized.** The per-dot diagnostic added above gave the answer.
The actual calibration data was clean: tight, low-noise (std 0.007-0.02),
and consistent across repeated dots at the same screen position -- so the
earlier "noisy narrow-range data" theory was wrong. Evaluating the
regularized 6-term fit at its own 9 training points showed it was
systematically bad specifically at the 4 corners (errors up to -21 grid
cells) while edges and center fit fine. Reason: a single `x*y` cross term
can't fully capture the real 2D coupling between the two gaze ratios --
confirmed directly, since the *same* screen y-position produced measurably
different mean `vertical_ratio` depending on which x-position dot it was
(e.g. top-left's ratioY mean 0.505 vs top-right's 0.451, both nominally
"top" dots).

Tried a full 9-term biquadratic tensor basis next (matched exactly to the
3x3 grid: 9 parameters for 9 points). Fit to the 9 clean per-dot means, it
reproduced all 9 targets exactly, as expected for a square, well-posed
system. But the system turned out severely ill-conditioned (condition
number ~15.8 million), and evaluating it at points *between* calibration
dots gave wildly wrong answers -- a point that should have interpolated to
a simple midpoint predicted -63.5 instead. An exact-fit polynomial through
9 points can oscillate arbitrarily between them; this is a textbook case of
that failure mode, and it would have made the cursor behave unpredictably
everywhere except the 9 exact calibration positions.

**Fixed by replacing parametric polynomial fitting with
`scipy.interpolate.LinearNDInterpolator`** (Delaunay triangulation +
piecewise-linear interpolation) over the 9 per-dot mean ratio readings,
with `NearestNDInterpolator` as a fallback for points outside the convex
hull of the calibration data. This is exact at all 9 calibration points by
construction, and mathematically cannot overshoot between them -- each
interpolated value is a weighted average of its enclosing triangle's three
vertices, so it's bounded by nearby real measurements, not by an arbitrary
curve fit. Verified end-to-end with the real reported per-dot statistics:
all 9 positions (corners included) now predict within 1-6 grid cells of
target, versus up to 21 cells off with the polynomial fit -- top-right and
bottom-right specifically improved to 1.2 and 5.6 cells off.

`RIDGE_ALPHA` and the ridge-fit helper are gone; regularization doesn't
apply to this approach.

**Cursor sometimes jumped to halfway across the screen at an edge, then
came back.** Retested after the interpolation fix: all four corners now
reachable, jitter much improved, but this new pattern showed up, distinct
from steady small jitter. The One Euro Filter alone can't fix it, and
actually makes it worse in one specific way: it's speed-adaptive by
design, so a single-frame outlier (a blink, a momentary MediaPipe landmark
glitch) looks identical to fast deliberate movement, which *lowers*
smoothing rather than raising it -- so the cursor visibly jumps toward the
spike, then decays back over several frames as the filter catches up.

Added `median_filter.py` (`MedianFilter`, window=3) as a pre-stage before
the One Euro Filter. A median is robust to a single wild sample in a way a
low-pass filter isn't: it just returns the middle value of the recent
window, so one outlier among otherwise-normal samples gets ignored rather
than blended in. Verified with synthetic data: injecting a single-frame
spike (0.5 -> 0.9) into an otherwise steady signal, the One-Euro-only
pipeline reproduced the reported pattern exactly (jump to 0.621, decaying
0.599 -> 0.59 -> 0.582 -> 0.57 over subsequent frames); with the median
pre-filter, the same spike is almost entirely absorbed (max deviation from
baseline 0.001 vs 0.121).

**App crashed outright with `pyautogui.FailSafeException`.** Worked well
initially, then crashed with a full traceback out of `startController`.
Checked PyAutoGUI's actual implementation: `failSafeCheck()` compares the
*current* cursor position against the four exact screen corners before
every `moveTo` call. Our own targets can never land exactly on a corner --
`grid_index * cellWidth + cellWidth / 2` always insets by at least half a
cell -- so this had to be triggered by something outside our calculation,
most likely the user's actual mouse or trackpad touching a corner.

Rather than disable the failsafe (explicitly not recommended, and it's a
reasonable safety mechanism to keep), wrapped the `moveTo` call in
`try/except pyautogui.FailSafeException` and treat it the same as pressing
Escape: stop the tracking loop cleanly instead of crashing. For an
assistive tool like this, "grab your real mouse to override" is a sensible
thing to support, not just an error to suppress.

Also fixed a one-line bug noticed while touching this code: `yPixel`'s
offset used `self.cellWidth / 2` instead of `self.cellHeight / 2`.
Harmless today since both happen to be 20, but wrong if they're ever set
differently.

**`dot 6` (bottom-left) had wildly noisier data than every other dot** --
`ratioY std=0.357`, roughly 15-50x every other dot's std (0.006-0.024).
Consistent with a chunk of glitch frames during that dot's collection (a
blink, or a momentary detection failure at an extreme downward gaze
angle). Since `LinearNDInterpolator` treats each dot's summary statistic
as an exact anchor point, a contaminated *mean* directly corrupts that
whole region of the interpolated surface. Switched from mean to median.
Verified with synthetic data matching this contamination pattern (45 clean
samples around 0.45, 16 glitch samples around 0.08, ~26% contamination):
the mean gets dragged to 0.35, while the median stays at 0.434, close to
the true clean-cluster center.

**Added click support: space bar clicks during mouse control, then
replaced with dwell-click.** First pass: the cv2 preview window
(`MouseController.startController`) already reads keyboard input via
`cv2.waitKey` for the ESC-to-stop check, so the same check also triggered
`pyautogui.click()` on space (ASCII 32).

This broke as soon as it left the preview window: `cv2.waitKey` only sees
key presses while our own window has OS keyboard focus. Once the gaze
cursor was used to click into another app (e.g. TextEdit), focus followed
there, so pressing space typed a literal space into the document instead
of clicking. Binding a different key wouldn't have fixed this -- any key
would leak into whatever app has focus the same way, just as a different
stray character. It's also a poor fit for the project's actual mission: a
tool built for people who can't reliably use a mouse shouldn't then
require a reliable keyboard press to click.

Replaced with dwell-click, the standard mechanism in real eye-tracking
assistive software (Tobii Dynavox, EyeMine, etc): hold the cursor within
`DWELL_RADIUS=25px` of a spot for `DWELL_SECONDS=1.0s` and it clicks
automatically, no keyboard involved, driven entirely by the cursor
position already being tracked. Verified the dwell state machine with
mocked timestamps: fires exactly once per dwell period, resets correctly
when the cursor moves away and returns, and small in-radius jitter
(+/-5px, well under the threshold) doesn't reset the timer or cause extra
clicks.

## Still open

- **Dependabot flagged 31 vulnerabilities** (1 critical, 20 high, 9 moderate,
  1 low) in dependencies. See
  `https://github.com/afan104/GazeMouse-Accessibility/security/dependabot`.
  Deferred by request.
- **No head-pose correction.** MediaPipe exposes all 468 face landmarks
  publicly (unlike GazeTracking), so `cv2.solvePnP`-based head-pose
  correction is realistic to add here if movement tolerance still isn't
  good enough after the fixes above. Not started.
