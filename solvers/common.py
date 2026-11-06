"""Solutions, coûts et validation : ce que tous les solveurs et le serveur ont en commun."""

from dataclasses import dataclass, field

from solvers.instance import Instance

Routes = list[list[int]]  # une tournée = clients dans l'ordre de visite, sans le dépôt (sommet 0)


@dataclass
class Solution:
    routes: Routes
    cost: float
    elapsed: float = 0.0
    history: list[tuple[float, int, float]] = field(default_factory=list)  # (temps_s, itération, coût)


def route_cost(inst: Instance, route: list[int]) -> float:
    if not route:
        return 0.0
    path = [0, *route, 0]
    return float(inst.dist[path[:-1], path[1:]].sum())


def total_cost(inst: Instance, routes: Routes) -> float:
    return sum(route_cost(inst, r) for r in routes)


def route_load(inst: Instance, route: list[int]) -> int:
    return int(inst.demand[route].sum()) if route else 0


def make_solution(inst: Instance, routes: Routes, history=None, elapsed: float = 0.0) -> Solution:
    routes = [list(r) for r in routes if r]
    return Solution(routes, total_cost(inst, routes), elapsed, list(history or []))


def check_solution(inst: Instance, routes: Routes) -> list[str]:
    """Violations trouvées (liste vide = solution valide)."""
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


def evaluate(inst: Instance, routes: Routes, elapsed: float = 0.0) -> dict:
    """Le résultat final d'un calcul, au format de l'API (voir docs/api.md)."""
    routes = [list(r) for r in routes if r]
    cost = total_cost(inst, routes)
    errors = check_solution(inst, routes)
    return {
        "cost": cost,
        "gap": None if not inst.bks else round(100 * (cost - inst.bks) / inst.bks, 2),
        "valid": not errors,
        "errors": errors,
        "n_routes": len(routes),
        "elapsed": round(elapsed, 2),
        "routes": routes,
        "per_route": [
            {"n_clients": len(r), "load": route_load(inst, r), "distance": route_cost(inst, r)}
            for r in routes
        ],
    }
