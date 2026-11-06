"""Génère la page HTML d'une instance : carte folium + tableaux + courbe de convergence.

Deux usages :
  - fichier statique et autonome (styles et carte inclus), ouvert dans le navigateur :
    `python -m interface instance.vrp`, ou depuis un notebook avec `build_page` / `write_page` ;
  - page servie par `interface/server.py`, avec un panneau de commande (instance, solveur,
    « Calculer ») : on passe alors `controls`.

Aucun JavaScript n'est écrit à la main : seuls les scripts de folium/Leaflet font marcher la
carte ; les onglets « Ma solution / Meilleure solution connue » sont en CSS pur.

Depuis un notebook :

    from interface.instance import load_instance
    from interface.page import build_page, write_page
    inst = load_instance("instances/A/A-n32-k5.vrp")
    write_page("sortie/A-n32-k5.html", build_page(inst, mine=ma_solution))
"""

import datetime as dt
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from interface import solvers
from interface.figures import MapLayer, build_map, convergence_svg, fr, route_color
from interface.geo import PRESETS, place_on_map
from interface.instance import Instance

TEMPLATES = Path(__file__).resolve().parent / "templates"
_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
_env.filters["fr"] = fr


def solution_view(inst: Instance, sol: solvers.Solution, km_per_unit: float) -> dict:
    """Les chiffres et lignes de tableau d'une solution, prêts pour le gabarit."""
    errors = solvers.check_solution(inst, sol.routes)
    return {
        "solver": sol.solver,
        "cost": sol.cost,
        "km": round(sol.cost * km_per_unit),
        "n_routes": len(sol.routes),
        "gap": None if not inst.bks else 100 * (sol.cost - inst.bks) / inst.bks,
        "elapsed": sol.elapsed,
        "valid": not errors,
        "errors": errors,
        "rows": [
            {
                "n": i + 1,
                "color": route_color(i),
                "path": " → ".join(["D", *map(str, r), "D"]),
                "clients": len(r),
                "load": solvers.route_load(inst, r),
                "pct": min(100, round(100 * solvers.route_load(inst, r) / inst.capacity)),
                "dist": solvers.route_cost(inst, r),
                "km": round(solvers.route_cost(inst, r) * km_per_unit),
            }
            for i, r in enumerate(sol.routes)
        ],
        "chart": convergence_svg([(h[0], h[2]) for h in sol.history], inst.bks),
    }


def build_page(
    inst: Instance | None,
    mine: solvers.Solution | None = None,
    zone: str = "France entière",
    span: float | None = None,
    settings: dict[str, str] | None = None,
    controls: dict | None = None,
    running: bool = False,
) -> str:
    """Page HTML de l'instance.

    - `mine` : solution calculée (tracée en trait plein) ;
    - la meilleure solution connue (fichier .sol voisin), si elle existe, est tracée en tirets
      sur la carte de ma solution, et a sa propre carte dans l'onglet « Meilleure solution connue » ;
    - `zone` / `span` : où poser l'instance sur la carte (cf. `interface.geo.PRESETS`) ;
    - `settings` : paramètres du calcul à rappeler en haut de page (libellé -> valeur) ;
    - `controls` : panneau de commande du mode serveur (formulaire), sinon page statique ;
    - `running` : calcul en cours, la page se recharge toute seule (mode serveur).
    """
    if zone not in PRESETS:
        raise ValueError(f"Zone inconnue : {zone!r} (au choix : {', '.join(PRESETS)})")
    css = (TEMPLATES / "style.css").read_text(encoding="utf-8")
    base = dict(css=css, controls=controls, running=running,
                generated=dt.datetime.now().strftime("%d/%m/%Y à %H:%M"))
    if inst is None:  # pas d'instance (mode serveur, rien de chargé) : seulement le panneau
        return _env.get_template("page.html").render(inst=None, settings={}, **base)

    lat0, lon0, span_default = PRESETS[zone]
    span = span or span_default
    frame = place_on_map(inst.coords, lat0, lon0, span)

    best = solvers.make_solution(inst, inst.best_routes, "Meilleure solution connue") if inst.best_routes else None

    # Carte principale : ma solution (+ la meilleure connue en tirets, masquée par défaut, que le
    # bouton de couches permet d'ajouter) ou, sans calcul, la meilleure connue en trait plein.
    layers = []
    if mine is not None:
        layers.append(MapLayer(f"Ma solution ({mine.solver})", mine.routes))
    if best is not None:
        layers.append(MapLayer("Meilleure solution connue", best.routes, dashed=mine is not None,
                               show=mine is None))
    # Pendant un calcul on ne montre que la solution en cours ; sinon, une seconde carte pour
    # l'onglet « Meilleure solution connue » (onglets en CSS, sans JavaScript).
    tabs = mine is not None and best is not None and not running
    best_layers = [MapLayer("Meilleure solution connue", best.routes)] if tabs else None

    shown = {"Zone": zone, "Étendue": f"{fr(span)} km", **(settings or {})}
    return _env.get_template("page.html").render(
        inst=inst, scale=frame.km_per_unit, settings=shown,
        map_main=build_map(inst, frame, layers),
        map_best=build_map(inst, frame, best_layers) if best_layers else None,
        tabs=tabs,
        mine=solution_view(inst, mine, frame.km_per_unit) if mine is not None else None,
        best=solution_view(inst, best, frame.km_per_unit) if best is not None and not running else None,
        **base,
    )


def write_page(path: str | Path, html: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
