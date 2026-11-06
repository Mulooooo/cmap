"""Instances, validation et métaheuristiques du notebook."""

from pathlib import Path

import numpy as np
import pytest

from solvers import SOLVERS
from solvers.common import check_solution, evaluate, make_solution, total_cost
from solvers.instance import load_instance, load_instance_from_bytes
from solvers.notebook import greedy_initial_solution

ROOT = Path(__file__).resolve().parent.parent
A32 = ROOT / "instances" / "A" / "A-n32-k5.vrp"
ALL = sorted((ROOT / "instances").rglob("*.vrp"))


@pytest.fixture(scope="module")
def inst():
    return load_instance(A32)


def test_load_instance(inst):
    assert inst.name == "A-n32-k5" and inst.n == 32 and inst.capacity == 100
    assert inst.n_vehicles == 5 and inst.bks == 784 and inst.demand[0] == 0
    assert inst.dist[0, 1] == 35  # (82,76)-(96,44) : 34,93 arrondi comme TSPLIB


def test_load_from_bytes_has_no_sol_file(inst):
    again = load_instance_from_bytes(A32.read_bytes(), "x.vrp")
    assert np.array_equal(again.dist, inst.dist) and again.best_routes is None


@pytest.mark.parametrize("vrp", ALL, ids=lambda p: p.stem)
def test_every_instance_matches_its_sol_file(vrp):
    """Les distances arrondies redonnent exactement le coût publié de chaque .sol."""
    i = load_instance(vrp)
    assert check_solution(i, i.best_routes) == []
    assert total_cost(i, i.best_routes) == i.bks


def test_check_solution(inst):
    assert check_solution(inst, [[1, 2]])  # clients manquants
    assert any("capacité" in e for e in check_solution(inst, [list(range(1, inst.n))]))
    assert any("plusieurs fois" in e for e in check_solution(inst, [list(range(1, inst.n)), [1]]))
    assert any("Le dépôt" in e for e in check_solution(inst, [[0, *range(1, inst.n)]]))
    seven = [[c] for c in range(1, 7)] + [list(range(7, inst.n))]
    assert any("flotte" in e for e in check_solution(inst, seven))
    assert check_solution(inst, inst.best_routes) == []


def test_evaluate_matches_the_contract(inst):
    res = evaluate(inst, inst.best_routes, 1.234)
    assert res["cost"] == 784 and res["gap"] == 0 and res["valid"] and res["errors"] == []
    assert res["n_routes"] == 5 and res["elapsed"] == 1.23
    assert [p["n_clients"] for p in res["per_route"]] == [len(r) for r in inst.best_routes]


@pytest.mark.parametrize("solver_id", ["hill_climbing", "simulated_annealing"])
def test_notebook_solvers(inst, solver_id):
    seen = []
    sol = SOLVERS[solver_id].fn(inst, 1.0, 0, lambda it, cost, routes: seen.append((it, cost)))
    assert check_solution(inst, sol.routes) == []
    assert sol.cost == total_cost(inst, sol.routes)
    assert sol.cost <= total_cost(inst, greedy_initial_solution(inst))  # jamais pire que le départ
    assert seen and seen[0][0] == 0  # le point de départ est annoncé
    assert all(a[1] >= b[1] for a, b in zip(seen, seen[1:]))  # le coût ne remonte jamais
    assert sol.history[0][2] >= sol.history[-1][2]


def test_same_seed_same_result(inst):
    a = SOLVERS["simulated_annealing"].fn(inst, 0.5, 3)
    b = SOLVERS["simulated_annealing"].fn(inst, 0.5, 3)
    assert a.history[0] == b.history[0]


def test_make_solution_drops_empty_routes(inst):
    assert make_solution(inst, [[1], [], [2]]).routes == [[1], [2]]
