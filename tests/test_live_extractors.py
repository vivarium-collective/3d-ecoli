import numpy as np
from ecoli_3d import build


def _bulk(ids, counts):
    return np.array(list(zip(ids, counts)),
                    dtype=[("id", "U40"), ("count", "i8")])


def test_bulk_to_counts_sums_and_strips_tag():
    bulk = _bulk(["GLC[c]", "GLC[p]", "ATP[c]"], [3, 4, 5])
    assert build.bulk_to_counts(bulk) == {"GLC": 7, "ATP": 5}


def test_bulk_to_locations_dominant_compartment():
    bulk = _bulk(["GLC[c]", "GLC[p]"], [1, 9])
    loc = build.bulk_to_locations(bulk)
    assert loc["GLC"] == "p"


def test_chromosome_state_from_live_unreplicated():
    fc = np.array([(1,)], dtype=[("_entryState", "i8")])
    n, ff = build.chromosome_state_from_live(fc, None)
    assert n == 1 and ff == 0.0
