import math
from pathlib import Path

import numpy as np
import pytest

from interface import solvers
from interface.geo import PRESETS, place_on_map
from interface.instance import load_instance, load_instance_from_bytes

ROOT = Path(__file__).resolve().parent.parent
A32 = ROOT / "instances" / "A-n32-k5.vrp"


@pytest.fixture(scope="module")
def inst():
    return load_instance(A32)


def test_load_instance(inst):
    assert inst.name == "A-n32-k5"
    assert inst.n == 32 and inst.capacity == 100
    assert inst.n_vehicles == 5 and inst.bks == 784
    assert inst.demand[0] == 0 and inst.min_vehicles == 5


def test_distances_rounded_like_tsplib(inst):
    # sommets 1 et 2 : (82,76) et (96,44) -> sqrt(14^2 + 32^2) = 34.93 -> 35
    assert inst.dist[0, 1] == 35


def test_load_from_bytes(inst):
    again = load_instance_from_bytes(A32.read_bytes(), "x.vrp")
    assert np.array_equal(again.dist, inst.dist)


def test_place_on_map_keeps_shape_and_scale(inst):
    lat0, lon0, span = PRESETS["France entière"]
    f = place_on_map(inst.coords, lat0, lon0, span)
    # le plus grand côté fait bien `span` km (en nord-sud, 1° = 111.32 km)
    assert math.isclose(f.km_per_unit * np.ptp(inst.coords, axis=0).max(), span)
    # le nuage est centré sur la zone demandée
    assert math.isclose((f.lat.min() + f.lat.max()) / 2, lat0, abs_tol=1e-6)
    assert math.isclose((f.lon.min() + f.lon.max()) / 2, lon0, abs_tol=1e-6)
    # les distances relatives sont conservées : même rapport est-ouest / nord-sud
    d_ns = (f.lat.max() - f.lat.min()) * 111.32
    d_ew = (f.lon.max() - f.lon.min()) * 111.32 * math.cos(math.radians(lat0))
    ratio_inst = np.ptp(inst.coords[:, 0]) / np.ptp(inst.coords[:, 1])
    assert math.isclose(d_ew / d_ns, ratio_inst, rel_tol=1e-6)


def test_check_solution_detects_errors(inst):
    assert solvers.check_solution(inst, [[1, 2]])  # clients manquants
    assert solvers.check_solution(inst, [list(range(1, inst.n))])  # capacité dépassée
    doubled = [list(range(1, inst.n)), [1]]
    assert any("plusieurs fois" in e for e in solvers.check_solution(inst, doubled))


def test_baseline_returns_valid_solution(inst):
    sol = solvers.SOLVERS["Baseline provisoire (Clarke-Wright + ILS)"](inst, 2.0, 0)
    assert solvers.check_solution(inst, sol.routes) == []
    assert sol.cost == solvers.total_cost(inst, sol.routes)
    assert sol.cost <= 839  # au moins aussi bon que Clarke-Wright seul
    assert sol.history and sol.history[0][2] >= sol.history[-1][2]


def test_registry_accepts_a_team_solver(inst):
    @solvers.register("test-un-camion-par-client")
    def trivial(inst, time_limit, seed, on_progress=None):
        return solvers.make_solution(inst, [[c] for c in range(1, inst.n)], "trivial")

    try:
        sol = solvers.SOLVERS["test-un-camion-par-client"](inst, 1, 0)
        assert len(sol.routes) == inst.n - 1
        assert solvers.check_solution(inst, sol.routes) == []
    finally:
        del solvers.SOLVERS["test-un-camion-par-client"]


def test_app_runs_end_to_end():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "interface" / "app.py"), default_timeout=60).run()
    assert not at.exception
    at.sidebar.slider[1].set_value(2)  # temps limite : 2 s
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert any("Solution valide" in s.value for s in at.success)
