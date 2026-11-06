# API du serveur (Flask)

Le serveur charge des instances VRPLIB et lance une métaheuristique Python choisie par son
nom. Le site lui parle en HTTP avec du JSON.

> Statut : **proposition à valider par l'équipe**, avant de coder les routes.

## Principes

- **Un seul calcul à la fois.** Lancer un calcul pendant qu'un autre tourne est refusé (`409`).
- **Les métaheuristiques sont celles du livrable 2** (notebooks), pour le moment : `hill_climbing`
  et `simulated_annealing`. Il suffira d'en ajouter à la liste pour qu'elles apparaissent.
- **Suivi par polling** : pendant un calcul, le site demande l'état toutes les **1 seconde**.
- Adresse de base : `/api`. Corps de requête et de réponse en JSON (UTF-8), sauf l'envoi d'un
  fichier `.vrp`.

## Conventions

| Sujet | Règle |
|---|---|
| Numérotation | Les sommets sont numérotés **0, 1, 2…** : le **0 est le dépôt**, les clients vont de 1 à n−1. Les tableaux `coords` et `demand` sont indexés par ce numéro. |
| Tournées | Une tournée est la liste des clients dans l'ordre de visite, **sans le dépôt** : `[[21, 31, 19], [12, 1]]`. |
| Distances | Calculées par le serveur, **arrondies à l'entier le plus proche** pour `EUC_2D` (convention TSPLIB, c'est ce qu'utilisent les optimums publiés). Le serveur ne renvoie pas la matrice, seulement les coordonnées. |
| Coût et gap | `gap = 100 × (coût − meilleure connue) / meilleure connue`, en pourcentage. `null` si l'instance n'a pas de meilleure solution connue. |
| Placement sur une carte | Le serveur renvoie les coordonnées **brutes** de l'instance. Les poser sur une carte est l'affaire du site. |
| Temps | En secondes, nombres décimaux. |

## Erreurs

Toutes les erreurs ont le même format, avec le bon code HTTP :

```json
{ "error": "Instance inconnue : A-n99-k9", "code": "not_found" }
```

| HTTP | `code` | Quand |
|---|---|---|
| 400 | `invalid_file` | fichier `.vrp` absent, illisible ou qui n'est pas un CVRP |
| 404 | `not_found` | instance, solveur ou calcul inconnu |
| 409 | `busy` | un calcul est déjà en cours (la réponse contient son `job_id`) |
| 413 | `too_large` | fichier envoyé de plus de 20 Mo |
| 422 | `invalid_param` | paramètre manquant ou hors limites (la réponse contient `field`) |
| 500 | `server_error` | erreur inattendue du serveur (le serveur reste en vie) |

## Les routes

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/health` | le serveur répond-il ? |
| GET | `/api/solvers` | liste des métaheuristiques |
| GET | `/api/instances` | liste des instances disponibles |
| GET | `/api/instances/<id>` | détail d'une instance (coordonnées, demandes, meilleure solution connue) |
| POST | `/api/instances` | envoyer un fichier `.vrp` |
| POST | `/api/jobs` | lancer un calcul |
| GET | `/api/jobs/<job_id>` | état d'un calcul, avec la meilleure solution trouvée |
| POST | `/api/jobs/<job_id>/stop` | arrêter un calcul |

---

### `GET /api/health`

```json
{ "status": "ok" }
```

### `GET /api/solvers`

```json
[
  { "id": "hill_climbing", "name": "Hill climbing", "description": "Montée de colline avec le voisinage relocate (livrable 2)" },
  { "id": "simulated_annealing", "name": "Recuit simulé", "description": "Recuit simulé avec le voisinage relocate (livrable 2)" }
]
```

`id` est ce qu'on envoie à `POST /api/jobs` ; `name` est fait pour être affiché.

### `GET /api/instances`

Les fichiers de `instances/` (sous-dossiers compris) : l'`id` est le nom du fichier sans
extension, unique dans VRPLIB.

```json
[
  { "id": "A-n32-k5", "name": "A-n32-k5", "n_clients": 31, "capacity": 100, "n_vehicles": 5,
    "best_known_cost": 784, "has_best_known_routes": true, "source": "library" }
]
```

### `GET /api/instances/<id>`

Réponse abrégée (`coords` et `demand` ont une entrée par sommet, dépôt compris, soit 32 ici) :

```json
{
  "id": "A-n32-k5",
  "name": "A-n32-k5",
  "source": "library",
  "n_clients": 31,
  "capacity": 100,
  "n_vehicles": 5,
  "edge_weight_type": "EUC_2D",
  "coords": [[82, 76], [96, 44], [50, 5]],
  "demand": [0, 19, 21],
  "best_known": {
    "cost": 784,
    "routes": [[21, 31, 19, 17, 13, 7, 26], [12, 1, 16, 30], [27, 24],
               [29, 18, 8, 9, 22, 15, 10, 25, 5, 20], [14, 28, 11, 4, 23, 3, 2, 6]]
  }
}
```

- `n_vehicles` : nombre de camions annoncé par l'instance (`k` de `A-n32-k5`), ou `null`.
- `best_known` : lu dans le fichier `.sol` voisin ; `null` s'il n'y en a pas (`best_known.cost`
  peut alors exister seul, lu dans le commentaire du `.vrp`, avec `routes: null`).
- Erreur : `404 not_found` si l'`id` n'existe pas.

### `POST /api/instances`

Envoi d'un fichier `.vrp` en `multipart/form-data`, champ **`file`** (20 Mo maximum) :

```bash
curl -F file=@A-n32-k5.vrp http://127.0.0.1:5000/api/instances
```

Réponse `201` : le même JSON que `GET /api/instances/<id>`, avec `"source": "upload"` et un
`id` généré (`up-3fa9c1d2`). Pas de `best_known.routes` (il n'y a pas de `.sol`). Les envois ne
sont gardés qu'en mémoire : un redémarrage du serveur les oublie.

Erreurs : `400 invalid_file`, `413 too_large`.

### `POST /api/jobs`

Lance un calcul.

```json
{ "instance_id": "A-n32-k5", "solver": "hill_climbing", "time_limit": 10, "seed": 0 }
```

| Champ | Type | Règle |
|---|---|---|
| `instance_id` | texte | obligatoire, une instance existante |
| `solver` | texte | obligatoire, un `id` de `GET /api/solvers` |
| `time_limit` | nombre | secondes, de 1 à 300, défaut 10 |
| `seed` | entier | ≥ 0, défaut 0 (même graine = même calcul) |

Réponse `202` :

```json
{ "job_id": "9f2c4a7b1e03", "status": "running" }
```

Erreurs : `404 not_found` (instance ou solveur), `422 invalid_param`, `409 busy` :

```json
{ "error": "Un calcul est déjà en cours", "code": "busy", "job_id": "9f2c4a7b1e03" }
```

### `GET /api/jobs/<job_id>`

L'état du calcul. À appeler **toutes les secondes** tant que `status` vaut `running`.

```json
{
  "job_id": "9f2c4a7b1e03",
  "instance_id": "A-n32-k5",
  "solver": "hill_climbing",
  "time_limit": 10,
  "seed": 0,
  "status": "running",
  "elapsed": 3.4,
  "best_cost": 903,
  "version": 41,
  "routes": [[16, 21, 31, 19, 17, 13], [6, 28, 4, 11, 8, 18, 14], [26, 7, 2, 3, 23, 9, 22, 24],
             [20, 5, 25, 10, 15, 29, 27], [30, 1, 12]],
  "history": [[0.0, 0, 2082], [0.0, 1, 2081], [0.0, 3, 1973]],
  "result": null,
  "error": null
}
```

| Champ | Sens |
|---|---|
| `status` | `running`, `done` (le solveur a fini), `stopped` (arrêté avec `/stop`), `error` |
| `elapsed` | temps écoulé depuis le lancement |
| `best_cost` | coût de la meilleure solution trouvée jusque-là |
| `version` | nombre qui augmente à chaque amélioration : s'il n'a pas changé, rien de nouveau à redessiner |
| `routes` | tournées de la meilleure solution trouvée jusque-là |
| `history` | courbe de convergence : `[temps, itération, meilleur coût]`, au plus 500 points |
| `result` | `null` tant que le calcul tourne ; sinon le résultat final (ci-dessous) |
| `error` | message si `status` vaut `error`, sinon `null` |

**Option pour alléger le polling :** `GET /api/jobs/<job_id>?since=41`. Si `version` n'a pas
dépassé 41, la réponse a `routes` et `history` à `null` (seuls `status`, `elapsed`, `best_cost`
et `version` sont à jour).

Quand le calcul est fini (`done` ou `stopped`), `result` est rempli :

```json
"result": {
  "cost": 870,
  "gap": 10.97,
  "valid": true,
  "errors": [],
  "n_routes": 5,
  "elapsed": 3.0,
  "routes": [[16, 21, 31, 19, 17, 13], [6, 28, 4, 11, 8, 18, 14], [26, 7, 2, 3, 23, 9, 22, 24],
             [20, 5, 25, 10, 15, 29, 27], [30, 1, 12]],
  "per_route": [
    { "n_clients": 6, "load": 98, "distance": 155 },
    { "n_clients": 7, "load": 70, "distance": 215 },
    { "n_clients": 8, "load": 97, "distance": 233 },
    { "n_clients": 7, "load": 91, "distance": 195 },
    { "n_clients": 3, "load": 54, "distance": 72 }
  ]
}
```

- `valid` : le serveur **vérifie toujours** la solution (chaque client visité une fois, charge ≤
  capacité, nombre de camions ≤ `n_vehicles`). Si elle est invalide, elle est quand même
  renvoyée, avec la raison dans `errors` (ex. `"7 camions utilisés pour une flotte de 6"`) : le
  site doit l'afficher comme invalide.
- `status: "error"` : `result` est `null`, `error` explique (solveur planté, ou temps limite
  dépassé : un solveur qui ne rend pas la main est arrêté de force après `time_limit` + 5 s).
- Les 20 derniers calculs sont gardés ; un calcul oublié répond `404 not_found`.

### `POST /api/jobs/<job_id>/stop`

Arrête le calcul et garde la meilleure solution trouvée. Réponse `200` : le même JSON que
`GET /api/jobs/<job_id>`, avec `status: "stopped"` et `result` rempli. Sans effet si le calcul
est déjà fini (on renvoie son état tel quel).

## Exemple complet

```bash
curl http://127.0.0.1:5000/api/solvers
curl http://127.0.0.1:5000/api/instances
curl http://127.0.0.1:5000/api/instances/A-n32-k5

curl -X POST http://127.0.0.1:5000/api/jobs -H 'Content-Type: application/json' \
     -d '{"instance_id": "A-n32-k5", "solver": "hill_climbing", "time_limit": 10, "seed": 0}'
# -> {"job_id": "9f2c4a7b1e03", "status": "running"}

curl http://127.0.0.1:5000/api/jobs/9f2c4a7b1e03          # à répéter chaque seconde
curl -X POST http://127.0.0.1:5000/api/jobs/9f2c4a7b1e03/stop
```

## Pas dans cette version

- Plusieurs calculs en même temps, file d'attente.
- Fenêtres de temps (CVRPTW).
- Campagne d'expériences sur plusieurs instances (`/api/batches`), prévue ensuite.
- Authentification : le serveur est prévu pour un usage local (`127.0.0.1`). Les appels depuis
  l'adresse du site seront autorisés par une configuration CORS (variable d'environnement).
