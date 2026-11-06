"""Simulation sur les vraies routes : client OSRM, horaires, carte animée et pages du site.

Aucun test n'appelle le vrai OSRM (il faut Internet et le service limite le débit) ; l'un d'eux,
ignoré par défaut, le fait : `OSRM_LIVE=1 pytest tests/test_simulation.py`.
"""

import os

import numpy as np
import pytest
import requests
from test_web import INSTANCE, RESULT, FakeApi, job_state

from web import create_app
from web.geo import place_on_map
from web.routing import OsrmClient, RoadRoute, RoutingError, RoutingUnavailable
from web.simulation import build_simulation, build_timeline, clock, straight_route, waypoint_indices


# ------------------------------------------------------------------------- outils
def osrm_response(points, distance=1000.0, duration=100.0):
    """Une réponse OSRM minimale : un tracé droit qui passe par tous les points."""
    return {"code": "Ok",
            "routes": [{"geometry": {"coordinates": [[lon, lat] for lat, lon in points]},
                        "legs": [{"distance": distance, "duration": duration} for _ in points[1:]]}],
            "waypoints": [{"location": [lon, lat]} for lat, lon in points]}


class FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        if self.data is None:
            raise ValueError("pas du JSON")
        return self.data


class FakeSession:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class StraightRouting:
    """Faux service d'itinéraires : lignes droites, 1 km et 100 s par étape."""

    def route(self, points):
        road = straight_route(points)
        return RoadRoute(road.coords, road.waypoints, [{"distance_m": 1000.0, "duration_s": 100.0} for _ in road.legs])


class DownRouting:
    def route(self, points):
        raise RoutingUnavailable("Le service d'itinéraires routiers (OSRM) ne répond pas")


class NoRouteRouting:
    def route(self, points):
        raise RoutingError("Impossible de trouver une route entre ces points")


PTS = [(48.69, 6.18), (48.85, 2.35), (45.76, 4.84), (48.69, 6.18)]  # (lat, lon)


def line_road(n=31, legs=(100.0, 200.0, 300.0)):
    """Un tracé droit de n points (~111 m entre deux points) avec 4 points de passage, 3 étapes."""
    coords = [(i * 0.001, 0.0) for i in range(n)]
    idx = [0, 10, 20, n - 1]
    return RoadRoute(coords, [coords[i] for i in idx],
                     [{"distance_m": 1112.0, "duration_s": d} for d in legs])


# -------------------------------------------------------------------- client OSRM
def test_osrm_parses_a_route():
    session = FakeSession(FakeResponse(osrm_response(PTS)))
    road = OsrmClient(min_interval=0, session=session).route(PTS)
    assert road.coords[0] == (6.18, 48.69) and len(road.legs) == 3 and road.distance_m == 3000 and road.duration_s == 300
    url, kwargs = session.calls[0]
    assert "/route/v1/driving/6.180000,48.690000;2.350000,48.850000;" in url  # longitude d'abord, comme OSRM
    assert kwargs["params"]["geometries"] == "geojson" and "User-Agent" in kwargs["headers"]


def test_osrm_answers_are_cached():
    session = FakeSession(FakeResponse(osrm_response(PTS)))
    client = OsrmClient(min_interval=0, session=session)
    assert client.route(PTS) is client.route(list(PTS))
    assert len(session.calls) == 1


def test_osrm_spaces_its_calls(monkeypatch):
    sleeps = []
    monkeypatch.setattr("web.routing.time.sleep", sleeps.append)
    client = OsrmClient(min_interval=1.1, session=FakeSession(FakeResponse(osrm_response(PTS))))
    client.route(PTS)
    client.route(PTS[:2])  # appel différent : on doit attendre avant de le lancer
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 1.1


@pytest.mark.parametrize("reply, error", [
    (FakeResponse({"code": "NoRoute", "message": "Impossible de trouver une route"}, 400), RoutingError),
    (FakeResponse({"code": "NoSegment"}, 400), RoutingError),
    (FakeResponse(None, 500), RoutingUnavailable),
    (FakeResponse({}, 429), RoutingUnavailable),
    (requests.ConnectionError("pas de réseau"), RoutingUnavailable),
    (requests.Timeout("trop lent"), RoutingUnavailable),
])
def test_osrm_errors(reply, error):
    with pytest.raises(error) as exc:
        OsrmClient(min_interval=0, session=FakeSession(reply)).route(PTS)
    assert error is RoutingUnavailable or not isinstance(exc.value, RoutingUnavailable)


# ---------------------------------------------------------------------- horaires
def test_waypoints_are_found_along_the_road():
    assert waypoint_indices(line_road()) == [0, 10, 20, 30]


def test_timeline_uses_osrm_durations_and_adds_the_delivery_time():
    tl = build_timeline(line_road(), service_s=600)
    assert tl.arrivals == [0, 100, 900, 1800]  # 100 s de route, 600 s de livraison, 200 s de route...
    assert tl.departures == [0, 700, 1500, 1800]
    assert tl.drive_s == 600 and tl.total_s == 1800 and tl.distance_m == 3336
    times = [t for t, _, _ in tl.points]
    assert times == sorted(times) and times[0] == 0 and times[-1] == 1800
    assert (100.0, *line_road().coords[10]) in tl.points and (700.0, *line_road().coords[10]) in tl.points  # il y reste 600 s
    assert tl.points[-1][1:] == line_road().coords[-1]  # il finit au dépôt


def test_timeline_is_thin_enough_for_an_animation():
    road = line_road(n=3001, legs=(1000.0, 1000.0, 1000.0))
    road.waypoints[1:3] = [road.coords[1000], road.coords[2000]]
    tl = build_timeline(road, service_s=0, step_m=1000)
    assert len(tl.points) < 700 < len(road.coords)  # ~1 point par km au lieu d'un par ~100 m


def test_straight_fallback_route():
    road = straight_route(PTS)
    assert len(road.legs) == 3 and road.distance_m > 800_000
    assert road.legs[0]["duration_s"] == pytest.approx(road.legs[0]["distance_m"] / (70 / 3.6))


def test_clock_shows_the_day_after_midnight():
    assert clock(0) == "08:00" and clock(3600) == "09:00"
    assert clock(26.5 * 3600) == "mar. 10:30"


# ------------------------------------------------------------------- la carte animée
FRAME = place_on_map(np.array(INSTANCE["coords"], dtype=float), 46.6, 2.4, 700)


def test_simulation_map_has_one_truck_per_route():
    sim = build_simulation(FRAME, [[1, 2], [3, 4]], StraightRouting())
    assert [t["n"] for t in sim.trucks] == [1, 2] and [t["clients"] for t in sim.trucks] == [2, 2]
    assert sim.warnings == [] and all(not t["straight"] for t in sim.trucks)
    assert sim.trucks[0]["road_km"] == 3.0 and sim.trucks[0]["drive_s"] == 300
    assert sim.trucks[0]["total_s"] == 300 + 2 * 600  # 2 clients, 10 minutes chacun
    assert "timedimension" in sim.html.lower() and "Camion 1" in sim.html and "Client 3" in sim.html


def test_unreachable_points_fall_back_to_straight_lines_with_a_warning():
    sim = build_simulation(FRAME, [[1, 2], [3, 4]], NoRouteRouting())
    assert all(t["straight"] for t in sim.trucks) and len(sim.warnings) == 2
    assert "Camion 1" in sim.warnings[0] and "vol d'oiseau" in sim.warnings[0]


def test_routing_service_down_is_not_hidden():
    with pytest.raises(RoutingUnavailable):
        build_simulation(FRAME, [[1, 2]], DownRouting())


# ------------------------------------------------------------------ pages du site
@pytest.fixture
def fake():
    return FakeApi()


def site(fake, routing=None):
    return create_app(api=fake, routing=routing or StraightRouting()).test_client()


def test_simulate_the_best_known_solution(fake):
    client = site(fake)
    html = client.get("/simulation?instance=A-n32-k5&view=best").get_data(as_text=True)
    assert "Meilleure solution connue" in html and "Résumé par camion" in html and "Route réelle" in html
    assert "<script" not in html.lower() and "← Retour aux résultats" in html
    src = html.split('src="/simulation/map/')[1].split('"')[0]
    page = client.get(f"/simulation/map/{src}")
    assert page.status_code == 200 and page.mimetype == "text/html" and "Camion 1" in page.get_data(as_text=True)


def test_simulate_my_solution(fake):
    fake.job_state = job_state("done", result=RESULT)
    html = site(fake).get("/simulation?instance=A-n32-k5&view=mine&job=j1").get_data(as_text=True)
    assert "Ma solution (hill_climbing)" in html and "Résumé par camion" in html


def test_simulation_needs_a_finished_solution(fake):
    client = site(fake)
    assert "abord un calcul" in client.get("/simulation?instance=A-n32-k5&view=mine").get_data(as_text=True)
    fake.job_state = job_state("running")
    assert "pas terminé" in client.get("/simulation?instance=A-n32-k5&view=mine&job=j1").get_data(as_text=True)
    fake.job_state = None
    assert "existe plus" in client.get("/simulation?instance=A-n32-k5&view=mine&job=perdu").get_data(as_text=True)


def test_simulation_of_an_instance_without_best_known_solution(fake):
    from test_web import INSTANCE as base
    import test_web
    test_web.INSTANCE = {**base, "best_known": None}
    try:
        html = site(fake).get("/simulation?instance=A-n32-k5&view=best").get_data(as_text=True)
    finally:
        test_web.INSTANCE = base
    assert "pas de meilleure solution connue" in html


def test_page_when_the_routing_service_is_down(fake):
    r = site(fake, DownRouting()).get("/simulation?instance=A-n32-k5&view=best")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "ne répond pas" in html and "<iframe" not in html


def test_page_warns_about_roads_that_cannot_be_found(fake):
    html = site(fake, NoRouteRouting()).get("/simulation?instance=A-n32-k5&view=best").get_data(as_text=True)
    assert "vol d'oiseau" in html and "Impossible de trouver une route" in html


def test_unknown_or_expired_map_token(fake):
    assert site(fake).get("/simulation/map/nimporte").status_code == 404


def test_only_the_last_maps_are_kept(fake):
    app = create_app(api=fake, routing=StraightRouting())
    client = app.test_client()
    for _ in range(10):
        client.get("/simulation?instance=A-n32-k5&view=best")
    assert len(app.extensions["sim_cache"]) == 8


def test_results_page_offers_the_simulation(fake):
    client = site(fake)
    html = client.get("/").get_data(as_text=True)
    assert "Simuler sur les vraies routes" in html and "/simulation?" in html and "view=best" in html
    assert "view=mine" not in html  # pas de calcul : rien de « mien » à simuler

    fake.job_state = job_state("done", result=RESULT)
    html = client.get("/?job=j1").get_data(as_text=True)
    assert html.count("Simuler sur les vraies routes") == 2 and "view=mine" in html and "job=j1" in html

    fake.job_state = job_state("running")
    assert "Simuler sur les vraies routes" not in client.get("/?job=j1").get_data(as_text=True)


# ----------------------------------------------------------- vrai OSRM (facultatif)
@pytest.mark.skipif(not os.environ.get("OSRM_LIVE"), reason="appelle le vrai OSRM : OSRM_LIVE=1")
def test_live_osrm_nancy_paris_lyon():
    road = OsrmClient().route([(48.69, 6.18), (48.85, 2.35), (45.76, 4.84)])
    assert 700_000 < road.distance_m < 900_000 and 6 * 3600 < road.duration_s < 12 * 3600
    assert len(road.coords) > 1000 and waypoint_indices(road)[-1] == len(road.coords) - 1
