"""3D structural E. coli — pack a v2ecoli molecular state into a 3D cell via
viva-parsimony, and render it in the bundled webapp / online viewer.

- :func:`build_model` — the bridge (state → ingredients → ``viva_parsimony.build_pack``).
- ``parsimony-ecoli`` composite — the process-bigraph wiring (see :mod:`ecoli_3d.composite`).
- ``ecoli_structural`` composite — baseline whole-cell run + packing step
  (see :mod:`ecoli_3d.composites.ecoli_structural`); referenced by the
  structural-ecoli/s01 study.

This package *imports* v2ecoli (for the molecular state + cell-envelope geometry)
and viva-parsimony (the packing engine); neither is vendored.
"""
from ecoli_3d.build import build_model, select_ingredients, load_state, categorize
from ecoli_3d import composite  # noqa: F401 — registers the "parsimony-ecoli" composite
# Register the "ecoli_structural" composite on package import, symmetric with
# the parsimony-ecoli import above. Without this, importing the workspace package
# during a registry scan never runs the @composite_generator in that module, so
# the composite the structural-ecoli/s01 study references is absent from the
# registry (and the study build fails) even though the study model page — which
# only renders the declared composite-id string — still shows it.
from ecoli_3d.composites import ecoli_structural  # noqa: F401

__all__ = ["build_model", "select_ingredients", "load_state", "categorize", "composite", "ecoli_structural"]
