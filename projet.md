# Projet

## Introduction

Depuis les années 90, il y a eu une véritable prise de conscience mondiale de la nécessité de réduire la consommation d'énergie et des émissions de gaz à effet de serre. Les premiers engagements sont apparus lors de la signature du protocole de Kyoto en 1997. Mais son entrée en vigueur n'a finalement eu lieu qu'en 2005 et de nombreux scientifiques ont jugé les efforts insuffisants pour ralentir le réchauffement climatique. Depuis, d'autres engagements plus ambitieux ont vu le jour (division par 4 des émissions d'ici 2050 pour la France par exemple, engagements de certaines grandes villes comme Paris). Mais la tâche est compliquée. Les pouvoirs publics et les collectivités territoriales n'ont pas la possibilité d'obliger les entreprises et les particuliers à changer leurs habitudes pour atteindre ces objectifs. L'action se porte donc avant tout à faire évoluer les comportements. L'économie et le recyclage des matières premières, l'amélioration des modes de transport et des performances énergétiques des bâtiments doivent devenir des priorités.

## Sujet

### Exercice

#### DESCRIPTION

L’ADEME (Agence de l’Environnement et de la Maîtrise de l’Energie) a récemment lancé un appel à manifestation d’intérêt pour promouvoir la réalisation de démonstrateurs et d’expérimentations de nouvelles solutions de mobilité pour les personnes et les marchandises adaptées à différents types de territoires.

Votre structure CesiCDP est déjà bien implantée dans le domaine. Aidé de nombreux partenaires, vous avez réalisé plusieurs études sur le thème de la Mobilité Multimodale Intelligente. Les nouvelles technologies de transport, plus économiques et moins polluantes ne sont pas sans poser de nouveaux défis notamment d’un point de vue de l’optimisation de la gestion des ressources. Mais ces problèmes de logistique du transport présentent un enjeu majeur pour l’avenir : ces applications sont nombreuses (distribution du courrier, livraison de produits, traitement du réseau routier, ramassage des ordures) et leur impact sur l’environnement peut être véritablement significatif.

Vous faites partie de l’équipe (4 personnes) mise en place par CesiCDP pour répondre à l’appel de l’ADEME. L’enjeu est d’obtenir de nouveaux marchés avec des financements très intéressants pour continuer à développer votre activité.

CesiCDP a décidé d’orienter son étude sur la gestion de tournées de livraison. Le problème algorithmique consiste à calculer sur un réseau routier une tournée permettant de relier entre elles un sous-ensemble de clients, puis de revenir à son point de départ, de manière à minimiser la durée totale de la tournée. Cette optimisation devra tenir compte du trafic prévu sur chaque axe pour les différentes tranches horaires.

L’idée est de proposer une méthode issue de la Recherche Opérationnelle pour générer une tournée de livraison correspondant à ce problème.

Le périmètre reste encore à préciser. Vous avez décrit une version de base du problème. Mais, afin de le rendre plus réaliste et retenir toute l’attention de l’ADEME, vous hésitez à ajouter des contraintes supplémentaires. Il faut s’attendre à ce qu’il soit ainsi plus dur à traiter.

- ***Version de base***

  - Le choix du modèle et le code en Python capable de résoudre des instances de taille importante (plusieurs milliers de villes)

  - Une étude statistique du comportement expérimental de l'algorithme

  - Une flotte de k camions de capacité identique

- **Version avancée**

  Fenêtre de temps de livraison pour chaque objet

  - Interdiction de livrer hors de la fenêtre

  - Possibilité d'attendre sur place l'ouverture de la fenêtre temporelle

#### ORGANISATION

L’échéance pour le dépôt des projets auprès de l’ADEME est fixée au 12 juillet prochain. Afin de tenir les délais et de préparer tous les rapports nécessaires, vous avez défini la feuille de route suivante :

1.  Modélisation formelle

2.  Conception algorithmique et implémentation

3.  Étude expérimentale

4.  Présentation du travail réalisé à votre équipe (en anglais) avant remise des livrables à l'ADEME

Chacune de ces étapes aboutira à un livrable que vous présenterez à votre responsable pour suivi et échanges. Ces livrables prendront la forme d’un Notebook présentant à la fois la démarche et le code correspondant (lorsqu’une implémentation est requise). L'aspect story-telling doit être privilégié dans la rédaction de chacun de ces Notebook.

Le code des différents livrables n'a pas à être au standard d'un code à industrialiser (pas besoin d'une grande modularité). Il doit en revanche rester lisible, commenté, et privilégier la performance. Il est fortement recommandé de suivre les recommandations PEP :

[https://openclassrooms.com/fr/courses/235344-apprenez-a-programmer-en-python/235263-de-bonnes-pratiques](https://openclassrooms.com/fr/courses/235344-apprenez-a-programmer-en-python/235263-de-bonnes-pratiques)

- ***Livrable Modélisation (check)***

  **Échéance :** au cours du prosit 3

  **Évaluation :** Non

  **Objectif :** Modéliser le problème au travers d'un Notebook Jupyter.

  **Description :** Ce premier livrable présente le problème que vous traitez ainsi que son contexte, le reformule de manière formelle, et en étudie les propriétés théoriques, notamment de complexité.

  D’une part, vous devrez proposer une représentation formelle des données, du problème, et de l’objectif à optimiser (en intégrant les contraintes supplémentaires que vous décidez de traiter). Cette formalisation devra permettre d’identifier la structure du problème et de le relier à des problèmes classiques de la littérature, afin d’en établir la complexité théorique (par exemple via une réduction vers un problème NP-difficile ou NP-complet).

  Une première version de la modélisation mathématique sous forme de Programme Linéaire en Nombres Entiers (PLNE) est attendue. Celle-ci devra inclure :

  - les variables de décision,

  - la fonction objectif,

  - l’ensemble des contraintes (y compris spécifiques au problème traité).

  Cette modélisation doit être suffisamment précise et rigoureuse pour être implémentée par la suite, sans pour autant nécessiter d’implémentation à ce stade. Les méthodes de résolution ne sont pas à aborder lors de ce check. Vous aurez l'occasion de les étudier en détails dans les boucles suivantes.

  Le point est réalisé avec le tuteur de projet afin de valider :

  - la pertinence de la formalisation,

  - la validité de la preuve de complexité,

  - la cohérence du modèle PLNE,

  Les éléments pourront ainsi être modifiés avant d'être intégrés dans le livrable final du projet.

  Recommandation :

  Il est fortement recommandé d’intégrer à ce notebook des références bibliographiques vers des articles ou des ouvrages scientifiques.

- **Livrable final du projet**

  **Échéance : la veille de la soutenance**

  **Évaluation : Oui**

  **Objectif :** Présenter l’ensemble de la démarche réalisée, la réalisation technique, et conclure sur les résultats obtenus.

  **Description :**

  1.  **Modélisation et méthodes de résolution** :

      Cette partie reprend et complète les éléments de modélisation formelle :

      - formalisation des données

      - preuve de complexité

      - modélisation mathématique sous forme de Programme Linéaire en Nombres Entiers (PLNE) complète et corrigée,

      - une présentation de l’utilisation éventuelle de cette approche exacte (résolution directe, benchmark, borne inférieure/supérieure, etc.),

      ainsi que :

      - la description de la méthode de résolution heuristique ou métaheuristique choisie,

      - sa formalisation adaptée au problème, incluant par exemple :

      - définition des solutions,

      - structure du voisinage (recherche locale, VNS, LNS, etc.),

      - opérateurs spécifiques (croisement, mutation, insertion, échange…),

      - mécanismes de guidage (ex : phéromones pour ACO, vitesses pour PSO, etc.).

  2.  **Implémentation :**

      Cette partie décrit la réalisation technique de la métaheuristique, incluant :

      - le fonctionnement général de l’algorithme,

      - les différentes étapes (initialisation, itérations, critères d’arrêt…),

      - les mécanismes internes (ex : sélection, croisement et mutation pour un algorithme génétique, évaporation des phéromones pour ACO, opérateurs de voisinage pour recherche locale, etc.),

      - l’implémentation des cas de test,

      - une démonstration du fonctionnement sur plusieurs instances (sans nécessité d’exhaustivité).

  3.  **Étude expérimentale**

      Cette partie analyse les performances de la solution proposée. Elle devra :

      - définir un plan d’expérience structuré, incluant différents scénarios de test (par exemple : taille des instances, répartition géographique, contraintes spécifiques comme les fenêtres de temps, etc.),

      - présenter les résultats expérimentaux (tableaux, indicateurs de performance, comparaisons),

      - analyser le comportement de l’algorithme (qualité des solutions, temps de calcul, robustesse, sensibilité aux paramètres…),

      - identifier les limitations de l’approche,

      - proposer des axes d’amélioration justifiés sur la base des observations.

      - La méthodologie expérimentale, les analyses statistiques et les conclusions devront être argumentées de manière rigoureuse.

- ***Soutenance***

  - **Échéance :** dernier jour du bloc

  - **Évaluation :** Oui

  - **Objectif :** Démontrer les capacités pour présenter oralement l'état d'avancement d'un projet dans un contexte professionnel

  - **Description :**

    - Elle doit être orientée résultats, avec démonstration de l’exécution du code (sur des cas suffisamment petits pour garder la présentation fluide) et présentation des résultats.

    - Il sera attendu une présentation de l'avancement du projet. Il est donc crucial de rappeler le contexte et les objectifs avant de mettre en valeur les réalisations et les résultats obtenus. Soyez transparents sur les défis rencontrés, mettez en évidence les étapes achevées, celles en cours et celles à venir (un planning/échéancier serait apprécié).

**Évaluation du projet (livrable final)**

**Travail attendu :**

1.  **Modélisation et résolution**

    Proposer :

    - un modèle mathématique (PLNE)

    - une métaheuristique (Recuit Simulé, Tabu Search, ALNS, etc.)

    - Implémenter en Python un solveur capable de traiter des instances de taille réaliste

    Livrable : code structuré et documenté (Notebook Jupyter ou script Python)

2.  **Analyse de performance**

    Évaluer :

    - la qualité des solutions

    - le temps de calcul (fonction de la taille de l’instance)

    - tester l’algorithme sur au moins 20 instances différentes issues de scénarios d’usages différents

    - Produire des analyses expérimentales (visualisations, statistiques, etc.) permettant de comprendre le comportement de votre approche

3.  **Validation sur instances de référence (VRPLIB)**

    - Utilisation de la bibliothèque `vrplib` pour charger des instances de référence.

    - Attendus :

    - comparaison avec les meilleures solutions connues

    - calcul du gap (%) défini par : gap = 100 x ((cout de votre solution - cout de la solution optimale) / cout de la solution optimale)

    - analyse des résultats obtenus

**Choix du problème :**

- **Niveau B (attendu)** : **CVRP** : véhicules avec capacité (identique pour tous les véhicules)

- **Niveau A (avancé)** : **CVRPTW** : véhicules avec capacité + **fenêtres de temps**

**Instances et analyse**

Des instances sont fournies pour les deux problèmes.

Les étudiants doivent :

- tester leur algorithme sur un ensemble varié d’instances,

- analyser les performances en fonction des caractéristiques des problèmes (sans nécessairement être exhaustif), par exemple :

- taille des instances,

- répartition des clients,

- contraintes du problème (capacité, fenêtres de temps, etc.).

L’objectif est de mettre en évidence le comportement de la méthode selon différents scénarios.

**Critères d’évaluation**

- Qualité des solutions (gap). Un gap supérieur à 7-10% entrainera une notation maximum de B

- Temps de calcul

- Qualité de l’analyse expérimentale

- Pertinence des conclusions

**Recommandations**

- Ne pas se limiter à présenter des résultats : les interpréter
- Identifier les forces et limites de votre approche
- Proposer des pistes d’amélioration

**Ressources** :

- [Tutoriels de validation et exemple de validation.](https://github.com/PyVRP/VRPLIB)
