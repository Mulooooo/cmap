"""Serveur web : API JSON + interface statique (carte MapLibre).

Lancer :  python -m interface        puis ouvrir http://127.0.0.1:8000

API
  GET  /api/config                       solveurs, zones, instances du dépôt
  POST /api/instances?filename=x.vrp     corps = contenu du .vrp (téléversement)
  POST /api/instances/library/{name}     charge une instance du dossier instances/
  GET  /api/instances/{id}?zone=&span=   instance placée sur la carte
  GET  /api/solve?instance=&solver=&time_limit=&seed=   flux SSE (progress, done)
"""

import asyncio
import json
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from interface import notebook_solvers  # noqa: F401  (enregistre les solveurs du notebook)
from interface import solvers
from interface.geo import PRESETS, place_on_map
from interface.instance import Instance, load_instance, load_instance_from_bytes

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
MAX_UPLOAD = 20 * 1024 * 1024  # 20 Mo
MAX_INSTANCES = 32  # instances gardées en mémoire (les plus anciennes sont oubliées)

app = FastAPI(title="CMAP - Tournées de livraison")
STORE: "OrderedDict[str, Instance]" = OrderedDict()


# ------------------------------------------------------------------ utilitaires
def _library() -> dict[str, Path]:
    """Instances du dépôt, sous-dossiers compris, nommées par leur chemin relatif (ex. A/A-n32-k5.vrp)."""
    base = ROOT / "instances"
    return {p.relative_to(base).as_posix(): p for p in sorted(base.rglob("*.vrp"))}


def _remember(inst: Instance) -> str:
    iid = uuid.uuid4().hex[:12]
    STORE[iid] = inst
    while len(STORE) > MAX_INSTANCES:
        STORE.popitem(last=False)
    return iid


def _get(iid: str) -> Instance:
    if iid not in STORE:
        raise HTTPException(404, "Instance inconnue (le serveur a peut-être redémarré) : recharge-la.")
    return STORE[iid]


def _payload(iid: str, inst: Instance, zone: str | None, span: float | None) -> dict:
    zone = zone or next(iter(PRESETS))
    if zone not in PRESETS:
        raise HTTPException(400, f"Zone inconnue : {zone}")
    lat0, lon0, default_span = PRESETS[zone]
    span = min(max(span if span is not None else default_span, 5.0), 3000.0)
    frame = place_on_map(inst.coords, lat0, lon0, span)
    return {
        "id": iid,
        "name": inst.name,
        "n": inst.n,
        "capacity": inst.capacity,
        "demand": inst.demand.tolist(),
        "total_demand": int(inst.demand.sum()),
        "min_vehicles": inst.min_vehicles,
        "n_vehicles": inst.n_vehicles,
        "bks": inst.bks,
        "has_time_windows": inst.time_windows is not None,
        "lat": frame.lat.tolist(),
        "lon": frame.lon.tolist(),
        "km_per_unit": frame.km_per_unit,
        "zone": zone,
        "span": span,
        # meilleure solution connue (fichier .sol voisin), au même format qu'un résultat de solveur
        "best": None if not inst.best_routes else _solution_payload(
            inst, solvers.make_solution(inst, inst.best_routes, "Meilleure solution connue")),
    }


def _solution_payload(inst: Instance, sol: solvers.Solution) -> dict:
    errors = solvers.check_solution(inst, sol.routes)
    return {
        "solver": sol.solver,
        "routes": sol.routes,
        "cost": sol.cost,
        "gap": None if not inst.bks else 100 * (sol.cost - inst.bks) / inst.bks,
        "valid": not errors,
        "errors": errors,
        "elapsed": sol.elapsed,
        "history": sol.history,
        "per_route": [
            {"load": solvers.route_load(inst, r), "dist": solvers.route_cost(inst, r), "n": len(r)}
            for r in sol.routes
        ],
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=_json_default)}\n\n"


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    raise TypeError(type(o))


class _Cancelled(BaseException):
    """Levée dans le callback de progression quand le navigateur a coupé le flux.
    BaseException pour ne pas être avalée par un `except Exception` du solveur."""


# -------------------------------------------------------------------------- API
@app.get("/api/config")
def config():
    return {
        "solvers": list(solvers.SOLVERS),
        "zones": {name: {"lat": v[0], "lon": v[1], "span": v[2]} for name, v in PRESETS.items()},
        "library": list(_library()),
    }


@app.post("/api/instances")
async def upload_instance(request: Request, filename: str = "instance.vrp",
                          zone: str | None = None, span: float | None = None):
    data = await request.body()
    if not data or len(data) > MAX_UPLOAD:
        raise HTTPException(400, "Fichier vide ou trop gros (20 Mo maximum).")
    try:
        inst = load_instance_from_bytes(data, filename)
    except Exception as exc:
        raise HTTPException(400, f"Fichier .vrp illisible : {exc}") from exc
    iid = _remember(inst)
    return _payload(iid, inst, zone, span)


@app.post("/api/instances/library/{name:path}")
def library_instance(name: str, zone: str | None = None, span: float | None = None):
    path = _library().get(name)  # on ne sert que les fichiers listés : pas de chemin libre
    if path is None:
        raise HTTPException(404, "Instance introuvable dans instances/")
    inst = load_instance(path)
    return _payload(_remember(inst), inst, zone, span)


@app.get("/api/instances/{iid}")
def get_instance(iid: str, zone: str | None = None, span: float | None = None):
    return _payload(iid, _get(iid), zone, span)


@app.get("/api/solve")
async def solve(request: Request, instance: str, solver: str, time_limit: float = 10.0, seed: int = 0):
    inst = _get(instance)
    fn = solvers.SOLVERS.get(solver)
    if fn is None:
        raise HTTPException(404, f"Solveur inconnu : {solver}")
    time_limit = min(max(time_limit, 1.0), 300.0)

    async def stream():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        cancel = threading.Event()
        last = [0.0]
        t0 = time.perf_counter()

        def put(item):
            loop.call_soon_threadsafe(queue.put_nowait, item)

        def on_progress(it, cost, routes):
            if cancel.is_set():
                raise _Cancelled()
            now = time.perf_counter()
            if now - last[0] < 0.25:  # on ne sature pas le navigateur
                return
            last[0] = now
            put(("progress", {"it": int(it), "cost": float(cost), "elapsed": now - t0,
                              "routes": [list(map(int, r)) for r in routes]}))

        def work():
            try:
                sol = fn(inst, time_limit, seed, on_progress)
                put(("done", _solution_payload(inst, sol)))
            except _Cancelled:
                put(("cancelled", {}))
            except Exception as exc:  # erreur du solveur : on la montre à l'écran
                put(("error", {"message": f"{type(exc).__name__}: {exc}"}))

        threading.Thread(target=work, daemon=True).start()
        try:
            while True:
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        return
                    yield ": keepalive\n\n"
                    continue
                yield _sse(event, data)
                if event in ("done", "cancelled", "error"):
                    return
        finally:
            cancel.set()  # le solveur s'arrêtera à sa prochaine amélioration

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# Version React (si elle a été compilée : cd frontend && npm install && npm run build).
REACT_DIST = ROOT / "frontend" / "dist"
if REACT_DIST.is_dir():
    app.mount("/react", StaticFiles(directory=REACT_DIST, html=True), name="react")

# Interface HTML (doit être monté en dernier : il capte tout ce que l'API n'a pas pris).
app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
