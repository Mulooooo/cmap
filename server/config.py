"""Réglages du serveur. Chaque valeur peut être remplacée par `create_app({...})` (tests)."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Config:
    # instances
    INSTANCES_DIR = ROOT / "instances"
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # taille max d'un .vrp envoyé (20 Mo)
    MAX_UPLOADS = 20  # envois gardés en mémoire (les plus anciens sont oubliés)

    # calculs
    TIME_LIMIT_MIN = 1
    TIME_LIMIT_MAX = 300
    TIME_LIMIT_DEFAULT = 10
    KILL_GRACE = 5.0  # secondes de marge avant d'arrêter de force un solveur qui ne rend pas la main
    MAX_JOBS_KEPT = 20  # calculs gardés en mémoire
    HISTORY_MAX_POINTS = 500  # taille max de `history` dans les réponses

    # réseau : le serveur n'écoute que sur la machine locale par défaut
    HOST = os.environ.get("HOST", "127.0.0.1")
    # 5001 et pas 5000 : sur macOS le port 5000 est pris par le récepteur AirPlay
    PORT = int(os.environ.get("PORT", "5001"))
    # adresses du site autorisées à appeler l'API, séparées par des virgules ("" = aucune)
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "")
