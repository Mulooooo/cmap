"""Lecture d'une instance VRPLIB (.vrp) dans une structure simple."""

import re
import tempfile
from dataclasses import dataclass
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
    edge_weight_type: str
    n_vehicles: int | None  # nombre de camions k annoncé (nom ou commentaire)
    bks: float | None  # meilleure solution connue (coût)
    best_routes: list[list[int]] | None  # tournées du fichier .sol voisin, si présent

    @property
    def n(self) -> int:
        return len(self.demand)


def _find_int(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def _build(raw: dict) -> Instance:
    for key in ("capacity", "demand", "node_coord", "depot", "edge_weight"):
        if key not in raw:
            raise ValueError(f"champ « {key} » absent : ce n'est pas un CVRP avec coordonnées")
    if int(np.asarray(raw["depot"]).ravel()[0]) != 0:
        raise ValueError("le dépôt doit être le premier sommet")

    # Les optimums publiés (Augerat, X, ...) sont calculés avec des distances arrondies à l'entier
    # le plus proche (convention TSPLIB EUC_2D) : on fait pareil pour que le gap soit comparable.
    dist = np.asarray(raw["edge_weight"], dtype=float)
    ewt = str(raw.get("edge_weight_type", "")).strip()
    if ewt == "EUC_2D":
        dist = np.rint(dist)

    name = str(raw.get("name", "instance"))
    comment = str(raw.get("comment", ""))
    return Instance(
        name=name,
        capacity=int(raw["capacity"]),
        coords=np.asarray(raw["node_coord"], dtype=float),
        demand=np.asarray(raw["demand"], dtype=int),
        dist=dist,
        edge_weight_type=ewt,
        n_vehicles=_find_int(r"-k(\d+)", name) or _find_int(r"trucks\s*:\s*(\d+)", comment),
        bks=_find_int(r"(?:optimal|best)\s+value\s*:\s*(\d+)", comment),
        best_routes=None,
    )


def load_instance(path: str | Path) -> Instance:
    """Charge un fichier .vrp. Un fichier .sol du même nom, à côté, donne la meilleure solution
    connue (tournées, et coût si le commentaire du .vrp ne le donne pas)."""
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
        inst = Instance(**{
            **inst.__dict__,
            "best_routes": [r for r in routes if r] or None,
            "bks": inst.bks if inst.bks is not None or not cost else float(cost.group(1)),
        })
    return inst


def load_instance_from_bytes(data: bytes, filename: str = "instance.vrp") -> Instance:
    """Charge une instance envoyée au serveur (fichier téléversé)."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / Path(filename).name
        p.write_bytes(data)
        return load_instance(p)
