"""Les routes de l'API. Le contrat (routes, JSON, codes d'erreur) est dans docs/api.md."""

from flask import Blueprint, current_app, jsonify, request

from server.jobs import Busy
from solvers import SOLVERS

bp = Blueprint("api", __name__, url_prefix="/api")


def error(code: str, message: str, status: int, **extra):
    return jsonify({"error": message, "code": code, **extra}), status


def _store():
    return current_app.extensions["store"]


def _jobs():
    return current_app.extensions["jobs"]


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.get("/solvers")
def solvers():
    return jsonify([{"id": s.id, "name": s.name, "description": s.description} for s in SOLVERS.values()])


# ------------------------------------------------------------------- instances
@bp.get("/instances")
def list_instances():
    return jsonify(_store().summaries())


@bp.get("/instances/<instance_id>")
def get_instance(instance_id):
    detail = _store().detail(instance_id)
    if detail is None:
        return error("not_found", f"Instance inconnue : {instance_id}", 404)
    return jsonify(detail)


@bp.post("/instances")
def upload_instance():
    file = request.files.get("file")  # lève 413 si le corps dépasse MAX_CONTENT_LENGTH
    if file is None:
        return error("invalid_file", "Champ « file » absent : envoie le .vrp en multipart/form-data", 400)
    data = file.read()
    if not data:
        return error("invalid_file", "Fichier vide", 400)
    try:
        instance_id = _store().add_upload(data, file.filename or "instance.vrp")
    except Exception as exc:  # fichier illisible, incomplet ou pas un CVRP
        return error("invalid_file", f"Fichier .vrp illisible : {exc}", 400)
    return jsonify(_store().detail(instance_id)), 201


# ------------------------------------------------------------------------ jobs
def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@bp.post("/jobs")
def start_job():
    cfg = current_app.config
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error("invalid_param", "Le corps doit être un objet JSON", 422, field="body")

    instance_id, solver_id = body.get("instance_id"), body.get("solver")
    for name, value in (("instance_id", instance_id), ("solver", solver_id)):
        if not isinstance(value, str) or not value:
            return error("invalid_param", f"« {name} » est obligatoire (texte)", 422, field=name)

    time_limit = body.get("time_limit", cfg["TIME_LIMIT_DEFAULT"])
    if not _number(time_limit) or not cfg["TIME_LIMIT_MIN"] <= time_limit <= cfg["TIME_LIMIT_MAX"]:
        return error("invalid_param",
                     f"« time_limit » doit être un nombre de {cfg['TIME_LIMIT_MIN']} à {cfg['TIME_LIMIT_MAX']} secondes",
                     422, field="time_limit")
    seed = body.get("seed", 0)
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        return error("invalid_param", "« seed » doit être un entier positif ou nul", 422, field="seed")

    found = _store().get(instance_id)
    if found is None:
        return error("not_found", f"Instance inconnue : {instance_id}", 404)
    if solver_id not in SOLVERS:
        return error("not_found", f"Solveur inconnu : {solver_id}", 404)

    try:
        job = _jobs().start(instance_id, found[0], SOLVERS[solver_id], time_limit, seed)
    except Busy as busy:
        return error("busy", "Un calcul est déjà en cours", 409, job_id=busy.job_id)
    return jsonify({"job_id": job.id, "status": job.status}), 202


@bp.get("/jobs/<job_id>")
def get_job(job_id):
    job = _jobs().get(job_id)
    if job is None:
        return error("not_found", f"Calcul inconnu : {job_id}", 404)
    since = request.args.get("since")
    if since is not None:
        try:
            since = int(since)
        except ValueError:
            return error("invalid_param", "« since » doit être un entier", 422, field="since")
    return jsonify(job.to_dict(current_app.config["HISTORY_MAX_POINTS"], since))


@bp.post("/jobs/<job_id>/stop")
def stop_job(job_id):
    jobs = _jobs()
    job = jobs.get(job_id)
    if job is None:
        return error("not_found", f"Calcul inconnu : {job_id}", 404)
    return jsonify(jobs.stop(job).to_dict(current_app.config["HISTORY_MAX_POINTS"]))
