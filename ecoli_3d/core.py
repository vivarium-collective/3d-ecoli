"""Workspace ``build_core`` for ecoli_3d.

The workbench's env worker discovers a workspace's processes/types by importing
``<package>.core`` and calling ``build_core()`` (no args); see
``vivarium_workbench.env_worker``. Without this module the worker logs
``could not import ecoli_3d.core`` and the Registry/analyses degrade to whatever
classes happen to be discoverable.

ecoli_3d builds its structural view on top of the v2ecoli whole-cell baseline, so
its core *is* v2ecoli's core (ECOLI_TYPES, emitters, the baseline processes) plus
ecoli_3d's own process-bigraph Steps. Importing the composite modules here also
runs their ``@composite_generator`` registrations, so ``parsimony-ecoli`` and
``ecoli_structural`` land in the registry regardless of import order.
"""

from __future__ import annotations

from typing import Any

__all__ = ["build_core"]


def build_core(core: Any = None):
    """Return a bigraph-schema core with the v2ecoli baseline + ecoli_3d classes.

    ``core`` is accepted for symmetry with other ``build_core`` implementations
    but ignored: the v2ecoli baseline must be provisioned on a core that already
    carries ECOLI_TYPES, so we always start from ``v2ecoli.core.build_core()``.
    """
    from v2ecoli.core import build_core as _v2_build_core

    core = _v2_build_core()

    # Register ecoli_3d's own Steps so they appear in the Registry tab. The
    # composites also register these via their ``core_extensions`` hooks at run
    # time; registering here too is idempotent and makes them discoverable
    # without building a composite first.
    from ecoli_3d.composite import EcoliStructuralStep

    core.register_link("EcoliStructuralStep", EcoliStructuralStep)
    try:
        from ecoli_3d.pack_step import EcoliPackStep

        core.register_link("EcoliPackStep", EcoliPackStep)
    except Exception:
        # EcoliPackStep pulls the viva-parsimony packing engine; never let an
        # optional-dep import break build_core (it is also registered lazily via
        # the ecoli_structural core_extensions hook at run time).
        pass

    # Import the composite modules so their @composite_generator entries register.
    from ecoli_3d import composite as _composite  # noqa: F401  → parsimony-ecoli
    from ecoli_3d.composites import ecoli_structural as _structural  # noqa: F401

    return core
