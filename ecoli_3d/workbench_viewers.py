"""Vivarium-workbench analysis viewer contributed by ecoli_3d.

The workbench (vivarium-workbench) discovers a ``<pkg>.workbench_viewers`` module
on the workspace package and every installed ``pbg-*``/``viva-*`` distribution,
and calls its ``get_viewers(ws_root)`` to render extra cards on the Explore tab.
This is the generic contribution seam.

ecoli_3d ships the **3D E. coli viewer** through it as an ``embed-3d`` viewer.
The workbench core holds NO parsimony-specific knowledge: it serves the viewer
webapp generically from whatever package the descriptor names in
``bundle_package`` (here ``viva_parsimony``, which ships its ``viewer/`` webapp as
package data) at ``/contributed-viewer/viva_parsimony/``, and matches the
``3d_pack`` capability against the studies that have a saved 3D pack
(``viz/3d/*.pack.json``). So the 3D viewer appears exactly in a workspace with a
3D pack and the viewer package installed — and nowhere else — without any
hardcoding in the workbench.

A study may still override to a hosted viewer (e.g. assets on Cloudflare R2) via
``ui.viz_viewer_urls`` in workspace.yaml; the workbench prefers that hosted URL
over the local bundle when present.
"""
from __future__ import annotations

from pathlib import Path

#: The distribution whose ``viewer/`` webapp the workbench serves for this tool.
#: ``viva_parsimony`` ships the parsimony 3D viewer bundle as package data.
VIEWER_BUNDLE_PACKAGE = "viva_parsimony"


def _studies_root(ws_root: Path) -> Path:
    """The directory holding study subdirs. Uses the shared ``viva_workspace``
    ``WorkspacePaths.studies`` resolver (honours a ``layout:`` remap /
    ``workspace/`` subdir)."""
    from viva_workspace import WorkspacePaths
    return WorkspacePaths.load(ws_root).studies


def _has_3d_pack(ws_root) -> bool:
    """Cheap check: does any study have a saved 3D pack?"""
    try:
        root = _studies_root(Path(ws_root))
    except Exception:
        return False
    return bool(root.is_dir() and next(root.glob("*/viz/3d/*.pack.json"), None))


def get_viewers(ws_root) -> list:
    """Contribute the **3D E. coli viewer** as a generic ``embed-3d`` tool.

    The workbench matches its ``requires: ["3d_pack"]`` against the studies with a
    saved 3D pack, and serves its webapp from ``bundle_package``'s ``viewer/`` dir
    at ``/contributed-viewer/<bundle_package>/``. Hosted ``viewer_url`` (from
    ``ui.viz_viewer_urls``) wins over the local bundle when present.
    """
    return [
        {
            "id": "ecoli-3d",   # kept: existing ui.analysis_tools_exclude configs refer to it
            "title": "3D E. coli viewer",
            "description": (
                "Open an interactive 3D molecular view of the cell — every "
                "molecule placed in real 3D space by parsimony — for a study's "
                "saved 3D pack."
            ),
            "kind": "embed-3d",
            "requires": ["3d_pack"],
            "bundle_package": VIEWER_BUNDLE_PACKAGE,
            "applies": _has_3d_pack,
        },
    ]
