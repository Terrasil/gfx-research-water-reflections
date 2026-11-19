# gfx-research-water-reflections

A controlled OpenGL experiment on **first-hit accuracy in screen-space reflections**. A tangent-plane Newton proposal refines the first depth-buffer bracket. The experiment tests whether this improves recovery of visible reflected objects at a fixed coarse budget. The same code also traces a polished, tilted metal panel.

![Interactive experiment with the quay scene](docs/preview.png)

## Hypothesis and methods

Compare guarded Newton with bisection on exactly the same projected segment and first sign-changing interval. The primary endpoint is recall of geometrically correct first hits among reference hits represented by the primary camera buffer. Track the change in wrong accepted hits per receiver. An increase above 0.005 is the prespecified material cost in this rate.

| Method ID | Coarse traversal and refinement |
|---|---|
| `uniform-bisect` | Uniform world-distance samples, followed by up to four bisections |
| `projective-bisect` | Uniform projected fractions with perspective-correct distances, followed by bisection |
| `projective-secant` | Same bracket, four guarded secant proposals, midpoint on rejection |
| `guarded-newton` | Same bracket, four guarded tangent-plane proposals, midpoint on rejection |
| `free-newton` | Unbracketed seed at 35% of the projected segment, up to six updates |

For a ray `O + t*d`, the tangent-plane update is `dot(N, P-O) / dot(N, d)` at a visible sample P. The guarded variant rejects a near-parallel denominator, a nonfinite step and any proposal outside the open bracket. A discontinuity can still mimic a root. First-object identity and distance are verified against an analytic scene intersection in a separate pass. The sky evaluator is identical for all methods. The primary metrics use linear reflection radiance before water tint and Fresnel.

The Newton inspiration is the 2026 JCGT work on **refractions and caustics** by Mayer, Assarsson and Sintorn. This project applies the update to reflected rays. Its projective comparator uses a budgeted traversal based on perspective-correct interpolation. It can skip pixels on long rays.

## Scene and evaluation matrix

| Scene | Purpose |
|---|---|
| `quay` | Broad planar targets, sphere and layered quay structures |
| `pilings` | Thin posts and crossbar against a rear wall |
| `occluded-bank` | Hidden, oblique and out-of-view surfaces |
| `tilted-metal` | Finite polished panel with fixed normal, separate transfer test |
| `empty-sky` | Null test. Every receiver must select the common environment |

The publication profile evaluates three cameras, two wave slope scales (0 and 0.14), and two coarse budgets (12 and 32). The tilted panel and empty control need only a flat normal. The empty control uses one camera. Captures are 640 × 360 pixels. There are **22 quality cases, 220 method images with accompanying raw buffers, and 24,000 raw timing queries**. Timing uses the quay and pilings at slope 0.14.

### Recorded quantities

- The first geometric hit is classified as observable when it projects into frame, has the same ID as the primary texel and lies within `max(0.03, 2 * world_pixel_width)` of that texel's stored position. Offscreen hits, unresolved in-frame geometry, environment and nonreceivers have distinct codes.
- `visible_recall` counts recovered observable first hits. A prediction must have the right object and a ray distance within the per-hit tolerance. `wrong_hits_per_receiver`, `precision`, `sky_false_positive`, per-class linear RGB RMSE, probes and midpoint fallbacks expose other trade-offs. Empty denominators remain blank.
- `reference.npz` stores linear RGB, positions and normals, masks, and RGBA diagnostics (object ID, first-hit distance, visibility class, distance tolerance). Class codes are 0 nonreceiver, 1 environment, 2 offscreen, 3 in-frame unresolved and 4 observable. The opaque ground is a real geometric object.
- Each method's `raw.npz` includes linear RGB and diagnostics (object ID, ray distance, depth probes, midpoint fallbacks). A predicted ID of -1 denotes a nonreceiver, 0 denotes an environment fallback. `regions.png` displays environment in blue, offscreen in orange, unresolved in red, observable in green.
- The primary summary fixes 32 steps and slope 0.14. It averages the three views within each water scene, then weights the three water scenes equally. Positive recall differences favor guarded Newton. The tilted metal panel is reported separately from that mean.

## Run on Windows

The automated runner uses Python 3.10 or later and a desktop OpenGL 4.3 context. It compiles the same GLSL files as the native viewer. The following PowerShell commands run from the extracted project directory.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools/study.py run --profile smoke --out runs/smoke
```

To run the hardware series on a Radeon RX 9070 XT and import the results into the companion paper, extract the two archives side by side. The optional renderer check verifies the active adapter. The command log and detected device are retained in the run manifest.

```powershell
.\.venv\Scripts\python.exe tools/study.py run --profile paper --out runs/rx9070xt --expect-renderer "9070 XT"
.\.venv\Scripts\python.exe tools/study.py analyze runs/rx9070xt --paper ../gfx-research-water-reflections-paper
```

Run the same command with `--resume` to continue an interrupted recording. Complete cases are verified and reused. A changed plan, code hash or device requires a fresh output directory. The working directory can contain spaces. Linux uses `.venv/bin/python` and EGL by default. On Windows the offscreen runner uses the default WGL context. On systems with multiple EGL devices, `--device INDEX` selects an adapter. Run `tools/study.py plan --profile paper` to print the entire case matrix without creating a graphics context.

| Profile | Intended use | Quality size | Timing size | Blocks × measured draws, per method and timing case |
|---|---|---|---|---|
| `smoke` | Validate the data and report pipeline on all five scenes | 144 × 80 | 144 × 80 | 1 × 3 |
| `quick` | Inspect camera, budget and parameter sensitivity | 320 × 180 | 640 × 360 | 3 × 10 |
| `paper` | Record the declared hardware suite | 640 × 360 | 1280 × 720 and 1920 × 1080 | 5 × 40 |

## Interactive viewer

The C++20 viewer uses CMake 3.25+, an OpenGL 4.6 core driver and `gfx-research-base v0.3`. First configuration downloads the base and its dependencies. With Ninja and a C++ toolchain on PATH:

```powershell
cmake -S . -B out/build -G Ninja -DCMAKE_BUILD_TYPE=Release "-DPython3_EXECUTABLE=$PWD/.venv/Scripts/python.exe"
cmake --build out/build --parallel
ctest --test-dir out/build --output-on-failure
.\out\build\gfx-research-water-reflections.exe
```

A local base checkout can be supplied with `-DGFX_RESEARCH_BASE_LOCAL_PATH=../gfx-research-base` at configuration. On Linux pass the absolute path to the virtual environment interpreter or activate it before configuring. The project locates its shaders in the source checkout.

| Control | Action |
|---|---|
| Experiment | Select method, budget, physical parameter and the geometric reference |
| Scene | Select geometry, camera, shaded image, isolated signal or traversal work |
| Capture | Save a clean PNG, or start a suite and close the preview to release the GPU |
| F1 / F9 | Toggle the panel / save the current image without UI |
| `--capture DIRECTORY` | Render the default view, save a clean PNG and exit |

GUI screenshots go to `captures/` under the launch directory. Their names carry the scene, view, method, budget, parameter and display mode. GUI-launched runs go to `runs/` in the project. The menu preview shown above was captured on software OpenGL. Its FPS is specific to that preview.

## Reproduce and inspect the data

1. Run the short profile and inspect `manifest.json`. It records the renderer, driver string, backend, OS, dependency versions, source SHA-256, exact plan, seed, command and completion state. A manual driver or clock note can be attached via `--hardware-note`.
2. The `quality/CASE` directory contains ground truth data and clean images. Each `bBUDGET/METHOD` subdirectory contains `scene.png`, `signal.png`, `error.png` and `raw.npz`. White is absolute linear error of 0.25 or greater in all error images. The stored arrays retain their full floating-point range. The first array row is the top of the image.
3. The `timing/CASE/timing.csv` rows retain individual GPU elapsed times in nanoseconds, method order, block and sample index. Only the uninstrumented effect draw is timed. GPU readback, geometry, reference rendering and image encoding happen outside the timed draws. Pair comparisons by case and block; images and consecutive frames share data.
4. `report/` contains aggregated quality and raw timing CSVs, per-block median and p95, paired differences, a fixed comparison panel and a LaTeX results fragment. The standalone `analyze` command verifies file hashes and recalculates the quality metrics from the NPZ files before import. It can be run on a machine without a graphics context after installing NumPy and Pillow.
5. Run the CPU cross-check with `.\.venv\Scripts\python.exe tests/test_reference.py`. It compares independent double-precision intersections with GPU outputs for the default scene. Challenge scenes also have method-independent reference masks and the empty-scene control.

The publication archive carries the editable manuscript and bibliography. To reproduce an archived run later, retain the project revision together with the complete run directory.
