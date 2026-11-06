"""Solveurs du livrable 2 de l'équipe (notebook), branchés dans l'interface.

Port fidèle des cellules du notebook `livrable_2_algo_modelisation_groupe_5_*.ipynb` :
  - greedy_initial_solution   (cellule 4)
  - is_possible               (cellule 3)
  - relocate                  (cellule 6)
  - hill_climbing             (cellule 8)
  - simulated_annealing       (cellule 9, t=70 et alpha=0.995 par défaut)

Écarts avec le notebook, tous nécessaires à l'interface :
  - `instance` est un `Instance` de l'interface, donc les distances sont arrondies à
    l'entier le plus proche (convention TSPLIB), comme les optimums des fichiers .sol ;
    le notebook lit `edge_weight` de vrplib, non arrondi.
  - la boucle `for _ in range(iterations)` devient « tant que le temps limite n'est pas
    atteint » : l'interface fixe un temps de calcul, pas un nombre d'itérations.
  - le générateur aléatoire est `random.Random(seed)` au lieu du `random` global.
  - le coût courant est gardé en mémoire au lieu d'être recalculé à chaque itération
    (même résultat, plus rapide).
  - dans le recuit, la probabilité d'acceptation vaut 0 quand la température tombe à 0
    (sur un long calcul `t` finit par s'annuler et `delta / t` planterait).
"""

import copy
import random
import time
from math import exp

from interface.instance import Instance
from interface.solvers import Routes, make_solution, register, total_cost


def vehicle_load(route, demand):
    total = 0
    for client in route:
        total += demand[client]
    return total


def is_possible(routes, inst: Instance, k):
    if len(routes) > k:
        return False
    for route in routes:
        if vehicle_load(route, inst.demand) > inst.capacity:
            return False
    clients = []
    for route in routes:
        clients += route
    if sorted(clients) != list(range(1, inst.n)):
        return False
    return True


def greedy_initial_solution(inst: Instance) -> Routes:
    routes = []
    current_route = []
    current_load = 0

    for client in range(1, inst.n):
        if current_load + inst.demand[client] > inst.capacity:
            routes.append(current_route)  # on ferme le camion
            current_route = []  # nouveau camion vide
            current_load = 0
        current_route.append(client)
        current_load += inst.demand[client]

    routes.append(current_route)  # ne pas oublier le dernier camion
    return routes


def relocate(routes, rng: random.Random):
    nouvelles_routes = copy.deepcopy(routes)

    # on choisit un camion au hasard, qui n'est pas vide
    camions_non_vides = []
    for i in range(len(nouvelles_routes)):
        if len(nouvelles_routes[i]) > 0:
            camions_non_vides.append(i)
    camion_depart = rng.choice(camions_non_vides)

    # on choisit un client dans ce camion et on l'enlève
    position = rng.randrange(len(nouvelles_routes[camion_depart]))
    client = nouvelles_routes[camion_depart].pop(position)

    # on choisit un camion d'arrivée et une place dedans
    camion_arrivee = rng.randrange(len(nouvelles_routes))
    nouvelle_place = rng.randint(0, len(nouvelles_routes[camion_arrivee]))
    nouvelles_routes[camion_arrivee].insert(nouvelle_place, client)

    return nouvelles_routes


def _fleet(inst: Instance, start: Routes) -> int:
    """k du notebook : nombre de camions annoncé par l'instance (sinon, celui de la solution de départ)."""
    return inst.n_vehicles or len(start)


def _clean(routes: Routes) -> Routes:
    return [list(r) for r in routes if r]


@register("Hill climbing (notebook)")
def hill_climbing(inst: Instance, time_limit: float = 10.0, seed: int = 0, on_progress=None):
    rng = random.Random(seed)
    t0 = time.perf_counter()
    deadline = t0 + time_limit

    best_routes = greedy_initial_solution(inst)
    k = _fleet(inst, best_routes)
    best_cost = total_cost(inst, best_routes)
    history = [(0.0, 0, best_cost)]
    if on_progress:
        on_progress(0, best_cost, _clean(best_routes))

    it = 0
    while time.perf_counter() < deadline:
        it += 1
        voisin = relocate(best_routes, rng)
        if is_possible(voisin, inst, k):
            cost = total_cost(inst, voisin)
            if cost <= best_cost:
                improved = cost < best_cost
                best_routes, best_cost = voisin, cost
                if improved:
                    history.append((time.perf_counter() - t0, it, best_cost))
                    if on_progress:
                        on_progress(it, best_cost, _clean(best_routes))

    history.append((time.perf_counter() - t0, it, best_cost))
    return make_solution(inst, best_routes, "Hill climbing (notebook)", history,
                         time.perf_counter() - t0)


def get_proba(delta, t):
    if t <= 0:
        return 0.0
    return exp(-(delta / t))


@register("Recuit simulé (notebook)")
def simulated_annealing(inst: Instance, time_limit: float = 10.0, seed: int = 0,
                        on_progress=None, t=70, alpha=0.995):
    rng = random.Random(seed)
    t0 = time.perf_counter()
    deadline = t0 + time_limit

    current = greedy_initial_solution(inst)
    k = _fleet(inst, current)
    current_cost = total_cost(inst, current)
    best = copy.deepcopy(current)
    best_cost = current_cost
    history = [(0.0, 0, best_cost)]
    if on_progress:
        on_progress(0, best_cost, _clean(best))

    it = 0
    while time.perf_counter() < deadline:
        it += 1
        voisin = relocate(copy.deepcopy(current), rng)
        if is_possible(voisin, inst, k):
            new_cost = total_cost(inst, voisin)
            delta = new_cost - current_cost
            if delta <= 0 or rng.random() < get_proba(delta, t):
                current, current_cost = voisin, new_cost
                if current_cost < best_cost:
                    best, best_cost = copy.deepcopy(current), current_cost
                    history.append((time.perf_counter() - t0, it, best_cost))
                    if on_progress:
                        on_progress(it, best_cost, _clean(best))
        t *= alpha

    history.append((time.perf_counter() - t0, it, best_cost))
    return make_solution(inst, best, "Recuit simulé (notebook)", history, time.perf_counter() - t0)
