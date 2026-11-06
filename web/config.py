"""Réglages du site (chaque valeur peut venir d'une variable d'environnement)."""

import os


class Config:
    # le serveur de calcul (voir docs/api.md) : python -m server
    API_URL = os.environ.get("API_URL", "http://127.0.0.1:5001")
    API_TIMEOUT = float(os.environ.get("API_TIMEOUT", "10"))

    # le site lui-même : 5002 (le 5001 est celui de l'API, le 5000 est pris par AirPlay sur macOS)
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", "5002"))

    REFRESH_SECONDS = 1  # pendant un calcul, la page se recharge toutes les secondes (polling)
    MAX_UPLOAD = 20 * 1024 * 1024

    # simulation sur les vraies routes (OSRM) ; pour un usage intensif, installer OSRM et changer l'adresse
    OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org")
    OSRM_TIMEOUT = float(os.environ.get("OSRM_TIMEOUT", "25"))
    SERVICE_SECONDS = 600  # temps passé chez chaque client pour livrer (10 minutes)
