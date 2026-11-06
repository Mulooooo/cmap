"""Les pages du site : un formulaire HTML et des pages générées côté serveur (aucun JavaScript).

L'état de la page est dans l'URL (instance, zone, solveur, calcul en cours) ; pendant un calcul la
page se recharge toute seule chaque seconde (<meta http-equiv="refresh">), ce qui est le « polling »
de docs/api.md. Tout ce qui touche au serveur de calcul passe par `web.api_client.ApiClient`.

  GET  /    la page (paramètres : instance, zone, span, solver, limit, seed, job, view, notice)
  POST /    le formulaire : action = show | solve | stop, fichier .vrp optionnel
"""

import math
import secrets
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
from flask import Blueprint, Response, current_app, redirect, render_template, request

from web.api_client import ApiError, Unreachable
from web.figures import MapLayer, build_map, convergence_svg, fr, route_color
from web.geo import PRESETS, place_on_map
from web.routing import RoutingUnavailable
from web.simulation import build_simulation, clock

bp = Blueprint("site", __name__)

NOTICES = {"busy": "Un calcul était déjà en cours : le voici (un seul calcul à la fois)."}


def _api():
    return current_app.extensions["api"]


# ------------------------------------------------------------------ chiffres d'une solution
def route_stats(inst: dict, routes: list[list[int]]) -> list[dict]:
    """Charge et distance de chaque tournée, calculées à partir des coordonnées de l'instance
    (pour la meilleure solution connue et les calculs en cours, que l'API ne détaille pas).
    La distance est arrondie à l'entier le plus proche, comme TSPLIB (EUC_2D)."""
    coords, demand = inst["coords"], inst["demand"]
    exact = inst.get("edge_weight_type") == "EUC_2D"

    def d(a, b):
        dist = math.hypot(coords[a][0] - coords[b][0], coords[a][1] - coords[b][1])
        return math.floor(dist + 0.5) if exact else dist

    out = []
    for r in routes:
        path = [0, *r, 0]
        out.append({
            "n_clients": len(r),
            "load": sum(demand[c] for c in r),
            "distance": sum(d(a, b) for a, b in zip(path, path[1:])),
        })
    return out


def solution_view(inst: dict, *, solver: str, routes, stats, cost, elapsed, history, km_per_unit,
                  valid=None, errors=()) -> dict:
    """Ce que le gabarit affiche pour une solution."""
    bks = (inst.get("best_known") or {}).get("cost")
    return {
        "solver": solver,
        "routes": routes,  # gardés pour tracer la carte
        "stats": stats,
        "cost": cost,
        "km": round(cost * km_per_unit),
        "n_routes": len(routes),
        "gap": None if not bks else 100 * (cost - bks) / bks,
        "elapsed": elapsed,
        "valid": valid,  # True / False, ou None pour une solution de référence non vérifiée
        "errors": list(errors),
        "rows": [
            {
                "n": i + 1, "color": route_color(i), "path": " → ".join(["D", *map(str, r), "D"]),
                "clients": s["n_clients"], "load": s["load"],
                "pct": min(100, round(100 * s["load"] / inst["capacity"])),
                "dist": s["distance"], "km": round(s["distance"] * km_per_unit),
            }
            for i, (r, s) in enumerate(zip(routes, stats))
        ],
        "chart": convergence_svg([(h[0], h[2]) for h in history or []], bks),
    }


# --------------------------------------------------------------------------------- la page
def _num(text, default, lo, hi, cast=float):
    try:
        return min(max(cast(str(text).replace(",", ".")), lo), hi)
    except (TypeError, ValueError):
        return default


def render_page(params: dict, error: str | None = None, status: int = 200):
    """Construit la page à partir des paramètres (ceux de l'URL ou du formulaire)."""
    api, cfg = _api(), current_app.config
    zone = params.get("zone") if params.get("zone") in PRESETS else next(iter(PRESETS))
    span_default = PRESETS[zone][2]
    span_typed = str(params.get("span") or "").strip()
    span = _num(span_typed, span_default, 5.0, 3000.0) if span_typed else span_default
    limit = _num(params.get("limit"), 10, 1, 300, int)
    seed = _num(params.get("seed"), 0, 0, 100000, int)

    ctx = {
        "error": error or NOTICES.get(params.get("notice")), "api_ok": True, "refresh": None,
        "zones": list(PRESETS), "zone": zone, "span_input": span_typed, "span_default": int(span_default),
        "limit": limit, "seed": seed, "solvers": [], "solver": params.get("solver"),
        "instances": [], "instance_id": None, "inst": None, "job": None, "running": False, "banner": None,
        "settings": {}, "tabs": False, "map_main": None, "map_best": None, "mine": None, "best": None,
        "scale": None, "sim_urls": {},
    }

    try:
        solvers = api.solvers()
        ctx["solvers"] = [(s["id"], s["name"]) for s in solvers]
        if ctx["solver"] not in [s[0] for s in ctx["solvers"]]:
            ctx["solver"] = ctx["solvers"][0][0] if ctx["solvers"] else None
        listing = api.instances()
        ctx["instances"] = [
            (i["id"], f"{i['name']} · {i['n_clients']} clients" + (" (fichier envoyé)" if i["source"] == "upload" else ""))
            for i in listing
        ]

        # l'instance demandée, sinon la première de la liste
        wanted = params.get("instance") or (listing[0]["id"] if listing else None)
        inst = None
        if wanted:
            try:
                inst = api.instance(wanted)
            except ApiError as exc:
                if exc.status != 404:
                    raise
                ctx["error"] = ctx["error"] or exc.message
                if listing:
                    wanted = listing[0]["id"]
                    inst = api.instance(wanted)
        ctx["instance_id"] = wanted
        if inst is None:
            return render_template("page.html", **ctx), status

        # le calcul demandé (il peut avoir été oublié par le serveur de calcul)
        job = None
        if params.get("job"):
            try:
                job = api.job(params["job"])
                if job["instance_id"] != wanted:
                    job = None  # il portait sur une autre instance
            except ApiError as exc:
                if exc.status != 404:
                    raise
                ctx["error"] = ctx["error"] or "Ce calcul n'existe plus (le serveur de calcul a redémarré ?)"
    except Unreachable as exc:
        ctx.update(api_ok=False, error=str(exc))
        return render_template("page.html", **ctx), 200 if status == 200 else status
    except ApiError as exc:
        ctx["error"] = exc.message
        return render_template("page.html", **ctx), status if status != 200 else 502

    # ---- placement de l'instance sur la carte
    lat0, lon0, _ = PRESETS[zone]
    frame = place_on_map(np.array(inst["coords"], dtype=float), lat0, lon0, span)
    kpu = frame.km_per_unit
    demand, capacity = inst["demand"], inst["capacity"]
    best_known = inst.get("best_known") or {}
    bks = best_known.get("cost")
    total = sum(demand)
    ctx["scale"] = kpu
    ctx["inst"] = {
        "name": inst["name"], "n_clients": inst["n_clients"], "capacity": capacity, "total_demand": total,
        "min_vehicles": math.ceil(total / capacity), "bks": bks,
    }

    # ---- ma solution : le résultat final, sinon la meilleure trouvée jusque-là
    running = job is not None and job["status"] == "running"
    mine = None
    if job is not None:
        label = {"running": "en cours", "stopped": "arrêté"}.get(job["status"])
        solver_name = dict(ctx["solvers"]).get(job["solver"], job["solver"]) + (f", {label}" if label else "")
        res = job["result"]
        if res is not None:  # calcul terminé ou arrêté : l'API a tout vérifié
            mine = solution_view(inst, solver=solver_name, routes=res["routes"], stats=res["per_route"],
                                 cost=res["cost"], elapsed=res["elapsed"], history=job["history"],
                                 km_per_unit=kpu, valid=res["valid"], errors=res["errors"])
        elif job["routes"]:  # en cours : on calcule les chiffres ici, l'API ne les détaille pas encore
            mine = solution_view(inst, solver=solver_name, routes=job["routes"],
                                 stats=route_stats(inst, job["routes"]), cost=job["best_cost"],
                                 elapsed=job["elapsed"], history=job["history"], km_per_unit=kpu, valid=True)
        ctx["settings"] = {"Solveur": solver_name, "Temps limite": f"{fr(job['time_limit'])} s", "Graine": str(job["seed"])}
        if running:
            ctx["refresh"] = cfg["REFRESH_SECONDS"]
            ctx["banner"] = (f"Calcul en cours… {fr(job['elapsed'])} s sur {fr(job['time_limit'])} s"
                             + (f" · meilleur coût {fr(job['best_cost'])}" if job["best_cost"] is not None else ""))
        elif job["status"] == "stopped":
            ctx["banner"] = "Calcul arrêté : meilleure solution trouvée jusque-là."
        elif job["status"] == "error":
            ctx["error"] = ctx["error"] or f"Erreur du calcul : {job['error']}"
    ctx["job"], ctx["running"] = (job["job_id"] if job else None), running

    # ---- meilleure solution connue (le détail de l'instance en donne les tournées)
    best = None
    if best_known.get("routes"):
        rs = best_known["routes"]
        stats = route_stats(inst, rs)
        best = solution_view(inst, solver="Meilleure solution connue", routes=rs, stats=stats,
                             cost=sum(s["distance"] for s in stats), elapsed=0, history=[], km_per_unit=kpu)

    # ---- cartes : ma solution (+ la meilleure en tirets, masquée) ; une 2e carte pour l'onglet « meilleure »
    layers = []
    if mine is not None:
        layers.append(MapLayer(f"Ma solution ({mine['solver']})", mine["routes"], mine["stats"]))
    if best is not None:
        layers.append(MapLayer("Meilleure solution connue", best["routes"], best["stats"],
                               dashed=mine is not None, show=mine is None))
    tabs = mine is not None and best is not None and not running
    ctx["tabs"] = tabs
    ctx["map_main"] = build_map(frame, demand, capacity, layers)
    if tabs:
        ctx["map_best"] = build_map(frame, demand, capacity,
                                    [MapLayer("Meilleure solution connue", best["routes"], best["stats"])])
    ctx["mine"] = mine
    ctx["best"] = None if running else best
    if not running:  # on ne simule qu'une solution terminée
        base = {"instance": wanted, "zone": zone, "span": span_typed, "solver": ctx["solver"], "limit": limit,
                "seed": seed, "job": ctx["job"] or ""}
        if mine is not None and job is not None and job["status"] in ("done", "stopped"):
            ctx["sim_urls"]["mine"] = "/simulation?" + urlencode({**base, "view": "mine"})
        if best is not None:
            ctx["sim_urls"]["best"] = "/simulation?" + urlencode({**base, "view": "best"})
    ctx["settings"] = {"Zone": zone, "Étendue": f"{fr(span)} km", **ctx["settings"]}
    return render_template("page.html", **ctx), status


# ----------------------------------------------------------------------------- routes
def _redirect(params: dict):
    q = {k: v for k, v in params.items() if v not in (None, "")}
    return redirect("/?" + urlencode(q), code=303)


@bp.get("/")
def index():
    return render_page(dict(request.args))


@bp.post("/")
def submit():
    api, form = _api(), request.form
    params = {k: form.get(k, "") for k in ("instance", "zone", "span", "solver", "limit", "seed", "job")}
    action = form.get("action", "show")

    file = request.files.get("file")
    if file is not None and file.filename:
        try:
            created = api.upload(file.read(), Path(file.filename).name)
        except Unreachable as exc:
            return render_page(params, str(exc), 200)
        except ApiError as exc:  # fichier illisible, trop gros...
            return render_page(params, exc.message, 400)
        params.update(instance=created["id"], job="")  # nouvelle instance : on repart de zéro

    try:
        if action == "stop" and params["job"]:
            api.stop(params["job"])
            return _redirect(params)
        if action == "solve":
            started = api.start_job(params["instance"], params["solver"],
                                    _num(params["limit"], 10, 1, 300, int), _num(params["seed"], 0, 0, 100000, int))
            return _redirect({**params, "job": started["job_id"]})
    except Unreachable as exc:
        return render_page(params, str(exc), 200)
    except ApiError as exc:
        if exc.code == "busy":  # un autre calcul tourne : on affiche celui-là
            return _redirect({**params, "job": exc.body.get("job_id"), "notice": "busy"})
        return render_page(params, exc.message, exc.status if exc.status < 500 else 502)
    return _redirect(params)  # action == "show"


# ------------------------------------------------------------------------ simulation
class SimError(Exception):
    """Pas de solution à simuler (l'utilisateur doit d'abord lancer ou terminer un calcul)."""


def _back_url(params: dict) -> str:
    keep = {k: params.get(k) for k in ("instance", "zone", "span", "solver", "limit", "seed", "job")}
    return "/?" + urlencode({k: v for k, v in keep.items() if v})


def _simulation_input(params: dict):
    """(instance, tournées à simuler, nom de la solution, placement sur la carte)."""
    api = _api()
    try:
        inst = api.instance(params.get("instance") or "")
    except ApiError as exc:
        raise SimError(exc.message) from exc
    except Unreachable as exc:
        raise SimError(str(exc)) from exc

    zone = params.get("zone") if params.get("zone") in PRESETS else next(iter(PRESETS))
    span_typed = str(params.get("span") or "").strip()
    span = _num(span_typed, PRESETS[zone][2], 5.0, 3000.0) if span_typed else PRESETS[zone][2]
    frame = place_on_map(np.array(inst["coords"], dtype=float), PRESETS[zone][0], PRESETS[zone][1], span)

    if params.get("view") == "best":
        routes = (inst.get("best_known") or {}).get("routes")
        if not routes:
            raise SimError("Cette instance n'a pas de meilleure solution connue à simuler.")
        return inst, routes, "Meilleure solution connue", frame
    if not params.get("job"):
        raise SimError("Lance d'abord un calcul : il n'y a pas encore de solution à simuler.")
    try:
        job = api.job(params["job"])
    except ApiError as exc:
        raise SimError("Ce calcul n'existe plus : relance-le." if exc.status == 404 else exc.message) from exc
    except Unreachable as exc:
        raise SimError(str(exc)) from exc
    if job["result"] is None:
        raise SimError("Le calcul n'est pas terminé : attends la fin, ou arrête-le, pour simuler sa meilleure solution.")
    return inst, job["result"]["routes"], f"Ma solution ({job['solver']})", frame


@bp.get("/simulation")
def simulation():
    params, cfg = dict(request.args), current_app.config
    ctx = {"back": _back_url(params), "error": None, "title": None, "inst": None, "trucks": [], "warnings": [],
           "token": None, "service_min": cfg["SERVICE_SECONDS"] // 60, "totals": None, "long_tours": False}
    try:
        inst, routes, title, frame = _simulation_input(params)
    except SimError as exc:
        ctx["error"] = str(exc)
        return render_template("simulation.html", **ctx), 200
    ctx.update(title=title, inst={"name": inst["name"], "n_clients": inst["n_clients"]})

    try:
        sim = build_simulation(frame, routes, current_app.extensions["routing"], cfg["SERVICE_SECONDS"])
    except RoutingUnavailable as exc:
        ctx["error"] = f"{exc}. Réessaie dans un instant (il faut une connexion Internet)."
        return render_template("simulation.html", **ctx), 200

    plan = route_stats(inst, routes)  # distances de l'instance (plan abstrait), converties en km de la carte
    for t, st in zip(sim.trucks, plan):
        t["plan_km"] = st["distance"] * frame.km_per_unit
        t["drive_h"], t["total_h"] = t["drive_s"] / 3600, t["total_s"] / 3600
    ctx["trucks"], ctx["warnings"] = sim.trucks, sim.warnings
    ctx["long_tours"] = any(t["total_h"] > 12 for t in sim.trucks)  # conseil : réduire l'étendue sur la carte
    ctx["totals"] = {"road_km": sum(t["road_km"] for t in sim.trucks), "plan_km": sum(t["plan_km"] for t in sim.trucks),
                     "last_return": clock(max(t["total_s"] for t in sim.trucks)) if sim.trucks else None}
    cache: OrderedDict = current_app.extensions["sim_cache"]
    ctx["token"] = secrets.token_urlsafe(8)
    cache[ctx["token"]] = sim.html
    while len(cache) > 8:  # on ne garde que les dernières cartes
        cache.popitem(last=False)
    return render_template("simulation.html", **ctx)


@bp.get("/simulation/map/<token>")
def simulation_map(token):
    html = current_app.extensions["sim_cache"].get(token)
    if html is None:
        return Response("Cette simulation n'est plus en mémoire : relance-la.", status=404, mimetype="text/plain")
    return Response(html, mimetype="text/html")
