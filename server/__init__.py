"""Serveur Flask : lance les métaheuristiques et répond au site en JSON (voir docs/api.md)."""

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from server.api import bp
from server.config import Config
from server.instances import InstanceStore
from server.jobs import JobManager

_CODES = {404: "not_found", 405: "method_not_allowed", 413: "too_large"}


def create_app(overrides: dict | None = None, job_worker=None) -> Flask:
    """`overrides` remplace des valeurs de `Config` ; `job_worker` remplace le corps du processus
    de calcul (réservé aux tests)."""
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.update(overrides or {})
    app.json.ensure_ascii = False  # accents lisibles dans les réponses
    app.json.sort_keys = False  # champs dans l'ordre du contrat (docs/api.md)

    app.extensions["store"] = InstanceStore(app.config["INSTANCES_DIR"], app.config["MAX_UPLOADS"])
    kwargs = {"worker": job_worker} if job_worker else {}
    app.extensions["jobs"] = JobManager(app.config["MAX_JOBS_KEPT"], app.config["KILL_GRACE"], **kwargs)
    app.register_blueprint(bp)

    origins = [o.strip() for o in app.config["CORS_ORIGINS"].split(",") if o.strip()]
    if origins:  # le site tourne sur une autre adresse : on l'autorise à appeler l'API
        CORS(app, resources={r"/api/*": {"origins": origins}})

    @app.errorhandler(HTTPException)
    def http_error(exc):  # même format d'erreur partout, y compris pour les routes inconnues
        message = {404: "Route inconnue", 413: "Fichier trop gros (20 Mo maximum)"}.get(exc.code, exc.description)
        return jsonify({"error": message, "code": _CODES.get(exc.code, "bad_request")}), exc.code

    @app.errorhandler(Exception)
    def unexpected(exc):  # une erreur du code ne doit jamais faire tomber le serveur
        app.logger.exception("Erreur inattendue")
        return jsonify({"error": "Erreur inattendue du serveur", "code": "server_error"}), 500

    return app
