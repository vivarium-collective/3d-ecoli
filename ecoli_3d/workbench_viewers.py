"""Vivarium-workbench analysis viewers contributed by ecoli_3d.

The workbench (vivarium-workbench) discovers a ``<pkg>.workbench_viewers`` module
on the workspace package and every installed ``pbg-*``/``viva-*`` distribution,
and calls its ``get_viewers(ws_root)`` to render extra cards on the Analyses
page. This is the generic contribution seam; ecoli_3d uses it to ship the
**3D E. coli viewer** deep-link — a launcher card that opens a study's saved
parsimony 3D pack in the hosted (Cloudflare R2) viewer.

Ported from v2ecoli's ``v2ecoli/workbench_viewers.py``, which also shipped a
Pathway Tools Omics Viewer launcher — that one stays v2ecoli's (it needs
v2ecoli's ptools TSV exports and ``ui.ptools_server_url`` config, neither of
which apply here).
"""
from __future__ import annotations

from pathlib import Path


def _studies_root(ws_root: Path) -> Path:
    """The directory holding study subdirs. Uses the shared ``viva_workspace``
    ``WorkspacePaths.studies`` resolver (honours a ``layout:`` remap /
    ``workspace/`` subdir)."""
    from viva_workspace import WorkspacePaths
    return WorkspacePaths.load(ws_root).studies


def _has_3d_pack(ws_root) -> bool:
    """Cheap check: does any study have a saved parsimony 3D pack?"""
    root = _studies_root(Path(ws_root))
    return bool(root.is_dir() and next(root.glob("*/viz/3d/*.pack.json"), None))


def _ecoli_3d_targets(ws_root) -> list:
    """Studies with a saved parsimony 3D pack → a deep-link to the HOSTED viewer.

    Reuses the workbench's saved-visualizations builder (which computes the public
    ``viewer_url`` for each 3D pack). Each target carries an external ``href`` so
    it opens directly in both the live workbench and the read-only dashboard —
    the hosted viewer needs no local launch backend.
    """
    try:
        from vivarium_workbench.lib import saved_visualizations as _sv
        payload = _sv.build_saved_visualizations(Path(ws_root))
    except Exception:
        return []
    out = []
    for item in (payload.get("saved") or []):
        url = item.get("viewer_url")
        if not url:
            continue
        n = item.get("n_placed")
        detail = f"{n:,} molecules placed" if isinstance(n, int) else "hosted 3D view"
        out.append({
            "study": item.get("study"),
            "label": item.get("study"),
            "detail": detail,
            "href": url,
        })
    return out


def get_viewers(ws_root) -> list:
    """Contribute the analysis viewer ecoli_3d ships:

    * **3D E. coli viewer** (deep-link to the hosted parsimony 3D viewer; available
      wherever a study has a saved 3D pack, including the read-only dashboard).

    The Data Explorer (timeseries / scatter / flux maps for any run) is the
    workbench's own built-in and is shown alongside this automatically.
    """
    return [
        {
            "id": "ecoli-3d",
            "title": "3D E. coli viewer",
            "description": (
                "Open an interactive 3D molecular view of the cell — every "
                "molecule placed in real 3D space by parsimony — in the hosted "
                "viewer."
            ),
            "kind": "launcher",
            "applies": _has_3d_pack,
            "targets": _ecoli_3d_targets,
        },
    ]
