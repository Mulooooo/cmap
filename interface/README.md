# Visualisation des tournées (HTML + folium)

À partir d'une instance VRPLIB (`.vrp`), génère **une page HTML** avec une carte de France
(folium / Leaflet), les tournées en couleur avec leur sens de parcours, le tableau par camion,
le gap par rapport à la meilleure solution connue et la courbe de convergence.

Pas de serveur : c'est un fichier `.html` autonome (styles et carte inclus) que l'on ouvre
dans le navigateur. Aucun JavaScript n'est écrit à la main ; seuls les scripts de folium font
marcher la carte (zoom, info-bulles, bouton de couches).

## Utiliser

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r interface/requirements.txt

# meilleure solution connue (si un .sol est à côté du .vrp) : l'instance A-n32-k5, par exemple
python -m interface instances/A/A-n32-k5.vrp

# + un calcul avec un solveur du notebook, comparé à la meilleure connue
python -m interface instances/A/A-n32-k5.vrp --solveur recuit --temps 20 --graine 1
```

La page est écrite dans `sortie/<instance>.html` et s'ouvre toute seule. Options :

| Option | Rôle |
|---|---|
| `--solveur NOM` | calcule une solution (nom ou morceau du nom ; `--solveurs` liste les choix) |
| `--temps S`, `--graine N` | temps de calcul (défaut 10 s) et graine aléatoire (défaut 0) |
| `--zone NOM`, `--etendue KM` | où poser l'instance sur la carte (France entière, Grand Est, Île-de-France…) |
| `--sortie FICHIER` | autre emplacement pour la page |
| `--sans-ouvrir` | ne pas ouvrir le navigateur |

Pendant le calcul, la progression s'affiche dans le terminal (pas en direct sur la page).

## Dans la page

- Le bouton en haut à droite de la carte change le fond (rues, gris clair, satellite, tous Esri)
  et affiche ou masque « Ma solution », « Meilleure solution connue » (en tirets) et les clients.
- Survoler un client donne sa demande et son camion ; survoler un trajet donne sa charge et sa
  distance.
- Les tableaux « Ma solution » et « Meilleure solution connue » sont à la suite, avec des
  liens d'ancre en haut de page.

## Depuis un notebook

```python
from interface.instance import load_instance
from interface.page import build_page, write_page
from interface.solvers import make_solution

inst = load_instance("instances/A/A-n32-k5.vrp")
ma_solution = make_solution(inst, routes, "Mon solveur", history)   # routes = [[3, 7, 1], [2, 5]]
write_page("sortie/A-n32-k5.html", build_page(inst, mine=ma_solution, zone="Grand Est (Nancy)"))
```

## Solveurs

Ceux du livrable 2 (notebook), portés dans `interface/notebook_solvers.py` :
`Hill climbing (notebook)` et `Recuit simulé (notebook)`. L'en-tête du fichier liste les
cellules d'origine et les (rares) écarts avec le notebook : distances arrondies, temps
limite à la place du nombre d'itérations, graine configurable.

Limite héritée du notebook : `is_possible` exige au plus `k` camions, mais le glouton de
départ en utilise parfois plus (ex. A-n37-k6 : 7 pour k = 6). Aucun voisin n'est alors
accepté, l'algorithme reste bloqué et la page affiche « Solution invalide ».

### Brancher un autre solveur

Une fonction enregistrée avec `@register` apparaît dans `--solveur` :

```python
from interface.solvers import register, make_solution

@register("Mon solveur")
def mon_solveur(inst, time_limit, seed, on_progress=None):
    # inst.dist[i][j]  distances (arrondies comme TSPLIB pour EUC_2D)
    # inst.demand[i]   demande du sommet i (0 pour le dépôt)
    # inst.capacity    capacité d'un camion ; inst.n_vehicles = k annoncé par l'instance
    # sommet 0 = dépôt, clients = 1..n-1
    ...
    # à chaque amélioration, pour la progression affichée dans le terminal (optionnel) :
    #     on_progress(iteration, meilleur_cout, routes)
    return make_solution(inst, routes, "Mon solveur", history)
```

- `routes` : liste de tournées, chacune est la liste des clients dans l'ordre de visite,
  **sans le dépôt**. Exemple : `[[3, 7, 1], [2, 5]]`.
- `history` : liste de `(temps_s, iteration, meilleur_cout)` pour la courbe de convergence
  (peut être vide).
- La page vérifie la solution (chaque client une fois, capacité, au plus `k` camions) et
  affiche « Solution invalide » avec la raison si besoin.

## Choix à connaître

- Les instances VRPLIB n'ont pas de position géographique : les points sont posés sur la
  carte par homothétie autour de la zone choisie (`interface/geo.py`). Ils ne correspondent
  pas à de vraies villes, donc certains tombent en mer ou à l'étranger. Les trajets sont à
  vol d'oiseau, pas sur le réseau routier.
- Les distances sont arrondies à l'entier le plus proche pour `EUC_2D` (convention TSPLIB),
  sinon le gap ne serait pas comparable aux valeurs publiées (ex. A-n32-k5 : 784).
- Les fonds de carte demandent Internet. Ni CARTO (folium exige désormais une clé d'API) ni
  OpenStreetMap (ses serveurs peuvent refuser les pages ouvertes depuis un fichier local : erreur
  403 « Access blocked ») ne sont utilisés ; les fonds viennent d'Esri.
- La meilleure solution connue vient du fichier `.sol` du même nom, à côté du `.vrp`.

## Tests

```bash
pip install pytest
pytest tests
```
