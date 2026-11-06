# Le site (Flask + folium)

Un second serveur Flask, séparé du serveur de calcul : il affiche des pages HTML (+ cartes
folium, **aucun JavaScript écrit à la main**) et ne fait que **parler au serveur de calcul par
requêtes API** ([docs/api.md](api.md)). Les métaheuristiques ne tournent jamais dans le site.

```
navigateur ──formulaires HTML──►  site (web/, port 5002)  ──requêtes HTTP/JSON──►  serveur de calcul (server/, port 5001)
          ◄──pages + cartes folium──                       ◄──────────────────       └─ un processus par métaheuristique
```

## Lancer (deux terminaux)

```bash
python -m server      # 1) le serveur de calcul  -> http://127.0.0.1:5001/api/health
python -m web         # 2) le site               -> http://127.0.0.1:5002
```

- `python -m web --api http://autre-machine:5001` ou la variable `API_URL` : adresse du serveur de calcul.
- `--port` / `PORT` : port du site (5002 par défaut ; le 5000 est pris par AirPlay sur macOS).
- Si le serveur de calcul est éteint, la page le dit (« Serveur de calcul injoignable ») et le bouton Calculer est grisé.

## Ce que fait la page

| Zone | Rôle | Appel API |
|---|---|---|
| Instance | choisir une instance du serveur, ou envoyer un fichier `.vrp` | `GET /api/instances`, `GET /api/instances/<id>`, `POST /api/instances` |
| Carte | zone (France, Grand Est…) et étendue de l'instance sur la carte | aucun (le placement se fait dans le site) |
| Calcul | métaheuristique, temps limite, graine, **▶ Calculer** / **■ Arrêter** | `GET /api/solvers`, `POST /api/jobs`, `POST /api/jobs/<id>/stop` |
| Résultats | carte, coût, gap, tableau par camion, courbe de convergence | `GET /api/jobs/<id>` |

- La page affiche d'abord la **meilleure solution connue** de l'instance (fichier `.sol`).
- Pendant un calcul, la page **ne se recharge pas toute seule** (un rechargement automatique fait clignoter la
  carte, et sans JavaScript on ne peut pas faire autrement). Le bandeau « Calcul en cours » a un bouton
  **↻ Actualiser** : chaque clic relit l'état du calcul (`GET /api/jobs/<id>`) et redessine la carte avec la
  meilleure solution trouvée. **■ Arrêter** garde la meilleure solution trouvée jusque-là.
- Une fois le calcul fini, les onglets **Ma solution / Meilleure solution connue** (en CSS) changent
  la carte et le tableau ; le bouton de couches de la carte permet aussi de superposer les deux.
- Un seul calcul à la fois : lancer un calcul pendant qu'un autre tourne affiche celui qui tourne.
- L'état de la page est dans l'URL (`?instance=…&zone=…&solver=…&job=…`) : on peut la copier.

## Simulation sur les vraies routes

Sous chaque solution (**Ma solution**, une fois le calcul fini ou arrêté, et **Meilleure solution
connue**), le bouton **▶ Simuler sur les vraies routes** **reste sur la même page** (`?…&sim=mine|best#carte`) :
la carte de la page est remplacée par une animation folium où les camions partent du dépôt à 8 h et
roulent de client en client **dans l'ordre de la solution**, par les vraies routes (chaque camion est une icône
camion de la couleur de sa tournée), avec 10 minutes de
livraison chez chaque client. Le lecteur ▶ (vitesse, curseur d'heure, bouton de couches) est dans la
carte ; un tableau sous la carte donne par camion la route réelle, le plan de l'instance, la conduite,
la durée avec livraisons et l'heure de retour. **Quitter la simulation** (bandeau ou bouton) ramène la carte
habituelle ; « Afficher » avec une autre zone ou étendue relance la simulation à la nouvelle échelle ; un nouveau
calcul l'arrête.

- Ce n'est **pas exactement ce que la métaheuristique a calculé** : elle travaille sur les distances
  du plan de l'instance (points posés sur la carte par homothétie), la simulation utilise les routes
  réelles, donc les distances et les durées sont différentes. Seul l'ordre des tournées est repris.
- Les itinéraires viennent d'**OSRM** (données OpenStreetMap), appelé depuis le site (`web/routing.py`) :
  une requête par camion, espacées d'au moins 1,1 s (le serveur public est un service de démonstration,
  il limite le débit). Compter ~1 s par camion la première fois ; les réponses sont gardées en mémoire.
  `OSRM_URL` permet d'utiliser un OSRM installé sur la machine.
- Il faut Internet. Si OSRM ne répond pas, la page le dit ; si un trajet est introuvable (point en mer...),
  ce camion est tracé à vol d'oiseau avec un avertissement.
- À l'échelle « France entière » les tournées de A-n32-k5 durent plus d'une journée. Pour des tournées
  plus réalistes, réduire l'**Étendue** de la carte (environ 100 km pour des tournées de 2 à 10 h) puis cliquer sur Afficher.
- Fichiers : `web/routing.py` (client OSRM), `web/simulation.py` (horaires le long du tracé et carte
  animée), `web/views.py` (paramètre `sim` de la page, et `/simulation/map/<id>` qui sert la carte animée).

## Remplacer l'affichage plus tard

Le front est volontairement mince et **isolé du reste** :

| Fichier | Rôle | À changer si on refait le front ? |
|---|---|---|
| `web/api_client.py` | **le seul fichier qui parle au serveur de calcul** (une méthode par route de l'API) | non, à réutiliser |
| `web/views.py` | routes du site, calcul des chiffres affichés | en partie |
| `web/figures.py`, `web/geo.py`, `web/simulation.py`, `web/routing.py` | cartes folium, courbe SVG, placement des points, simulation sur les routes (OSRM) | selon la techno de carte |
| `web/templates/` | HTML et CSS | oui |

Le serveur de calcul n'a rien à changer : un autre front (React, Vue, autre) n'a qu'à appeler les
mêmes routes (avec `CORS_ORIGINS` côté serveur de calcul pour autoriser son adresse).

## Choix à connaître

- Les instances VRPLIB n'ont pas de position géographique : les points sont posés sur la carte par
  homothétie (ils ne correspondent pas à de vraies villes), les trajets sont à vol d'oiseau.
- Pour la meilleure solution connue et pendant un calcul, le site recalcule charge et distance de chaque
  tournée à partir des coordonnées (distance arrondie, comme TSPLIB) ; une fois le calcul fini, il
  affiche les chiffres vérifiés par le serveur de calcul. Un test vérifie que les deux retombent sur 784
  pour A-n32-k5.
- Les fonds de carte (Esri) demandent Internet. OpenStreetMap et CARTO ne sont pas utilisés : le
  premier refuse parfois les pages sans `Referer`, le second exige une clé d'API avec folium.

## Tests

```bash
pytest tests/test_web.py     # avec un faux serveur de calcul, puis avec le vrai (en mémoire)
```
