# 3d-ecoli VR Usability Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing 3d-ecoli WebXR mode usable on Meta Quest — molecules sharpen as you approach, grab-to-explore is the reliable primary interaction, no dizziness, stable framerate, discoverable controls.

**Architecture:** All viewer/VR code lives in `pbg-parsimony/pbg_parsimony/viewer/` (vanilla ES modules, no bundler). We extract the *pure, testable* logic (grab resolution, motion-settle gate, adaptive triangle budget, vignette curve) into a new `vr-helpers.js` module unit-tested with Node's built-in `node:test`, and wire those helpers into `vr.js` (session/locomotion) and `viewer.js` (LOD/render loop). Visual/integration behavior is verified in the Immersive Web Emulator on desktop, then on a real Quest. Every change is guarded by `renderer.xr.isPresenting` so the desktop path is untouched.

**Tech Stack:** JavaScript (ES modules), three.js 0.160 (via CDN importmap), WebXR, Node 25 (`node --test`) for unit tests, Immersive Web Emulator (Chrome/Edge extension) for desktop XR verification.

## Global Constraints

- All code edits land in `/Users/eranagmon/code/pbg-parsimony/pbg_parsimony/viewer/` — **not** in `3d-ecoli`.
- Desktop/2D viewer behavior MUST be unchanged: every behavioral change is guarded by `renderer.xr.isPresenting` (or the VR-only `vr.js` path).
- No new runtime dependencies, no bundler, no CDN additions. New code is plain ES modules.
- `vr-helpers.js` MUST stay free of any `three` import (pure logic only) so it runs under `node --test` with no DOM/WebGL.
- New viewer source files MUST be added to the publish copy list `ecoli_3d/publish/03_assemble_local_view.py:26` or they won't ship.
- Browser module cache is busted via `?v=N` query strings: `index.html` loads `./viewer.js?v=50`; `viewer.js` imports `./vr.js?v=46`. Bump the relevant query whenever the imported file changes (final publish task).
- Unit tests run from the viewer dir with `node --test`. A test-only `package.json` (`{"type":"module"}`) makes Node treat `.js` as ESM; it is source-only and never staged/published.

---

### Task 1: Test harness + hardened grab read (`resolveGrab`)

Establishes the Node test cycle and fixes the "grab sometimes dies" problem by accepting grip **or** trigger **or** hand-pinch.

**Files:**
- Create: `pbg-parsimony/pbg_parsimony/viewer/package.json` (test-only, `{"type":"module"}`)
- Create: `pbg-parsimony/pbg_parsimony/viewer/vr-helpers.js`
- Create: `pbg-parsimony/pbg_parsimony/viewer/vr-helpers.test.js`
- Modify: `pbg-parsimony/pbg_parsimony/viewer/vr.js:189-195` (`isGrabbing`) + import line
- Modify: `ecoli_3d/publish/03_assemble_local_view.py:26` (add `vr-helpers.js` to copy tuple)

**Interfaces:**
- Produces: `resolveGrab(gamepad, hand) -> boolean`
  - `gamepad`: `{ buttons: Array<{pressed:boolean}> } | null` — buttons[0]=trigger, buttons[1]=grip
  - `hand`: `{ pinching: boolean } | null`
  - Returns `true` if trigger OR grip pressed OR hand pinching.

- [ ] **Step 1: Create the test-only package.json**

Create `pbg-parsimony/pbg_parsimony/viewer/package.json`:

```json
{
  "type": "module",
  "private": true
}
```

- [ ] **Step 2: Write the failing test**

Create `pbg-parsimony/pbg_parsimony/viewer/vr-helpers.test.js`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { resolveGrab } from "./vr-helpers.js";

test("resolveGrab: trigger pressed grabs", () => {
  assert.equal(resolveGrab({ buttons: [{ pressed: true }, { pressed: false }] }, null), true);
});

test("resolveGrab: grip pressed grabs", () => {
  assert.equal(resolveGrab({ buttons: [{ pressed: false }, { pressed: true }] }, null), true);
});

test("resolveGrab: hand pinch grabs with no gamepad", () => {
  assert.equal(resolveGrab(null, { pinching: true }), true);
});

test("resolveGrab: nothing pressed does not grab", () => {
  assert.equal(resolveGrab({ buttons: [{ pressed: false }, { pressed: false }] }, { pinching: false }), false);
});

test("resolveGrab: null inputs do not grab or throw", () => {
  assert.equal(resolveGrab(null, null), false);
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/eranagmon/code/pbg-parsimony/pbg_parsimony/viewer && node --test`
Expected: FAIL — `Cannot find module './vr-helpers.js'` (or `resolveGrab is not exported`).

- [ ] **Step 4: Write minimal implementation**

Create `pbg-parsimony/pbg_parsimony/viewer/vr-helpers.js`:

```js
// vr-helpers.js — pure, dependency-free logic for the WebXR path.
// No `three` import: this module is unit-tested under `node --test`.

// Grab is active when grip (button[1]) OR trigger (button[0]) is pressed,
// OR the hand-tracking source reports a pinch. Tolerant of null inputs so a
// controllers-off / binding-quirk session can still grab.
export function resolveGrab(gamepad, hand) {
  if (gamepad && gamepad.buttons) {
    const trig = gamepad.buttons[0] && gamepad.buttons[0].pressed;
    const grip = gamepad.buttons[1] && gamepad.buttons[1].pressed;
    if (trig || grip) return true;
  }
  if (hand && hand.pinching) return true;
  return false;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/eranagmon/code/pbg-parsimony/pbg_parsimony/viewer && node --test`
Expected: PASS — 5 tests pass.

- [ ] **Step 6: Wire `resolveGrab` into vr.js**

In `vr.js`, add the import near the top (after the `import * as THREE` line ~25):

```js
import { resolveGrab } from "./vr-helpers.js";
```

Replace `isGrabbing` (`vr.js:189-195`) with:

```js
  function isGrabbing(ctrl) {
    const src = ctrl.userData.inputSource;
    const gp = src && src.gamepad;
    // Hand-tracking pinch: WebXR exposes a `hand` map; treat a tracked hand with
    // a near-zero thumb–index gap as a pinch. selectstart also fires for pinch,
    // but reading it here keeps grab stateless per frame.
    const hand = src && src.hand ? { pinching: !!ctrl.userData.pinching } : null;
    return resolveGrab(gp, hand);
  }
```

Add pinch tracking via the controller `selectstart`/`selectend` events. In the controller setup loop (`vr.js:53-59`), add:

```js
    c.addEventListener("selectstart", () => { c.userData.pinching = true; });
    c.addEventListener("selectend", () => { c.userData.pinching = false; });
```

- [ ] **Step 7: Add vr-helpers.js to the publish copy list**

In `ecoli_3d/publish/03_assemble_local_view.py:26`, change:

```python
for f in ("viewer.js", "obj-worker.js", "vr.js"):
```

to:

```python
for f in ("viewer.js", "obj-worker.js", "vr.js", "vr-helpers.js"):
```

- [ ] **Step 8: Emulator smoke check**

With the Immersive Web Emulator installed, serve the viewer locally
(`cd out/ecoli3d/_view && python -m http.server 8799` after a local assemble, OR
load the source viewer dir directly). Enter VR, hold the emulator's trigger and
move a controller — the cell should drag. Repeat with grip. Confirm no console errors.
Expected: drag works on both trigger and grip.

- [ ] **Step 9: Commit**

```bash
cd /Users/eranagmon/code/pbg-parsimony
git add pbg_parsimony/viewer/package.json pbg_parsimony/viewer/vr-helpers.js pbg_parsimony/viewer/vr-helpers.test.js pbg_parsimony/viewer/vr.js
git commit -m "feat(vr): hardened grab read (grip/trigger/pinch) + node test harness"
cd /Users/eranagmon/code/3d-ecoli
git add ecoli_3d/publish/03_assemble_local_view.py
git commit -m "build(vr): stage vr-helpers.js in local view assembly"
```

---

### Task 2: Reassess-on-settle gate (fixes "eggs never sharpen", part A)

Re-run LOD reassessment ~180 ms after VR navigation **settles**, so finer meshes load when you pull the cell closer — never mid-motion (which hitches).

**Files:**
- Modify: `pbg-parsimony/pbg_parsimony/viewer/vr-helpers.js` (add `makeMotionGate`)
- Modify: `pbg-parsimony/pbg_parsimony/viewer/vr-helpers.test.js` (add tests)
- Modify: `pbg-parsimony/pbg_parsimony/viewer/vr.js` (note motion; expose `maybeReassess`)
- Modify: `pbg-parsimony/pbg_parsimony/viewer/viewer.js:3150-3156` (call gate from `tick`)

**Interfaces:**
- Consumes: `scheduleReassess()` (`viewer.js:1669-1677`) — existing debounced reassess trigger.
- Produces:
  - `makeMotionGate(idleMs) -> { noteMotion(now), shouldFire(now) }`
    - `noteMotion(now)`: record that the view moved at time `now` (ms).
    - `shouldFire(now)`: returns `true` exactly **once** after motion has been idle ≥ `idleMs`; returns `false` until the next `noteMotion`.
  - `vrApi.updateVR(dt, now)` — now takes a timestamp (ms) second arg.
  - `vrApi.maybeReassess(now) -> boolean` — true once per settle.

- [ ] **Step 1: Write the failing tests**

Append to `vr-helpers.test.js`:

```js
import { makeMotionGate } from "./vr-helpers.js";

test("makeMotionGate: fires once after idle window elapses", () => {
  const g = makeMotionGate(180);
  g.noteMotion(1000);
  assert.equal(g.shouldFire(1100), false); // still within idle window
  assert.equal(g.shouldFire(1180), true);  // window elapsed → fire once
  assert.equal(g.shouldFire(1200), false);  // does not fire again until new motion
});

test("makeMotionGate: new motion re-arms the gate", () => {
  const g = makeMotionGate(180);
  g.noteMotion(0);
  assert.equal(g.shouldFire(200), true);
  g.noteMotion(500);
  assert.equal(g.shouldFire(600), false);
  assert.equal(g.shouldFire(700), true);
});

test("makeMotionGate: does not fire before any motion", () => {
  const g = makeMotionGate(180);
  assert.equal(g.shouldFire(10000), false);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/eranagmon/code/pbg-parsimony/pbg_parsimony/viewer && node --test`
Expected: FAIL — `makeMotionGate is not exported`.

- [ ] **Step 3: Implement `makeMotionGate`**

Append to `vr-helpers.js`:

```js
// Fires once after VR navigation has been idle for `idleMs`. Used to defer the
// (expensive) LOD reassess until motion settles, so detail upgrades without the
// per-frame walk that caused stutter.
export function makeMotionGate(idleMs) {
  let lastMotion = -Infinity;
  let armed = false; // becomes true on motion, false after firing
  return {
    noteMotion(now) { lastMotion = now; armed = true; },
    shouldFire(now) {
      if (armed && now - lastMotion >= idleMs) { armed = false; return true; }
      return false;
    },
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/eranagmon/code/pbg-parsimony/pbg_parsimony/viewer && node --test`
Expected: PASS — all motion-gate tests pass.

- [ ] **Step 5: Wire the gate into vr.js**

In `initVR` (after the imports/constants, near the other `let` state ~`vr.js:89`), add:

```js
  const reassessGate = makeMotionGate(180);
```

Add the import at top of `vr.js` (extend the Task 1 import):

```js
import { resolveGrab, makeMotionGate } from "./vr-helpers.js";
```

Change `updateVR(dt)` signature (`vr.js:264`) to `updateVR(dt, now)` and note motion whenever the dolly moves. Specifically:

- After the grab branch `if (updateGrab()) return true;` (`vr.js:283`), change to:

```js
    if (updateGrab()) { reassessGate.noteMotion(now); return true; }
```

- After the LEFT-stick fly block (`vr.js:295-299`), inside the `if (lx || ly) { ... }`, add as the last line of that block:

```js
      reassessGate.noteMotion(now);
```

- Inside the snap-turn armed block (after `dolly.quaternion.premultiply(_q);`, `vr.js:308`), add:

```js
        reassessGate.noteMotion(now);
```

- Inside the right-stick-Y zoom block (after `dolly.scale.setScalar(newScale);`, `vr.js:321`), add:

```js
      reassessGate.noteMotion(now);
```

Add `maybeReassess` to the returned API (`vr.js:326`):

```js
  return {
    updateVR,
    maybeReassess(now) { return reassessGate.shouldFire(now); },
    get presenting() { return renderer.xr.isPresenting; },
  };
```

- [ ] **Step 6: Call the gate from viewer.js tick**

In `viewer.js` `tick()` VR branch (`viewer.js:3150-3156`), replace:

```js
    if (vrApi) vrApi.updateVR(dt);
```

with:

```js
    if (vrApi) {
      vrApi.updateVR(dt, now);
      // Detail upgrade: once VR navigation settles, re-run the LOD pass so
      // molecules near the user load finer meshes (no per-frame walk → no hitch).
      if (vrApi.maybeReassess(now)) scheduleReassess();
    }
```

(`now` is already defined at `viewer.js:3145`.)

- [ ] **Step 7: Emulator verification**

Enter VR in the emulator. Grab and pull the cell toward you, release. Within ~0.2 s
after releasing, watch the mesh-loading counter / network panel — finer LODs should
begin loading and the molecules near you should visibly change from smooth eggs toward
real shapes. Confirm NO reassess churn while continuously moving (it should only fire
after you stop).
Expected: detail upgrades on settle; no mid-motion stutter.

- [ ] **Step 8: Commit**

```bash
cd /Users/eranagmon/code/pbg-parsimony
git add pbg_parsimony/viewer/vr-helpers.js pbg_parsimony/viewer/vr-helpers.test.js pbg_parsimony/viewer/vr.js pbg_parsimony/viewer/viewer.js
git commit -m "feat(vr): reassess LODs after navigation settles (sharpen on approach)"
```

---

### Task 3: Distance-aware VR LOD pick (fixes "eggs never sharpen", part B)

The VR branch currently pins every mesh to the coarsest level (`VR_LOD_INDEX = 0`). Now that reassess re-runs on approach (Task 2), let the pick respond to distance, with a coarse floor for safety. The per-frame triangle budget still caps total geometry.

**Files:**
- Modify: `pbg-parsimony/pbg_parsimony/viewer/viewer.js:1818-1829` (VR LOD pick)
- Modify: `pbg-parsimony/pbg_parsimony/viewer/viewer.js:1573` (`VR_LOD_INDEX` → floor semantics)

**Interfaces:**
- Consumes: existing per-placement `scale`, `projectedRadiusPx`, `lods[]`, `lodVoxelPixelTarget` computed earlier in `reassessLODs` (`viewer.js:1775-1817`).
- Produces: no new exports; behavior change only.

- [ ] **Step 1: Repurpose the VR constant as a coarsest-allowed floor**

At `viewer.js:1573`, replace:

```js
const VR_LOD_INDEX = 0;
```

with:

```js
// In VR, never pick a level finer than necessary, but allow finer than this only
// as the user approaches. This is the COARSEST level always acceptable; the
// projected-size pick may choose finer (higher index) levels near the camera.
const VR_LOD_FLOOR = 0;
```

- [ ] **Step 2: Make the VR pick distance-aware**

In `reassessLODs`, replace the VR override block (`viewer.js:1818-1829`):

```js
      if (isPresentingNow) {
        desired = -1;
        for (let i = Math.min(VR_LOD_INDEX, lods.length - 1); i >= 0; i--) {
          if (!lods[i].degenerate) { desired = i; break; }
        }
        if (desired === -1) {
          for (let i = 0; i < lods.length; i++) if (!lods[i].degenerate) { desired = i; break; }
        }
      }
```

with:

```js
      if (isPresentingNow) {
        // Distance-aware in VR: keep the per-pixel `desired` chosen above, but
        // clamp it no coarser than VR_LOD_FLOOR so far-away molecules still read
        // as real (coarse) shapes rather than smooth eggs. The VR triangle budget
        // below remains the hard cap on total geometry.
        const floor = Math.min(VR_LOD_FLOOR, lods.length - 1);
        if (desired < floor) desired = floor;
        while (desired >= 0 && lods[desired].degenerate) desired--;
        if (desired < 0) {
          for (let i = 0; i < lods.length; i++) if (!lods[i].degenerate) { desired = i; break; }
        }
      }
```

- [ ] **Step 3: Emulator verification**

Enter VR. From far back the cell shows coarse-but-real shapes. Grab and pull a region
close, release, wait for settle — the nearby molecules should load progressively finer
LODs (visibly more detailed) while distant ones stay coarse. Confirm the frame stays
responsive (budget caps geometry).
Expected: detail scales with distance; no runaway geometry.

- [ ] **Step 4: Commit**

```bash
cd /Users/eranagmon/code/pbg-parsimony
git add pbg_parsimony/viewer/viewer.js
git commit -m "feat(vr): distance-aware LOD pick with coarse floor (replaces fixed pin)"
```

---

### Task 4: Adaptive VR triangle budget (framerate stability)

Shrink the per-frame triangle budget when fps drops and restore it when there's headroom, so the Quest GPU can't be overcommitted into a hitch/hang.

**Files:**
- Modify: `pbg-parsimony/pbg_parsimony/viewer/vr-helpers.js` (add `makeAdaptiveBudget`)
- Modify: `pbg-parsimony/pbg_parsimony/viewer/vr-helpers.test.js` (add tests)
- Modify: `pbg-parsimony/pbg_parsimony/viewer/viewer.js:1578` (use dynamic budget)
- Modify: `pbg-parsimony/pbg_parsimony/viewer/viewer.js:1724` (read current budget)
- Modify: `pbg-parsimony/pbg_parsimony/viewer/viewer.js:3186-3194` (feed fps)

**Interfaces:**
- Produces: `makeAdaptiveBudget({ base, min, max, targetFps, step }) -> { value, update(fps) }`
  - `value` (getter): current budget (triangles).
  - `update(fps)`: adjust toward target; returns new value. Below `targetFps` → multiply by `(1 - step)` down to `min`; above `targetFps + 6` → multiply by `(1 + step/2)` up to `max`.

- [ ] **Step 1: Write the failing tests**

Append to `vr-helpers.test.js`:

```js
import { makeAdaptiveBudget } from "./vr-helpers.js";

test("makeAdaptiveBudget: shrinks below target, clamped to min", () => {
  const b = makeAdaptiveBudget({ base: 1000, min: 200, max: 1000, targetFps: 66, step: 0.2 });
  b.update(40); // below target
  assert.equal(b.value, 800);
  for (let i = 0; i < 20; i++) b.update(40);
  assert.equal(b.value, 200); // clamped at min
});

test("makeAdaptiveBudget: grows with headroom, clamped to max", () => {
  const b = makeAdaptiveBudget({ base: 200, min: 200, max: 1000, targetFps: 66, step: 0.2 });
  b.update(80); // well above target
  assert.equal(b.value, 220);
  for (let i = 0; i < 50; i++) b.update(80);
  assert.equal(b.value, 1000); // clamped at max
});

test("makeAdaptiveBudget: holds steady near target", () => {
  const b = makeAdaptiveBudget({ base: 500, min: 200, max: 1000, targetFps: 66, step: 0.2 });
  b.update(68); // between target and target+6 → no change
  assert.equal(b.value, 500);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/eranagmon/code/pbg-parsimony/pbg_parsimony/viewer && node --test`
Expected: FAIL — `makeAdaptiveBudget is not exported`.

- [ ] **Step 3: Implement `makeAdaptiveBudget`**

Append to `vr-helpers.js`:

```js
// Feedback controller for the VR triangle budget. Drop the budget when fps is
// under target (more sphere proxies, fewer meshes) and recover it slowly when
// there is headroom. Keeps the Quest GPU from being pushed into a hang.
export function makeAdaptiveBudget({ base, min, max, targetFps, step }) {
  let value = base;
  return {
    get value() { return value; },
    update(fps) {
      if (fps < targetFps) value = Math.max(min, Math.round(value * (1 - step)));
      else if (fps > targetFps + 6) value = Math.min(max, Math.round(value * (1 + step / 2)));
      return value;
    },
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/eranagmon/code/pbg-parsimony/pbg_parsimony/viewer && node --test`
Expected: PASS.

- [ ] **Step 5: Wire the adaptive budget into viewer.js**

Add the import at the top of `viewer.js` (where other local modules are imported, near `viewer.js:19`):

```js
import { makeAdaptiveBudget } from "./vr-helpers.js";
```

At `viewer.js:1578`, keep `VR_TRIANGLE_BUDGET` as the base and add the controller below it:

```js
const VR_TRIANGLE_BUDGET = 600000;
// Adaptive cap: starts at the static budget, drops when fps falls under ~66 on a
// 72 Hz Quest, recovers when there is headroom. Bounds GPU load so a heavy view
// can't lock the headset.
const vrBudget = makeAdaptiveBudget({
  base: VR_TRIANGLE_BUDGET, min: 150000, max: VR_TRIANGLE_BUDGET, targetFps: 66, step: 0.2,
});
```

At `viewer.js:1724`, replace:

```js
  let vrTriBudget = isPresentingNow ? VR_TRIANGLE_BUDGET : Infinity;
```

with:

```js
  let vrTriBudget = isPresentingNow ? vrBudget.value : Infinity;
```

In `tick()`, inside the fps-update block (`viewer.js:3188-3193`, where `const fps = ...` is computed), after `const fps = fpsCount / fpsAccum;` add:

```js
    if (renderer.xr.isPresenting) {
      const before = vrBudget.value;
      if (vrBudget.update(fps) !== before) scheduleReassess(); // re-pick meshes under the new cap
    }
```

- [ ] **Step 6: Emulator verification**

Emulator fps won't mirror a Quest, but verify no errors and that forcing a low fps
(e.g. throttle CPU in devtools) reduces drawn meshes (more spheres) and a reassess
fires. Confirm desktop (non-VR) is unaffected — `vrTriBudget` stays `Infinity`.
Expected: budget responds to fps in VR only; desktop unchanged.

- [ ] **Step 7: Commit**

```bash
cd /Users/eranagmon/code/pbg-parsimony
git add pbg_parsimony/viewer/vr-helpers.js pbg_parsimony/viewer/vr-helpers.test.js pbg_parsimony/viewer/viewer.js
git commit -m "feat(vr): adaptive triangle budget driven by measured fps"
```

---

### Task 5: Comfort vignette + gentler smooth-fly

Fade a radial vignette in during smooth self-motion (fly / scale-about-head) and out when still or grabbing; lower the default fly speed. Grab-driven (hand-locked) motion does not trigger the vignette.

**Files:**
- Modify: `pbg-parsimony/pbg_parsimony/viewer/vr-helpers.js` (add `vignetteIntensity`)
- Modify: `pbg-parsimony/pbg_parsimony/viewer/vr-helpers.test.js` (add tests)
- Modify: `pbg-parsimony/pbg_parsimony/viewer/vr.js` (vignette mesh + per-frame opacity; `FLY_SPEED`)

**Interfaces:**
- Consumes: `THREE` (already imported in `vr.js`); the smooth-motion magnitude computed in `updateVR` (fly stick deflection + zoom rate).
- Produces:
  - `vignetteIntensity(motionMagnitude, opts?) -> number` in `[0, maxIntensity]`, where `opts = { maxAt = 1, maxIntensity = 0.6 }`. Linear ramp clamped at both ends.

- [ ] **Step 1: Write the failing tests**

Append to `vr-helpers.test.js`:

```js
import { vignetteIntensity } from "./vr-helpers.js";

test("vignetteIntensity: zero motion → zero", () => {
  assert.equal(vignetteIntensity(0), 0);
});

test("vignetteIntensity: full motion → maxIntensity", () => {
  assert.equal(vignetteIntensity(1), 0.6);
});

test("vignetteIntensity: clamps above maxAt", () => {
  assert.equal(vignetteIntensity(5), 0.6);
});

test("vignetteIntensity: respects custom opts", () => {
  assert.equal(vignetteIntensity(0.5, { maxAt: 1, maxIntensity: 0.4 }), 0.2);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/eranagmon/code/pbg-parsimony/pbg_parsimony/viewer && node --test`
Expected: FAIL — `vignetteIntensity is not exported`.

- [ ] **Step 3: Implement `vignetteIntensity`**

Append to `vr-helpers.js`:

```js
// Maps current smooth-motion magnitude (0..maxAt) to a vignette opacity. Smooth
// self-motion is the nausea trigger; grab motion (hand-locked) passes 0 here.
export function vignetteIntensity(motionMagnitude, { maxAt = 1, maxIntensity = 0.6 } = {}) {
  const t = Math.max(0, Math.min(1, motionMagnitude / maxAt));
  return t * maxIntensity;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/eranagmon/code/pbg-parsimony/pbg_parsimony/viewer && node --test`
Expected: PASS.

- [ ] **Step 5: Lower the default fly speed**

At `vr.js:32`, change:

```js
const FLY_SPEED = 1.2;        // head-metres / second at full stick deflection (gentle)
```

to:

```js
const FLY_SPEED = 0.7;        // head-metres / second at full stick deflection (gentler; grab is primary)
```

- [ ] **Step 6: Build the vignette mesh (head-locked)**

Extend the `vr.js` import:

```js
import { resolveGrab, makeMotionGate, vignetteIntensity } from "./vr-helpers.js";
```

In `initVR`, after the `dolly`/controllers setup (~`vr.js:59`), create a camera-locked vignette quad:

```js
  // Comfort vignette: a head-locked quad with a radial-alpha shader. Opacity is
  // driven each frame by smooth-motion magnitude (0 while still or grabbing).
  const vignetteMat = new THREE.ShaderMaterial({
    transparent: true, depthTest: false, depthWrite: false,
    uniforms: { uOpacity: { value: 0 } },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
    fragmentShader: `
      varying vec2 vUv; uniform float uOpacity;
      void main(){
        float d = distance(vUv, vec2(0.5));
        float a = smoothstep(0.30, 0.50, d) * uOpacity;
        gl_FragColor = vec4(0.0, 0.0, 0.0, a);
      }`,
  });
  const vignette = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), vignetteMat);
  vignette.frustumCulled = false;
  vignette.renderOrder = 9999;
  vignette.visible = false;
```

Add/remove the vignette to the camera on enter/exit. In `enterVR`, after `dolly.add(camera);` (`vr.js:126`), add:

```js
    camera.add(vignette);
    vignette.visible = true;
```

In the session `end` handler, after `parent.add(camera);` (`vr.js:136`), add:

```js
      camera.remove(vignette);
      vignette.visible = false;
```

- [ ] **Step 7: Drive vignette opacity from smooth motion**

In `updateVR`, accumulate a smooth-motion magnitude and set the uniform. At the top of
`updateVR` (after the early-return, `vr.js:265`), add:

```js
    let smoothMotion = 0;
```

In the LEFT-stick fly block, after applying motion, set:

```js
      smoothMotion = Math.max(smoothMotion, Math.hypot(lx, ly));
```

In the right-stick-Y zoom block, after applying scale, set:

```js
      smoothMotion = Math.max(smoothMotion, Math.abs(ry));
```

Before `return false;` at the end of `updateVR` (`vr.js:323`), add:

```js
    // Ease toward the target opacity so it fades rather than snaps.
    const target = vignetteIntensity(smoothMotion);
    const cur = vignetteMat.uniforms.uOpacity.value;
    vignetteMat.uniforms.uOpacity.value = cur + (target - cur) * Math.min(1, dt * 8);
```

Note: the grab branch returns before this line (grab → no vignette), and after a grab
returns we leave the last eased value; add the same easing toward 0 in the grab branch
by changing `if (updateGrab()) { reassessGate.noteMotion(now); return true; }` to:

```js
    if (updateGrab()) {
      reassessGate.noteMotion(now);
      const cur = vignetteMat.uniforms.uOpacity.value;
      vignetteMat.uniforms.uOpacity.value = cur + (0 - cur) * Math.min(1, dt * 8);
      return true;
    }
```

- [ ] **Step 8: Emulator verification**

Enter VR. Push the left stick to fly — a soft dark vignette should fade in at the edges;
release and it fades out. Grab-and-drag should show **no** vignette. Confirm the cell
view is unobstructed at center.
Expected: vignette tracks smooth motion only; fades smoothly; grab is clear.

- [ ] **Step 9: Commit**

```bash
cd /Users/eranagmon/code/pbg-parsimony
git add pbg_parsimony/viewer/vr-helpers.js pbg_parsimony/viewer/vr-helpers.test.js pbg_parsimony/viewer/vr.js
git commit -m "feat(vr): comfort vignette on smooth motion + gentler fly default"
```

---

### Task 6: In-VR controls hint panel

On VR entry, show a small head-anchored hint that auto-dismisses after ~6 s or on first grab.

**Files:**
- Modify: `pbg-parsimony/pbg_parsimony/viewer/vr.js` (hint sprite + lifecycle)

**Interfaces:**
- Consumes: `THREE`, the `camera`, the existing enter/exit lifecycle and `updateGrab` grab state.
- Produces: no exports; visual only.

- [ ] **Step 1: Build the hint texture + mesh**

In `initVR`, after the vignette setup (Task 5 Step 6), add:

```js
  // One-shot controls hint: a head-anchored label drawn from a canvas texture.
  function makeHintTexture() {
    const c = document.createElement("canvas");
    c.width = 1024; c.height = 256;
    const x = c.getContext("2d");
    x.fillStyle = "rgba(10,12,18,0.82)";
    roundRect(x, 0, 0, c.width, c.height, 28); x.fill();
    x.fillStyle = "#eaf0ff";
    x.font = "600 44px system-ui, sans-serif";
    x.textAlign = "center"; x.textBaseline = "middle";
    x.fillText("Grab to move  ·  Two hands to zoom", c.width / 2, 92);
    x.fillText("Right stick to turn  ·  Face button to exit", c.width / 2, 168);
    const t = new THREE.CanvasTexture(c);
    t.anisotropy = 4;
    return t;
  }
  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  const hintMat = new THREE.MeshBasicMaterial({
    map: makeHintTexture(), transparent: true, depthTest: false, depthWrite: false,
  });
  const hint = new THREE.Mesh(new THREE.PlaneGeometry(0.8, 0.2), hintMat);
  hint.position.set(0, -0.25, -1.0); // head-anchored, slightly below center, 1 m out
  hint.renderOrder = 9998;
  hint.frustumCulled = false;
  hint.visible = false;
  let hintHideAt = 0;
```

- [ ] **Step 2: Show on enter, hide on exit**

In `enterVR`, after `vignette.visible = true;` (Task 5 Step 6), add:

```js
    camera.add(hint);
    hint.visible = true;
    hintHideAt = performance.now() + 6000;
```

In the session `end` handler, after `vignette.visible = false;`, add:

```js
      camera.remove(hint);
      hint.visible = false;
```

- [ ] **Step 3: Auto-dismiss (timer or first grab)**

At the top of `updateVR`, after the existing early-return (`vr.js:265`), add:

```js
    if (hint.visible && now >= hintHideAt) hint.visible = false;
```

In the grab branch (the `if (updateGrab()) { ... }` block from Task 5 Step 7), add `hint.visible = false;` as the first line inside the block.

- [ ] **Step 4: Emulator verification**

Enter VR — the hint appears head-anchored below center and disappears after ~6 s, or
immediately when you grab. Confirm it doesn't block the central view and is gone after
dismissal.
Expected: hint shows on entry, auto-dismisses on timer/grab.

- [ ] **Step 5: Commit**

```bash
cd /Users/eranagmon/code/pbg-parsimony
git add pbg_parsimony/viewer/vr.js
git commit -m "feat(vr): one-shot in-VR controls hint on entry"
```

---

### Task 7: Stage, publish, and Quest verification pass

Bump cache-bust versions, run the publish pipeline, and verify the full batch on a real Quest.

**Files:**
- Modify: `pbg-parsimony/pbg_parsimony/viewer/index.html:350` (bump `viewer.js?v=`)
- Modify: `pbg-parsimony/pbg_parsimony/viewer/viewer.js:19` (bump `vr.js?v=` import)

**Interfaces:** none (release task).

- [ ] **Step 1: Run the unit tests one final time**

Run: `cd /Users/eranagmon/code/pbg-parsimony/pbg_parsimony/viewer && node --test`
Expected: PASS — all helper tests green.

- [ ] **Step 2: Bump cache-bust query strings**

In `viewer.js` import (`viewer.js:19`), bump `./vr.js?v=46` → `./vr.js?v=47`.
In `index.html:350`, bump `./viewer.js?v=50` → `./viewer.js?v=51`.

(`vr.js` imports `./vr-helpers.js` with no version query; that's fine for a new file, but
if a later edit needs busting, add `?v=1` consistently in both `vr.js` and the assemble
replacement.)

- [ ] **Step 3: Stage + publish**

Confirm with the user who runs publishing (per the spec's open question), then run:

```bash
cd /Users/eranagmon/code/3d-ecoli
python ecoli_3d/publish/03_assemble_local_view.py   # stages viewer incl. vr-helpers.js
bash ecoli_3d/publish/04_publish_r2.sh              # pushes to R2
```

Expected: `vr-helpers.js` present in the staged `_view/` dir and uploaded.

- [ ] **Step 4: Quest verification (on-headset)**

Open `tinyurl.com/27f8726u` (→ the R2 viewer) on the Quest, Enter VR, and verify:
1. Molecules render as real coarse shapes immediately (no permanent eggs).
2. Grab (grip/trigger) drags reliably; two-hand pinch zooms.
3. Pulling the cell close and pausing makes nearby molecules sharpen.
4. Smooth fly shows a comfort vignette; grab does not; no dizziness over ~2 min use.
5. Framerate stays smooth under a dense view (adaptive budget engages).
6. The controls hint appears on entry and dismisses.
7. Desktop/2D viewer (no headset) is unchanged.

Expected: all seven pass. Log any that don't for a follow-up batch.

- [ ] **Step 5: Commit + push**

```bash
cd /Users/eranagmon/code/pbg-parsimony
git add pbg_parsimony/viewer/index.html pbg_parsimony/viewer/viewer.js
git commit -m "build(vr): bump viewer/vr cache-bust for Phase 1 release"
```

---

## Self-Review

**Spec coverage:**
- Eggs never sharpen → Tasks 2 (reassess-on-settle) + 3 (distance-aware pick). ✓
- Grab-to-explore reliable → Task 1 (hardened grab) + Task 2 (zoom triggers reassess). ✓
- Comfort vignette + gentler fly + snap-turn retained → Task 5 (snap-turn is left untouched). ✓
- Framerate stability → Task 4 (adaptive budget); foveation/framebuffer already in `vr.js:107-109` and unchanged. ✓
- In-VR controls hint → Task 6. ✓
- Desktop unchanged → all behavior guarded by `isPresenting` / VR-only paths; verified in each task. ✓
- Testing strategy (emulator + node tests + Quest) → embedded per task + Task 7. ✓
- Publishing-cadence open question → surfaced in Task 7 Step 3. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `resolveGrab`, `makeMotionGate`, `makeAdaptiveBudget`, `vignetteIntensity` signatures match between their defining task, their tests, and their call sites in `vr.js`/`viewer.js`. `vrApi` gains `updateVR(dt, now)` and `maybeReassess(now)`, used consistently in `viewer.js` tick. `VR_LOD_INDEX` is fully renamed to `VR_LOD_FLOOR` (Task 3) with no stale references. ✓

**Note on TDD scope:** Pure helpers (Tasks 1, 2, 4, 5) use real red→green `node --test` cycles. Integration/visual changes (Tasks 3, 6 and the wiring halves) cannot be unit-tested without a WebGL/WebXR context, so they use emulator verification steps — this is the honest test cycle for this no-bundler browser codebase.
