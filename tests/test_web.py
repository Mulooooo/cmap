"""Tests du site : pages HTML, formulaires, et dialogue avec le serveur de calcul.

Deux sortes de tests : avec un FAUX serveur de calcul (cas limites : serveur éteint, erreurs...),
et avec le VRAI serveur de calcul (`server/`) branché en mémoire, sans réseau.
"""

import io
import time
from pathlib import Path

import pytest

from server import create_app as create_api
from web import create_app as create_site
from web.api_client import ApiClient, ApiError, Unreachable
from web.views import route_stats

ROOT = Path(__file__).resolve().parent.parent
A32 = ROOT / "instances" / "A" / "A-n32-k5.vrp"


# ------------------------------------------------------------------ outils de test
class InProcessApi(ApiClient):
    """Le vrai client d'API, mais le transport parle directement à l'application Flask du serveur."""

    def __init__(self, api_app):
        super().__init__("http://api.test")
        self.api_app = api_app
        self.http = api_app.test_client()

    def _request(self, method, path, **kwargs):
        if "files" in kwargs:
            name, data = kwargs.pop("files")["file"]
            kwargs = {"data": {"file": (io.BytesIO(data), name)}, "content_type": "multipart/form-data"}
        r = self.http.open(path, method=method, **kwargs)
        return r.status_code, r.get_json()


INSTANCE = {
    "id": "A-n32-k5", "name": "A-n32-k5", "source": "library", "n_clients": 4, "capacity": 100,
    "n_vehicles": 2, "edge_weight_type": "EUC_2D",
    "coords": [[50, 50], [60, 50], [60, 60], [40, 50], [40, 40]], "demand": [0, 30, 30, 30, 30],
    "best_known": {"cost": 80, "routes": [[1, 2], [3, 4]]},
}
SUMMARY = {"id": "A-n32-k5", "name": "A-n32-k5", "n_clients": 4, "capacity": 100, "n_vehicles": 2,
           "best_known_cost": 80, "has_best_known_routes": True, "source": "library"}
SOLVERS = [{"id": "hill_climbing", "name": "Hill climbing", "description": "x"},
           {"id": "simulated_annealing", "name": "Recuit simulé", "description": "y"}]


class FakeApi:
    """Un serveur de calcul de pacotille : rend ce qu'on lui a préparé et note les appels."""

    def __init__(self):
        self.down = False
        self.calls = []
        self.job_state = None  # dict renvoyé par job()
        self.start_error = None  # ApiError à lever au lancement
        self.upload_error = None
        self.instance_error = None

    def _guard(self, name, *args):
        self.calls.append((name, *args))
        if self.down:
            raise Unreachable("Serveur de calcul injoignable (http://fake)")

    def solvers(self):
        self._guard("solvers")
        return SOLVERS

    def instances(self):
        self._guard("instances")
        return [SUMMARY]

    def instance(self, instance_id):
        self._guard("instance", instance_id)
        if self.instance_error or instance_id != "A-n32-k5":
            raise self.instance_error or ApiError(404, "not_found", f"Instance inconnue : {instance_id}")
        return INSTANCE

    def upload(self, data, filename):
        self._guard("upload", filename)
        if self.upload_error:
            raise self.upload_error
        return {**INSTANCE, "id": "up-1234", "source": "upload"}

    def start_job(self, instance_id, solver, time_limit, seed):
        self._guard("start_job", instance_id, solver, time_limit, seed)
        if self.start_error:
            raise self.start_error
        return {"job_id": "j1", "status": "running"}

    def job(self, job_id):
        self._guard("job", job_id)
        if self.job_state is None:
            raise ApiError(404, "not_found", "Calcul inconnu")
        return self.job_state

    def stop(self, job_id):
        self._guard("stop", job_id)
        return self.job_state


def job_state(status="running", **over):
    base = {"job_id": "j1", "instance_id": "A-n32-k5", "solver": "hill_climbing", "time_limit": 10, "seed": 0,
            "status": status, "elapsed": 2.5, "best_cost": 90.0, "version": 3, "routes": [[1, 2], [3, 4]],
            "history": [[0.0, 0, 120.0], [1.0, 5, 90.0]], "result": None, "error": None}
    return {**base, **over}


RESULT = {"cost": 82.0, "gap": 2.5, "valid": True, "errors": [], "n_routes": 2, "elapsed": 9.9,
          "routes": [[1, 2], [4, 3]],
          "per_route": [{"n_clients": 2, "load": 60, "distance": 40.0}, {"n_clients": 2, "load": 60, "distance": 42.0}]}


@pytest.fixture
def fake():
    return FakeApi()


@pytest.fixture
def client(fake):
    return create_site(api=fake).test_client()


# ----------------------------------------------------------------------------- pages
def test_home_shows_the_instance_the_solvers_and_the_best_known_solution(client, fake):
    html = client.get("/").get_data(as_text=True)
    assert "A-n32-k5" in html and "4 clients" in html
    assert 'value="hill_climbing"' in html and "Recuit simulé" in html  # menu des métaheuristiques
    assert "▶ Calculer" in html and "Aucune solution à afficher" not in html
    assert 'id="best"' in html and 'id="mine"' not in html and "<iframe" in html
    assert ("instance", "A-n32-k5") in fake.calls  # la 1re instance de la liste est choisie


def test_the_page_has_no_javascript_of_its_own(client, fake):
    fake.job_state = job_state("done", result=RESULT)
    html = client.get("/?job=j1").get_data(as_text=True)
    assert "<script" not in html.lower() and "onclick" not in html.lower()  # la carte est dans l'iframe srcdoc


def test_running_job_reloads_every_second_and_shows_progress(client, fake):
    fake.job_state = job_state("running")
    html = client.get("/?job=j1").get_data(as_text=True)
    assert '<meta http-equiv="refresh" content="1">' in html
    assert "■ Arrêter" in html and "Calcul en cours" in html and "meilleur coût 90" in html
    assert 'id="mine"' in html and 'id="v-best"' not in html  # pas d'onglets avant la fin


def test_finished_job_shows_both_solutions_and_no_reload(client, fake):
    fake.job_state = job_state("done", result=RESULT)
    html = client.get("/?job=j1").get_data(as_text=True)
    assert 'http-equiv="refresh"' not in html and "▶ Calculer" in html
    assert "Solution valide (Hill climbing)" in html and "Gap vs meilleure connue" in html
    assert 'id="mine"' in html and 'id="best"' in html and 'id="v-mine"' in html and html.count('class="map map-') == 2


def test_an_invalid_solution_is_shown_as_invalid(client, fake):
    bad = {**RESULT, "valid": False, "errors": ["7 camions utilisés pour une flotte de 6"]}
    fake.job_state = job_state("done", result=bad)
    assert "Solution invalide : 7 camions utilisés pour une flotte de 6" in client.get("/?job=j1").get_data(as_text=True)


def test_stopped_job(client, fake):
    fake.job_state = job_state("stopped", result=RESULT)
    html = client.get("/?job=j1").get_data(as_text=True)
    assert "Calcul arrêté" in html and 'http-equiv="refresh"' not in html and "Hill climbing, arrêté" in html


def test_failed_job_shows_the_error(client, fake):
    fake.job_state = job_state("error", routes=None, best_cost=None, error="RuntimeError: boum")
    assert "Erreur du calcul : RuntimeError: boum" in client.get("/?job=j1").get_data(as_text=True)


def test_forgotten_job_does_not_break_the_page(client, fake):
    fake.job_state = None  # le serveur de calcul répond 404
    html = client.get("/?job=perdu").get_data(as_text=True)
    assert "existe plus" in html and "A-n32-k5" in html


def test_unknown_instance_falls_back_to_the_first_one(client):
    html = client.get("/?instance=Z-n9-k2").get_data(as_text=True)
    assert "Instance inconnue : Z-n9-k2" in html and "A-n32-k5" in html


def test_page_when_the_compute_server_is_down(client, fake):
    fake.down = True
    r = client.get("/")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "injoignable" in html and "disabled" in html  # bouton Calculer grisé
    assert "<iframe" not in html


def test_numeric_fields_accept_the_values_the_site_proposes(client):
    """Un champ `number` avec min=5 et step=10 refuse 100 ou 250 (seulement 5, 15, 25...) : le navigateur
    bloquerait « Afficher ». L'étendue doit accepter n'importe quelle valeur."""
    html = client.get("/").get_data(as_text=True)
    span = html.split('name="span"')[1].split(">")[0]
    assert 'step="any"' in span
    for field in ("limit", "seed"):  # entiers : un pas de 1 depuis un minimum entier convient
        tag = html.split(f'name="{field}"')[1].split(">")[0]
        assert 'step="1"' in tag or "step" not in tag


def test_garbage_parameters_are_ignored(client):
    r = client.get("/?zone=Mars&span=xyz&limit=abc&seed=-3&solver=magie&view=zzz")
    assert r.status_code == 200 and "France entière" in r.get_data(as_text=True)


def test_user_input_is_escaped(client, fake):
    fake.instance_error = ApiError(404, "not_found", "<img src=x onerror=alert(1)>")
    html = client.get("/?instance=x").get_data(as_text=True)
    assert "<img src=x" not in html and "&lt;img src=x" in html


# -------------------------------------------------------------------------- formulaires
def post(client, **fields):
    return client.post("/", data={"instance": "A-n32-k5", "zone": "France entière", "span": "", "solver": "hill_climbing",
                                  "limit": "10", "seed": "0", "job": "", **fields}, follow_redirects=False)


def test_calculer_starts_a_job_and_redirects_to_it(client, fake):
    r = post(client, action="solve", solver="simulated_annealing", limit="7", seed="3")
    assert r.status_code == 303 and "job=j1" in r.headers["Location"] and "instance=A-n32-k5" in r.headers["Location"]
    assert ("start_job", "A-n32-k5", "simulated_annealing", 7, 3) in fake.calls


def test_calculer_while_another_job_runs_shows_that_job(client, fake):
    fake.start_error = ApiError(409, "busy", "Un calcul est déjà en cours", {"job_id": "autre"})
    loc = post(client, action="solve").headers["Location"]
    assert "job=autre" in loc and "notice=busy" in loc
    fake.job_state = job_state("running", job_id="autre")
    assert "un seul calcul à la fois" in client.get(loc).get_data(as_text=True)


def test_api_validation_error_is_shown(client, fake):
    fake.start_error = ApiError(422, "invalid_param", "« time_limit » doit être un nombre de 1 à 300 secondes")
    r = post(client, action="solve", limit="9999")
    assert r.status_code == 422 and "time_limit" in r.get_data(as_text=True)


def test_arreter_stops_the_job(client, fake):
    fake.job_state = job_state("stopped", result=RESULT)
    r = post(client, action="stop", job="j1")
    assert r.status_code == 303 and "job=j1" in r.headers["Location"] and ("stop", "j1") in fake.calls


def test_afficher_keeps_the_choices_in_the_url(client):
    r = post(client, action="show", zone="Île-de-France", span="50", limit="20", seed="4")
    loc = r.headers["Location"]
    assert r.status_code == 303 and "zone=%C3%8Ele-de-France" in loc and "span=50" in loc and "limit=20" in loc


def test_upload_a_vrp_file(client, fake):
    r = client.post("/", data={"action": "show", "zone": "France entière", "file": (io.BytesIO(b"contenu"), "mon.vrp")},
                    content_type="multipart/form-data", follow_redirects=False)
    assert r.status_code == 303 and "instance=up-1234" in r.headers["Location"]
    assert ("upload", "mon.vrp") in fake.calls


def test_bad_upload_shows_the_api_message(client, fake):
    fake.upload_error = ApiError(400, "invalid_file", "Fichier .vrp illisible : x")
    r = client.post("/", data={"action": "show", "file": (io.BytesIO(b"x"), "bad.vrp")}, content_type="multipart/form-data")
    assert r.status_code == 400 and "Fichier .vrp illisible" in r.get_data(as_text=True)


def test_forms_when_the_compute_server_is_down(client, fake):
    fake.down = True
    r = post(client, action="solve")
    assert r.status_code == 200 and "injoignable" in r.get_data(as_text=True)


# ------------------------------------------------------------------- le client d'API
def test_real_client_reports_an_unreachable_server():
    with pytest.raises(Unreachable):
        ApiClient("http://127.0.0.1:9", timeout=1).health()


# ------------------------------- avec le VRAI serveur de calcul (branché en mémoire, sans réseau)
@pytest.fixture
def real():
    api_app = create_api({"TESTING": True})
    api = InProcessApi(api_app)
    yield create_site(api=api).test_client(), api
    for job in list(api_app.extensions["jobs"]._jobs.values()):
        api_app.extensions["jobs"].stop(job)


def test_site_and_api_agree_on_distances(real):
    """Le site recalcule les distances de la meilleure solution connue : elles doivent retomber sur 784."""
    _, api = real
    inst = api.instance("A-n32-k5")
    stats = route_stats(inst, inst["best_known"]["routes"])
    assert sum(s["distance"] for s in stats) == inst["best_known"]["cost"] == 784
    assert [s["load"] for s in stats] == [98, 72, 44, 98, 98]


def test_real_home_page(real):
    site, _ = real
    html = site.get("/").get_data(as_text=True)
    assert "A-n32-k5" in html and "Hill climbing" in html and "Meilleure connue" in html
    assert "98/100" in html  # tableau de la meilleure solution connue


def test_real_run_from_the_form_to_the_result_page(real):
    site, api = real
    r = post(site, action="solve", limit="2")
    assert r.status_code == 303
    url = r.headers["Location"]
    time.sleep(0.5)
    running = site.get(url).get_data(as_text=True)
    assert 'http-equiv="refresh"' in running and "Arrêter" in running
    # un 2e calcul pendant celui-là : refusé par le serveur de calcul, le site affiche le premier
    again = post(site, action="solve", limit="2").headers["Location"]
    assert "notice=busy" in again and again.split("job=")[1].split("&")[0] == url.split("job=")[1].split("&")[0]

    deadline = time.time() + 30
    while time.time() < deadline and 'http-equiv="refresh"' in (page := site.get(url).get_data(as_text=True)):
        time.sleep(0.3)
    assert "Solution valide (Hill climbing)" in page and 'id="mine"' in page and 'id="best"' in page
    assert "Convergence" in page and "Gap vs meilleure connue" in page


def test_real_stop_from_the_form(real):
    site, api = real
    url = post(site, action="solve", limit="60").headers["Location"]
    job = url.split("job=")[1].split("&")[0]
    time.sleep(1.5)
    assert post(site, action="stop", job=job).status_code == 303
    html = site.get(url).get_data(as_text=True)
    assert "Calcul arrêté" in html and "Hill climbing, arrêté" in html and 'http-equiv="refresh"' not in html


def test_real_upload_then_compute_on_it(real):
    site, _ = real
    r = site.post("/", data={"action": "show", "file": (io.BytesIO(A32.read_bytes()), "mon.vrp")},
                  content_type="multipart/form-data", follow_redirects=False)
    assert r.status_code == 303 and "instance=up-" in r.headers["Location"]
    page = site.get(r.headers["Location"]).get_data(as_text=True)
    assert "(fichier envoyé)" in page
