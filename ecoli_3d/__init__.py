"""3D structural E. coli — pack a v2ecoli molecular state into a 3D cell via
viva-parsimony, and render it in the bundled webapp / online viewer.

- :func:`build_model` — the bridge (state → ingredients → ``viva_parsimony.build_pack``).
- ``parsimony-ecoli`` composite — the process-bigraph wiring (see :mod:`ecoli_3d.composite`).

This package *imports* v2ecoli (for the molecular state + cell-envelope geometry)
and viva-parsimony (the packing engine); neither is vendored.
"""
from ecoli_3d.build import build_model, select_ingredients, load_state, categorize
from ecoli_3d import composite  # noqa: F401 — registers the "parsimony-ecoli" composite

__all__ = ["build_model", "select_ingredients", "load_state", "categorize", "composite"]
