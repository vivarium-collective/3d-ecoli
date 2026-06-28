# 3d-ecoli VR Usability — Phase 1 Design

**Date:** 2026-06-28
**Status:** Approved (design); ready for implementation plan
**Scope:** Phase 1 of 2. Phase 1 makes the existing VR mode *usable* on Meta Quest.
Phase 2 (separate spec) adds an in-VR control panel mirroring the 2D viewer's side menu.

## Context

3d-ecoli builds a packed 3D model of a whole *E. coli* cell and stages it into a
three.js WebGL viewer. The viewer (2D/desktop + WebXR/VR) and its code live in
**`pbg-parsimony/pbg_parsimony/viewer/`** — not in `3d-ecoli`. 3d-ecoli builds the
data pack (`ecoli_3d/build.py`) and stages the viewer from pbg-parsimony into a
publishable bundle (`ecoli_3d/publish/03_assemble_local_view.py`), which is pushed to
Cloudflare R2 (`ecoli_3d/publish/04_publish_r2.sh`). Live viewer:
`https://pub-eb913fbbdc584bd7add047c823570b13.r2.dev/viewer/index.html`.

Key viewer files:
- `pbg-parsimony/pbg_parsimony/viewer/vr.js` — WebXR session, dolly rig, grab + stick locomotion.
- `pbg-parsimony/pbg_parsimony/viewer/viewer.js` — three.js scene, LOD/mesh streaming (`reassessLODs`), main loop (`tick`), VR wiring (`initVR` call ~line 3200).
- `pbg-parsimony/pbg_parsimony/viewer/index.html` — DOM + CSS, `#vr-button`, side menu.

### Workflow constraint (shapes the whole effort)
All edits land in **pbg-parsimony**, then must be re-staged + re-published before they
can be tested on the headset. Each on-headset test requires physically donning the
Quest. To cut the loop, we use the **Immersive Web Emulator** browser extension to
fake a headset + controllers on desktop and verify most logic before each Quest pass.
Work is batched accordingly: land a coherent set of fixes, emulator-verify, then one
Quest pass per batch — not one Quest pass per change.

## Problem (observed on-device)

Entering VR works, but:
1. **Molecules stay egg-shaped and never sharpen** as you approach — stuck on the
   coarse ellipsoid fallback spheres.
2. **Can't zoom in / interact** — zoom and grab feel unresponsive.
3. **Glitchy and nausea-inducing** — frame hitches plus smooth self-motion.

### Root causes (traced in code)
- **Eggs never sharpen:** In VR, `tick()` (`viewer.js:3150-3156`) deliberately does
  *not* call `reassessLODs()` per frame — only once on entry (camera parked
  `START_BACK = 16000` Å away) and again each time a mesh finishes loading. Moving or
  zooming never re-evaluates LOD, so finer meshes are never requested. The VR LOD pick
  is also pinned to a fixed coarse level (`VR_LOD_INDEX`, `viewer.js:1818-1829`) rather
  than distance-aware.
- **Zoom feels dead:** Zoom (two-hand pinch `vr.js:216-241`; right-stick-Y
  `vr.js:315-322`) does change `dolly.scale`, but nothing schedules a reassess, so
  detail never improves — it reads as "nothing happened."
- **Grab can die:** Grab reads grip(button[1]) **or** trigger(button[0]) only
  (`vr.js:189-195`); a controller-binding quirk or hand-tracking-only session loses it.
- **Nausea:** Smooth fly (`vr.js:293-299`) + continuous scale-about-head
  (`vr.js:315-322`) are classic vestibular-mismatch triggers, compounded by frame
  hitches from mesh parsing.

## Goals

- Molecules render as real shapes and **sharpen as the user pulls the cell closer**.
- **Grab-to-explore** (one-hand drag, two-hand pinch-to-scale) is the comfortable,
  reliable primary interaction; zoom visibly improves detail.
- **No dizziness** under normal use: grab-first, comfort vignette on smooth motion,
  snap-turn retained.
- **Stable framerate** — the Quest GPU can never be overcommitted into a hitch/hang.
- A short, dismissible **in-VR controls hint** so the interaction model is discoverable.

## Non-goals (Phase 1)

- The in-VR molecule-selection / view-settings control panel → **Phase 2**.
- Membrane rendering in VR (stays hidden, as today).
- Hand-tracking gestures beyond "pinch = grab."
- Any change to the desktop/2D viewer behavior.

## Design

All changes are VR-path-only (guarded by `renderer.xr.isPresenting`) so the desktop
path is untouched.

### 1. Fix "eggs never sharpen" (LOD reassess on VR navigation)
- Add a **debounced VR reassess**: when VR navigation changes the view (grab-release,
  two-hand pinch-end, right-stick-Y zoom idle, smooth-fly idle), schedule
  `reassessLODs()` ~150–200 ms after motion **settles**. Never reassess mid-motion
  (that re-walks the whole drawn set and causes the hitch the current code avoids).
- Implementation sketch: `updateVR(dt)` already knows when grab/zoom/fly are active
  (it returns/branches on them). Have it mark "view changed" + "motion idle since T";
  `tick()` calls a `maybeReassessVR()` that fires `scheduleReassess()` once the idle
  window elapses. Reuse the existing `scheduleReassess` debounce machinery
  (`viewer.js:1669-1677`).
- Make the VR LOD pick **distance-aware** again: replace the fixed `VR_LOD_INDEX` pin
  with the normal projected-size pick (`viewer.js:1800-1817`) clamped to a coarsest
  floor for safety, so approaching the cell selects finer LODs. The per-frame
  **VR triangle budget** (`viewer.js:1719-1724, 1860-1876`) remains the hard safety cap.

### 2. Grab-to-explore as the primary, reliable interaction
- Keep one-hand drag + two-hand pinch-to-scale (`vr.js:175-262`) — already comfortable.
- **Harden the grab read** (`isGrabbing`, `vr.js:189-195`): treat grab as true on
  grip **or** trigger **or** a hand-tracking pinch (`inputSource.hand` pinch / selectstart),
  so a binding quirk or controllers-off session still grabs.
- Ensure zoom paths (two-hand pinch + right-stick-Y) mark "view changed" so the
  debounced reassess (above) runs and detail visibly improves after zoom.

### 3. Comfort
- **Radial comfort vignette:** a screen-space dark radial mask that fades *in* during
  smooth fly / continuous scale-about-head and fades *out* when still or grabbing.
  Implement as a fixed overlay quad on the XR camera (or a fullscreen DOM/canvas layer
  composited in the XR layer) driven by current smooth-motion magnitude. Grab-driven
  motion does **not** trigger the vignette (hand-locked motion is low-nausea).
- Keep 30° snap-turn (`vr.js:303-312`).
- Demote smooth-fly to a gentler default (`FLY_SPEED` lowered); still available on the
  left stick as secondary locomotion.

### 4. Framerate stability
- Verify foveation + 0.8× framebuffer scale apply (`vr.js:107-109`).
- **Adaptive VR triangle budget:** track measured fps (the `tick()` fps accumulator,
  `viewer.js:3186-3194`). If fps drops below a target (e.g. < ~66 on a 72 Hz Quest),
  shrink `VR_TRIANGLE_BUDGET` for subsequent reassess passes (more sphere proxies, fewer
  meshes) until fps recovers; raise it back gradually when there's headroom. Bounds the
  GPU so it can't be pushed into a hang/forced-restart state.

### 5. Discoverability
- On VR entry, show a small, **auto-dismissing in-VR hint** (~6 s, or until first grab):
  "Grab to move · Two hands to zoom · Right stick to turn · Face button to exit."
  Rendered as a world- or camera-anchored panel in the XR scene (not a DOM element,
  which is invisible while immersed). Keep it lightweight (single text texture/sprite).

## Testing strategy

1. **Desktop emulator:** Immersive Web Emulator extension. Verify: VR entry/exit, grab
   drag (one + two hand), pinch scale, stick fly + snap-turn, that reassess fires after
   motion settles and LODs upgrade, vignette fade in/out, hint appears/dismisses.
2. **Unit-ish checks where feasible:** pure helpers (debounce/idle timing, adaptive-budget
   math, grab-state resolution from a synthetic gamepad/hand input) tested in isolation.
3. **Quest pass per batch:** confirm shapes sharpen on approach, no dizziness, stable fps,
   controls discoverable. Verify no regression to the desktop/2D viewer.

## Risks / open questions

- **Emulator fidelity:** the emulator won't reproduce real Quest GPU limits or hand-
  tracking exactly; framerate/comfort still need a real Quest pass.
- **Vignette in XR layers:** compositing a screen-space vignette correctly in the WebXR
  render path may need an XR-camera-attached quad rather than a DOM overlay; spike early.
- **Reassess timing:** the idle window (150–200 ms) trades responsiveness vs. hitch-
  avoidance; tune on-device.
- **Publishing cadence:** confirm who runs the stage+publish step for each Quest pass
  (assumed: re-run `03_assemble_local_view.py` → `04_publish_r2.sh`).

## Acceptance criteria

- Pulling the cell closer in VR causes molecules to load finer meshes and visibly sharpen
  (no permanent eggs), without mid-motion hitching.
- Grab (one + two hand) works reliably across grip/trigger/pinch; zoom changes scale and
  improves detail.
- Smooth motion shows a comfort vignette; grab motion does not; snap-turn retained.
- Framerate stays stable (adaptive budget engages under load); no GPU hang.
- An in-VR controls hint appears on entry and auto-dismisses.
- Desktop/2D viewer behavior is unchanged.
