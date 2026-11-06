"""Tests de l'API (docs/api.md) avec le client de test Flask. Les calculs sont de vrais processus."""

import io
import time
from pathlib import Path

import pytest

import fake_workers
from server import create_app

ROOT = Path(__file__).resolve().parent.parent
A32 = ROOT / "instances" / "A" / "A-n32-k5.vrp"
JOB = {"instance_id": "A-n32-k5", "solver": "hill_climbing", "time_limit": 1, "seed": 0}


def make_client(**kwargs):
    app = create_app({"TESTING": True, **kwargs.pop("config", {})}, **kwargs)
    return app, app.test_client()


@pytest.fixture
def client():
    app, c = make_client()
    yield c
    jobs = app.extensions["jobs"]  # ne laisser aucun processus de calcul derrière soi
    for job in list(jobs._jobs.values()):
        jobs.stop(job)


def wait_finished(client, job_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").get_json()
        if body["status"] != "running":
            return body
        time.sleep(0.2)
    raise AssertionError("le calcul ne se termine pas")


# ------------------------------------------------------------------- petites routes
def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_solvers(client):
    solvers = client.get("/api/solvers").get_json()
    assert [s["id"] for s in solvers] == ["hill_climbing", "simulated_annealing"]
    assert all({"id", "name", "description"} <= set(s) for s in solvers)


def test_errors_have_one_format_everywhere(client):
    for r in (client.get("/api/nimporte"), client.get("/api/instances/inconnue"),
              client.get("/api/jobs/inconnu")):
        assert r.status_code == 404 and r.get_json()["code"] == "not_found" and r.get_json()["error"]
    r = client.post("/api/health")
    assert r.status_code == 405 and r.get_json()["code"] == "method_not_allowed"


def test_json_is_readable_and_in_contract_order(client):
    raw = client.get("/api/solvers").get_data(as_text=True)
    assert "Montée de colline" in raw  # pas de é
    assert raw.index('"id"') < raw.index('"name"') < raw.index('"description"')


# -------------------------------------------------------------------------- instances
def test_list_instances(client):
    items = client.get("/api/instances").get_json()
    assert len(items) == 27
    first = next(i for i in items if i["id"] == "A-n32-k5")
    assert first == {"id": "A-n32-k5", "name": "A-n32-k5", "n_clients": 31, "capacity": 100,
                     "n_vehicles": 5, "best_known_cost": 784, "has_best_known_routes": True,
                     "source": "library"}


def test_instance_detail(client):
    d = client.get("/api/instances/A-n32-k5").get_json()
    assert d["n_clients"] == 31 and d["capacity"] == 100 and d["n_vehicles"] == 5
    assert len(d["coords"]) == len(d["demand"]) == 32  # dépôt compris
    assert d["coords"][:2] == [[82, 76], [96, 44]] and d["demand"][:3] == [0, 19, 21]
    assert d["best_known"]["cost"] == 784 and len(d["best_known"]["routes"]) == 5
    assert sorted(c for r in d["best_known"]["routes"] for c in r) == list(range(1, 32))


def test_instance_ids_never_become_file_paths(client):
    for bad in ("..%2F..%2Fetc%2Fpasswd", "A%2FA-n32-k5", "../requirements"):
        assert client.get(f"/api/instances/{bad}").status_code == 404


def test_upload_then_use_an_instance(client):
    r = client.post("/api/instances", data={"file": (io.BytesIO(A32.read_bytes()), "mon.vrp")},
                    content_type="multipart/form-data")
    assert r.status_code == 201
    d = r.get_json()
    assert d["source"] == "upload" and d["id"].startswith("up-") and d["n_clients"] == 31
    assert d["best_known"]["routes"] is None  # pas de .sol à côté d'un envoi
    assert client.get(f"/api/instances/{d['id']}").get_json()["id"] == d["id"]
    assert any(i["id"] == d["id"] for i in client.get("/api/instances").get_json())
    job = client.post("/api/jobs", json={**JOB, "instance_id": d["id"]}).get_json()
    assert wait_finished(client, job["job_id"])["result"]["valid"]


@pytest.mark.parametrize("payload", [b"", b"ceci n'est pas un vrp", b"NAME : x\nTYPE : CVRP\n"])
def test_upload_rejects_bad_files(client, payload):
    r = client.post("/api/instances", data={"file": (io.BytesIO(payload), "x.vrp")},
                    content_type="multipart/form-data")
    assert r.status_code == 400 and r.get_json()["code"] == "invalid_file"


def test_upload_without_file_field(client):
    r = client.post("/api/instances", data={"autre": "x"}, content_type="multipart/form-data")
    assert r.status_code == 400 and r.get_json()["code"] == "invalid_file"


def test_upload_too_large():
    _, c = make_client(config={"MAX_CONTENT_LENGTH": 200})  # le .vrp d'exemple fait ~700 octets
    r = c.post("/api/instances", data={"file": (io.BytesIO(A32.read_bytes()), "x.vrp")},
               content_type="multipart/form-data")
    assert r.status_code == 413 and r.get_json()["code"] == "too_large"


def test_uploads_are_bounded():
    _, c = make_client(config={"MAX_UPLOADS": 2})
    ids = [c.post("/api/instances", data={"file": (io.BytesIO(A32.read_bytes()), "x.vrp")},
                  content_type="multipart/form-data").get_json()["id"] for _ in range(3)]
    assert c.get(f"/api/instances/{ids[0]}").status_code == 404  # le plus ancien est oublié
    assert c.get(f"/api/instances/{ids[2]}").status_code == 200


# ------------------------------------------------------------------------------ calculs
def test_full_run_then_result(client):
    r = client.post("/api/jobs", json=JOB)
    assert r.status_code == 202 and r.get_json()["status"] == "running"
    job_id = r.get_json()["job_id"]

    job = wait_finished(client, job_id)
    assert job["status"] == "done" and job["error"] is None
    assert job["instance_id"] == "A-n32-k5" and job["solver"] == "hill_climbing"
    res = job["result"]
    assert res["valid"] and res["errors"] == [] and res["n_routes"] == len(res["routes"]) <= 5
    assert res["cost"] == job["best_cost"] and res["gap"] == round(100 * (res["cost"] - 784) / 784, 2)
    assert sorted(c for r in res["routes"] for c in r) == list(range(1, 32))
    assert sum(p["distance"] for p in res["per_route"]) == res["cost"]
    assert all(p["load"] <= 100 for p in res["per_route"])
    hist = job["history"]
    assert hist[0][2] >= hist[-1][2] and hist[-1][2] == res["cost"]  # le coût ne remonte jamais
    assert job["routes"] == res["routes"]


def test_progress_while_running_and_since(client):
    job_id = client.post("/api/jobs", json={**JOB, "time_limit": 4}).get_json()["job_id"]
    time.sleep(1.5)
    now = client.get(f"/api/jobs/{job_id}").get_json()
    assert now["status"] == "running" and now["result"] is None
    assert now["best_cost"] is not None and now["routes"] and now["version"] >= 1
    # rien de nouveau depuis cette version : on n'envoie pas les tournées
    same = client.get(f"/api/jobs/{job_id}?since={now['version']}").get_json()
    if same["version"] == now["version"]:
        assert same["routes"] is None and same["history"] is None
        assert same["best_cost"] == now["best_cost"] and same["status"] == "running"
    assert client.get(f"/api/jobs/{job_id}?since=abc").status_code == 422


def test_only_one_job_at_a_time(client):
    first = client.post("/api/jobs", json={**JOB, "time_limit": 30}).get_json()["job_id"]
    r = client.post("/api/jobs", json=JOB)
    assert r.status_code == 409
    assert r.get_json() == {"error": "Un calcul est déjà en cours", "code": "busy", "job_id": first}
    client.post(f"/api/jobs/{first}/stop")
    assert client.post("/api/jobs", json=JOB).status_code == 202  # le créneau est libre de nouveau


def test_stop_keeps_the_best_solution(client):
    job_id = client.post("/api/jobs", json={**JOB, "time_limit": 60}).get_json()["job_id"]
    time.sleep(1.5)
    r = client.post(f"/api/jobs/{job_id}/stop")
    assert r.status_code == 200
    job = r.get_json()
    assert job["status"] == "stopped" and job["elapsed"] < 10
    assert job["result"]["valid"] and job["result"]["cost"] == job["best_cost"]
    again = client.post(f"/api/jobs/{job_id}/stop").get_json()  # sans effet sur un calcul déjà arrêté
    assert again["status"] == "stopped" and again["result"] == job["result"]
    assert client.get(f"/api/jobs/{job_id}").get_json()["status"] == "stopped"


def test_stop_after_done_changes_nothing(client):
    job_id = client.post("/api/jobs", json=JOB).get_json()["job_id"]
    done = wait_finished(client, job_id)
    assert client.post(f"/api/jobs/{job_id}/stop").get_json()["result"] == done["result"]


def test_same_seed_same_run(client):
    costs = []
    for _ in range(2):
        job_id = client.post("/api/jobs", json={**JOB, "seed": 5}).get_json()["job_id"]
        costs.append(wait_finished(client, job_id)["history"][0])
    assert costs[0] == costs[1]  # le point de départ (glouton) est identique


def test_notebook_greedy_start_can_exceed_the_fleet(client):
    """Limite connue du notebook : le glouton utilise 7 camions pour k = 6, l'algorithme reste
    bloqué ; le serveur renvoie la solution et la dit invalide au lieu de la cacher."""
    job_id = client.post("/api/jobs", json={**JOB, "instance_id": "A-n37-k6"}).get_json()["job_id"]
    res = wait_finished(client, job_id)["result"]
    assert res["valid"] is False and any("flotte" in e for e in res["errors"])


@pytest.mark.parametrize("body, field", [
    (None, "body"), ([1], "body"), ({}, "instance_id"), ({"instance_id": 5, "solver": "x"}, "instance_id"),
    ({"instance_id": "A-n32-k5"}, "solver"),
    ({**JOB, "time_limit": 0}, "time_limit"), ({**JOB, "time_limit": 301}, "time_limit"),
    ({**JOB, "time_limit": "10"}, "time_limit"), ({**JOB, "time_limit": True}, "time_limit"),
    ({**JOB, "seed": -1}, "seed"), ({**JOB, "seed": 1.5}, "seed"), ({**JOB, "seed": "0"}, "seed"),
])
def test_job_parameters_are_validated(client, body, field):
    r = client.post("/api/jobs", json=body) if body is not None else client.post("/api/jobs", data="pas du json")
    assert r.status_code == 422
    assert r.get_json()["code"] == "invalid_param" and r.get_json()["field"] == field


def test_job_with_unknown_instance_or_solver(client):
    r = client.post("/api/jobs", json={**JOB, "instance_id": "Z-n9-k2"})
    assert r.status_code == 404 and "Z-n9-k2" in r.get_json()["error"]
    r = client.post("/api/jobs", json={**JOB, "solver": "magie"})
    assert r.status_code == 404 and "magie" in r.get_json()["error"]


def test_time_limit_defaults(client):
    job = client.post("/api/jobs", json={"instance_id": "A-n32-k5", "solver": "hill_climbing"}).get_json()
    got = client.get(f"/api/jobs/{job['job_id']}").get_json()
    assert got["time_limit"] == 10 and got["seed"] == 0


def test_old_jobs_are_forgotten():
    app, c = make_client(config={"MAX_JOBS_KEPT": 2})
    ids = []
    for _ in range(3):
        ids.append(c.post("/api/jobs", json=JOB).get_json()["job_id"])
        wait_finished(c, ids[-1])
    assert c.get(f"/api/jobs/{ids[0]}").status_code == 404
    assert c.get(f"/api/jobs/{ids[2]}").status_code == 200


# ------------------------------------------------- un solveur qui se comporte mal
def test_a_crashing_solver_does_not_kill_the_server():
    _, c = make_client(job_worker=fake_workers.crash)
    job = wait_finished(c, c.post("/api/jobs", json=JOB).get_json()["job_id"])
    assert job["status"] == "error" and job["error"] == "RuntimeError: boum" and job["result"] is None
    assert c.get("/api/health").status_code == 200
    assert c.post("/api/jobs", json=JOB).status_code == 202  # le créneau est libéré


def test_a_solver_that_never_returns_is_killed():
    _, c = make_client(config={"KILL_GRACE": 0.5}, job_worker=fake_workers.hang)
    started = time.time()
    job = wait_finished(c, c.post("/api/jobs", json=JOB).get_json()["job_id"])
    assert job["status"] == "error" and "temps limite" in job["error"]
    assert time.time() - started < 10


def test_a_solver_process_that_dies_silently():
    _, c = make_client(job_worker=fake_workers.die)
    job = wait_finished(c, c.post("/api/jobs", json=JOB).get_json()["job_id"])
    assert job["status"] == "error" and "sans résultat" in job["error"]


# ------------------------------------------------------------------------- réseau
def test_cors_is_off_by_default_and_configurable():
    _, c = make_client()
    r = c.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert "Access-Control-Allow-Origin" not in r.headers
    _, c = make_client(config={"CORS_ORIGINS": "http://localhost:5173, http://site.local"})
    r = c.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    r = c.get("/api/health", headers={"Origin": "http://pirate.example"})
    assert "Access-Control-Allow-Origin" not in r.headers
