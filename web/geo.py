"""Placement des coordonnées abstraites d'une instance sur une carte réelle.

Les instances VRPLIB n'ont pas de position géographique : ce sont des points
dans un plan (ex. 100 x 100). On les pose sur la carte avec une simple
homothétie, centrée sur une position choisie. La forme du nuage et les
distances relatives sont conservées, donc la solution a la même allure sur la
carte que dans le plan.
"""

import math
from dataclasses import dataclass

import numpy as np

KM_PER_DEG_LAT = 111.32

# nom -> (latitude, longitude, étendue en km du plus grand côté du nuage)
PRESETS: dict[str, tuple[float, float, float]] = {
    "France entière": (46.6, 2.4, 700.0),
    "Grand Est (Nancy)": (48.69, 6.18, 250.0),
    "Île-de-France": (48.85, 2.35, 90.0),
    "Rhône-Alpes (Lyon)": (45.76, 4.84, 250.0),
    "Sud-Ouest (Toulouse)": (43.6, 1.44, 300.0),
}


@dataclass(frozen=True)
class MapFrame:
    """Résultat du placement : positions géographiques + échelle."""

    lat: np.ndarray
    lon: np.ndarray
    km_per_unit: float  # 1 unité de distance de l'instance = tant de km sur la carte
    center_lat: float
    center_lon: float
    span_km: float


def place_on_map(
    coords: np.ndarray, center_lat: float, center_lon: float, span_km: float
) -> MapFrame:
    """Projette `coords` (n, 2) autour de (center_lat, center_lon).

    Le plus grand côté du rectangle englobant mesure `span_km` kilomètres.
    L'axe y de l'instance pointe vers le nord, l'axe x vers l'est.
    """
    mins, maxs = coords.min(axis=0), coords.max(axis=0)
    extent = float((maxs - mins).max()) or 1.0
    km_per_unit = span_km / extent
    offset_km = (coords - (mins + maxs) / 2) * km_per_unit

    lat = center_lat + offset_km[:, 1] / KM_PER_DEG_LAT
    lon = center_lon + offset_km[:, 0] / (KM_PER_DEG_LAT * math.cos(math.radians(center_lat)))
    return MapFrame(lat, lon, km_per_unit, center_lat, center_lon, span_km)
