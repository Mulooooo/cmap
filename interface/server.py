"""Petit serveur local : la page de `interface.page` avec un vrai bouton « Calculer ».

Aucun JavaScript écrit à la main : la page est un formulaire HTML. L'état (instance, zone,
solveur, calcul en cours) est dans l'URL ; pendant un calcul la page se recharge toute seule
(<meta http-equiv="refresh">) et le bouton « Arrêter » l'interrompt.

Lancer :  python -m interface --serveur        puis ouvrir http://127.0.0.1:8000

  GET  /    la page (paramètres : src, zone, span, solver, limit, seed, job)
  POST /    le formulaire : action = show | solve | stop, fichier .vrp optionnel
"""

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from interface import notebook_solvers  # noqa: F401  (enregistre les solveurs du notebook)
from interface import solvers
from interface.figures import fr
from interface.geo import PRESETS
from interface.instance import Instance, load_instance, load_instance_from_bytes
from interface.page import build_page

ROOT = Path(__file__).resolve().parent.parent
MAX_UPLOAD = 20 * 1024 * 1024  # 20 Mo
KEEP = 32  # fichiers téléversés et calculs gardés en mémoire (les plus anciens sont oubliés)

app = FastAPI(title="CMAP - Tournées de livraison")
UPLOADS: "OrderedDict[str, Instance]" = OrderedDict()
JOBS: "OrderedDict[str, Job]" = OrderedDict()


# ----------------------------------------------------------------------- instances
def _library() -> dict[str, Path]:
    """Instances du dépôt, sous-dossiers compris, nommées par leur chemin relatif (ex. A/A-n32-k5.vrp)."""
    base = ROOT / "instances"
    return {p.relative_to(base).as_posix(): p for p in sorted(base.rglob("*.vrp"))}


@lru_cache(maxsize=64)
def _library_instance(name: str) -> Instance:
    return load_instance(_library()[name])


class BadSource(Exception):
    pass


def _resolve(src: str | None) -> tuple[str, Instance]:
    """`src` vaut « lib:<chemin relatif> » ou « up:<id> » ; on ne sert que les fichiers listés
    (pas de chemin libre). Sans `src`, on prend la première instance du dépôt."""
    lib = _library()
    if not src:
        if not lib:
            raise BadSource("Aucune instance dans instances/ : téléverse un fichier .vrp.")
        src = "lib:" + next(iter(lib))
    kind, _, key = src.partition(":")
    if kind == "lib" and key in lib:
        return src, _library_instance(key)
    if kind == "up" and key in UPLOADS:
        return src, UPLOADS[key]
    raise BadSource("Instance introuvable (le serveur a peut-être redémarré) : recharge-la.")


def _remember(store: OrderedDict, key: str, value) -> None:
    store[key] = value
    while len(store) > KEEP:
        store.popitem(last=False)


# --------------------------------------------------------------------------- calculs
class _Cancelled(BaseException):
    """Levée dans le callback de progression quand l'utilisateur a arrêté le calcul.
    BaseException pour ne pas être avalée par un `except Exception` du solveur."""


@dataclass
class Job:
    id: str
    src: str
    inst: Instance
    solver: str
    time_limit: float
    seed: int
    started: float = field(default_factory=time.perf_counter)
    status: str = "running"  # running | done | stopped | error
    live: solvers.Routes | None = None  # meilleures tournées reçues pendant le calcul
    live_cost: float | None = None
    history: list = field(default_factory=list)  # (temps_s, itération, meilleur coût)
    solution: solvers.Solution | None = None
    error: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def current(self) -> solvers.Solution | None:
        """Solution à afficher : le résultat final, sinon la meilleure trouvée jusque-là."""
        if self.solution is not None:
            return self.solution
        if self.live:
            label = f"{self.solver}, en cours" if self.status == "running" else self.solver
            return solvers.make_solution(self.inst, self.live, label, self.history,
                                         time.perf_counter() - self.started)
        return None


def start_job(src: str, inst: Instance, solver: str, time_limit: float, seed: int) -> Job:
    job = Job(uuid.uuid4().hex[:12], src, inst, solver, time_limit, seed)
    fn = solvers.SOLVERS[solver]

    def on_progress(it, cost, routes):
        if job.cancel.is_set():
            raise _Cancelled()
        job.live = [[int(c) for c in r] for r in routes]
        job.live_cost = float(cost)
        job.history.append((time.perf_counter() - job.started, int(it), float(cost)))

    def work():
        try:
            sol = fn(inst, time_limit, seed, on_progress)
            with job.lock:
                if job.status == "running":
                    job.solution, job.status = sol, "done"
        except _Cancelled:
            pass
        except Exception as exc:  # erreur du solveur : on la montre à l'écran
            with job.lock:
                if job.status == "running":
                    job.error, job.status = f"{type(exc).__name__}: {exc}", "error"

    _remember(JOBS, job.id, job)
    threading.Thread(target=work, daemon=True).start()
    return job


def stop_job(job: Job) -> None:
    """Arrête le calcul tout de suite : on garde la meilleure solution trouvée jusque-là.
    Le solveur lui-même s'interrompt à son prochain appel de on_progress."""
    with job.lock:
        if job.status != "running":
            return
        job.cancel.set()
        job.status = "stopped"
        if job.live:
            job.solution = solvers.make_solution(
                job.inst, job.live, f"{job.solver}, arrêté", job.history,
                time.perf_counter() - job.started)


# ----------------------------------------------------------------------------- page
def _num(text, default, lo, hi, cast=float):
    try:
        return min(max(cast(str(text).replace(",", ".")), lo), hi)
    except (TypeError, ValueError):
        return default


def render_page(params: dict, error: str | None = None, status: int = 200) -> HTMLResponse:
    """Construit la page à partir des paramètres (ceux de l'URL ou du formulaire)."""
    zone = params.get("zone") if params.get("zone") in PRESETS else next(iter(PRESETS))
    span_default = PRESETS[zone][2]
    span_typed = str(params.get("span") or "").strip()
    span = _num(span_typed, span_default, 5.0, 3000.0) if span_typed else span_default
    solver = params.get("solver") if params.get("solver") in solvers.SOLVERS else next(iter(solvers.SOLVERS))
    limit = _num(params.get("limit"), 10, 1, 300, int)
    seed = _num(params.get("seed"), 0, 0, 100000, int)

    try:
        src, inst = _resolve(params.get("src"))
    except BadSource as exc:
        error = error or str(exc)
        try:  # instance perdue : on retombe sur la première du dépôt
            src, inst = _resolve(None)
        except BadSource:
            src, inst = "", None

    sources = [(f"lib:{name}", name) for name in _library()]
    if src.startswith("up:") and inst is not None:
        sources.insert(0, (src, f"{inst.name} (fichier téléversé)"))

    job = JOBS.get(params.get("job") or "")
    if job is not None and job.src != src:
        job = None  # le calcul portait sur une autre instance
    running = job is not None and job.status == "running"
    if job is not None and job.status == "error":
        error = error or f"Erreur du solveur : {job.error}"

    banner = None
    settings = {}
    if job is not None:
        settings = {"Solveur": job.solver, "Temps limite": f"{fr(job.time_limit)} s", "Graine": str(job.seed)}
        if running:
            banner = (f"Calcul en cours… {fr(time.perf_counter() - job.started)} s sur {fr(job.time_limit)} s"
                      + (f" · meilleur coût {fr(job.live_cost)}" if job.live_cost is not None else ""))
        elif job.status == "stopped":
            banner = "Calcul arrêté : meilleure solution trouvée jusque-là."

    controls = {
        "sources": sources, "src": src, "zones": list(PRESETS), "zone": zone,
        "span_input": span_typed, "span_default": int(span_default),
        "solvers": list(solvers.SOLVERS), "solver": solver, "limit": limit, "seed": seed,
        "job": job.id if job is not None else None, "error": error, "banner": banner,
    }
    html = build_page(inst, mine=job.current() if job is not None else None, zone=zone, span=span,
                      settings=settings, controls=controls, running=running)
    return HTMLResponse(html, status_code=status)


def _redirect(params: dict) -> RedirectResponse:
    q = {k: v for k, v in params.items() if v not in (None, "")}
    return RedirectResponse("/?" + urlencode(q), status_code=303)


# ---------------------------------------------------------------------------- routes
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render_page(dict(request.query_params))


@app.post("/", response_class=HTMLResponse)
async def submit(
    action: str = Form("show"),
    src: str = Form(""),
    file: UploadFile | None = File(None),
    zone: str = Form(""),
    span: str = Form(""),
    solver: str = Form(""),
    limit: str = Form("10"),
    seed: str = Form("0"),
    job: str = Form(""),
):
    params = {"src": src, "zone": zone, "span": span, "solver": solver, "limit": limit,
              "seed": seed, "job": job}

    if file is not None and file.filename:
        data = await file.read(MAX_UPLOAD + 1)
        if not data or len(data) > MAX_UPLOAD:
            return render_page(params, "Fichier vide ou trop gros (20 Mo maximum).", 400)
        try:
            inst = load_instance_from_bytes(data, file.filename)
        except Exception as exc:
            return render_page(params, f"Fichier .vrp illisible : {exc}", 400)
        uid = uuid.uuid4().hex[:12]
        _remember(UPLOADS, uid, inst)
        params.update(src=f"up:{uid}", job="")  # nouvelle instance : on repart de zéro

    if action == "stop":
        j = JOBS.get(job)
        if j is not None:
            stop_job(j)
        return _redirect(params)

    if action == "solve":
        try:
            src_key, inst = _resolve(params["src"])
        except BadSource as exc:
            return render_page(params, str(exc), 404)
        if solver not in solvers.SOLVERS:
            return render_page(params, f"Solveur inconnu : {solver}", 400)
        j = start_job(src_key, inst, solver, _num(limit, 10, 1, 300, int), _num(seed, 0, 0, 100000, int))
        return _redirect({**params, "src": src_key, "job": j.id})

    return _redirect(params)  # action == "show"
