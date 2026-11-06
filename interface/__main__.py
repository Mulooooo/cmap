"""Visualisation des tournées : page HTML avec carte folium.

    python -m interface --serveur                                      page avec boutons (calcul en direct)
    python -m interface instances/A/A-n32-k5.vrp                       fichier HTML : meilleure solution connue
    python -m interface instances/A/A-n32-k5.vrp --solveur recuit      fichier HTML + calcul avec un solveur
    python -m interface --solveurs                                     liste des solveurs
"""

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

from interface import notebook_solvers  # noqa: F401  (enregistre les solveurs du notebook)
from interface import solvers
from interface.figures import fr
from interface.geo import PRESETS
from interface.instance import load_instance
from interface.page import build_page, write_page


def choose_solver(query: str) -> str:
    """Nom exact, ou morceau du nom (sans casse) s'il ne désigne qu'un seul solveur."""
    names = list(solvers.SOLVERS)
    if query in names:
        return query
    found = [n for n in names if query.lower() in n.lower()]
    if len(found) == 1:
        return found[0]
    detail = "plusieurs solveurs correspondent" if found else "solveur inconnu"
    sys.exit(f"{detail} : {query!r}. Au choix : " + " ; ".join(names))


def serve(port: int, open_browser: bool = True) -> None:
    """Page avec boutons : un petit serveur local (uvicorn) sur 127.0.0.1."""
    try:
        import uvicorn
    except ImportError:
        sys.exit("Le mode --serveur demande : pip install fastapi uvicorn python-multipart")
    url = f"http://127.0.0.1:{port}"
    print(f"Page : {url}   (Ctrl+C pour arrêter)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("interface.server:app", host="127.0.0.1", port=port, log_level="warning")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        prog="python -m interface",
        description="Génère la page HTML d'une instance VRPLIB (carte folium, tableaux, convergence).",
    )
    ap.add_argument("instance", nargs="?", help="fichier .vrp (un .sol du même nom donne la meilleure solution connue)")
    ap.add_argument("--solveur", help="calcule une solution avec ce solveur (nom ou morceau du nom)")
    ap.add_argument("--temps", type=float, default=10.0, help="temps de calcul en secondes (défaut : 10)")
    ap.add_argument("--graine", type=int, default=0, help="graine aléatoire (défaut : 0)")
    ap.add_argument("--zone", default="France entière", choices=list(PRESETS),
                    help="où poser l'instance sur la carte (défaut : France entière)")
    ap.add_argument("--etendue", type=float, help="largeur de l'instance sur la carte, en km (défaut : selon la zone)")
    ap.add_argument("--sortie", help="fichier HTML à écrire (défaut : sortie/<instance>.html)")
    ap.add_argument("--sans-ouvrir", action="store_true", help="ne pas ouvrir la page dans le navigateur")
    ap.add_argument("--solveurs", action="store_true", help="affiche la liste des solveurs et quitte")
    ap.add_argument("--serveur", action="store_true",
                    help="lance un petit serveur local : la page a un menu de solveurs et un bouton Calculer")
    ap.add_argument("--port", type=int, default=8000, help="port du serveur (défaut : 8000)")
    args = ap.parse_args(argv)

    if args.solveurs:
        print("\n".join(solvers.SOLVERS))
        return
    if args.serveur:
        return serve(args.port, open_browser=not args.sans_ouvrir)
    if not args.instance:
        ap.error("indique un fichier .vrp (ou --solveurs)")
    path = Path(args.instance).expanduser()
    if not path.is_file():
        sys.exit(f"Fichier introuvable : {path}")
    try:
        inst = load_instance(path)
    except Exception as exc:
        sys.exit(f"Fichier .vrp illisible : {exc}")

    print(f"{inst.name} : {inst.n - 1} clients, capacité {inst.capacity}"
          + (f", meilleure connue {fr(inst.bks)}" if inst.bks else ""))

    mine, settings = None, {}
    if args.solveur:
        name = choose_solver(args.solveur)
        t0, last = time.perf_counter(), [0.0]

        def on_progress(it, cost, routes):  # une ligne par amélioration, au plus 2 par seconde
            now = time.perf_counter()
            if now - last[0] >= 0.5:
                last[0] = now
                print(f"  {fr(now - t0):>6} s · itération {it} · coût {fr(cost)}")

        print(f"Calcul : {name}, {fr(args.temps)} s, graine {args.graine}")
        mine = solvers.SOLVERS[name](inst, args.temps, args.graine, on_progress)
        errors = solvers.check_solution(inst, mine.routes)
        gap = f", gap {fr(100 * (mine.cost - inst.bks) / inst.bks)} %" if inst.bks else ""
        print(f"Résultat : coût {fr(mine.cost)}, {len(mine.routes)} camions{gap}")
        if errors:
            print("Attention, solution invalide : " + " ; ".join(errors))
        settings = {"Solveur": name, "Temps limite": f"{fr(args.temps)} s", "Graine": str(args.graine)}
    elif not inst.best_routes:
        print("Pas de fichier .sol à côté de l'instance et pas de --solveur : seuls les clients seront affichés.")

    html = build_page(inst, mine=mine, zone=args.zone, span=args.etendue, settings=settings)
    out = write_page(args.sortie or Path("sortie") / f"{inst.name}.html", html)
    print(f"Page écrite : {out.resolve()}")
    if not args.sans_ouvrir:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
