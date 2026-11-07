"""Les pages du site : un formulaire HTML et des pages générées côté serveur (aucun JavaScript).

L'état de la page est dans l'URL (instance, zone, solveur, calcul en cours, simulation).
Tout ce qui touche au serveur de calcul passe par `web.api_client.ApiClient`.

Parcours d'un calcul, sans JavaScript et sans rechargement qui clignote :
  Calculer -> /calcul : page d'attente (un rond qui tourne) envoyée tout de suite, que le serveur garde
  ouverte pendant que le calcul tourne ; à la fin il y ajoute « va sur la page de résultat » -> /

  GET  /        la page (paramètres : instance, zone, span, solver, limit, seed, job, sim, notice)
  POST /        le formulaire : action = show | solve | stop, fichier .vrp optionnel
  GET  /calcul  la page d'attente d'un calcul en cours (même paramètres, job obligatoire)
"""

import math
import secrets
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
from flask import Blueprint, Response, current_app, redirect, render_template, request
from markupsafe import escape

from web.api_client import ApiError, Unreachable
from web.figures import MapLayer, build_map, convergence_svg, fr, route_color
from web.geo import PRESETS, place_on_map
from web.routing import RoutingUnavailable
from web.simulation import build_simulation, clock

bp = Blueprint("site", __name__)

NOTICES = {"busy": "Un calcul était déjà en cours : on attend sa fin (un seul calcul à la fois)."}
STATE_KEYS = ("instance", "zone", "span", "solver", "limit", "seed", "job", "notice")  # l'état de la page, dans l'URL


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


def render_page(params: dict, error: str | None = None, status: int = 200, wait_if_running: bool = False):
    """Construit la page à partir des paramètres (ceux de l'URL ou du formulaire).

    Avec `wait_if_running`, un calcul en cours envoie vers la page d'attente au lieu d'afficher
    un résultat partiel : le résultat arrive tout seul à la fin."""
    api, cfg = _api(), current_app.config
    zone = params.get("zone") if params.get("zone") in PRESETS else next(iter(PRESETS))
    span_default = PRESETS[zone][2]
    span_typed = str(params.get("span") or "").strip()
    span = _num(span_typed, span_default, 5.0, 3000.0) if span_typed else span_default
    limit = _num(params.get("limit"), 10, 1, 300, int)
    seed = _num(params.get("seed"), 0, 0, 100000, int)

    ctx = {
        "error": error or NOTICES.get(params.get("notice")), "api_ok": True,
        "zones": list(PRESETS), "zone": zone, "span_input": span_typed, "span_default": int(span_default),
        "limit": limit, "seed": seed, "solvers": [], "solver": params.get("solver"),
        "instances": [], "instance_id": None, "inst": None, "job": None, "running": False, "banner": None,
        "settings": {}, "tabs": False, "map_main": None, "map_best": None, "mine": None, "best": None,
        "scale": None, "sim_urls": {}, "sim": None, "sim_active": None, "sim_exit_url": None,
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
    if running and wait_if_running:
        state = {k: params.get(k) for k in STATE_KEYS if params.get(k)}
        return redirect("/calcul?" + urlencode({**state, "instance": wanted, "job": job["job_id"]}), code=303)
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
    ctx["mine"] = mine
    ctx["best"] = None if running else best

    # ---- simulation sur les vraies routes : demandée par ?sim=mine|best, elle reste sur cette page
    # et remplace la carte habituelle par la carte animée
    base = {"instance": wanted, "zone": zone, "span": span_typed, "solver": ctx["solver"], "limit": limit,
            "seed": seed, "job": ctx["job"] or ""}
    can_sim_mine = mine is not None and job is not None and job["status"] in ("done", "stopped")
    if not running:  # on ne simule qu'une solution terminée
        if can_sim_mine:
            ctx["sim_urls"]["mine"] = "/?" + urlencode({**base, "sim": "mine"}) + "#carte"
        if best is not None:
            ctx["sim_urls"]["best"] = "/?" + urlencode({**base, "sim": "best"}) + "#carte"
    ctx["sim_exit_url"] = "/?" + urlencode(base) + "#carte"

    sim_view = params.get("sim") if params.get("sim") in ("mine", "best") else None
    sim_routes = sim_title = None
    if sim_view and not running:
        if sim_view == "mine" and can_sim_mine:
            sim_routes, sim_title = mine["routes"], f"Ma solution ({mine['solver']})"
        elif sim_view == "mine":
            ctx["error"] = ctx["error"] or "Lance d'abord un calcul : il n'y a pas encore de solution à simuler."
        elif best is not None:
            sim_routes, sim_title = best["routes"], "Meilleure solution connue"
        else:
            ctx["error"] = ctx["error"] or "Cette instance n'a pas de meilleure solution connue à simuler."

    simulation = None
    if sim_routes:
        try:
            simulation = build_simulation(frame, sim_routes, current_app.extensions["routing"], cfg["SERVICE_SECONDS"])
        except RoutingUnavailable as exc:  # on garde la page et sa carte habituelle, avec le message
            ctx["error"] = ctx["error"] or f"{exc}. Réessaie dans un instant (il faut une connexion Internet)."

    if simulation is not None:
        plan = route_stats(inst, sim_routes)  # distances de l'instance (plan abstrait), à l'échelle de la carte
        for t, st in zip(simulation.trucks, plan):
            t["plan_km"] = st["distance"] * kpu
            t["drive_h"], t["total_h"] = t["drive_s"] / 3600, t["total_s"] / 3600
        token = secrets.token_urlsafe(8)
        cache: OrderedDict = current_app.extensions["sim_cache"]
        cache[token] = simulation.html
        while len(cache) > 8:  # on ne garde que les dernières cartes
            cache.popitem(last=False)
        ctx["sim"] = {
            "token": token, "title": sim_title, "trucks": simulation.trucks, "warnings": simulation.warnings,
            "service_min": cfg["SERVICE_SECONDS"] // 60,
            "long_tours": any(t["total_h"] > 12 for t in simulation.trucks),
            "totals": {"road_km": sum(t["road_km"] for t in simulation.trucks),
                       "plan_km": sum(t["plan_km"] for t in simulation.trucks),
                       "last_return": clock(max(t["total_s"] for t in simulation.trucks))},
        }
        ctx["sim_active"] = sim_view
        # la carte de la page devient la simulation ; pas d'onglets, les deux solutions restent listées
    else:
        tabs = mine is not None and best is not None and not running
        ctx["tabs"] = tabs
        ctx["map_main"] = build_map(frame, demand, capacity, layers)
        if tabs:
            ctx["map_best"] = build_map(frame, demand, capacity,
                                        [MapLayer("Meilleure solution connue", best["routes"], best["stats"])])
    ctx["settings"] = {"Zone": zone, "Étendue": f"{fr(span)} km", **ctx["settings"]}
    return render_template("page.html", **ctx), status


# ----------------------------------------------------------------------------- routes
def _redirect(params: dict, path: str = "/"):
    q = {k: v for k, v in params.items() if v not in (None, "")}
    return redirect(f"{path}?" + urlencode(q), code=303)


@bp.get("/")
def index():
    return render_page(dict(request.args), wait_if_running=True)


@bp.get("/calcul")
def waiting():
    """Page d'attente d'un calcul : un rond qui tourne, puis le résultat s'affiche tout seul.

    Sans JavaScript : la page est envoyée tout de suite (le rond est une animation CSS) et la
    connexion reste ouverte pendant que le serveur de calcul travaille ; à la fin on ajoute une
    balise « va sur la page de résultat » (`<meta http-equiv="refresh">`, que le navigateur applique
    dès qu'elle arrive). Une seule navigation : rien ne clignote, rien à actualiser."""
    api, cfg = _api(), current_app.config
    state = {k: request.args.get(k) for k in STATE_KEYS if request.args.get(k)}
    # la page qui montrera le résultat (ou l'explication d'un problème) ; sans le message « un calcul tournait déjà »,
    # qui n'a de sens que pendant l'attente
    result_url = "/?" + urlencode({k: v for k, v in state.items() if k != "notice"})
    if not state.get("job"):
        return redirect(result_url, code=303)
    try:
        job = api.job(state["job"])
        solver_name = dict((s["id"], s["name"]) for s in api.solvers()).get(job["solver"], job["solver"])
    except (ApiError, Unreachable):
        return redirect(result_url, code=303)  # calcul oublié, serveur éteint : la page principale l'explique
    if job["status"] != "running":
        return redirect(result_url, code=303)  # déjà fini : directement le résultat

    page = render_template(
        "waiting.html", instance=job["instance_id"], solver=solver_name, time_limit=job["time_limit"],
        duration=job["time_limit"] + 1.5, url=result_url,  # + le démarrage du calcul
        state={k: v for k, v in state.items() if k != "notice"}, notice=NOTICES.get(state.get("notice")))
    head, tail = page.split("<!--SUITE-->")
    job_id, poll = job["job_id"], cfg["WAIT_POLL_SECONDS"]
    give_up = time.monotonic() + job["time_limit"] + cfg["WAIT_EXTRA_SECONDS"]

    def stream():
        yield head + "<!-- " + "." * 1024 + " -->\n"  # de quoi pousser le début de la page jusqu'au navigateur
        while time.monotonic() < give_up:
            time.sleep(poll)
            try:
                if api.job(job_id)["status"] != "running":
                    break
            except (ApiError, Unreachable):
                break  # la page de résultat dira ce qui s'est passé
        yield f'<meta http-equiv="refresh" content="0;url={escape(result_url)}">' + tail

    return Response(stream(), mimetype="text/html", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@bp.post("/")
def submit():
    api, form = _api(), request.form
    params = {k: form.get(k, "") for k in ("instance", "zone", "span", "solver", "limit", "seed", "job", "sim")}
    action = form.get("action", "show")

    file = request.files.get("file")
    if file is not None and file.filename:
        try:
            created = api.upload(file.read(), Path(file.filename).name)
        except Unreachable as exc:
            return render_page(params, str(exc), 200)
        except ApiError as exc:  # fichier illisible, trop gros...
            return render_page(params, exc.message, 400)
        params.update(instance=created["id"], job="", sim="")  # nouvelle instance : on repart de zéro

    try:
        if action == "stop" and params["job"]:
            api.stop(params["job"])
            return _redirect(params)
        if action == "solve":
            started = api.start_job(params["instance"], params["solver"],
                                    _num(params["limit"], 10, 1, 300, int), _num(params["seed"], 0, 0, 100000, int))
            # nouveau calcul : plus de simulation, et la page d'attente (le rond qui tourne)
            return _redirect({**params, "job": started["job_id"], "sim": ""}, "/calcul")
    except Unreachable as exc:
        return render_page(params, str(exc), 200)
    except ApiError as exc:
        if exc.code == "busy":  # un autre calcul tourne : on affiche celui-là
            return _redirect({**params, "job": exc.body.get("job_id"), "notice": "busy"}, "/calcul")
        return render_page(params, exc.message, exc.status if exc.status < 500 else 502)
    return _redirect(params)  # action == "show"


# ------------------------------------------------------------------ carte de la simulation
@bp.get("/simulation/map/<token>")
def simulation_map(token):
    html = current_app.extensions["sim_cache"].get(token)
    if html is None:
        return Response("Cette simulation n'est plus en mémoire : relance-la.", status=404, mimetype="text/plain")
    return Response(html, mimetype="text/html")
