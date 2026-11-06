"""Simulation d'une solution sur le vrai réseau routier : les camions roulent de point en point.

On ne rejoue pas exactement ce que la métaheuristique a calculé (ses distances sont celles du plan
de l'instance, pas celles des routes) : on prend l'ORDRE de ses tournées et on le fait rouler sur de
vraies routes, avec les vraies durées de trajet et un temps de livraison à chaque client.
"""

import datetime as dt
import math
from urllib.parse import quote
from dataclasses import dataclass, field

import folium
import numpy as np
from folium.plugins import TimestampedGeoJson

from web.figures import add_basemaps, route_color
from web.geo import MapFrame
from web.routing import RoadRoute, RoutingError, RoutingUnavailable

START = dt.datetime(2026, 1, 5, 8, 0, 0)  # un jour quelconque : les camions partent tous du dépôt à 8 h
FALLBACK_KMH = 70.0  # vitesse d'un trajet à vol d'oiseau (si OSRM ne trouve pas d'itinéraire)
SAMPLE_M = 1000  # un point de la trace tous les ~1 km : assez fin pour l'animation, léger pour la page


def _haversine_m(lon1, lat1, lon2, lat2):
    """Distance à vol d'oiseau en mètres (accepte des tableaux numpy)."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * np.arcsin(np.sqrt(a))


def straight_route(points: list[tuple[float, float]]) -> RoadRoute:
    """Repli : lignes droites entre les points, à vitesse constante (points = (lat, lon))."""
    coords = [(lon, lat) for lat, lon in points]
    legs = []
    for (lo1, la1), (lo2, la2) in zip(coords, coords[1:]):
        d = float(_haversine_m(lo1, la1, lo2, la2))
        legs.append({"distance_m": d, "duration_s": d / (FALLBACK_KMH / 3.6)})
    return RoadRoute(coords=coords, waypoints=list(coords), legs=legs)


def waypoint_indices(road: RoadRoute) -> list[int]:
    """Position de chaque point de passage (dépôt, clients, dépôt) dans le tracé, dans l'ordre."""
    xy = np.array(road.coords)
    out, idx = [0], 0
    for w in road.waypoints[1:-1]:
        d = _haversine_m(xy[idx:, 0], xy[idx:, 1], w[0], w[1])
        idx += int(np.argmin(d))
        out.append(idx)
    out.append(len(xy) - 1)  # le retour au dépôt est la fin du tracé
    return out


@dataclass
class Timeline:
    points: list[tuple[float, float, float]]  # (secondes depuis le départ, longitude, latitude)
    arrivals: list[float]  # heure d'arrivée à chaque point de passage (0 pour le départ)
    departures: list[float]  # heure de départ de chaque point de passage
    distance_m: float
    drive_s: float  # temps de conduite
    total_s: float  # temps de conduite + livraisons


def build_timeline(road: RoadRoute, service_s: float, step_m: float = SAMPLE_M) -> Timeline:
    """Horaires le long du tracé : les durées de chaque étape viennent d'OSRM, réparties sur le
    tracé au prorata de la distance, avec `service_s` secondes d'arrêt à chaque client."""
    xy = np.array(road.coords)
    seg = _haversine_m(xy[:-1, 0], xy[:-1, 1], xy[1:, 0], xy[1:, 1])
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    wp = waypoint_indices(road)

    points, arrivals, departures = [], [0.0], [0.0]
    t = 0.0
    for i, leg in enumerate(road.legs):
        a, b = wp[i], wp[i + 1]
        span = cum[b] - cum[a]
        last_kept = cum[a]
        for j in range(a, b + 1):
            if j in (a, b) or cum[j] - last_kept >= step_m:
                frac = (cum[j] - cum[a]) / span if span > 0 else 1.0
                points.append((t + leg["duration_s"] * frac, float(xy[j, 0]), float(xy[j, 1])))
                last_kept = cum[j]
        t += leg["duration_s"]
        arrivals.append(t)
        if i + 1 < len(road.legs):  # un client : le camion y reste le temps de livrer
            t += service_s
            points.append((t, float(xy[b, 0]), float(xy[b, 1])))
        departures.append(t)
    # le point d'arrivée de chaque étape est répété au départ de la suivante : on retire les doublons
    dedup = [points[0]]
    for p in points[1:]:
        if p != dedup[-1]:
            dedup.append(p)
    drive = sum(leg["duration_s"] for leg in road.legs)
    return Timeline(dedup, arrivals, departures, float(road.distance_m), drive, t)


DAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def truck_icon(color: str) -> dict:
    """Icône de camion (SVG) de la couleur de la tournée, au format `L.icon` de Leaflet.

    Vu de face : un camion de face se lit de la même façon quel que soit le sens de la route."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="42" height="42" viewBox="0 0 28 28">'
        f'<rect x="3.5" y="1.5" width="21" height="12" rx="2" fill="{color}" stroke="#fff" stroke-width="1.6"/>'  # la caisse
        f'<rect x="5.5" y="10.5" width="17" height="11.5" rx="2.5" fill="{color}" stroke="#fff" stroke-width="1.6"/>'  # la cabine
        '<rect x="8" y="12.5" width="12" height="5" rx="1" fill="#dff1ff" stroke="#fff" stroke-width=".8"/>'  # le pare-brise
        '<circle cx="9" cy="19.3" r="1.5" fill="#ffe27a"/><circle cx="19" cy="19.3" r="1.5" fill="#ffe27a"/>'  # les phares
        '<rect x="5.5" y="22" width="17" height="2.6" rx="1" fill="#333" stroke="#fff" stroke-width=".8"/>'  # le pare-chocs
        '<rect x="2.2" y="17.5" width="3.4" height="7" rx="1" fill="#222" stroke="#fff" stroke-width=".8"/>'  # les roues
        '<rect x="22.4" y="17.5" width="3.4" height="7" rx="1" fill="#222" stroke="#fff" stroke-width=".8"/>'
        "</svg>"
    )
    return {"iconUrl": "data:image/svg+xml;charset=utf-8," + quote(svg), "iconSize": [42, 42],
            "iconAnchor": [21, 21], "popupAnchor": [0, -21]}


def clock(seconds: float) -> str:
    """Heure d'horloge ; le jour est ajouté quand on a passé minuit (« mar. 10:33 »)."""
    t = START + dt.timedelta(seconds=seconds)
    return t.strftime("%H:%M") if t.date() == START.date() else f"{DAYS[t.weekday()]} {t:%H:%M}"


def _iso(seconds: float) -> str:
    return (START + dt.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Simulation:
    html: str
    trucks: list[dict]
    warnings: list[str] = field(default_factory=list)


def build_simulation(frame: MapFrame, routes: list[list[int]], routing, service_s: float = 600) -> Simulation:
    """Calcule les itinéraires routiers de chaque camion et fabrique la carte animée.

    `routing.route(points)` : voir `web.routing.OsrmClient`. Une `RoutingUnavailable` (service
    éteint) remonte à l'appelant ; un trajet introuvable passe en ligne droite, avec un avertissement.
    """
    def latlon(i):
        return float(frame.lat[i]), float(frame.lon[i])

    trucks, warnings, features, roads = [], [], [], []
    m = folium.Map(location=[frame.center_lat, frame.center_lon], zoom_start=6, tiles=None,
                   width="100%", height="100%", control_scale=True)
    add_basemaps(m)

    for k, route in enumerate(routes):
        color = route_color(k)
        points = [latlon(0), *[latlon(c) for c in route], latlon(0)]
        straight = False
        try:
            road = routing.route(points)
        except RoutingUnavailable:
            raise
        except RoutingError as exc:
            road, straight = straight_route(points), True
            warnings.append(f"Camion {k + 1} : {exc}. Trajet tracé à vol d'oiseau.")
        tl = build_timeline(road, service_s)
        roads.append(road)

        # l'itinéraire complet, en filigrane, avec les clients (à leur position sur la route)
        group = folium.FeatureGroup(name=f"Camion {k + 1}" + (" (vol d'oiseau)" if straight else ""))
        folium.PolyLine([(lat, lon) for _, lon, lat in tl.points], color=color, weight=3, opacity=0.35,
                        dash_array="6 6" if straight else None).add_to(group)
        for step, client in enumerate(route, 1):
            lon, lat = road.waypoints[step]
            folium.CircleMarker(
                (lat, lon), radius=5, color="#ffffff", weight=1.5, fill=True, fill_color=color, fill_opacity=1,
                tooltip=f"Client {client} · camion {k + 1}, étape {step}<br>arrivée {clock(tl.arrivals[step])}"
                        f" · repart {clock(tl.departures[step])}").add_to(group)
        group.add_to(m)

        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[lon, lat] for _, lon, lat in tl.points]},
            "properties": {
                "times": [_iso(t) for t, _, _ in tl.points],
                "style": {"color": color, "weight": 5, "opacity": 0.95},
                "icon": "marker",  # un camion, pas un point
                "iconstyle": truck_icon(color),
                "popup": f"Camion {k + 1}",
            },
        })
        trucks.append({
            "n": k + 1, "color": color, "clients": len(route), "road_km": tl.distance_m / 1000,
            "drive_s": tl.drive_s, "total_s": tl.total_s, "return": clock(tl.total_s), "straight": straight,
        })

    depot_lon, depot_lat = roads[0].waypoints[0] if roads else (frame.lon[0], frame.lat[0])
    folium.Marker(
        (depot_lat, depot_lon), tooltip="Dépôt (départ à 8 h)",
        icon=folium.DivIcon(
            icon_size=(60, 26), icon_anchor=(30, 13),
            html='<div style="background:#111;color:#fff;font:600 12px sans-serif;text-align:center;'
                 'line-height:22px;border:2px solid #fff;border-radius:13px;'
                 'box-shadow:0 1px 6px rgba(0,0,0,.4)">Dépôt</div>')).add_to(m)

    if features:
        longest_min = max(t["total_s"] for t in trucks) / 60
        step_min = max(1, math.ceil(longest_min / 240))  # ~240 images pour la journée la plus longue
        TimestampedGeoJson(
            {"type": "FeatureCollection", "features": features},
            period=f"PT{step_min}M", add_last_point=True, auto_play=False, loop=False,
            max_speed=20, loop_button=True, date_options="ddd HH:mm", time_slider_drag_update=True,
            transition_time=120,
        ).add_to(m)
        lons = [c[0] for r in roads for c in r.coords]
        lats = [c[1] for r in roads for c in r.coords]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(30, 30))
    folium.LayerControl(collapsed=True, position="topright").add_to(m)
    return Simulation(m.get_root().render(), trucks, warnings)
