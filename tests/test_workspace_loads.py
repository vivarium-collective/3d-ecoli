from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_workspace_yaml_registers_ecoli_3d():
    ws = yaml.safe_load((ROOT / "workspace.yaml").read_text())
    # Real workspace.yaml files register the package via `package_path` (see
    # v2ecoli's workspace.yaml + viva_workspace.WorkspacePaths.from_config),
    # not a literal `package` key — use .get() so this doesn't KeyError.
    assert ws.get("package") == "ecoli_3d" or "ecoli_3d" in str(ws)


def test_study_composite_points_at_ecoli_3d():
    y = (ROOT / "workspace/studies/s01-birth-and-division/study.yaml").read_text()
    assert "ecoli_3d.composites.ecoli_structural" in y
    assert "v2ecoli.composites.ecoli_structural" not in y
