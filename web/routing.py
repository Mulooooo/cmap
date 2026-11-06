"""Itinéraires sur le vrai réseau routier, avec OSRM (https://project-osrm.org).

Pour la simulation : un camion va du dépôt à chaque client dans l'ordre de la solution, puis
revient. On demande à OSRM l'itinéraire qui passe par tous ces points dans cet ordre : il renvoie
le tracé exact sur les routes, la distance et la durée de chaque étape.

Le serveur public (router.project-osrm.org) est un service de démonstration : usage léger, une
requête par seconde au plus. On espace donc les appels et on garde les réponses en mémoire.
Pour un usage intensif, `OSRM_URL` peut pointer vers un OSRM installé sur la machine.
"""

import threading
import time
from dataclasses import dataclass

import requests

USER_AGENT = "cmap-cesi-projet/0.1 (projet étudiant)"


class RoutingError(Exception):
    """OSRM a répondu, mais n'a pas trouvé d'itinéraire (point hors réseau routier, îles...)."""


class RoutingUnavailable(RoutingError):
    """OSRM ne répond pas (pas de connexion, trop lent, erreur du service)."""


@dataclass
class RoadRoute:
    coords: list[tuple[float, float]]  # tracé sur les routes, (longitude, latitude)
    waypoints: list[tuple[float, float]]  # points demandés, ramenés sur la route la plus proche
    legs: list[dict]  # une étape par paire de points : {"distance_m": ..., "duration_s": ...}

    @property
    def distance_m(self) -> float:
        return sum(leg["distance_m"] for leg in self.legs)

    @property
    def duration_s(self) -> float:
        return sum(leg["duration_s"] for leg in self.legs)


class OsrmClient:
    def __init__(self, base_url: str = "https://router.project-osrm.org", timeout: float = 25.0,
                 min_interval: float = 1.1, session=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.min_interval = min_interval  # secondes entre deux appels (politique du serveur public)
        self.session = session or requests
        self._cache: dict[tuple, RoadRoute] = {}
        self._lock = threading.Lock()
        self._last_call = 0.0

    def route(self, points: list[tuple[float, float]]) -> RoadRoute:
        """Itinéraire passant par `points` (latitude, longitude) dans cet ordre."""
        key = tuple((round(lat, 6), round(lon, 6)) for lat, lon in points)
        with self._lock:  # un seul appel à la fois : le serveur public limite le débit
            if key in self._cache:
                return self._cache[key]
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            try:
                road = self._fetch(points)
            finally:
                self._last_call = time.monotonic()
            self._cache[key] = road
            return road

    def _fetch(self, points) -> RoadRoute:
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
        try:
            r = self.session.get(
                f"{self.base_url}/route/v1/driving/{coords}",
                params={"overview": "full", "geometries": "geojson", "steps": "false"},
                headers={"User-Agent": USER_AGENT}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise RoutingUnavailable("Le service d'itinéraires routiers (OSRM) ne répond pas") from exc
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code >= 500 or r.status_code == 429:
            raise RoutingUnavailable(f"Le service d'itinéraires est indisponible (HTTP {r.status_code})")
        if data.get("code") != "Ok" or not data.get("routes"):
            raise RoutingError(data.get("message") or f"Aucun itinéraire trouvé ({data.get('code', r.status_code)})")
        best = data["routes"][0]
        return RoadRoute(
            coords=[(lon, lat) for lon, lat in best["geometry"]["coordinates"]],
            waypoints=[(w["location"][0], w["location"][1]) for w in data["waypoints"]],
            legs=[{"distance_m": leg["distance"], "duration_s": leg["duration"]} for leg in best["legs"]],
        )
