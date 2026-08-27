"""Task 4: the in-memory ``pack_from_state`` seam.

``pack_from_state`` is the file-free core extracted from ``build_model`` — it
takes pre-computed live state (counts, volume, locations, RNAP loci, replication
state) as parameters and packs a 3D model without any ``load_state`` file round-
trip. ``EcoliPackStep`` (v2ecoli) drives this same core from LIVE simulation
state, so its public signature is load-bearing and must not drift.

The signature test is always run. The real pack test needs both the parsimony
binary (``PARSIMONY_HOME``) and the reference structure cache; without the cache
it skips (mirrors the sibling ``test_build_*`` real-build tests) so the suite
never fails merely because structures aren't staged on this host.
"""
import json
import os
import shutil
from pathlib import Path

import pytest

from ecoli_3d import build

# Reference structure cache (populated by earlier real build runs — no network).
# Same path the sibling real-build tests use; absent on hosts that only run the
# lightweight unit tests, in which case the pack test skips.
_STRUCT_CACHE = Path(
    "/Users/eranagmon/code/v2e-pdmp-refresh/out/ecoli3d_expanded/structures"
)


def test_pack_from_state_signature_accepts_live_params():
    """The public seam threads live params without reading files."""
    import inspect
    sig = inspect.signature(build.pack_from_state)
    for p in ("counts", "volume_fl", "locations", "rnaps",
              "n_chromosomes", "fork_fraction", "envelope", "relax"):
        assert p in sig.parameters, f"pack_from_state missing param {p!r}"


def test_pack_from_state_relax_true_raises():
    """B has no relax path: relax=True must raise, never silently ignore."""
    with pytest.raises(NotImplementedError):
        build.pack_from_state("out", "t", {}, 1.0, relax=True)


@pytest.mark.skipif(not os.environ.get("PARSIMONY_HOME"),
                    reason="parsimony binary absent; pack skipped (never falsely passes)")
def test_pack_from_state_writes_pack(tmp_path, monkeypatch):
    """The live path (shape=None → Capsule.from_volume_fl envelope) packs a real
    model from in-memory state, no ``load_state`` file round-trip."""
    if not _STRUCT_CACHE.exists():
        pytest.skip(f"structure cache not available at {_STRUCT_CACHE}")
    monkeypatch.setenv(
        "PARSIMONY_HOME",
        os.environ.get("PARSIMONY_HOME", "/Users/eranagmon/code/parsimony"),
    )
    # Pre-seed the structures cache so no network downloads occur.
    struct_cache = tmp_path / "structures"
    struct_cache.mkdir(parents=True, exist_ok=True)
    for fname in ("rna_polymerase.pdb", "dna_segment.pdb", "replisome.pdb",
                  "70s_ribosome.cif", "groel.pdb", "eg10367_monomer.pdb"):
        src = _STRUCT_CACHE / fname
        if src.exists():
            shutil.copy(src, struct_cache / fname)

    # EG10893-MONOMER is a real EcoCyc protein id (a top-N monomer candidate);
    # the curated 70S/RNAP/GroEL/GAPDH assemblies come from the seeded cache.
    counts = {"EG10893-MONOMER": 100}
    res = build.pack_from_state(str(tmp_path), "t", counts, volume_fl=1.0,
                                locations={}, top_n=5, scale=0.1,
                                rnaps=[], n_chromosomes=1, fork_fraction=0.0)
    assert Path(res["pack_path"]).exists()
    pack = json.loads(Path(res["pack_path"]).read_text())
    assert isinstance(pack.get("placements"), list)
