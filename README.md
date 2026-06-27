# 3d-ecoli

**An interactive 3D structural model of an _E. coli_ cell** — every molecule placed
at true abundance inside the cell envelope, driven by a whole-cell simulation.

### ▶ [Open the live viewer](https://pub-eb913fbbdc584bd7add047c823570b13.r2.dev/viewer/index.html)

[![live viewer](https://img.shields.io/badge/live%20viewer-open-2ea44f)](https://pub-eb913fbbdc584bd7add047c823570b13.r2.dev/viewer/index.html)
[![python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![imports](https://img.shields.io/badge/imports-v2ecoli%20%2B%20pbg--parsimony-555)](#how-it-works)

It couples the **[v2ecoli](https://github.com/vivarium-collective/v2ecoli)**
whole-cell model (molecular composition + cell geometry) to the
**[pbg-parsimony](https://github.com/vivarium-collective/pbg-parsimony)** packing
engine (a cellPACK-style placer with a Rust core), then renders the result in the
browser.

## What the model shows

Built directly from a v2ecoli cell state, at **true 1:1 abundance**, all confined
inside the cell envelope:

- 🧬 **Chromosome** at real genomic geometry — a supercoiled 4.6 Mbp fiber in the capsule
- 🔴 **Active RNAPs** each at its real genomic locus
- 🧵 **Nascent RNA** transcribed off each RNAP, length ∝ the real transcript length
- 🩵 **Free mRNA** floating in the cytoplasm
- 🟢 **Active ribosomes** seated on mRNAs, plus free 30S / 50S subunits
- 🟠 **Nascent peptides** trailing from each translating ribosome
- 📍 **Replication markers** — oriC, terC, replisomes
- 🔬 **~560 protein species** from AlphaFold + curated PDB assemblies

### Two cell states (switch them in the viewer's dropdown)

| State | Cell | Species | Molecules placed |
|---|---|---|---|
| **Birth** | 1.8 µm rod, one chromosome | 563 | 1.90 M |
| **Pre-division** | 3.06 µm rod, two nucleoids, septum-confined | 564 | 3.25 M |

## How it works

```
v2ecoli  ──(molecular state + ShapeStep cell envelope)──┐
                                                         ├──▶  ecoli_3d  ──▶  3D pack + viewer
pbg-parsimony  ──(Ingredient / Chromosome / build_pack engine)──┘
```

`ecoli_3d` **imports** both repos — it does not vendor them:

- **v2ecoli** supplies the cell state (via `build_composite("baseline")` or a saved
  snapshot) and the cell envelope (`v2ecoli.cell_shape.ShapeStep`).
- **pbg-parsimony** supplies the packing engine (`Ingredient` / `Chromosome` /
  `build_pack`) with its Rust geometry core.

This repo holds only the **bridge**: selecting species, mapping them to real
structures (AlphaFold per UniProt + curated PDB for large assemblies), placing the
transcription/translation machinery from the state, and orchestrating the pack.

**Method.** Follows Maritan, Autin, Karr, Covert, Olson & Goodsell, *"Building
Structural Models of a Whole Mycoplasma Cell"* (J. Mol. Biol. 2022), updated for
_E. coli_ with AlphaFold-DB structures and true-abundance packing.

## Layout

| Path | What |
|---|---|
| `ecoli_3d/build.py` | the bridge: state → ingredients → `build_pack` → pack + sidecar |
| `ecoli_3d/composite.py` | the `parsimony-ecoli` process-bigraph `Step` |
| `ecoli_3d/data/` | committed cell-state snapshots (`v2ecoli_state*.npz`) + reference tables |
| `ecoli_3d/publish/` | the reproducible build/publish pipeline — see [`REPRODUCE.md`](ecoli_3d/publish/REPRODUCE.md) |
| `ecoli_3d/webapp/` | the bundled viewer page |
| `scripts/capture_structural_snapshot.py` | regenerate the snapshots from a live sim |
| `docs/history/` | the superseded June-2026 fork-based design (provenance) |

## Build it yourself

Full pinned, reproducible pipeline in
[`ecoli_3d/publish/REPRODUCE.md`](ecoli_3d/publish/REPRODUCE.md). In short:

```bash
# build one cell state (needs PARSIMONY_HOME → a built parsimony binary)
PARSIMONY_HOME=<parsimony> python -m ecoli_3d.build --out out/ecoli3d --state snapshot --top-n 400
```

`--top-n` is the species-richness knob (400 → ~560 species); `--state` is
`snapshot` (birth) or `division` (pre-division). The publish scripts compact each
pack to a web-friendly format and push it to the live viewer.

## Install (development)

```bash
# into a Python 3.12.12 env that already has v2ecoli + pbg-parsimony installed:
pip install -e . --no-deps
```

`requires-python == 3.12.12` (inherited from v2ecoli). A full fresh install pulls
v2ecoli and its whole-cell-model dependency stack via the git sources in
`pyproject.toml`. Run the tests with `pytest`.

## Provenance

Prototyped inside `v2ecoli/structural/` (June 2026), then extracted into this
importing workspace so v2ecoli stays focused on the simulation. The earlier
fork-based predecessor design is preserved in
[`docs/history/`](docs/history/).
