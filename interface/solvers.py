"""Contrat entre l'interface et les solveurs, + un solveur provisoire.

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

import random
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

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
    for i, r in enumerate(routes, 1):
        if route_load(inst, r) > inst.capacity:
            errors.append(f"Camion {i} : charge {route_load(inst, r)} > capacité {inst.capacity}")
    return errors


def make_solution(
    inst: Instance, routes: Routes, solver: str, history=None, elapsed: float = 0.0
) -> Solution:
    routes = [list(r) for r in routes if r]
    return Solution(routes, total_cost(inst, routes), solver, elapsed, list(history or []))


# --------------------------------------------------------------------------- #
# Solveur provisoire : Clarke-Wright + recherche locale itérée.
# Sert uniquement à tester l'interface tant que le solveur de l'équipe n'est pas
# branché. Il n'a pas vocation à être évalué ni comparé dans l'étude.
# --------------------------------------------------------------------------- #


def _savings(inst: Instance) -> Routes:
    d, q, cap = inst.dist, inst.demand, inst.capacity
    routes = {i: [i] for i in range(1, inst.n)}
    owner = {i: i for i in routes}
    load = {i: int(q[i]) for i in routes}
    pairs = sorted(
        ((d[0, i] + d[0, j] - d[i, j], i, j) for i in routes for j in routes if i < j),
        reverse=True,
    )
    for gain, i, j in pairs:
        if gain <= 0:
            break
        ri, rj = owner[i], owner[j]
        if ri == rj or load[ri] + load[rj] > cap:
            continue
        a, b = routes[ri], routes[rj]
        if a[-1] == i and b[0] == j:
            merged = a + b
        elif a[0] == i and b[-1] == j:
            merged = b + a
        elif a[0] == i and b[0] == j:
            merged = a[::-1] + b
        elif a[-1] == i and b[-1] == j:
            merged = a + b[::-1]
        else:
            continue
        routes[ri], load[ri] = merged, load[ri] + load[rj]
        for c in b:
            owner[c] = ri
        del routes[rj], load[rj]
    return list(routes.values())


def _local_search(inst: Instance, routes: Routes, deadline: float) -> None:
    """2-opt intra-tournée, relocate et swap inter-tournées, jusqu'à l'optimum local."""
    d, q, cap = inst.dist, inst.demand, inst.capacity
    eps = 1e-9
    improved = True
    while improved and time.perf_counter() < deadline:
        improved = False
        # 2-opt
        for r in routes:
            p = [0, *r, 0]
            for i in range(1, len(p) - 2):
                for j in range(i + 1, len(p) - 1):
                    delta = d[p[i - 1], p[j]] + d[p[i], p[j + 1]] - d[p[i - 1], p[i]] - d[p[j], p[j + 1]]
                    if delta < -eps:
                        p[i : j + 1] = p[i : j + 1][::-1]
                        r[:] = p[1:-1]
                        improved = True
        loads = [route_load(inst, r) for r in routes]
        # relocate : déplacer un client vers une autre tournée
        for a, ra in enumerate(routes):
            for i, c in enumerate(list(ra)):
                if c not in ra:
                    continue
                i = ra.index(c)
                prev, nxt = (ra[i - 1] if i else 0), (ra[i + 1] if i + 1 < len(ra) else 0)
                gain = d[prev, c] + d[c, nxt] - d[prev, nxt]
                for b, rb in enumerate(routes):
                    if a == b or loads[b] + q[c] > cap:
                        continue
                    for k in range(len(rb) + 1):
                        x, y = (rb[k - 1] if k else 0), (rb[k] if k < len(rb) else 0)
                        if d[x, c] + d[c, y] - d[x, y] - gain < -eps:
                            ra.pop(i)
                            rb.insert(k, c)
                            loads[a] -= q[c]
                            loads[b] += q[c]
                            improved = True
                            break
                    else:
                        continue
                    break
        # swap : échanger deux clients de tournées différentes
        for a in range(len(routes)):
            for b in range(a + 1, len(routes)):
                ra, rb = routes[a], routes[b]
                for i in range(len(ra)):
                    for j in range(len(rb)):
                        c, e = ra[i], rb[j]
                        if loads[a] - q[c] + q[e] > cap or loads[b] - q[e] + q[c] > cap:
                            continue
                        pa, na = (ra[i - 1] if i else 0), (ra[i + 1] if i + 1 < len(ra) else 0)
                        pb, nb = (rb[j - 1] if j else 0), (rb[j + 1] if j + 1 < len(rb) else 0)
                        delta = (
                            d[pa, e] + d[e, na] - d[pa, c] - d[c, na]
                            + d[pb, c] + d[c, nb] - d[pb, e] - d[e, nb]
                        )
                        if delta < -eps:
                            ra[i], rb[j] = e, c
                            loads[a] += q[e] - q[c]
                            loads[b] += q[c] - q[e]
                            improved = True
        routes[:] = [r for r in routes if r]


def _shake(inst: Instance, routes: Routes, rng: random.Random, k: int = 3) -> None:
    """Retire k clients au hasard et les réinsère à leur meilleure place faisable."""
    d, q, cap = inst.dist, inst.demand, inst.capacity
    clients = [c for r in routes for c in r]
    removed = rng.sample(clients, min(k, len(clients)))
    for r in routes:
        r[:] = [c for c in r if c not in removed]
    routes[:] = [r for r in routes if r]
    for c in removed:
        best, where = None, None
        for r in routes:
            if route_load(inst, r) + q[c] > cap:
                continue
            for k_ in range(len(r) + 1):
                x, y = (r[k_ - 1] if k_ else 0), (r[k_] if k_ < len(r) else 0)
                cost = d[x, c] + d[c, y] - d[x, y]
                if best is None or cost < best:
                    best, where = cost, (r, k_)
        if where is None:
            routes.append([c])
        else:
            where[0].insert(where[1], c)


@register("Baseline provisoire (Clarke-Wright + ILS)")
def baseline(inst: Instance, time_limit: float = 5.0, seed: int = 0, on_progress=None) -> Solution:
    rng = random.Random(seed)
    t0 = time.perf_counter()
    deadline = t0 + time_limit

    best = _savings(inst)
    _local_search(inst, best, deadline)
    best_cost = total_cost(inst, best)
    history = [(time.perf_counter() - t0, 0, best_cost)]
    if on_progress:
        on_progress(0, best_cost, [list(r) for r in best])

    it = 0
    while time.perf_counter() < deadline:
        it += 1
        cand = [list(r) for r in best]
        _shake(inst, cand, rng, k=rng.randint(2, 5))
        _local_search(inst, cand, deadline)
        cost = total_cost(inst, cand)
        if cost < best_cost - 1e-9:
            best, best_cost = cand, cost
            history.append((time.perf_counter() - t0, it, best_cost))
            if on_progress:
                on_progress(it, best_cost, [list(r) for r in best])

    history.append((time.perf_counter() - t0, it, best_cost))
    return make_solution(inst, best, "Baseline provisoire", history, time.perf_counter() - t0)
