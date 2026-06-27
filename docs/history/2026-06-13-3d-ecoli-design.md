# 3d-ecoli — Design Spec

**Date:** 2026-06-13
**Status:** Draft for review
**Repo to create:** `github.com/vivarium-collective/3d-ecoli` (process-bigraph workspace)
**Imports:** [`v2ecoli`](https://github.com/vivarium-collective/v2ecoli) (molecular state) · `parsimony` (structural packing)

> Note: this spec currently lives in the `parsimony` repo because that is the
> repo under active modification. Phase 0 moves it into the new `3d-ecoli`
> workspace under `docs/`.

---

## 1. Goal

Produce an explorable **3D structural model of an *E. coli* cell** by coupling
the **v2ecoli** whole-cell model (molecular composition) to the **parsimony**
packing engine (the cellPACK rewrite), following the method of Maritan, Autin,
Karr, Covert, Olson & Goodsell, *"Building Structural Models of a Whole
Mycoplasma Cell"* (J Mol Biol 2022) — but updated for *E. coli* with:

- **AlphaFold-DB structures** for the proteome (the 2026 advantage the paper
  lacked — it relied on HHpred homology models for 683 ingredients), plus
  curated PDB for large assemblies.
- A **configurable abundance scale** (the real cell has 2–4 M protein
  molecules vs. ~27 k in the MG 3D model).
- **Snapshot-driven** coupling: pack a chosen v2ecoli time point, not a live
  co-simulation (that is a later phase).

## 2. Method mapping (Maritan 2022 → 3d-ecoli)

| Maritan 2022 (Mycoplasma) | 3d-ecoli (E. coli) |
|---|---|
| WholeCellKB + WC-MG simulation (counts, localization, expression, geometry) | **v2ecoli** ParCa state + composite snapshot |
| Mesoscope (recipe curation, ID mapping, localization, bead/mesh assignment) | **3d-ecoli bridge** (new Python) |
| HHpred homology models (683 ingredients) | **AlphaFold DB** per UniProt + curated PDB for assemblies |
| LatticeNucleoid (supercoiled 0.58 Mbp sphere nucleoid) | **parsimony** supercoiled fiber, 4.6 Mbp, in a capsule |
| CellPACKgpu + NVIDIA Flex (voxel placement + relaxation) | **parsimony** octree backend + staged pipeline (+ relax later) |
| Sphere cell, single membrane | **Capsule** cell; inner membrane first, gram-negative envelope later |
| Supplementary Table S1 ingredient schema | Recipe ingredient fields, mostly auto-filled from v2ecoli |

## 3. Architecture — snapshot → recipe → pack

Three layers; data flows one direction.

### Layer 1 · v2ecoli (imported, unchanged)

Provides, at a chosen simulated time point T:

- `listeners.monomer_counts` — protein monomer copy numbers (incl. complexed
  subunits).
- `listeners.rna_counts` — mRNA / rRNA / tRNA counts (TU + cistron level).
- `listeners.unique_molecule_counts` + unique stores — `active_ribosome`,
  `active_RNAP`, `active_replisome` **with chromosome coordinates / positions**.
- Complex stoichiometry — `parca_state['process']['complexation'].stoichiometry`
  (sparse subunit→complex matrix).
- Per-protein compartment — `proteins.tsv` `computational_compartment` /
  bulk-ID compartment tags (`c` cytoplasm, `i` inner membrane, `p` periplasm,
  `o` outer membrane, `e` extracellular).
- Gene coordinates — `genes.tsv` (`left_end_pos`, `right_end_pos`, `direction`,
  ~4,315 genes, 4.6 Mbp circular genome).
- Cell geometry — `listeners.mass.volume` → capsule length/diameter via the
  EcoliWCM bridge capsule map.
- IDs — EcoCyc primary IDs; b-numbers + symbols in synonyms; **UniProt** present
  in the knowledge base for mapping.

Accessed two ways:
- **Static**: `load_parca_state()` from `models/parca/parca_state.pkl.gz` — no
  full simulation, gives initial counts + geometry per condition.
- **Dynamic**: `composite = v2ecoli.build_composite("baseline"); composite.update({}, T)`
  then read `composite.state` — counts + positioned uniques at time T.

### Layer 2 · 3d-ecoli bridge (new Python — the "Mesoscope" role)

A small, testable package `3d_ecoli/bridge/` with these units:

1. `state.py` — **extract** a v2ecoli snapshot at T into a plain dataclass
   `CellSnapshot` (counts by species+compartment, complex stoichiometry,
   capsule geometry, genome table, positioned uniques). One clear input
   (v2ecoli composite/parca state) → one clear output (CellSnapshot).
2. `idmap.py` — **map** EcoCyc protein ID → UniProt accession (via v2ecoli
   synonyms + the UniProt E. coli K-12 reference proteome `UP000000625`
   mapping, cached locally). Returns `{ecocyc_id: uniprot_acc}`.
3. `structures.py` — **resolve** a structure source per species:
   - curated **PDB** IDs for large assemblies (70S ribosome, RNAP core+σ,
     GroEL/ES, ATP synthase, pyruvate dehydrogenase, …) — a small hand
     table `assemblies.toml`;
   - **AlphaFold DB** model `AF-<acc>-F1` (mmCIF/PDB) per UniProt otherwise,
     downloaded + cached under `structures/cache/`;
   - complexes lacking a PDB → Phase 1: represent by sphere/largest-subunit;
     Phase 2: assemble subunit AF models by stoichiometry.
   Returns a `StructureRef` per species (path or PDB id + chain selection).
4. `scale.py` — apply the **abundance knob**: `top_n` (keep N most abundant) or
   `abundance_scale` (multiply all counts by a fraction, floor at 1 for kept
   species). Reports what was dropped (no silent truncation).
5. `recipe.py` — **author** a parsimony recipe JSON: capsule compartment,
   `objects` with `mesh_lods` (or sphere fallback), `regions.interior` /
   `regions.surface`, `chromosome` block; and the **genome CSV** emitted from
   `genes.tsv` (E. coli locus tags + coordinates + `# genome_length_bp=4641652`).
6. `run.py` — orchestrate: `parsimony mesh` (batch over resolved structures) →
   `parsimony pipeline run <recipe-derived pipeline> --proxy-lod 2` →
   `parsimony viewer --pack …`.

### Layer 3 · parsimony (modified — the "CellPACK + LatticeNucleoid + Flex" role)

Already in place: capsule compartment geometry, octree backend, generic
supercoiled-fiber nucleoid, a mesher that accepts arbitrary PDB/mmCIF files,
`ecoli_starter.json`, a passing capsule integration test.

Changes required:

- **Generalize the locus parser** in `crates/parsimony-core/src/genome.rs`
  (currently hardcoded to `MG_<digits>`, lines ~237–259) to a configurable
  scheme so it can match E. coli IDs (b-numbers / EcoCyc). Drive it from a
  field in the genome CSV header or the chromosome spec.
- **Rod nucleoid at scale**: confirm `generate_supercoiled_fiber` /
  `generate_nucleoid` run inside a **capsule** (not just sphere) and at
  ~4.6 Mbp. Bead spacing is a recipe parameter; choose spacing so total beads
  stay tractable (instanced dsDNA segments are cheap, but keep an eye on count).
- **AlphaFold-aware meshing** (optional, Phase 2): trim very-low-pLDDT tails
  before surfacing so disordered termini don't inflate the envelope.
- No change needed to the staged-pipeline architecture or octree.

> Decision recap: the user confirmed parsimony is ours to modify, and the split
> is "engine generalizations in parsimony, data/recipe authoring in the
> 3d-ecoli bridge." We do **not** add a monolithic `translate-ecoli` command;
> the bridge authors recipes and calls the existing `mesh` / `pipeline` /
> `viewer` subcommands. (A thin `translate-ecoli` convenience wrapper may be
> added later if useful, but it is not on the critical path.)

### The pbg composite

`3d-ecoli` is a process-bigraph workspace. Its composite imports v2ecoli's
baseline composite upstream and adds a **`ParsimonyPackStep`** (a
process-bigraph `Step`) whose:
- **inputs**: the v2ecoli state snapshot at T + scale config,
- **outputs**: the packed model path + a model summary (counts placed, volume
  occupancy, pack time),
and a viewer launch. For the snapshot MVP this is effectively
`v2ecoli → emit snapshot → ParsimonyPackStep → viewer`, wrapped so it is
catalogued and reproducible in the workspace (`pbg-study` / `pbg-run`).

## 4. Compartments & geometry

- Cell shape: **capsule** (spherocylinder), dimensions from v2ecoli volume.
- **Phase 1**: two regions — `interior` (cytoplasm) and `surface` (single inner
  membrane, lipids placed on the capsule surface with `principal_vector`).
- **Phase 2** (gram-negative envelope): concentric capsule shells — inner
  membrane (inner surface), periplasm (thin shell region), outer membrane
  (outer surface). Proteins routed to a region by their v2ecoli compartment tag
  (`c`→interior, `i`→inner membrane, `p`→periplasm, `o`→outer membrane).

## 5. Phasing

Each phase is its own spec → plan → implement cycle. **This spec details Phase 0
+ Phase 1**; Phases 2–3 are roadmap.

### Phase 0 — Scaffold + smoke test
- Create `vivarium-collective/3d-ecoli` as a pbg workspace.
- Add `v2ecoli` and `parsimony` as imports/dependencies.
- Stand up the bridge package skeleton + `ParsimonyPackStep`.
- **Smoke test**: drive the existing `ecoli_starter.json` end-to-end through
  bridge → `parsimony pipeline`/`viewer` (no new structures). Proves the
  plumbing and the pbg wiring.
- Deliverable: `ecoli_starter` renders via the 3d-ecoli composite.

### Phase 1 — Real demo subset (first true 3D E. coli)
- `state.py` + `idmap.py` + `structures.py` (AlphaFold + assembly PDB table) +
  `scale.py` (`top_n`) + `recipe.py`.
- Pull the **top-N most abundant** v2ecoli species at one time point.
- Fetch AlphaFold/PDB structures, mesh them.
- Compartments: cytoplasm + single inner membrane.
- Nucleoid: 4.6 Mbp supercoiled rod fiber from v2ecoli `genes.tsv`; place RNAP
  along it.
- Pack via octree staged pipeline; view.
- Deliverable: a crowded, recognizable 3D E. coli (tens of thousands of
  instances) on screen, built from real structures and real v2ecoli counts.

### Phase 2 — Full configurable proteome (roadmap)
All ~4,000 species; complex assembly from subunit AF models; `abundance_scale`
dialed toward full abundance; gram-negative envelope (periplasm + OM); RNAP at
real transcription sites and ribosomes on mRNA from v2ecoli positioned uniques.

### Phase 3 — Dynamics (roadmap)
Live co-simulation composite; multiple time points / cell-cycle frames;
Flex-style relaxation pass to resolve residual clashes.

## 6. Out of scope (YAGNI for now)
- Live bidirectional coupling / animation (Phase 3).
- Metabolite/ion/solvent placement (the MG paper also omitted these).
- Atomic-detail MD or relaxation beyond what parsimony already offers.
- The terminal organelle / appendages (E. coli pili/flagella) — not modeled.

## 7. Open questions / risks
- **Chromosome bead count**: 4.6 Mbp is ~8× Mycoplasma. Confirm octree + DNA
  segment instancing stays tractable; tune bead spacing.
- **EcoCyc→UniProt coverage**: a few species may lack a clean UniProt/AF entry
  (e.g. some complexes, RNAs) — fall back to sphere/PDB; log gaps explicitly.
- **AlphaFold envelope inflation**: disordered termini may bloat meshes; may
  need pLDDT trimming sooner than Phase 2.
- **Spec location**: moves into the 3d-ecoli repo at Phase 0.

## 8. Success criteria (Phase 0 + 1)
1. `3d-ecoli` workspace exists on vivarium-collective, importing v2ecoli +
   parsimony, with a green smoke test rendering `ecoli_starter`.
2. The bridge turns a real v2ecoli snapshot into a parsimony recipe + genome CSV.
3. parsimony packs a capsule E. coli with a 4.6 Mbp rod nucleoid + top-N real
   AlphaFold/PDB structures + inner membrane, and the viewer shows it.
4. The whole Phase-1 build is reproducible from one composite/run entrypoint.
