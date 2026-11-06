"""Lancer le serveur :  python -m server   (puis http://127.0.0.1:5001/api/health)"""

import argparse

from server import create_app
from server.config import Config


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m server", description="Serveur de calcul VRP (API JSON)")
    ap.add_argument("--host", default=Config.HOST)
    ap.add_argument("--port", type=int, default=Config.PORT)
    args = ap.parse_args()
    app = create_app()
    print(f"API sur http://{args.host}:{args.port}/api   (Ctrl+C pour arrêter)")
    app.run(host=args.host, port=args.port, threaded=True, debug=False)


if __name__ == "__main__":  # nécessaire : les calculs sont lancés par multiprocessing en mode « spawn »
    main()
