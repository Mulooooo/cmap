"""Les métaheuristiques disponibles pour le serveur.

Pour en ajouter une : écrire une fonction `solve(inst, time_limit, seed, on_progress=None) -> Solution`
(voir `solvers/notebook.py`) et l'inscrire dans `SOLVERS` avec un `id` stable : c'est l'identifiant
que le site envoie à l'API.

  - `inst`        : `solvers.instance.Instance` (sommet 0 = dépôt, clients 1..n-1)
  - `time_limit`  : secondes de calcul
  - `seed`        : graine aléatoire (même graine = même calcul)
  - `on_progress` : à appeler à chaque amélioration, `on_progress(iteration, cout, tournees)`, pour
                    le suivi en direct (facultatif mais recommandé : un calcul arrêté garde
                    la dernière solution annoncée)
"""

from dataclasses import dataclass
from typing import Callable

from solvers import notebook


@dataclass(frozen=True)
class Solver:
    id: str
    name: str
    description: str
    fn: Callable


SOLVERS: dict[str, Solver] = {
    s.id: s
    for s in (
        Solver("hill_climbing", "Hill climbing",
               "Montée de colline avec le voisinage relocate (livrable 2)", notebook.hill_climbing),
        Solver("simulated_annealing", "Recuit simulé",
               "Recuit simulé avec le voisinage relocate (livrable 2)", notebook.simulated_annealing),
    )
}
