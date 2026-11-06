# Interface web

Charge une instance VRPLIB (`.vrp`), l'affiche sur une carte de France, lance un
solveur et montre les tournées en direct (une couleur par camion), avec le gap
par rapport à la meilleure solution connue, le tableau par camion et la courbe de
convergence. Survoler un camion dans le tableau le met en évidence sur la carte.

Un backend Python (FastAPI) appelle les solveurs ; deux interfaces utilisent la
même API :

| Interface | Adresse | Technologie |
|---|---|---|
| HTML / JavaScript | http://127.0.0.1:8000/ | `interface/static/` (rien à compiler) |
| React | http://127.0.0.1:8000/react/ | `frontend/` (Vite + TypeScript, à compiler) |

## Lancer

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r interface/requirements.txt
python -m interface            # --port 8000 --host 127.0.0.1
```

Version React (Node 20+) :

```bash
cd frontend
npm install
npm run build                  # produit frontend/dist, servi sur /react/ par python -m interface
# ou, pour développer avec rechargement à chaud (python -m interface doit tourner) :
npm run dev                    # http://localhost:5173
```

L'instance se choisit dans le panneau de gauche : un fichier de `instances/` (sous-dossiers
compris, ex. `A/A-n32-k5.vrp`) ou un fichier `.vrp` glissé / téléversé (n'importe où sur la
page). Ajouter un `.vrp` dans `instances/` suffit pour qu'il apparaisse dans la liste après
un redémarrage du serveur. La meilleure solution connue (gap) vient du commentaire du
fichier, sinon du fichier `.sol` voisin (ligne `Cost N`).

## Meilleure solution connue

Quand un fichier `.sol` du même nom est à côté du `.vrp` (c'est le cas des instances de
`instances/A/`), l'interface l'affiche dès le chargement de l'instance, avec son tableau
et son coût. Après un calcul, les boutons « Ma solution » / « Meilleure solution connue »
permettent de comparer les deux sur la carte. Un fichier téléversé n'a pas de `.sol` :
seul le calcul est affiché.

## Solveurs disponibles

Ceux du livrable 2 (notebook), portés dans `interface/notebook_solvers.py` :
`Hill climbing (notebook)` et `Recuit simulé (notebook)`. L'en-tête du fichier liste les
cellules d'origine et les (rares) écarts avec le notebook : distances arrondies, temps
limite à la place du nombre d'itérations, graine configurable.

Limite héritée du notebook : `is_possible` exige au plus `k` camions, mais le glouton de
départ en utilise parfois plus (ex. A-n37-k6 : 7 pour k = 6). Aucun voisin n'est alors
accepté, l'algorithme reste bloqué et l'interface affiche « Solution invalide ».

## Brancher un autre solveur

Le solveur est une fonction enregistrée dans `interface/solvers.py` (ou dans
n'importe quel module importé par `interface/server.py`). Les deux interfaces le
proposent alors dans la liste « Solveur ».

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
- `make_solution` calcule le coût ; le serveur vérifie ensuite la validité
  (chaque client visité une fois, capacité respectée) et l'interface affiche une
  erreur sinon. Une exception dans le solveur est affichée à l'écran.
- Le bouton « Arrêter » coupe le flux : le solveur est interrompu à son prochain
  appel de `on_progress` (sinon il va au bout de son temps limite).

## API

| Route | Rôle |
|---|---|
| `GET /api/config` | solveurs, zones, instances du dépôt |
| `POST /api/instances?filename=x.vrp` | téléverse un `.vrp` (corps = contenu, 20 Mo max) |
| `POST /api/instances/library/{nom}` | charge un fichier de `instances/` |
| `GET /api/instances/{id}?zone=&span=` | replace l'instance sur la carte |
| `GET /api/solve?instance=&solver=&time_limit=&seed=` | flux SSE : `progress` puis `done` (ou `error`) |

Les instances sont gardées en mémoire (32 au plus) : un redémarrage du serveur les
oublie, il faut les recharger.

## Choix à connaître

- Les instances VRPLIB n'ont pas de position géographique : les points sont posés
  sur la carte par homothétie autour de la zone choisie (`interface/geo.py`). Ils
  ne correspondent pas à de vraies villes, donc certains tombent en mer ou à
  l'étranger. Les trajets sont à vol d'oiseau, pas sur le réseau routier.
- Les distances sont arrondies à l'entier le plus proche pour `EUC_2D`
  (convention TSPLIB), sinon le gap ne serait pas comparable aux valeurs publiées
  (ex. A-n32-k5 : 784).
- Les fonds de carte (CARTO) et MapLibre (version HTML, via unpkg) demandent un accès
  à Internet.
- L'interface est prévue pour un usage local : pas d'authentification, et chaque
  calcul lance un thread.

## Tests

```bash
pip install pytest httpx
pytest tests
```
