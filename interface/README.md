# Interface graphique

Charge une instance VRPLIB (`.vrp`), l'affiche sur une carte de France, lance un
solveur et montre les tournées en direct (une couleur par camion), avec le gap
par rapport à la meilleure solution connue et la courbe de convergence.

## Lancer

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r interface/requirements.txt
streamlit run interface/app.py
```

L'instance se choisit dans le panneau de gauche : un fichier de `instances/`,
un fichier téléversé, ou un chemin local (ex. `~/Downloads/A-n32-k5.vrp`).

## Brancher le solveur de l'équipe

Le solveur est une fonction enregistrée dans `interface/solvers.py` (ou dans
n'importe quel module importé par `app.py`). L'interface le propose alors dans
la liste « Solveur ».

```python
from interface.solvers import register, make_solution

@register("Recuit simulé")
def recuit(inst, time_limit, seed, on_progress=None):
    # inst.dist[i][j]  distances (arrondies comme TSPLIB pour EUC_2D)
    # inst.demand[i]   demande du sommet i (0 pour le dépôt)
    # inst.capacity    capacité d'un camion
    # sommet 0 = dépôt, clients = 1..n-1
    ...
    # à chaque amélioration, pour l'affichage en direct (optionnel) :
    #     on_progress(iteration, meilleur_cout, routes)
    return make_solution(inst, routes, "Recuit simulé", history)
```

- `routes` : liste de tournées, chacune est la liste des clients dans l'ordre de
  visite, **sans le dépôt**. Exemple : `[[3, 7, 1], [2, 5]]`.
- `history` : liste de `(temps_s, iteration, meilleur_cout)` pour la courbe de
  convergence (peut être vide).
- `make_solution` calcule le coût ; l'interface vérifie ensuite la validité
  (chaque client visité une fois, capacité respectée) et affiche une erreur
  sinon.

Le solveur « Baseline provisoire » (Clarke-Wright + recherche locale itérée) ne
sert qu'à tester l'interface avant que le vrai solveur soit prêt.

## Choix à connaître

- Les instances VRPLIB n'ont pas de position géographique : les points sont posés
  sur la carte par homothétie autour de la zone choisie (`interface/geo.py`). Ils
  ne correspondent pas à de vraies villes, donc certains tombent en mer ou à
  l'étranger. Les trajets sont à vol d'oiseau, pas sur le réseau routier.
- Les distances sont arrondies à l'entier le plus proche pour `EUC_2D`
  (convention TSPLIB), sinon le gap ne serait pas comparable aux valeurs publiées
  (ex. A-n32-k5 : 784).

## Tests

```bash
pip install pytest
pytest tests
```
