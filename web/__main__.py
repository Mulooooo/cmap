"""Lancer le site :  python -m web   (puis http://127.0.0.1:5002 ; le serveur de calcul doit tourner)"""

import argparse

from web import create_app
from web.config import Config


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m web", description="Site de visualisation des tournées")
    ap.add_argument("--host", default=Config.HOST)
    ap.add_argument("--port", type=int, default=Config.PORT)
    ap.add_argument("--api", default=Config.API_URL, help="adresse du serveur de calcul (défaut : %(default)s)")
    args = ap.parse_args()
    app = create_app({"API_URL": args.api})
    print(f"Site sur http://{args.host}:{args.port}   (serveur de calcul : {args.api})   Ctrl+C pour arrêter")
    app.run(host=args.host, port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
