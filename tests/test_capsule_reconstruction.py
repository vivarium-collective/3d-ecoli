from ecoli_3d.build import _capsules_from_shape


def test_capsules_from_shape_numeric():
    shape = {"radius_A": 5000.0, "half_len_A": 8000.0,
             "inner_radius_A": 4642.0, "inner_half_len_A": 7427.0}
    outer, inner, env = _capsules_from_shape(shape)
    assert abs(outer.radius - 5000.0) < 1e-6
    assert abs(inner.half_len - 7427.0) < 1e-6
    assert env["outer"] is outer and env["inner"] is inner
