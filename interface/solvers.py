"""Contrat entre l'interface et les solveurs.

Brancher le solveur de l'équipe
-------------------------------
Écrire une fonction avec cette signature et l'enregistrer :

    from interface.solvers import register, make_solution

    @register("Recuit simulé")
    def recuit(inst, time_limit, seed, on_progress=None):
        ...
        # à chaque amélioration (optionnel, pour l'affichage en direct) :
        #     on_progress(iteration, best_cost, routes)
        return make_solution(inst, routes, "Recuit simulé", history)

`routes` est une liste de tournées ; chaque tournée est la liste des clients
dans l'ordre de visite, sans le dépôt (sommet 0). Exemple : [[3, 7, 1], [2, 5]].
`history` est une liste de (temps_s, iteration, meilleur_cout) pour la courbe de
convergence (peut être vide).
"""

from dataclasses import dataclass, field
from typing import Callable

from interface.instance import Instance

Routes = list[list[int]]
ProgressCb = Callable[[int, float, Routes], None]
SolverFn = Callable[..., "Solution"]

SOLVERS: dict[str, SolverFn] = {}


@dataclass
class Solution:
    routes: Routes
    cost: float
    solver: str
    elapsed: float = 0.0
    history: list[tuple[float, int, float]] = field(default_factory=list)


def register(name: str) -> Callable[[SolverFn], SolverFn]:
    """Décorateur : rend un solveur disponible dans l'interface."""

    def deco(fn: SolverFn) -> SolverFn:
        SOLVERS[name] = fn
        return fn

    return deco


def route_cost(inst: Instance, route: list[int]) -> float:
    if not route:
        return 0.0
    path = [0, *route, 0]
    return float(inst.dist[path[:-1], path[1:]].sum())


def total_cost(inst: Instance, routes: Routes) -> float:
    return sum(route_cost(inst, r) for r in routes)


def route_load(inst: Instance, route: list[int]) -> int:
    return int(inst.demand[route].sum()) if route else 0


def check_solution(inst: Instance, routes: Routes) -> list[str]:
    """Liste des violations (vide = solution valide) : clients visités une fois, capacité."""
    errors = []
    seen = [c for r in routes for c in r]
    missing = set(range(1, inst.n)) - set(seen)
    dupes = {c for c in seen if seen.count(c) > 1}
    if 0 in seen:
        errors.append("Le dépôt (0) ne doit pas apparaître dans une tournée")
    if missing:
        errors.append(f"Clients non visités : {sorted(missing)}")
    if dupes:
        errors.append(f"Clients visités plusieurs fois : {sorted(dupes)}")
    if inst.n_vehicles and len(routes) > inst.n_vehicles:
        errors.append(f"{len(routes)} camions utilisés pour une flotte de {inst.n_vehicles}")
    for i, r in enumerate(routes, 1):
        if route_load(inst, r) > inst.capacity:
            errors.append(f"Camion {i} : charge {route_load(inst, r)} > capacité {inst.capacity}")
    return errors


def make_solution(
    inst: Instance, routes: Routes, solver: str, history=None, elapsed: float = 0.0
) -> Solution:
    routes = [list(r) for r in routes if r]
    return Solution(routes, total_cost(inst, routes), solver, elapsed, list(history or []))
