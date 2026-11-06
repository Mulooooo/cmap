"""Faux corps de processus de calcul, pour tester le serveur (ils doivent être importables par le
processus enfant, d'où ce module à part)."""

import time


def crash(solver_id, inst, time_limit, seed, q):
    q.put(("error", "RuntimeError: boum"))


def hang(solver_id, inst, time_limit, seed, q):
    time.sleep(60)  # ne rend jamais la main


def die(solver_id, inst, time_limit, seed, q):
    raise SystemExit(3)  # le processus s'arrête sans rien envoyer
