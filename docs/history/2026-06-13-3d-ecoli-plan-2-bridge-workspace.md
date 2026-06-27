# 3d-ecoli Plan 2 — v2ecoli→parsimony Bridge & pbg Composite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the `vivarium-collective/3d-ecoli` repo (a fork of v2ecoli), build a Python bridge + process-bigraph composite that turns a v2ecoli molecular snapshot into a 3D structural model of an *E. coli* cell, packed by parsimony and viewable in the browser.

**Architecture:** 3d-ecoli is a **fork of v2ecoli**, so the `v2ecoli` package is in-tree (import it directly — no external dependency). A new `ecoli3d/` package holds the bridge: extract a snapshot from v2ecoli → map EcoCyc IDs to UniProt → fetch AlphaFold/PDB structures → author a parsimony recipe + genome CSV → invoke the `parsimony` CLI (a separate Rust repo) to mesh + pack → view. A `ParsimonyPackStep` (process-bigraph `Step`) and a `@composite_generator` wire it into the pbg ecosystem.

**Tech Stack:** Python 3.12, process-bigraph / bigraph-schema (in-tree via v2ecoli), `pytest` (markers `fast`/`sim`), `requests`/`urllib` for AlphaFold + UniProt, the `parsimony` CLI binary (built from `github.com/prismofeverything/parsimony`).

**Depends on:** Plan 1 (`parsimony` E. coli engine) for the capsule rod-nucleoid support and the genome-CSV / recipe interface. Phase-0 tasks (1, 7-9 smoke) do not need Plan 1; the Phase-1 real-cell task (10) does.

**Specs/Plans:** `docs/superpowers/specs/2026-06-13-3d-ecoli-design.md` (this repo), `docs/superpowers/plans/2026-06-13-3d-ecoli-plan-1-parsimony-engine.md` (parsimony repo).

---

## Prerequisite: the parsimony binary

The bridge shells out to the `parsimony` binary. Build it once:

```bash
git clone https://github.com/prismofeverything/parsimony /Users/eranagmon/code/parsimony  # if absent
cd /Users/eranagmon/code/parsimony && cargo build --release
# binary at target/release/parsimony
```

The bridge locates it via `$PARSIMONY_BIN`, else `$PARSIMONY_HOME/target/release/parsimony`, else `parsimony` on `PATH` (Task 1).

---

## File Structure

**Create (new `ecoli3d/` package):**
- `ecoli3d/__init__.py` — package marker + public exports.
- `ecoli3d/config.py` — locate the parsimony binary + the parsimony repo (for `examples/`); `ParsimonyNotFound` error.
- `ecoli3d/state.py` — `CellSnapshot` dataclass + `snapshot_from_v2ecoli(...)`.
- `ecoli3d/idmap.py` — `ecocyc_to_uniprot(...)` via UniProt proteome UP000000625, cached to `ecoli3d/data/ecocyc_uniprot.tsv`.
- `ecoli3d/structures.py` — `resolve_structure(...)` (AlphaFold per UniProt + curated `assemblies.toml`), `mesh_structures(...)` (calls `parsimony mesh`).
- `ecoli3d/assemblies.toml` — curated PDB ids for large assemblies (ribosome, RNAP, GroEL, …).
- `ecoli3d/scale.py` — `apply_scale(...)` (`top_n` / `abundance_scale`, logs drops).
- `ecoli3d/recipe.py` — `author_recipe(...)` (parsimony recipe JSON) + `write_genome_csv(...)`.
- `ecoli3d/run.py` — `build_3d_ecoli(...)` orchestration (snapshot → structures → recipe → pack → pack path).
- `ecoli3d/steps/__init__.py`, `ecoli3d/steps/parsimony_pack.py` — `ParsimonyPackStep(Step)`.
- `ecoli3d/composites/__init__.py`, `ecoli3d/composites/parsimony_ecoli.py` — `@composite_generator`.
- `tests/test_ecoli3d_*.py` — per-module tests.

**Modify:**
- `pyproject.toml` — add `ecoli3d*` to `[tool.setuptools] packages.find.include`.

---

## Task 1: Package skeleton + parsimony binary discovery

**Files:**
- Create: `ecoli3d/__init__.py`, `ecoli3d/config.py`
- Modify: `pyproject.toml` (packages include)
- Test: `tests/test_ecoli3d_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ecoli3d_config.py
import os, pytest

@pytest.mark.fast
def test_find_parsimony_bin_via_env(tmp_path, monkeypatch):
    from ecoli3d.config import find_parsimony_bin, ParsimonyNotFound
    fake = tmp_path / "parsimony"
    fake.write_text("#!/bin/sh\n"); fake.chmod(0o755)
    monkeypatch.setenv("PARSIMONY_BIN", str(fake))
    assert find_parsimony_bin() == str(fake)

@pytest.mark.fast
def test_find_parsimony_bin_missing_raises(monkeypatch):
    from ecoli3d.config import find_parsimony_bin, ParsimonyNotFound
    monkeypatch.delenv("PARSIMONY_BIN", raising=False)
    monkeypatch.delenv("PARSIMONY_HOME", raising=False)
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(ParsimonyNotFound):
        find_parsimony_bin()
```

- [ ] **Step 2: Run; verify it fails**

Run: `pytest tests/test_ecoli3d_config.py -v`
Expected: FAIL — `ModuleNotFoundError: ecoli3d`.

- [ ] **Step 3: Implement `config.py` + `__init__.py`**

```python
# ecoli3d/__init__.py
"""3D structural E. coli: bridge v2ecoli molecular state to parsimony packing."""
from ecoli3d.config import find_parsimony_bin, parsimony_examples_dir, ParsimonyNotFound

__all__ = ["find_parsimony_bin", "parsimony_examples_dir", "ParsimonyNotFound"]
```

```python
# ecoli3d/config.py
import os, shutil
from pathlib import Path

class ParsimonyNotFound(RuntimeError):
    """The parsimony binary could not be located."""

def find_parsimony_bin() -> str:
    """Locate the parsimony binary: $PARSIMONY_BIN, else
    $PARSIMONY_HOME/target/release/parsimony, else `parsimony` on PATH."""
    env = os.environ.get("PARSIMONY_BIN")
    if env and Path(env).exists():
        return env
    home = os.environ.get("PARSIMONY_HOME")
    if home:
        cand = Path(home) / "target" / "release" / "parsimony"
        if cand.exists():
            return str(cand)
    found = shutil.which("parsimony")
    if found:
        return found
    raise ParsimonyNotFound(
        "parsimony binary not found. Set PARSIMONY_BIN to the binary, or "
        "PARSIMONY_HOME to the parsimony repo (with target/release/parsimony built)."
    )

def parsimony_examples_dir() -> Path:
    """Path to parsimony's examples/ (for genome/, recipes/, pdb_meshes/)."""
    home = os.environ.get("PARSIMONY_HOME")
    if home and (Path(home) / "examples").is_dir():
        return Path(home) / "examples"
    bin_path = Path(find_parsimony_bin()).resolve()
    # .../<repo>/target/release/parsimony -> <repo>/examples
    for parent in bin_path.parents:
        if (parent / "examples").is_dir() and (parent / "Cargo.toml").exists():
            return parent / "examples"
    raise ParsimonyNotFound("could not locate parsimony examples/ — set PARSIMONY_HOME")
```

- [ ] **Step 4: Add the package to pyproject + run tests**

Edit `pyproject.toml` `[tool.setuptools]`:
```toml
packages = { find = { where = ["."], include = ["v2ecoli*", "pbg_v2ecoli*", "ecoli3d*"] } }
```
Run: `pip install -e . && pytest tests/test_ecoli3d_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add ecoli3d/__init__.py ecoli3d/config.py tests/test_ecoli3d_config.py pyproject.toml
git commit -m "feat(ecoli3d): package skeleton + parsimony binary discovery"
```

---

## Task 2: Extract a CellSnapshot from v2ecoli

**Files:**
- Create: `ecoli3d/state.py`
- Test: `tests/test_ecoli3d_state.py`

`CellSnapshot` is the bridge's clean interface to v2ecoli: a list of species `(ecocyc_id, compartment, count)`, capsule geometry, and genome length. The exact label-access API for the `monomer_counts` labeled array must be confirmed against the live object — Step 1 is a spike to pin it before implementing.

- [ ] **Step 1: SPIKE — pin the snapshot API against a live composite**

Run this throwaway snippet inside the venv and READ the output to confirm field shapes (do not commit it):

```python
# scratch_spike.py  (delete after)
import v2ecoli
c = v2ecoli.build_composite("baseline", seed=0, cache_dir="out/cache")
c.run(2)  # minimal advance to populate listeners
cell = c.state.get("agents", {}).get("0", c.state)
mc = cell["listeners"]["monomer_counts"]
print("monomer_counts type:", type(mc), "len:", getattr(mc, "shape", len(mc)))
# How are the monomer IDs (labels, with [c]/[i]/[p]/[o] tags) stored? Inspect:
print("keys at cell['listeners']:", list(cell["listeners"].keys())[:20])
print("volume:", cell["listeners"]["mass"]["volume"])
# Find where the ordered monomer-id labels live (config of the counts deriver,
# or a sibling store). Print a handful of ids to confirm the compartment tag.
```

Run: `cd /Users/eranagmon/code/3d-ecoli && source .venv/bin/activate && python scratch_spike.py`
Record: how to get the ordered list of monomer IDs aligned with `monomer_counts`, and the units of `volume`. Adjust the code in Step 3 to match what you observed.

- [ ] **Step 2: Write the failing test (marked `sim` — it runs the composite)**

```python
# tests/test_ecoli3d_state.py
import pytest

@pytest.mark.sim
def test_snapshot_has_species_geometry_and_genome():
    from ecoli3d.state import snapshot_from_v2ecoli
    snap = snapshot_from_v2ecoli(composite="baseline", seed=0, advance_s=2.0)
    assert len(snap.species) > 1000, f"expected a populated proteome, got {len(snap.species)}"
    # Compartment tags are one of the EcoCyc abbreviations.
    comps = {s.compartment for s in snap.species}
    assert comps <= {"c", "i", "p", "o", "e", "j", "m"}, comps
    assert "c" in comps  # cytoplasm always present
    # Capsule geometry: radius ~0.5 µm, length > diameter (a rod).
    assert snap.capsule_radius_um == pytest.approx(0.5, abs=0.01)
    assert snap.capsule_length_um > 2 * snap.capsule_radius_um
    assert snap.genome_length_bp == 4_641_652
```

- [ ] **Step 3: Implement `state.py`**

```python
# ecoli3d/state.py
from __future__ import annotations
import math
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Species:
    ecocyc_id: str      # e.g. "EG10001" / "MONOMER-1" (without compartment tag)
    compartment: str    # c | i | p | o | e | j | m
    count: int

@dataclass(frozen=True)
class CellSnapshot:
    species: list[Species]
    capsule_radius_um: float
    capsule_length_um: float
    genome_length_bp: int
    extra: dict = field(default_factory=dict)

def _split_tag(label: str) -> tuple[str, str]:
    """`MONOMER-1[c]` -> ("MONOMER-1", "c"); no tag -> ("...", "c")."""
    if label.endswith("]") and "[" in label:
        base, tag = label[:-1].rsplit("[", 1)
        return base, tag
    return label, "c"

def _capsule_dims_um(volume_fl: float) -> tuple[float, float]:
    """v2ecoli bridge.py geometry: radius 0.5 µm; length from volume (fL≈µm³)."""
    radius = 0.5
    if volume_fl > 0:
        cyl = (volume_fl - (4.0 / 3.0) * math.pi * radius ** 3) / (math.pi * radius ** 2)
        length = max(2 * radius, cyl + 2 * radius)
    else:
        length = 2.0
    return radius, length

def snapshot_from_v2ecoli(*, composite: str = "baseline", seed: int = 0,
                          advance_s: float = 2.0) -> CellSnapshot:
    import v2ecoli
    comp = v2ecoli.build_composite(composite, seed=seed, cache_dir="out/cache")
    if advance_s > 0:
        comp.run(advance_s)
    cell = comp.state.get("agents", {}).get("0", comp.state)
    counts = cell["listeners"]["monomer_counts"]
    labels = _monomer_labels(comp, cell)   # <- from the Step-1 spike; see below
    species = []
    for label, n in zip(labels, list(counts)):
        if int(n) <= 0:
            continue
        base, tag = _split_tag(str(label))
        species.append(Species(ecocyc_id=base, compartment=tag, count=int(n)))
    radius, length = _capsule_dims_um(float(cell["listeners"]["mass"]["volume"]))
    genome_length = _genome_length(comp)   # see below
    return CellSnapshot(species, radius, length, genome_length)

def _monomer_labels(comp, cell) -> list[str]:
    """Ordered monomer-id labels aligned with listeners.monomer_counts.
    EXACT source confirmed by the Step-1 spike — adjust this body to match."""
    # Most likely: the counts deriver's config carries the ordered ids.
    # Fallback paths to try (in order) based on the spike:
    #   cell["listeners"].get("monomer_ids")
    #   comp.state[...]/process config "monomer_ids"
    raise NotImplementedError("set from the Step-1 spike result")

def _genome_length(comp) -> int:
    """E. coli K-12 genome length. Prefer the live value; constant fallback."""
    try:
        # sim_data.process.replication.genome_length (see v2ecoli initial_conditions.py:154)
        return int(comp.state["agents"]["0"]["..."])  # adjust per spike
    except Exception:
        return 4_641_652
```

Replace `_monomer_labels` / `_genome_length` bodies with the exact access paths confirmed in Step 1. (Leaving `NotImplementedError` is acceptable ONLY between Steps 1 and 3 of this task; it must be real before Step 4.)

- [ ] **Step 4: Run; verify it passes**

Run: `pytest tests/test_ecoli3d_state.py -v -m sim`
Expected: PASS. Delete `scratch_spike.py`.

- [ ] **Step 5: Commit**

```bash
git add ecoli3d/state.py tests/test_ecoli3d_state.py
git commit -m "feat(ecoli3d): CellSnapshot extraction from v2ecoli (species/geometry/genome)"
```

---

## Task 3: EcoCyc → UniProt mapping

**Files:**
- Create: `ecoli3d/idmap.py`, `ecoli3d/data/.gitkeep`
- Test: `tests/test_ecoli3d_idmap.py`

v2ecoli has **no UniProt field**. Build the cross-reference from the UniProt E. coli K-12 reference proteome (UP000000625), which lists, per entry, the UniProt accession + the gene's ordered-locus name (b-number) and EcoCyc xref. Cache it to a TSV so the network fetch happens once.

- [ ] **Step 1: Write the failing test (offline — uses a cached fixture)**

```python
# tests/test_ecoli3d_idmap.py
import pytest

@pytest.mark.fast
def test_idmap_reads_cache(tmp_path):
    from ecoli3d.idmap import load_cached_map
    cache = tmp_path / "ecocyc_uniprot.tsv"
    cache.write_text("ecocyc\tuniprot\tbnumber\nEG10031\tP0A7Z4\tb3987\n")
    m = load_cached_map(cache)
    assert m["EG10031"] == "P0A7Z4"
    assert m["b3987"] == "P0A7Z4"  # b-numbers indexed too

@pytest.mark.fast
def test_resolve_uniprot_prefers_ecocyc_then_bnumber():
    from ecoli3d.idmap import resolve_uniprot
    m = {"EG10031": "P0A7Z4", "b3987": "P0A7Z4"}
    assert resolve_uniprot("EG10031", m) == "P0A7Z4"
    assert resolve_uniprot("b3987", m) == "P0A7Z4"
    assert resolve_uniprot("UNKNOWN", m) is None
```

- [ ] **Step 2: Run; verify fail**

Run: `pytest tests/test_ecoli3d_idmap.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `idmap.py`**

```python
# ecoli3d/idmap.py
from __future__ import annotations
import csv, io, urllib.request
from pathlib import Path

_DEFAULT_CACHE = Path(__file__).parent / "data" / "ecocyc_uniprot.tsv"
# UniProt REST: stream the K-12 reference proteome with the fields we need.
_UNIPROT_URL = (
    "https://rest.uniprot.org/uniprotkb/stream?"
    "query=proteome:UP000000625&format=tsv&"
    "fields=accession,gene_oln,xref_ecogene,gene_primary"
)

def fetch_uniprot_map(cache: Path = _DEFAULT_CACHE) -> Path:
    """Download the UP000000625 proteome and write ecocyc/uniprot/bnumber TSV."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(_UNIPROT_URL, timeout=120) as r:
        text = r.read().decode("utf-8")
    rows = []
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    for row in reader:
        acc = (row.get("Entry") or "").strip()
        oln = (row.get("Gene Names (ordered locus)") or "").strip().split(";")[0].strip()
        # EcoCyc/EcoGene xref column name varies; capture whatever is present.
        ecocyc = ""
        for k, v in row.items():
            if v and ("EcoCyc" in k or "EcoGene" in k):
                ecocyc = v.split(";")[0].strip(); break
        if acc and (oln or ecocyc):
            rows.append((ecocyc, acc, oln))
    with open(cache, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["ecocyc", "uniprot", "bnumber"])
        w.writerows(rows)
    return cache

def load_cached_map(cache: Path = _DEFAULT_CACHE) -> dict[str, str]:
    """Map both EcoCyc id and b-number → UniProt accession."""
    out: dict[str, str] = {}
    with open(cache, newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            acc = row["uniprot"].strip()
            if row.get("ecocyc"):
                out[row["ecocyc"].strip()] = acc
            if row.get("bnumber"):
                out[row["bnumber"].strip()] = acc
    return out

def ecocyc_to_uniprot(cache: Path = _DEFAULT_CACHE) -> dict[str, str]:
    if not cache.exists():
        fetch_uniprot_map(cache)
    return load_cached_map(cache)

def resolve_uniprot(ecocyc_or_b: str, m: dict[str, str]) -> str | None:
    return m.get(ecocyc_or_b)
```

- [ ] **Step 4: Run unit tests; then a live-fetch smoke (network)**

Run: `pytest tests/test_ecoli3d_idmap.py -v` → PASS.
Smoke (network, manual): `python -c "from ecoli3d.idmap import fetch_uniprot_map, load_cached_map as L; p=fetch_uniprot_map(); print(len(L(p)), 'mappings')"` — expect a few thousand. Confirm the EcoCyc/b-number column names against the live TSV header; adjust `fetch_uniprot_map` if UniProt's field labels differ. Commit the generated `ecoli3d/data/ecocyc_uniprot.tsv` so downstream runs are offline.

- [ ] **Step 5: Commit**

```bash
git add ecoli3d/idmap.py ecoli3d/data/ tests/test_ecoli3d_idmap.py
git commit -m "feat(ecoli3d): EcoCyc/b-number -> UniProt mapping (UP000000625, cached)"
```

---

## Task 4: Structure resolution (AlphaFold + curated PDB) + meshing

**Files:**
- Create: `ecoli3d/structures.py`, `ecoli3d/assemblies.toml`
- Test: `tests/test_ecoli3d_structures.py`

Per species: if it's in the curated `assemblies.toml` (ribosome, RNAP, GroEL, ATP synthase, …) use that PDB id; else map to UniProt and use the AlphaFold model `AF-<acc>-F1-model_v4.pdb`. Download to a cache; mesh via `parsimony mesh`.

- [ ] **Step 1: Curated assemblies table**

```toml
# ecoli3d/assemblies.toml — large/known E. coli assemblies by PDB id.
# key = species id substring or EcoCyc complex id; pdb = RCSB id.
[ribosome_70S]
pdb = "4YBB"      # E. coli 70S ribosome
[rna_polymerase]
pdb = "6ALH"      # E. coli RNAP holoenzyme
[groel]
pdb = "1AON"      # GroEL/GroES
[atp_synthase]
pdb = "6OQR"      # E. coli ATP synthase
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_ecoli3d_structures.py
import pytest

@pytest.mark.fast
def test_alphafold_url_for_accession():
    from ecoli3d.structures import alphafold_pdb_url
    u = alphafold_pdb_url("P0A7Z4")
    assert u.endswith("AF-P0A7Z4-F1-model_v4.pdb")
    assert "alphafold" in u

@pytest.mark.fast
def test_resolve_prefers_curated_assembly():
    from ecoli3d.structures import resolve_structure, load_assemblies
    asm = load_assemblies()
    ref = resolve_structure("groel", uniprot=None, assemblies=asm)
    assert ref.kind == "pdb" and ref.id == "1AON"
    ref2 = resolve_structure("EG10031", uniprot="P0A7Z4", assemblies=asm)
    assert ref2.kind == "alphafold" and ref2.id == "P0A7Z4"
    ref3 = resolve_structure("EGxxxxx", uniprot=None, assemblies=asm)
    assert ref3 is None  # no structure available -> caller sphere-fallbacks
```

- [ ] **Step 3: Implement `structures.py`**

```python
# ecoli3d/structures.py
from __future__ import annotations
import subprocess, tomllib, urllib.request
from dataclasses import dataclass
from pathlib import Path
from ecoli3d.config import find_parsimony_bin

_ASM = Path(__file__).parent / "assemblies.toml"

@dataclass(frozen=True)
class StructureRef:
    kind: str   # "pdb" | "alphafold"
    id: str     # PDB id or UniProt accession
    slug: str   # mesh basename (lowercased id)

def load_assemblies(path: Path = _ASM) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)

def alphafold_pdb_url(acc: str) -> str:
    return f"https://alphafold.ebi.ac.uk/files/AF-{acc}-F1-model_v4.pdb"

def resolve_structure(species_id: str, uniprot: str | None, assemblies: dict) -> StructureRef | None:
    for key, entry in assemblies.items():
        if key in species_id.lower():
            return StructureRef("pdb", entry["pdb"], entry["pdb"].lower())
    if uniprot:
        return StructureRef("alphafold", uniprot, f"af-{uniprot.lower()}")
    return None

def fetch_structure(ref: StructureRef, cache_dir: Path) -> Path:
    """Download a PDB (RCSB) or AlphaFold model into cache_dir; return the path."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{ref.slug}.pdb"
    if out.exists():
        return out
    url = (f"https://files.rcsb.org/download/{ref.id}.pdb"
           if ref.kind == "pdb" else alphafold_pdb_url(ref.id))
    with urllib.request.urlopen(url, timeout=120) as r, open(out, "wb") as w:
        w.write(r.read())
    return out

def mesh_structure(pdb_path: Path, out_dir: Path) -> str:
    """Run `parsimony mesh <pdb>` -> <slug>.lod*.obj in out_dir; return slug."""
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([find_parsimony_bin(), "mesh", str(pdb_path), "--out-dir", str(out_dir)],
                   check=True)
    return pdb_path.stem
```

- [ ] **Step 4: Run unit tests; live-fetch smoke**

Run: `pytest tests/test_ecoli3d_structures.py -v` → PASS.
Smoke (network): fetch + mesh one AlphaFold model:
`python -c "from ecoli3d.structures import *; from pathlib import Path; r=StructureRef('alphafold','P0A7Z4','af-p0a7z4'); p=fetch_structure(r, Path('out/struct')); print(mesh_structure(p, Path('out/meshes')))"`
Expect `.lod*.obj` files written. (AlphaFold PDBs have long disordered tails — note for Plan 3: pLDDT trimming.)

- [ ] **Step 5: Commit**

```bash
git add ecoli3d/structures.py ecoli3d/assemblies.toml tests/test_ecoli3d_structures.py
git commit -m "feat(ecoli3d): structure resolution (AlphaFold + curated PDB) and meshing"
```

---

## Task 5: Abundance scaling

**Files:**
- Create: `ecoli3d/scale.py`
- Test: `tests/test_ecoli3d_scale.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_ecoli3d_scale.py
import pytest
from ecoli3d.state import Species

@pytest.mark.fast
def test_top_n_keeps_most_abundant():
    from ecoli3d.scale import apply_scale
    sp = [Species(f"g{i}", "c", count=i) for i in range(1, 101)]
    kept, dropped = apply_scale(sp, top_n=10)
    assert len(kept) == 10
    assert min(s.count for s in kept) == 91   # the 10 largest
    assert dropped == 90

@pytest.mark.fast
def test_abundance_scale_floors_at_one():
    from ecoli3d.scale import apply_scale
    sp = [Species("a", "c", 1000), Species("b", "c", 3)]
    kept, _ = apply_scale(sp, abundance_scale=0.1)
    counts = {s.ecocyc_id: s.count for s in kept}
    assert counts["a"] == 100 and counts["b"] == 1  # floor at 1, not 0
```

- [ ] **Step 2: Run; verify fail.** `pytest tests/test_ecoli3d_scale.py -v` → FAIL.

- [ ] **Step 3: Implement `scale.py`**

```python
# ecoli3d/scale.py
from __future__ import annotations
import logging
from dataclasses import replace
from ecoli3d.state import Species

log = logging.getLogger("ecoli3d.scale")

def apply_scale(species: list[Species], *, top_n: int | None = None,
                abundance_scale: float = 1.0) -> tuple[list[Species], int]:
    """Keep the `top_n` most abundant (if set) and multiply counts by
    `abundance_scale` (floored at 1 for kept species). Returns (kept, n_dropped)
    and logs the drop so truncation is never silent."""
    ordered = sorted(species, key=lambda s: s.count, reverse=True)
    kept = ordered[:top_n] if top_n is not None else ordered
    dropped = len(ordered) - len(kept)
    if abundance_scale != 1.0:
        kept = [replace(s, count=max(1, round(s.count * abundance_scale))) for s in kept]
    if dropped:
        log.warning("abundance scaling dropped %d/%d species (top_n=%s)",
                    dropped, len(ordered), top_n)
    return kept, dropped
```

- [ ] **Step 4: Run; verify pass.** `pytest tests/test_ecoli3d_scale.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add ecoli3d/scale.py tests/test_ecoli3d_scale.py
git commit -m "feat(ecoli3d): abundance scaling (top_n / abundance_scale, logged)"
```

---

## Task 6: Recipe + genome-CSV authoring

**Files:**
- Create: `ecoli3d/recipe.py`
- Test: `tests/test_ecoli3d_recipe.py`

Author a parsimony recipe JSON (capsule cell, `mesh_lods` per resolved structure or sphere fallback, interior/surface regions routed by compartment tag, chromosome block) and a genome CSV in parsimony's format (reuse the same schema as Plan 1's `examples/genome/ecoli_k12_genes.csv`).

- [ ] **Step 1: Failing test**

```python
# tests/test_ecoli3d_recipe.py
import json, pytest
from ecoli3d.state import Species, CellSnapshot

@pytest.mark.fast
def test_author_recipe_has_capsule_and_regions(tmp_path):
    from ecoli3d.recipe import author_recipe
    snap = CellSnapshot(
        species=[Species("groel", "c", 50), Species("ompA", "o", 200)],
        capsule_radius_um=0.5, capsule_length_um=2.0, genome_length_bp=4_641_652)
    structures = {"groel": ("mesh", ["groel.lod0.obj", "groel.lod1.obj"]),
                  "ompA": ("sphere", 25.0)}
    recipe = author_recipe(snap, structures, mesh_rel="../pdb_meshes",
                           genome_csv="../genome/ecoli_k12_genes.csv")
    cell = recipe["composition"]["cell"]
    assert cell["compartment"]["kind"] == "capsule"
    # µm -> Å (×10000): radius 0.5 µm = 5000 Å; half-length along x.
    assert cell["compartment"]["radius"] == pytest.approx(5000.0)
    ids = {d["object"] for d in cell["regions"]["interior"]}
    assert "groel" in ids                       # cytoplasm -> interior
    assert any(d["object"] == "ompA" for d in cell["regions"]["surface"])  # o -> surface
    assert recipe["chromosome"]["genome"] == "../genome/ecoli_k12_genes.csv"
    assert recipe["chromosome"]["beads"] > 1000
```

- [ ] **Step 2: Run; verify fail.** `pytest tests/test_ecoli3d_recipe.py -v` → FAIL.

- [ ] **Step 3: Implement `recipe.py`**

```python
# ecoli3d/recipe.py
from __future__ import annotations
import csv, json
from pathlib import Path
from ecoli3d.state import CellSnapshot

UM_TO_A = 10_000.0  # 1 µm = 10,000 Å
# Compartment tag -> recipe region. Inner membrane / outer membrane / periplasm
# all route to "surface" in Phase 1 (single envelope); refined in Phase 2.
_SURFACE_TAGS = {"i", "o", "m", "p", "j"}
_LOD_VOXELS = [16.0, 8.0, 4.0, 2.5]

def _capsule(snap: CellSnapshot) -> dict:
    r = snap.capsule_radius_um * UM_TO_A
    half = max(r, (snap.capsule_length_um * UM_TO_A) / 2.0 - r)  # cylinder half-length
    return {"kind": "capsule", "a": [-half, 0, 0], "b": [half, 0, 0], "radius": r}

def _object_entry(struct) -> dict:
    kind, payload = struct
    if kind == "mesh":
        return {"type": "mesh", "mesh_lods": [
            {"path": p, "voxel_size": v} for p, v in zip(payload, _LOD_VOXELS)]}
    return {"type": "single_sphere", "radius": float(payload)}

def author_recipe(snap: CellSnapshot, structures: dict, *, mesh_rel: str,
                  genome_csv: str, bead_spacing: float = 135.0,
                  bead_radius: float = 12.0) -> dict:
    objects, interior, surface = {}, [], []
    for s in snap.species:
        if s.ecocyc_id not in structures:
            continue
        st = structures[s.ecocyc_id]
        if st[0] == "mesh":
            st = ("mesh", [f"{mesh_rel}/{p}" for p in st[1]])
        objects[s.ecocyc_id] = _object_entry(st)
        (surface if s.compartment in _SURFACE_TAGS else interior).append(
            {"object": s.ecocyc_id, "count": int(s.count)})
    beads = max(1000, snap.genome_length_bp // 40)  # ~40 bp/bead (coarse first pass)
    return {
        "name": "ecoli_3d", "version": "0.1.0", "format_version": "2.1-parsimony",
        "description": "3D E. coli authored from a v2ecoli snapshot.",
        "bounding_box": [[-(snap.capsule_length_um*UM_TO_A), -snap.capsule_radius_um*UM_TO_A*1.2,
                          -snap.capsule_radius_um*UM_TO_A*1.2],
                         [ (snap.capsule_length_um*UM_TO_A),  snap.capsule_radius_um*UM_TO_A*1.2,
                           snap.capsule_radius_um*UM_TO_A*1.2]],
        "objects": objects,
        "composition": {
            "space": {"regions": {"interior": ["cell"]}},
            "cell": {"compartment": _capsule(snap),
                     "regions": {"interior": interior, "surface": surface}},
        },
        "chromosome": {
            "beads": beads, "spacing": bead_spacing, "bead_radius": bead_radius,
            "color": [0.85, 0.75, 0.45], "compartment": "cell",
            "genome": genome_csv,
            "supercoil": {"radius": 90.0, "pitch": 130.0, "domains": 200},
            "proteins": [],
        },
    }

def write_recipe(recipe: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recipe, indent=2))
    return path
```

- [ ] **Step 4: Run; verify pass.** `pytest tests/test_ecoli3d_recipe.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add ecoli3d/recipe.py tests/test_ecoli3d_recipe.py
git commit -m "feat(ecoli3d): author parsimony recipe (capsule + regions + chromosome)"
```

---

## Task 7: ParsimonyPackStep (process-bigraph Step)

**Files:**
- Create: `ecoli3d/steps/__init__.py`, `ecoli3d/steps/parsimony_pack.py`
- Test: `tests/test_ecoli3d_pack_step.py`

A `Step` that takes a recipe path (+ pipeline) and runs `parsimony pipeline run` (octree), emitting the pack path + summary. Follows the v2ecoli `EcoliStep` convention (see `v2ecoli/library/ecoli_step.py`).

- [ ] **Step 1: Failing test (fast — uses a fake binary, no real pack)**

```python
# tests/test_ecoli3d_pack_step.py
import os, json, pytest

@pytest.mark.fast
def test_pack_step_invokes_pipeline(tmp_path, monkeypatch):
    from ecoli3d.steps.parsimony_pack import run_pack
    # Fake parsimony that just writes a pack file where expected.
    fake = tmp_path / "parsimony"
    pack = tmp_path / "out.pack.json"
    fake.write_text(f'#!/bin/sh\necho \'{{"placements":[]}}\' > "{pack}"\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PARSIMONY_BIN", str(fake))
    result = run_pack(pipeline=str(tmp_path / "p.pipeline.json"),
                      out_pack=str(pack), proxy_lod=2)
    assert result["pack_path"] == str(pack)
    assert os.path.exists(pack)
```

- [ ] **Step 2: Run; verify fail.** `pytest tests/test_ecoli3d_pack_step.py -v` → FAIL.

- [ ] **Step 3: Implement the Step + the `run_pack` helper**

```python
# ecoli3d/steps/__init__.py
from ecoli3d.steps.parsimony_pack import ParsimonyPackStep, run_pack
__all__ = ["ParsimonyPackStep", "run_pack"]
```

```python
# ecoli3d/steps/parsimony_pack.py
from __future__ import annotations
import subprocess
from pathlib import Path
from process_bigraph import Step
from ecoli3d.config import find_parsimony_bin

def run_pack(*, pipeline: str, out_pack: str, proxy_lod: int = 2) -> dict:
    """Run `parsimony pipeline run <pipeline> --out <out> --proxy-lod N`."""
    cmd = [find_parsimony_bin(), "pipeline", "run", pipeline,
           "--out", out_pack, "--proxy-lod", str(proxy_lod)]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return {"pack_path": out_pack, "stdout": proc.stdout.strip()}

class ParsimonyPackStep(Step):
    """Pack a parsimony recipe (via its staged pipeline) into a viewer pack."""
    config_schema = {
        "pipeline_path": {"_type": "string", "_default": ""},
        "out_pack": {"_type": "string", "_default": "out/ecoli_3d.pack.json"},
        "proxy_lod": {"_type": "integer", "_default": 2},
    }
    def inputs(self):
        return {"recipe_ready": {"_type": "boolean", "_default": False}}
    def outputs(self):
        return {"pack": {"pack_path": {"_type": "string", "_default": ""},
                         "stdout": {"_type": "string", "_default": ""}}}
    def update(self, state, interval=None):
        if not state.get("recipe_ready", True):
            return {}
        res = run_pack(pipeline=self.config["pipeline_path"],
                       out_pack=self.config["out_pack"],
                       proxy_lod=self.config["proxy_lod"])
        return {"pack": res}
```

(Confirm the `Step` base import + config access pattern against `v2ecoli/library/ecoli_step.py`; if the codebase wraps `Step` as `EcoliStep` with a `parameters`/`initialize` convention, subclass that instead and read config via `self.parameters`.)

- [ ] **Step 4: Run; verify pass.** `pytest tests/test_ecoli3d_pack_step.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add ecoli3d/steps/ tests/test_ecoli3d_pack_step.py
git commit -m "feat(ecoli3d): ParsimonyPackStep wrapping `parsimony pipeline run`"
```

---

## Task 8: Orchestration — `build_3d_ecoli`

**Files:**
- Create: `ecoli3d/run.py`
- Test: `tests/test_ecoli3d_run.py` (fast unit of the wiring; the full end-to-end is Task 10)

- [ ] **Step 1: Failing test (wire snapshot→scale→structures→recipe with fakes)**

```python
# tests/test_ecoli3d_run.py
import pytest
from ecoli3d.state import Species, CellSnapshot

@pytest.mark.fast
def test_build_recipe_from_snapshot(monkeypatch, tmp_path):
    from ecoli3d import run as R
    snap = CellSnapshot([Species("groel","c",50), Species("ompA","o",200)],
                        0.5, 2.0, 4_641_652)
    monkeypatch.setattr(R, "snapshot_from_v2ecoli", lambda **k: snap)
    # Fake structure resolution: groel curated, ompA sphere-fallback.
    monkeypatch.setattr(R, "_resolve_all", lambda species, **k:
                        {"groel": ("mesh", ["1aon.lod0.obj"]), "ompA": ("sphere", 25.0)})
    recipe_path, _ = R.build_recipe_only(top_n=2, out_dir=tmp_path)
    assert recipe_path.exists()
```

- [ ] **Step 2: Run; verify fail.** → FAIL.

- [ ] **Step 3: Implement `run.py`** (snapshot → scale → resolve+fetch+mesh → recipe + genome CSV → pipeline JSON → pack). Provide `build_recipe_only(...)` (used by the test) and `build_3d_ecoli(...)` (full, calls `run_pack`). Reuse `state.snapshot_from_v2ecoli`, `scale.apply_scale`, `idmap.ecocyc_to_uniprot`, `structures.*`, `recipe.author_recipe/write_recipe`, and write a pipeline JSON mirroring `examples/pipelines/ecoli_nucleoid.pipeline.json` (Plan 1). Copy the genome CSV from `parsimony_examples_dir()/genome/ecoli_k12_genes.csv`.

```python
# ecoli3d/run.py  (skeleton — fill the bodies; all helpers exist from Tasks 2-7)
from __future__ import annotations
import json, shutil
from pathlib import Path
from ecoli3d.state import snapshot_from_v2ecoli
from ecoli3d.scale import apply_scale
from ecoli3d.idmap import ecocyc_to_uniprot, resolve_uniprot
from ecoli3d.structures import load_assemblies, resolve_structure, fetch_structure, mesh_structure
from ecoli3d.recipe import author_recipe, write_recipe
from ecoli3d.steps.parsimony_pack import run_pack
from ecoli3d.config import parsimony_examples_dir

def _resolve_all(species, *, mesh_dir: Path, struct_dir: Path) -> dict:
    asm = load_assemblies(); idm = ecocyc_to_uniprot(); out = {}
    for s in species:
        ref = resolve_structure(s.ecocyc_id, resolve_uniprot(s.ecocyc_id, idm), asm)
        if ref is None:
            out[s.ecocyc_id] = ("sphere", 25.0); continue   # fallback bead
        slug = mesh_structure(fetch_structure(ref, struct_dir), mesh_dir)
        out[s.ecocyc_id] = ("mesh", [f"{slug}.lod{i}.obj" for i in range(4)])
    return out

def build_recipe_only(*, top_n=50, abundance_scale=1.0, out_dir=Path("out/ecoli3d"),
                      composite="baseline", seed=0, advance_s=2.0):
    out_dir = Path(out_dir); mesh_dir = out_dir / "pdb_meshes"
    snap = snapshot_from_v2ecoli(composite=composite, seed=seed, advance_s=advance_s)
    kept, _ = apply_scale(snap.species, top_n=top_n, abundance_scale=abundance_scale)
    snap = type(snap)(kept, snap.capsule_radius_um, snap.capsule_length_um, snap.genome_length_bp)
    structs = _resolve_all(kept, mesh_dir=mesh_dir, struct_dir=out_dir / "struct")
    # genome CSV from parsimony's examples (Plan 1 fixture).
    csv_src = parsimony_examples_dir() / "genome" / "ecoli_k12_genes.csv"
    csv_dst = out_dir / "genome" / "ecoli_k12_genes.csv"
    csv_dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy(csv_src, csv_dst)
    recipe = author_recipe(snap, structs, mesh_rel="pdb_meshes",
                           genome_csv="genome/ecoli_k12_genes.csv")
    recipe_path = write_recipe(recipe, out_dir / "ecoli_3d.json")
    pipeline = {"name": "ecoli_3d_staged", "recipe": "ecoli_3d.json", "seed": seed,
                "strict_bounds": True, "backend": "octree", "stages": [
                    {"id": "chromosome", "kind": "chromosome"},
                    {"id": "interior", "kind": "pack", "include": [], "exclude": [],
                     "densify": True, "depends_on": ["chromosome"], "clearance_cell_size": 40}]}
    pipe_path = out_dir / "ecoli_3d.pipeline.json"
    pipe_path.write_text(json.dumps(pipeline, indent=2))
    return recipe_path, pipe_path

def build_3d_ecoli(*, top_n=50, abundance_scale=1.0, out_dir=Path("out/ecoli3d"), **kw):
    recipe_path, pipe_path = build_recipe_only(top_n=top_n, abundance_scale=abundance_scale,
                                               out_dir=out_dir, **kw)
    return run_pack(pipeline=str(pipe_path), out_pack=str(Path(out_dir)/"ecoli_3d.pack.json"))
```

- [ ] **Step 4: Run; verify pass.** `pytest tests/test_ecoli3d_run.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add ecoli3d/run.py tests/test_ecoli3d_run.py
git commit -m "feat(ecoli3d): build_3d_ecoli orchestration (snapshot->recipe->pack)"
```

---

## Task 9 (Phase 0): Composite + smoke test through ecoli_starter

**Files:**
- Create: `ecoli3d/composites/__init__.py`, `ecoli3d/composites/parsimony_ecoli.py`
- Test: `tests/test_ecoli3d_composite.py`

Register the composite generator and smoke-test the packing path end-to-end using parsimony's existing `ecoli_starter.json` (no v2ecoli snapshot, no new structures) — proving the Step + binary wiring.

- [ ] **Step 1: Failing smoke test (real parsimony, small recipe)**

```python
# tests/test_ecoli3d_composite.py
import os, json, pytest
from pathlib import Path

@pytest.mark.sim
def test_pack_ecoli_starter_via_step(tmp_path):
    """Drive parsimony's ecoli_starter through ParsimonyPackStep's run_pack."""
    from ecoli3d.config import parsimony_examples_dir, find_parsimony_bin
    from ecoli3d.steps.parsimony_pack import run_pack
    find_parsimony_bin()  # skips clearly if not built
    examples = parsimony_examples_dir()
    # Author a 1-stage pipeline over the committed ecoli_starter recipe.
    pipe = tmp_path / "starter.pipeline.json"
    pipe.write_text(json.dumps({
        "name": "starter", "recipe": str(examples / "recipes" / "ecoli_starter.json"),
        "seed": 0, "strict_bounds": True, "backend": "octree",
        "stages": [{"id": "all", "kind": "pack", "include": [], "exclude": [], "densify": False}]}))
    out = tmp_path / "starter.pack.json"
    res = run_pack(pipeline=str(pipe), out_pack=str(out), proxy_lod=2)
    data = json.loads(Path(res["pack_path"]).read_text())
    assert len(data["placements"]) > 1000
```

- [ ] **Step 2: Run; verify fail** (until the composite + wiring exist / parsimony built). If parsimony isn't built, build it (see Prerequisite).

- [ ] **Step 3: Implement the composite generator**

```python
# ecoli3d/composites/__init__.py
from ecoli3d.composites import parsimony_ecoli  # noqa: F401 — register decorator
__all__ = ["parsimony_ecoli"]
```

```python
# ecoli3d/composites/parsimony_ecoli.py
from typing import Any
from pbg_superpowers.composite_generator import composite_generator

@composite_generator(
    name="parsimony-ecoli",
    description="Pack a 3D E. coli from a v2ecoli snapshot via parsimony.",
    parameters={
        "seed": {"type": "integer", "default": 0},
        "top_n": {"type": "integer", "default": 50},
        "abundance_scale": {"type": "number", "default": 1.0},
        "out_dir": {"type": "string", "default": "out/ecoli3d"},
    },
)
def parsimony_ecoli(core: Any = None, *, seed: int = 0, top_n: int = 50,
                    abundance_scale: float = 1.0, out_dir: str = "out/ecoli3d") -> dict:
    """A thin process-bigraph document that runs build_3d_ecoli as one Step.
    (The heavy lifting is in ecoli3d.run; this exposes it to the pbg/dashboard.)"""
    if core is None:
        from v2ecoli.core import build_core
        core = build_core()
    from ecoli3d.steps.parsimony_pack import ParsimonyPackStep
    core.register_link("ParsimonyPackStep", ParsimonyPackStep)
    # For Phase 1 the recipe/pipeline are produced by ecoli3d.run.build_recipe_only
    # before instantiation; the Step then packs them. Wire a minimal doc:
    state = {
        "recipe_ready": True,
        "pack": {"pack_path": "", "stdout": ""},
        "parsimony_pack": {
            "_type": "step", "address": "local:ParsimonyPackStep",
            "config": {"pipeline_path": f"{out_dir}/ecoli_3d.pipeline.json",
                       "out_pack": f"{out_dir}/ecoli_3d.pack.json", "proxy_lod": 2},
            "inputs": {"recipe_ready": ["recipe_ready"]},
            "outputs": {"pack": ["pack"]},
        },
    }
    return {"state": state, "flow_order": ["parsimony_pack"]}
```

(Confirm the exact composite-document shape — `state`/`flow_order` keys and the step edge format — against `v2ecoli/composites/baseline.py`; mirror it precisely.)

- [ ] **Step 4: Run; verify pass.** `pytest tests/test_ecoli3d_composite.py -v -m sim` → PASS. Also confirm registration: `python -c "import ecoli3d.composites; from pbg_superpowers.composite_generator import _REGISTRY; print('parsimony-ecoli' in {e.name for e in _REGISTRY.values()})"` → `True`.

- [ ] **Step 5: Commit**

```bash
git add ecoli3d/composites/ tests/test_ecoli3d_composite.py
git commit -m "feat(ecoli3d): parsimony-ecoli composite + Phase-0 smoke test"
```

---

## Task 10 (Phase 1): End-to-end real 3D E. coli

**Files:**
- Create: `reports/ecoli3d_report.py` (a small entrypoint), `tests/test_ecoli3d_e2e.py`

Build a real cell: snapshot at top_n=50 → AlphaFold/PDB structures → recipe + 4.6 Mbp rod nucleoid → octree pack → view. **Requires Plan 1** (capsule nucleoid in parsimony).

- [ ] **Step 1: Failing end-to-end test (slow; network + sim + pack)**

```python
# tests/test_ecoli3d_e2e.py
import json, pytest
from pathlib import Path

@pytest.mark.sim
@pytest.mark.slow
def test_end_to_end_real_subset(tmp_path):
    from ecoli3d.run import build_3d_ecoli
    res = build_3d_ecoli(top_n=50, out_dir=tmp_path)
    data = json.loads(Path(res["pack_path"]).read_text())
    # Chromosome beads + a few thousand protein/lipid placements.
    assert len(data["placements"]) > 20_000, len(data["placements"])
```

- [ ] **Step 2: Run; verify it fails first (then passes once Plan 1 is merged into the parsimony build).**

- [ ] **Step 3: Implement `reports/ecoli3d_report.py`**

```python
#!/usr/bin/env python3
"""Build + open a 3D E. coli. Usage: python reports/ecoli3d_report.py --top-n 50"""
import argparse
from pathlib import Path
from ecoli3d.run import build_3d_ecoli
from ecoli3d.config import find_parsimony_bin
import subprocess

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--abundance-scale", type=float, default=1.0)
    ap.add_argument("--out-dir", default="out/ecoli3d")
    a = ap.parse_args()
    res = build_3d_ecoli(top_n=a.top_n, abundance_scale=a.abundance_scale, out_dir=Path(a.out_dir))
    print("packed:", res["pack_path"])
    print(res["stdout"])
    # Optional view: copy into parsimony viewer/data and launch.
    # subprocess.run([find_parsimony_bin(), "viewer", "--pack", "<copied name>"])

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the real build + view it**

Run:
```bash
cd /Users/eranagmon/code/3d-ecoli && source .venv/bin/activate && \
PARSIMONY_HOME=/Users/eranagmon/code/parsimony python reports/ecoli3d_report.py --top-n 50
```
Expected: prints a pack path; `len(placements) > 20000`. Copy the pack into parsimony's `viewer/data/` and open `http://localhost:8123/viewer/index.html?file=data/<name>.pack.json` — confirm a rod-shaped E. coli with a filled nucleoid + real protein meshes.

- [ ] **Step 5: Commit (local only)**

```bash
git add reports/ecoli3d_report.py tests/test_ecoli3d_e2e.py
git commit -m "feat(ecoli3d): end-to-end real 3D E. coli (Phase 1)"
```

> **Local-only project.** Per the user's decision, the 3d-ecoli repo stays
> local — do NOT `git push` or open a PR. The repo has no `origin` remote
> (`upstream` points at the v2ecoli parent for reference/fetch only). Keep all
> work on local branches.

---

## Self-Review

**Spec coverage (`2026-06-13-3d-ecoli-design.md`, Layer 2 bridge + pbg composite):**
- state.py / CellSnapshot → Task 2. ✅
- idmap.py (EcoCyc→UniProt; no UniProt in v2ecoli) → Task 3. ✅
- structures.py (AlphaFold + curated PDB) → Task 4. ✅
- scale.py (top_n / abundance_scale) → Task 5. ✅
- recipe.py (capsule, regions by compartment, chromosome) + genome CSV → Task 6. ✅
- ParsimonyPackStep → Task 7; orchestration → Task 8. ✅
- pbg composite → Task 9 (Phase 0 smoke). ✅
- Phase-1 real cell → Task 10. ✅
- Gram-negative envelope deferred to Phase 2 (compartment tags `i/o/p` all route to one surface for now — see `recipe.py::_SURFACE_TAGS`). ✅ (documented)

**Placeholder scan:** Two deliberate, named spikes/verifications (Task 2 Step 1 — pin the labeled-array API against the live object; and "confirm against v2ecoli/library/ecoli_step.py / baseline.py" in Tasks 7, 9) — these exist because the labeled-array label access and the exact composite-document edge shape cannot be verified without running v2ecoli. They are framed as "run this, observe, then implement against what you saw," with best-guess code provided — not blank TODOs. Everything else is concrete code. `state.py::_monomer_labels` is the one body that legitimately must be completed from the Step-1 spike before Task 2 Step 4.

**Type consistency:** `CellSnapshot`/`Species` (Task 2) flow unchanged into scale (Task 5), recipe (Task 6), run (Task 8). `StructureRef` (Task 4) → `(kind, payload)` tuples consumed by `recipe._object_entry` (Task 6) and `run._resolve_all` (Task 8) consistently. `run_pack(...)` signature identical in Task 7 (def), Task 8 (call), Task 9 (test). ✅

**Risks for the executor:**
- The v2ecoli labeled-array label access (Task 2) is the single biggest unknown — do the spike first.
- UniProt field labels in the TSV header (Task 3) may differ from `xref_ecogene`/`gene_oln`; confirm against the live header and adjust.
- AlphaFold disordered tails inflate meshes (note for Phase 2/3 — pLDDT trim).
- Task 10 depends on Plan 1 being built into the `parsimony` binary on `PARSIMONY_HOME`.
