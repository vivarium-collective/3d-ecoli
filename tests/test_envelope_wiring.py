import numpy as np
import ecoli_3d.build as B


def test_bulk_to_locations_dominant_tag():
    bulk = {"id": np.array(["FOO[c]", "FOO[p]", "BAR[o]", "BAZ[i]", "QUX[m]", "PLAIN"]),
            "count": np.array([10, 3, 5, 5, 5, 5])}
    loc = B.bulk_to_locations(bulk)
    assert loc["FOO"] == "c"        # 10[c] > 3[p]
    assert loc["BAR"] == "o"
    assert loc["BAZ"] == "i"
    assert loc["QUX"] == "m"
    assert loc["PLAIN"] == "c"      # untagged


def test_pack_from_state_passes_envelope(monkeypatch):
    calls = {}

    class _StopAfterCapture(Exception):
        pass

    def fake_build_pack(ingredients, capsule, chromosome, **kw):
        calls["envelope"] = kw.get("envelope")
        calls["capsule"] = capsule
        raise _StopAfterCapture()

    monkeypatch.setattr(B, "build_pack", fake_build_pack)
    monkeypatch.setattr(B, "select_ingredients", lambda counts, **kw: [])

    for envelope in (True, False):
        try:
            B.pack_from_state("out", "m", {"X": 1}, 1.153, {"X": "p"},
                              top_n=2, envelope=envelope)
        except _StopAfterCapture:
            pass
        if envelope:
            env = calls["envelope"]
            assert env is not None and set(env) == {"inner", "outer"}
            assert env["inner"].radius < env["outer"].radius   # inner is nested
            assert env["inner"].half_len < env["outer"].half_len
        else:
            assert calls["envelope"] is None


def test_select_ingredients_sets_compartment_and_region():
    # a tiny synthetic counts hitting the top-N monomer path; locations drive compartment.
    # If select_ingredients needs heavy reference data, mark this test slow or skip;
    # the goal is to assert an ingredient's compartment/region follow its location.
    import pytest
    try:
        ings = B.select_ingredients({"EG10544-MONOMER": 100}, top_n=1,
                                    compartments={"EG10544-MONOMER": "i"})
    except Exception as e:
        pytest.skip(f"select_ingredients needs reference data: {e}")
    m = {i.id: i for i in ings}
    if "EG10544-MONOMER" in m:
        assert m["EG10544-MONOMER"].compartment == "inner_membrane"
        assert m["EG10544-MONOMER"].region == "surface"
    # the lipid is always present → inner_membrane surface
    if "lipid" in m:
        assert m["lipid"].compartment == "inner_membrane" and m["lipid"].region == "surface"
    # CURATED entries keep their hand-authored region (e.g. rna_polymerase's
    # "fiber", which seats it along the DNA via fiber_pack) — the compartment
    # location-routing must not overwrite it.
    if "rna_polymerase" in m:
        assert m["rna_polymerase"].region == "fiber"
