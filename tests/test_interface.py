import json
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


# ------------------------------------------------------------------ API web
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from interface.server import app

    return TestClient(app)


def _sse_events(response):
    """Découpe un flux text/event-stream en [(événement, données JSON)]."""
    events, name = [], None
    for line in response.iter_lines():
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and name:
            events.append((name, json.loads(line.split(":", 1)[1])))
            name = None
    return events


def test_api_config(client):
    cfg = client.get("/api/config").json()
    assert "A-n32-k5.vrp" in cfg["library"]
    assert "France entière" in cfg["zones"]
    assert cfg["solvers"]


def test_api_library_instance_is_placed_on_the_map(client):
    p = client.post("/api/instances/library/A-n32-k5.vrp").json()
    assert p["name"] == "A-n32-k5" and p["n"] == 32 and p["bks"] == 784
    assert len(p["lat"]) == len(p["lon"]) == 32
    assert 41 < min(p["lat"]) and max(p["lat"]) < 52  # en France métropolitaine
    # on peut replacer la même instance ailleurs
    q = client.get(f"/api/instances/{p['id']}", params={"zone": "Île-de-France", "span": 50}).json()
    assert q["span"] == 50 and abs(sum(q["lat"]) / 32 - 48.85) < 0.5


def test_api_upload(client):
    p = client.post("/api/instances", params={"filename": "x.vrp"}, content=A32.read_bytes()).json()
    assert p["name"] == "A-n32-k5"


def test_api_load_keeps_the_chosen_zone(client):
    params = {"zone": "Grand Est (Nancy)", "span": 120}
    p = client.post("/api/instances/library/A-n32-k5.vrp", params=params).json()
    assert p["zone"] == "Grand Est (Nancy)" and p["span"] == 120
    u = client.post("/api/instances", params={**params, "filename": "x.vrp"}, content=A32.read_bytes()).json()
    assert u["zone"] == "Grand Est (Nancy)" and u["span"] == 120


def test_api_rejects_bad_input(client):
    assert client.post("/api/instances", params={"filename": "x.vrp"}, content=b"pas un vrp").status_code == 400
    assert client.post("/api/instances", content=b"").status_code == 400
    # pas de chemin libre : seuls les fichiers listés de instances/ sont servis
    assert client.post("/api/instances/library/..%2Finterface%2Fserver.py").status_code in (404, 405)
    assert client.post("/api/instances/library/server.py").status_code == 404
    assert client.post("/api/instances/library/inconnu.vrp").status_code == 404
    assert client.get("/api/instances/nope").status_code == 404
    iid = client.post("/api/instances/library/A-n32-k5.vrp").json()["id"]
    assert client.get(f"/api/instances/{iid}", params={"zone": "Mars"}).status_code == 400
    assert client.get("/api/solve", params={"instance": iid, "solver": "inconnu"}).status_code == 404


def test_api_solve_streams_progress_then_a_valid_solution(client):
    iid = client.post("/api/instances/library/A-n32-k5.vrp").json()["id"]
    solver = next(iter(client.get("/api/config").json()["solvers"]))
    with client.stream("GET", "/api/solve",
                       params={"instance": iid, "solver": solver, "time_limit": 2, "seed": 0}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(r)
    kinds = [k for k, _ in events]
    assert kinds[-1] == "done" and "progress" in kinds
    sol = events[-1][1]
    assert sol["valid"] and sol["errors"] == []
    assert sol["gap"] is not None and sol["gap"] < 10
    assert len(sol["per_route"]) == len(sol["routes"])


def test_api_reports_solver_errors(client):
    @solvers.register("test-solveur-qui-plante")
    def broken(inst, time_limit, seed, on_progress=None):
        raise RuntimeError("boum")

    try:
        iid = client.post("/api/instances/library/A-n32-k5.vrp").json()["id"]
        with client.stream("GET", "/api/solve",
                           params={"instance": iid, "solver": "test-solveur-qui-plante"}) as r:
            events = _sse_events(r)
        assert events == [("error", {"message": "RuntimeError: boum"})]
    finally:
        del solvers.SOLVERS["test-solveur-qui-plante"]


def test_api_flags_an_invalid_team_solution(client):
    @solvers.register("test-solution-incomplete")
    def incomplete(inst, time_limit, seed, on_progress=None):
        return solvers.make_solution(inst, [[1, 2, 3]], "incomplete")

    try:
        iid = client.post("/api/instances/library/A-n32-k5.vrp").json()["id"]
        with client.stream("GET", "/api/solve",
                           params={"instance": iid, "solver": "test-solution-incomplete"}) as r:
            sol = _sse_events(r)[-1][1]
        assert sol["valid"] is False and any("non visités" in e for e in sol["errors"])
    finally:
        del solvers.SOLVERS["test-solution-incomplete"]


def test_static_page_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "CMAP" in r.text
    assert client.get("/app.js").status_code == 200
