"""Chargement d'une instance VRPLIB (.vrp) dans une structure simple."""

import re
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import vrplib


@dataclass(frozen=True)
class Instance:
    """Instance CVRP. Le sommet 0 est le dépôt, les clients sont 1..n-1."""

    name: str
    capacity: int
    coords: np.ndarray  # (n, 2) coordonnées brutes du fichier
    demand: np.ndarray  # (n,) demande de chaque sommet (0 pour le dépôt)
    dist: np.ndarray  # (n, n) distances, arrondies comme TSPLIB si EUC_2D
    n_vehicles: int | None  # nombre de camions annoncé (nom ou commentaire)
    bks: float | None  # meilleure solution connue (commentaire du fichier)
    comment: str = ""
    time_windows: np.ndarray | None = None  # (n, 2) pour CVRPTW, sinon None
    best_routes: list[list[int]] | None = None  # tournées du fichier .sol voisin, si présent

    @property
    def n(self) -> int:
        return len(self.demand)

    @property
    def min_vehicles(self) -> int:
        """Borne inférieure sur le nombre de camions : ceil(demande totale / capacité)."""
        return int(np.ceil(self.demand.sum() / self.capacity))


def _find_int(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def _build(raw: dict) -> Instance:
    name = str(raw.get("name", "instance"))
    comment = str(raw.get("comment", ""))
    coords = np.asarray(raw["node_coord"], dtype=float)

    depot = int(np.asarray(raw["depot"]).ravel()[0])
    if depot != 0:
        raise ValueError(f"Dépôt attendu au sommet 0 (trouvé : {depot})")

    # Les benchmarks (Augerat, X, ...) donnent leur optimum avec des distances
    # arrondies à l'entier le plus proche (convention TSPLIB EUC_2D) : on fait
    # pareil pour que le gap soit comparable à la valeur publiée.
    dist = np.asarray(raw["edge_weight"], dtype=float)
    if str(raw.get("edge_weight_type", "")).strip() == "EUC_2D":
        dist = np.rint(dist)

    tw = raw.get("time_window")
    return Instance(
        name=name,
        capacity=int(raw["capacity"]),
        coords=coords,
        demand=np.asarray(raw["demand"], dtype=int),
        dist=dist,
        n_vehicles=_find_int(r"-k(\d+)", name) or _find_int(r"trucks\s*:\s*(\d+)", comment),
        bks=_find_int(r"(?:optimal|best)\s+value\s*:\s*(\d+)", comment),
        comment=comment,
        time_windows=None if tw is None else np.asarray(tw, dtype=float),
    )


def load_instance(path: str | Path) -> Instance:
    """Charge un fichier .vrp depuis le disque.

    Si un fichier .sol du même nom existe à côté, on en lit les tournées (meilleure
    solution connue) et, si le commentaire du fichier ne donne pas la valeur
    optimale, son coût (ligne « Cost N »).
    """
    path = Path(path)
    inst = _build(vrplib.read_instance(str(path)))
    sol = path.with_suffix(".sol")
    if sol.is_file():
        text = sol.read_text()
        routes = [
            [int(c) for c in m.group(1).split()]
            for m in re.finditer(r"^Route\s*#\d+\s*:\s*(.*)$", text, flags=re.MULTILINE)
        ]
        cost = re.search(r"^Cost\s+([\d.]+)", text, flags=re.MULTILINE)
        inst = replace(
            inst,
            best_routes=[r for r in routes if r] or None,
            bks=inst.bks if inst.bks is not None or not cost else float(cost.group(1)),
        )
    return inst


def load_instance_from_bytes(data: bytes, filename: str = "instance.vrp") -> Instance:
    """Charge une instance envoyée par l'interface (fichier téléversé)."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / Path(filename).name
        p.write_bytes(data)
        return load_instance(p)
