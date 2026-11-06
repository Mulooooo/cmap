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
- Pendant un calcul, la page se recharge **toutes les secondes** (`<meta http-equiv="refresh">`) :
  c'est le polling de `GET /api/jobs/<id>`. La carte suit la meilleure solution trouvée.
- Une fois le calcul fini, les onglets **Ma solution / Meilleure solution connue** (en CSS) changent
  la carte et le tableau ; le bouton de couches de la carte permet aussi de superposer les deux.
- Un seul calcul à la fois : lancer un calcul pendant qu'un autre tourne affiche celui qui tourne.
- L'état de la page est dans l'URL (`?instance=…&zone=…&solver=…&job=…`) : on peut la copier.

## Remplacer l'affichage plus tard

Le front est volontairement mince et **isolé du reste** :

| Fichier | Rôle | À changer si on refait le front ? |
|---|---|---|
| `web/api_client.py` | **le seul fichier qui parle au serveur de calcul** (une méthode par route de l'API) | non, à réutiliser |
| `web/views.py` | routes du site, calcul des chiffres affichés | en partie |
| `web/figures.py`, `web/geo.py` | cartes folium, courbe SVG, placement des points | selon la techno de carte |
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
