"""Le moteur de calcul : un seul calcul à la fois, chacun dans son propre processus.

Pourquoi un processus et pas un thread : une métaheuristique est du Python pur qui occupe un
cœur à 100 %. Dans un thread elle ralentirait tout le serveur (GIL) et on ne pourrait pas
l'arrêter ; un processus se coupe proprement avec `terminate()`.

Le processus envoie ses progrès par une file ; un thread du serveur la lit et tient le `Job`
à jour. Le site ne parle jamais au processus : il interroge `GET /api/jobs/<id>`.
"""

import multiprocessing as mp
import queue
import threading
import time
import uuid
from collections import OrderedDict

from solvers import SOLVERS, Solver
from solvers.common import evaluate
from solvers.instance import Instance


class Busy(Exception):
    """Un calcul tourne déjà ; `job_id` est le sien."""

    def __init__(self, job_id: str):
        super().__init__(job_id)
        self.job_id = job_id


def _worker(solver_id: str, inst: Instance, time_limit: float, seed: int, q) -> None:
    """Corps du processus : lance le solveur et envoie ses progrès dans `q`."""
    last = [0.0]

    def on_progress(it, cost, routes):
        now = time.perf_counter()
        if now - last[0] >= 0.2:  # au plus 5 envois par seconde : pas la peine d'inonder le serveur
            last[0] = now
            q.put(("progress", int(it), float(cost), [list(map(int, r)) for r in routes]))

    try:
        sol = SOLVERS[solver_id].fn(inst, time_limit, seed, on_progress)
        q.put(("done", [list(map(int, r)) for r in sol.routes], [list(h) for h in sol.history], sol.elapsed))
    except BaseException as exc:  # le serveur doit toujours savoir pourquoi un calcul s'est arrêté
        q.put(("error", f"{type(exc).__name__}: {exc}"))


def _thin(points: list, n: int) -> list:
    """Au plus n points, en gardant le premier et le dernier."""
    if len(points) <= n:
        return points
    step = (len(points) - 1) / (n - 1)
    return [points[round(i * step)] for i in range(n)]


class Job:
    def __init__(self, instance_id: str, inst: Instance, solver: Solver, time_limit: float, seed: int):
        self.id = uuid.uuid4().hex[:12]
        self.instance_id, self.inst, self.solver = instance_id, inst, solver
        self.time_limit, self.seed = time_limit, seed
        self.status = "running"  # running | done | stopped | error
        self.started = time.perf_counter()
        self.finished: float | None = None
        self.best_cost: float | None = None
        self.version = 0  # augmente à chaque amélioration reçue
        self.routes: list | None = None
        self.history: list = []  # [temps, itération, coût]
        self.result: dict | None = None
        self.error: str | None = None
        self.process = None
        self.lock = threading.Lock()

    @property
    def elapsed(self) -> float:
        return (self.finished or time.perf_counter()) - self.started

    def to_dict(self, history_max: int, since: int | None = None) -> dict:
        with self.lock:
            fresh = since is None or self.version > since  # rien de nouveau : on n'envoie pas les tournées
            return {
                "job_id": self.id,
                "instance_id": self.instance_id,
                "solver": self.solver.id,
                "time_limit": self.time_limit,
                "seed": self.seed,
                "status": self.status,
                "elapsed": round(self.elapsed, 2),
                "best_cost": self.best_cost,
                "version": self.version,
                "routes": self.routes if fresh else None,
                "history": _thin(self.history, history_max) if fresh else None,
                "result": self.result,
                "error": self.error,
            }


class JobManager:
    def __init__(self, keep: int = 20, kill_grace: float = 5.0, worker=_worker):
        self.keep, self.kill_grace, self._worker = keep, kill_grace, worker
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._lock = threading.Lock()
        self._ctx = mp.get_context("spawn")  # « spawn » : le seul mode sûr partout (macOS, Windows)

    # ------------------------------------------------------------------ API
    def start(self, instance_id: str, inst: Instance, solver: Solver, time_limit: float, seed: int) -> Job:
        with self._lock:
            for j in self._jobs.values():
                if j.status == "running":
                    raise Busy(j.id)
            job = Job(instance_id, inst, solver, time_limit, seed)
            q = self._ctx.Queue()
            job.process = self._ctx.Process(
                target=self._worker, args=(solver.id, inst, time_limit, seed, q), daemon=True)
            job.process.start()
            self._jobs[job.id] = job
            while len(self._jobs) > self.keep:  # on oublie les plus anciens, jamais celui qui tourne
                oldest = next(iter(self._jobs))
                if self._jobs[oldest].status == "running":
                    break
                self._jobs.popitem(last=False)
        threading.Thread(target=self._watch, args=(job, q), daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def stop(self, job: Job) -> Job:
        """Arrête le calcul et garde la meilleure solution reçue jusque-là. Sans effet s'il est fini."""
        with job.lock:
            if job.status == "running":
                job.status = "stopped"
                job.finished = time.perf_counter()
                if job.routes:
                    job.result = evaluate(job.inst, job.routes, job.elapsed)
        self._kill(job)
        return job

    # ------------------------------------------------------------- interne
    def _kill(self, job: Job) -> None:
        p = job.process
        if p is not None and p.is_alive() and job.status != "running":
            p.terminate()

    def _fail(self, job: Job, message: str) -> None:
        with job.lock:
            if job.status != "running":
                return
            job.status, job.error, job.finished = "error", message, time.perf_counter()
        if job.process is not None and job.process.is_alive():
            job.process.terminate()

    def _handle(self, job: Job, msg: tuple) -> None:
        kind = msg[0]
        with job.lock:
            if job.status != "running":
                return
            if kind == "progress":
                _, it, cost, routes = msg
                job.best_cost, job.routes, job.version = cost, routes, job.version + 1
                job.history.append([round(time.perf_counter() - job.started, 2), it, cost])
            elif kind == "done":
                _, routes, history, elapsed = msg
                job.status, job.finished = "done", time.perf_counter()
                job.routes = routes
                job.history = [[round(t, 2), it, cost] for t, it, cost in history]
                job.result = evaluate(job.inst, routes, elapsed)
                job.best_cost = job.result["cost"]
                job.version += 1
        if kind == "error":
            self._fail(job, msg[1])

    def _watch(self, job: Job, q) -> None:
        """Lit les messages du processus, détecte le temps dépassé et la mort du processus."""
        dead = False
        while job.status == "running":
            try:
                self._handle(job, q.get(timeout=0.1))
                continue
            except queue.Empty:
                pass
            if dead:  # le processus est mort et la file est vide : il n'a pas rendu de résultat
                self._fail(job, "Le processus du solveur s'est arrêté sans résultat")
            elif time.perf_counter() - job.started > job.time_limit + self.kill_grace:
                self._fail(job, "Le solveur a dépassé son temps limite")
            elif not job.process.is_alive():
                dead = True  # une dernière lecture de la file avant de conclure
        if job.process is not None:
            job.process.join(timeout=2)
            if job.process.is_alive():
                job.process.terminate()
