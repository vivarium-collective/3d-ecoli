# 3d-ecoli

A 3D structural model of an *E. coli* cell. It couples the **v2ecoli** whole-cell
model (molecular composition + cell geometry) to the **pbg-parsimony** packing
engine (a cellPACK-style placer with a Rust core), rendering every molecule at
true abundance inside the cell envelope.

The model shows the chromosome at real genomic geometry, every active RNAP at its
real locus, nascent RNA off each RNAP, free mRNA, active ribosomes + free 30S/50S
subunits, nascent peptides, enlarged replication markers, and — for the dividing
cell — a septum-confined two-nucleoid pre-division state.

**Live viewer:** https://pub-eb913fbbdc584bd7add047c823570b13.r2.dev/viewer/index.html

## How it relates to the other repos

```
v2ecoli  ──(molecular state + ShapeStep cell envelope)──┐
                                                         ├──▶  ecoli_3d  ──▶  3D pack + viewer
pbg-parsimony  ──(Ingredient / Chromosome / build_pack engine)──┘
```

`ecoli_3d` **imports** both — it does not vendor them. v2ecoli supplies the cell
state (via `build_composite("baseline")` or a saved snapshot) and the cell
envelope (`v2ecoli.cell_shape.ShapeStep`); pbg-parsimony supplies the packing
engine. This repo holds only the bridge: species selection, structure mapping,
and the 3D geometry orchestration.

## Layout

- `ecoli_3d/build.py` — the bridge: v2ecoli state → ingredients → `build_pack` → pack + sidecar.
- `ecoli_3d/composite.py` — the `parsimony-ecoli` process-bigraph `Step`.
- `ecoli_3d/data/` — committed cell-state snapshots (`v2ecoli_state*.npz`) + reference tables.
- `ecoli_3d/publish/` — the reproducible build/publish pipeline (see `publish/REPRODUCE.md`).
- `ecoli_3d/webapp/` — the bundled viewer page.
- `scripts/capture_structural_snapshot.py` — regenerate the snapshots from a live sim.
- `docs/history/` — the original (superseded) June-2026 fork-based design, kept for provenance.

## Install (development)

```bash
# into a Python 3.12.12 env that already has v2ecoli + pbg-parsimony editable-installed:
pip install -e . --no-deps
```

`requires-python == 3.12.12` (inherited from v2ecoli). A full fresh install pulls
v2ecoli and its whole-cell-model dependency stack via the git sources in
`pyproject.toml`.

## Build the 3D model

See `ecoli_3d/publish/REPRODUCE.md` for the pinned, reproducible pipeline. In short:

```bash
PARSIMONY_HOME=<parsimony> python -m ecoli_3d.build --out out/ecoli3d --state snapshot --top-n 400
```

## Provenance

Extracted from `v2ecoli/structural/` (June 2026), which is where this work was
prototyped before being split into its own importing workspace. The
fork-based predecessor design lives in `docs/history/`.
