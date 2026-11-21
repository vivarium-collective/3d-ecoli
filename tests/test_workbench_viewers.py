"""ecoli_3d contributes the 3D viewer as a generic embed-3d tool.

Importing ecoli_3d.workbench_viewers goes through ecoli_3d.__init__ (which pulls
the viva_parsimony engine), so skip when that isn't installed.
"""
import pytest

wv = pytest.importorskip(
    "ecoli_3d.workbench_viewers",
    reason="needs the viva_parsimony engine (ecoli_3d package deps)")


def test_contributes_a_single_embed_3d_viewer():
    viewers = wv.get_viewers("/ws")
    assert len(viewers) == 1
    v = viewers[0]
    # generic contributed-viewer contract: no hosted href / launch — the
    # workbench serves the bundle itself and capability-matches the pack.
    assert v["id"] == "ecoli-3d"           # kept for existing exclude configs
    assert v["kind"] == "embed-3d"
    assert v["requires"] == ["3d_pack"]
    assert v["bundle_package"] == "viva_parsimony" == wv.VIEWER_BUNDLE_PACKAGE
    assert callable(v["applies"])
    # it declares no hosted href itself (hosting is per-study via ui.viz_viewer_urls)
    assert "href" not in v and "launch" not in v


def test_has_3d_pack_detects_a_saved_pack(tmp_path):
    # No workspace / no pack → False, and never raises.
    assert wv._has_3d_pack(tmp_path) is False
    (tmp_path / "workspace.yaml").write_text("name: t\n")
    viz3d = tmp_path / "studies" / "s01" / "viz" / "3d"
    viz3d.mkdir(parents=True)
    (viz3d / "x.pack.json").write_text("{}")
    assert wv._has_3d_pack(tmp_path) is True
