"""Le site : des pages HTML (+ folium) qui parlent au serveur de calcul par requêtes API."""

from collections import OrderedDict
from pathlib import Path

from flask import Flask

from web.api_client import ApiClient
from web.config import Config
from web.figures import fr
from web.routing import OsrmClient
from web.views import bp

HERE = Path(__file__).resolve().parent


def create_app(overrides: dict | None = None, api=None, routing=None) -> Flask:
    """`overrides` remplace des valeurs de `Config` ; `api` et `routing` remplacent le client du serveur
    de calcul et celui du service d'itinéraires routiers (réservé aux tests)."""
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.update(overrides or {})
    app.config["MAX_CONTENT_LENGTH"] = app.config["MAX_UPLOAD"]
    app.extensions["api"] = api or ApiClient(app.config["API_URL"], app.config["API_TIMEOUT"])
    app.extensions["routing"] = routing or OsrmClient(app.config["OSRM_URL"], app.config["OSRM_TIMEOUT"])
    app.extensions["sim_cache"] = OrderedDict()  # cartes de simulation déjà fabriquées
    app.register_blueprint(bp)
    app.jinja_env.filters["fr"] = fr

    css = (HERE / "templates" / "style.css").read_text(encoding="utf-8")
    app.context_processor(lambda: {"css": css})  # la feuille de style est écrite dans la page
    return app
