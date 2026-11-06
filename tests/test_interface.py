import math
import time
from pathlib import Path

import numpy as np
import pytest

from interface import solvers
from interface.__main__ import choose_solver, main
from interface.geo import PRESETS, place_on_map
from interface.instance import load_instance, load_instance_from_bytes
from interface.page import build_page

ROOT = Path(__file__).resolve().parent.parent
A32 = ROOT / "instances" / "A" / "A-n32-k5.vrp"
HILL = "Hill climbing (notebook)"
RECUIT = "Recuit simulé (notebook)"


@pytest.fixture(scope="module")
def inst():
    return load_instance(A32)


# ------------------------------------------------------------------- instance
def test_load_instance(inst):
    assert inst.name == "A-n32-k5"
    assert inst.n == 32 and inst.capacity == 100
    assert inst.n_vehicles == 5 and inst.bks == 784
    assert inst.demand[0] == 0 and inst.min_vehicles == 5


def test_best_known_falls_back_to_the_sol_file(tmp_path):
    text = A32.read_text().replace("Optimal value: 784", "")  # commentaire sans valeur optimale
    (tmp_path / "x.vrp").write_text(text)
    (tmp_path / "x.sol").write_text("Route #1: 1 2\nCost 784\n")
    assert load_instance(tmp_path / "x.vrp").bks == 784


def test_distances_rounded_like_tsplib(inst):
    # sommets 1 et 2 : (82,76) et (96,44) -> sqrt(14^2 + 32^2) = 34.93 -> 35
    assert inst.dist[0, 1] == 35


def test_load_from_bytes(inst):
    again = load_instance_from_bytes(A32.read_bytes(), "x.vrp")
    assert np.array_equal(again.dist, inst.dist)
    assert again.best_routes is None  # pas de .sol à côté d'un fichier téléversé


def test_load_instance_reads_the_best_known_solution(inst):
    assert inst.best_routes and len(inst.best_routes) == 5
    assert solvers.check_solution(inst, inst.best_routes) == []
    assert solvers.total_cost(inst, inst.best_routes) == inst.bks == 784  # distances arrondies


@pytest.mark.parametrize("vrp", sorted((ROOT / "instances").rglob("*.vrp")), ids=lambda p: p.stem)
def test_every_repo_instance_matches_its_sol_file(vrp):
    i = load_instance(vrp)
    assert solvers.check_solution(i, i.best_routes) == []
    assert solvers.total_cost(i, i.best_routes) == i.bks


# ------------------------------------------------------------------------ carte
def test_place_on_map_keeps_shape_and_scale(inst):
    lat0, lon0, span = PRESETS["France entière"]
    f = place_on_map(inst.coords, lat0, lon0, span)
    # le plus grand côté fait bien `span` km
    assert math.isclose(f.km_per_unit * np.ptp(inst.coords, axis=0).max(), span)
    # le nuage est centré sur la zone demandée
    assert math.isclose((f.lat.min() + f.lat.max()) / 2, lat0, abs_tol=1e-6)
    assert math.isclose((f.lon.min() + f.lon.max()) / 2, lon0, abs_tol=1e-6)
    # les distances relatives sont conservées : même rapport est-ouest / nord-sud
    d_ns = (f.lat.max() - f.lat.min()) * 111.32
    d_ew = (f.lon.max() - f.lon.min()) * 111.32 * math.cos(math.radians(lat0))
    ratio_inst = np.ptp(inst.coords[:, 0]) / np.ptp(inst.coords[:, 1])
    assert math.isclose(d_ew / d_ns, ratio_inst, rel_tol=1e-6)


# ---------------------------------------------------------------------- solveurs
def test_check_solution_detects_errors(inst):
    assert solvers.check_solution(inst, [[1, 2]])  # clients manquants
    assert solvers.check_solution(inst, [list(range(1, inst.n))])  # capacité dépassée
    doubled = [list(range(1, inst.n)), [1]]
    assert any("plusieurs fois" in e for e in solvers.check_solution(inst, doubled))


def test_check_solution_enforces_the_fleet_size(inst):
    routes = [[c] for c in range(1, 7)] + [list(range(7, inst.n))]  # 7 camions pour une flotte de 5
    assert any("flotte" in e for e in solvers.check_solution(inst, routes))


@pytest.mark.parametrize("name", [HILL, RECUIT])
def test_notebook_solvers_return_a_valid_solution(inst, name):
    from interface.notebook_solvers import greedy_initial_solution

    sol = solvers.SOLVERS[name](inst, 1.5, 0)
    assert solvers.check_solution(inst, sol.routes) == []
    assert sol.cost == solvers.total_cost(inst, sol.routes)
    assert sol.cost <= solvers.total_cost(inst, greedy_initial_solution(inst))  # jamais pire que le départ
    assert sol.history and sol.history[0][2] >= sol.history[-1][2]


def test_notebook_solvers_report_progress(inst):
    seen = []
    solvers.SOLVERS[HILL](inst, 0.5, 0, lambda it, cost, routes: seen.append((it, cost, routes)))
    assert seen and seen[0][0] == 0  # le point de départ est signalé
    assert all(a[1] >= b[1] for a, b in zip(seen, seen[1:]))  # le coût ne remonte jamais


def test_notebook_greedy_start_can_exceed_the_fleet():
    """Limite connue du notebook : sur A-n37-k6 le glouton utilise 7 camions pour k = 6, donc
    is_possible refuse tous les voisins et l'algorithme reste bloqué sur une solution invalide."""
    inst = load_instance(ROOT / "instances" / "A" / "A-n37-k6.vrp")
    sol = solvers.SOLVERS[HILL](inst, 0.5, 0)
    assert any("flotte" in e for e in solvers.check_solution(inst, sol.routes))


def test_registry_accepts_a_team_solver(inst):
    @solvers.register("test-un-camion-par-client")
    def trivial(inst, time_limit, seed, on_progress=None):
        return solvers.make_solution(inst, [[c] for c in range(1, inst.n)], "trivial")

    try:
        sol = solvers.SOLVERS["test-un-camion-par-client"](inst, 1, 0)
        assert len(sol.routes) == inst.n - 1
        # clients et capacités sont bons ; seule la flotte (5 camions) est dépassée
        errors = solvers.check_solution(inst, sol.routes)
        assert len(errors) == 1 and "flotte" in errors[0]
    finally:
        del solvers.SOLVERS["test-un-camion-par-client"]


# -------------------------------------------------------------------------- page
def test_page_shows_the_best_known_solution_by_default(inst):
    html = build_page(inst)
    assert "<iframe" in html and "leaflet" in html.lower()  # carte folium
    assert "Meilleure solution connue" in html and "Solution valide" in html
    assert 'id="best"' in html and 'id="mine"' not in html
    assert "Client 1 · demande 19" in html  # info-bulles des clients, dans la carte


def test_basemaps_work_from_a_local_file(inst):
    """OpenStreetMap répond 403 aux pages ouvertes en fichier local, CartoDB exige une clé : on
    n'utilise que des fonds qui marchent sans clé ni Referer."""
    html = build_page(inst)
    assert "arcgisonline.com" in html  # fond par défaut : Esri
    assert "openstreetmap.org" not in html.replace("OpenStreetMap contributors", "")
    assert "cartocdn" not in html and "basemaps.cartocdn" not in html


def test_page_has_no_script_of_its_own(inst):
    mine = solvers.SOLVERS[HILL](inst, 0.5, 0)
    html = build_page(inst, mine=mine)
    # la carte folium est dans un iframe `srcdoc` (échappé) : aucune balise <script> dans la page elle-même
    assert "<script" not in html.lower()
    assert "onclick" not in html.lower()


def test_page_compares_my_solution_with_the_best_known(inst):
    mine = solvers.SOLVERS[HILL](inst, 0.5, 0)
    html = build_page(inst, mine=mine, settings={"Solveur": HILL, "Graine": "0"})
    assert 'id="mine"' in html and 'id="best"' in html
    # onglets en CSS : deux cartes (la mienne, la meilleure connue) et deux boutons radio cachés
    assert html.count('class="map map-') == 2 and 'id="v-mine"' in html and 'id="v-best"' in html
    assert "Gap vs meilleure connue" in html and "Convergence" in html
    assert HILL in html


def test_page_flags_an_invalid_solution(inst):
    bad = solvers.make_solution(inst, [[1, 2, 3]], "incomplète")
    assert "Solution invalide" in build_page(inst, mine=bad)


def test_page_without_any_solution(tmp_path):
    (tmp_path / "x.vrp").write_text(A32.read_text())  # pas de .sol à côté
    html = build_page(load_instance(tmp_path / "x.vrp"))
    assert "Aucune solution à afficher" in html and "<iframe" in html


def test_page_rejects_an_unknown_zone(inst):
    with pytest.raises(ValueError, match="Zone inconnue"):
        build_page(inst, zone="Mars")


def test_page_escapes_the_instance_name(tmp_path):
    text = A32.read_text().replace("NAME : A-n32-k5", "NAME : <b>x</b>")
    (tmp_path / "x.vrp").write_text(text)
    html = build_page(load_instance(tmp_path / "x.vrp"))
    assert "<b>x</b>" not in html.split("<main>")[1].split("<iframe")[0]


# ---------------------------------------------------------------------------- CLI
def test_cli_writes_the_page(tmp_path, capsys):
    out = tmp_path / "page.html"
    main([str(A32), "--solveur", "recuit", "--temps", "1", "--sortie", str(out), "--sans-ouvrir"])
    html = out.read_text(encoding="utf-8")
    assert RECUIT in html and 'id="mine"' in html and 'id="best"' in html
    assert "Résultat : coût" in capsys.readouterr().out


def test_cli_without_solver_shows_the_best_known(tmp_path):
    out = tmp_path / "page.html"
    main([str(A32), "--sortie", str(out), "--sans-ouvrir"])
    html = out.read_text(encoding="utf-8")
    assert 'id="best"' in html and 'id="mine"' not in html


def test_cli_zone_and_span(tmp_path):
    out = tmp_path / "page.html"
    main([str(A32), "--zone", "Île-de-France", "--etendue", "50", "--sortie", str(out), "--sans-ouvrir"])
    assert "Île-de-France" in out.read_text(encoding="utf-8") and "50 km" in out.read_text(encoding="utf-8")


def test_cli_errors(tmp_path):
    with pytest.raises(SystemExit):
        main([str(tmp_path / "absent.vrp"), "--sans-ouvrir"])
    bad = tmp_path / "bad.vrp"
    bad.write_text("pas un vrp")
    with pytest.raises(SystemExit):
        main([str(bad), "--sans-ouvrir"])
    with pytest.raises(SystemExit):
        main([str(A32), "--solveur", "inconnu", "--sans-ouvrir"])


def test_choose_solver():
    assert choose_solver("hill") == HILL
    assert choose_solver("RECUIT") == RECUIT
    assert choose_solver(HILL) == HILL
    with pytest.raises(SystemExit):
        choose_solver("(notebook)")  # ambigu : correspond aux deux


# ------------------------------------------------------------------------ serveur
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from interface.server import app

    return TestClient(app)


def _solve(client, solver=HILL, limit="2", src="lib:A/A-n32-k5.vrp"):
    r = client.post("/", data={"action": "solve", "src": src, "solver": solver, "limit": limit,
                               "seed": "0", "zone": "France entière"}, follow_redirects=False)
    assert r.status_code == 303 and "job=" in r.headers["location"]
    return r.headers["location"]


def _wait_until_finished(client, url, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        page = client.get(url).text
        if 'http-equiv="refresh"' not in page:
            return page
        time.sleep(0.3)
    raise AssertionError("le calcul ne se termine pas")


def test_server_home_has_the_controls(client):
    html = client.get("/").text
    assert "<form" in html and "▶ Calculer" in html and "Métaheuristique" in html
    assert HILL in html and RECUIT in html  # menu des solveurs
    assert "lib:A/A-n32-k5.vrp" in html and "Meilleure solution connue" in html
    assert "<script" not in html.lower()


def test_server_solve_runs_then_shows_both_solutions(client):
    url = _solve(client)
    running = client.get(url).text
    assert 'http-equiv="refresh"' in running and "Arrêter" in running  # page qui se recharge seule
    done = _wait_until_finished(client, url)
    assert "Solution valide (Hill climbing (notebook))" in done
    assert 'id="mine"' in done and 'id="best"' in done and 'id="v-best"' in done  # onglets
    assert "Gap vs meilleure connue" in done and "▶ Calculer" in done


def test_server_stop_keeps_the_best_solution_so_far(client):
    url = _solve(client, limit="60")
    time.sleep(0.5)
    job = url.split("job=")[1].split("&")[0]
    r = client.post("/", data={"action": "stop", "src": "lib:A/A-n32-k5.vrp", "job": job,
                               "solver": HILL, "limit": "60", "seed": "0"}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get(r.headers["location"]).text
    assert "Calcul arrêté" in page and 'http-equiv="refresh"' not in page
    assert 'id="mine"' in page


def test_server_upload_a_vrp_file(client):
    r = client.post("/", data={"action": "show", "zone": "France entière"},
                    files={"file": ("x.vrp", A32.read_bytes())}, follow_redirects=False)
    assert r.status_code == 303 and "src=up%3A" in r.headers["location"]
    page = client.get(r.headers["location"]).text
    assert "(fichier téléversé)" in page and 'id="best"' not in page  # pas de .sol à côté
    # on peut calculer sur ce fichier
    src = r.headers["location"].split("src=")[1].split("&")[0].replace("%3A", ":")
    assert "Solution valide" in _wait_until_finished(client, _solve(client, src=src))


def test_server_rejects_a_bad_file(client):
    r = client.post("/", data={"action": "show"}, files={"file": ("bad.vrp", b"pas un vrp")})
    assert r.status_code == 400 and "illisible" in r.text
    assert "lib:A/A-n32-k5.vrp" in r.text  # la page reste utilisable


def test_server_only_serves_listed_instances(client):
    for src in ("lib:../../etc/passwd", "lib:interface/server.py", "up:inconnu", "n'importe quoi"):
        r = client.get("/", params={"src": src})
        assert r.status_code == 200 and "introuvable" in r.text
        assert "A-n32-k5" in r.text  # retombe sur la première instance du dépôt


def test_server_shows_a_solver_crash(client):
    @solvers.register("test-solveur-qui-plante")
    def broken(inst, time_limit, seed, on_progress=None):
        raise RuntimeError("boum")

    try:
        page = _wait_until_finished(client, _solve(client, solver="test-solveur-qui-plante"))
        assert "Erreur du solveur" in page and "RuntimeError: boum" in page
    finally:
        del solvers.SOLVERS["test-solveur-qui-plante"]


def test_server_ignores_silly_parameters(client):
    r = client.get("/", params={"limit": "abc", "seed": "-5", "span": "xyz", "zone": "Mars"})
    assert r.status_code == 200 and "France entière" in r.text
