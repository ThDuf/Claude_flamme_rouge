# Plan : une seule interface, dans le navigateur, puis une vraie 3D

## 1. Le constat (novembre 2026)

Le jeu a deux interfaces :

- **sur le PC** : tkinter (`main.py`, `menu.py`, `gui.py`, `editor.py`, `tour_screens.py`, `ui.py`) ;
- **en ligne** : `online/server.py` + `online/rooms.py`, et la page `online/static/` (Canvas 2D).

Le dessin n'est pas entièrement écrit deux fois : `boardview.py` calcule des formes (« primitives ») que le
serveur envoie au navigateur, qui ne fait que les peindre. Mais tout ce qui bouge (coureurs, animations, météo,
cyclistes de la vue 3D, zoom) est recodé dans `app.js`, avec des commentaires « comme boardview.… ». Chaque
nouveauté visuelle se fait donc deux fois, et la vue 3D (projection isométrique faite à la main, `iso.py`)
ne pourra pas aller beaucoup plus loin : pas de lumière, pas de caméra libre, pas de modèles.

Ce qui existe seulement sur le PC :

| Fonction | Fichier(s) tkinter | En ligne ? |
|---|---|---|
| Grand Tour (étapes, classements, maillots, écrans entre étapes, classement final) | `menu.py`, `tour_screens.py`, `gui.py` | non |
| Éditeur de parcours | `editor.py` | non (et les parcours du PC ne sont pas proposés sur Render) |
| Partie à plusieurs sur le même écran, main cachée entre deux équipes (`--secret`) | `gui.py` | non (chacun joue sur son appareil, ou l'écran partagé) |
| Mini-carte, suivi de la tête ou du peloton | `gui.py`, `boardview.py` | en partie (caméra « suivre ») |

## 2. La cible

- **Python reste** pour le moteur de règles (`flamme_rouge/`) et le serveur (`online/`). Il est testé et
  n'a besoin de rien d'autre que la bibliothèque standard, et Render le déploie sans étape de build.
- **Le navigateur devient la seule interface**, en local comme en ligne. Pour jouer sur le PC, on lance
  `python main.py`, qui démarre le serveur sur `127.0.0.1` et ouvre le navigateur.
- **La vraie 3D passe par Three.js**, en module JavaScript copié dans `online/static/vendor/`. Pas de CDN ni
  de npm : le site reste un dossier de fichiers statiques.
- **Le serveur envoie la scène, pas des pixels.** Pour la 3D, le navigateur a besoin des cases en coordonnées
  du monde (coins, altitude, files, terrain), des coureurs et des zones de météo. C'est lui qui fait la
  projection.

## 3. Les étapes

Chaque étape correspond à une PR, et le jeu reste jouable après chacune.

### Étape 1 : le mode local passe par le navigateur (faite)

Réalisée un peu différemment de ce qui était prévu ci-dessous : `main.py` fait tourner le serveur lui-même
(pas dans un thread) sur un port libre, les parcours de `parcours/` étaient déjà proposés, et le mode « même
écran » n'est pas un type de salon : un joueur peut tenir plusieurs équipes (« + Ici aussi »), ce qui permet
de mélanger même écran et appareils distants. Voir `en_ligne.md`, « Jouer sur ce PC ».

- `main.py` démarre `online.server` dans un thread, sur `127.0.0.1` avec un port libre, puis appelle
  `webbrowser.open(...)`. Le serveur s'arrête avec la fenêtre de commande.
- En local, le serveur propose aussi les parcours du dossier `parcours/`, ce qu'il ne fait pas sur Render
  (voir `en_ligne.md`).
- Nouveau mode **« même écran »** : un salon dont toutes les places « Joueur » sont tenues par le même
  navigateur. La page affiche à tour de rôle la main de chaque équipe, avec un écran « passe l'appareil » si
  l'option *main cachée* est cochée. Ce mode remplace `gui.py --secret`.
- tkinter reste disponible, avec `python main.py --tk`, jusqu'à l'étape 4.

### Étape 2 : le Grand Tour en ligne (faite)

Le salon a un mode « Grand Tour » (liste d'étapes, jour de repos) ; `Room` garde un `Tour` et passe par
`/api/tour_next` de l'arrivée aux résultats, puis à l'étape suivante. Tests : `tests/test_online_tour.py`.

- `Room` contient un `Tour` (`flamme_rouge/tour.py`) au lieu d'une seule `Game`. Le salon choisit les étapes,
  et après chaque arrivée on passe à un écran « résultats de l'étape » avant l'étape suivante.
- `state()` envoie les classements (général, points, montagne) et les maillots. La page reprend les deux
  écrans de `tour_screens.py`.
- Tests : étendre `tests/test_online.py` avec une partie complète de deux étapes, jouée par l'IA.

### Étape 3 : l'éditeur de parcours dans le navigateur

- Nouvelle page `editor.html` : la palette des tuiles, le plan, l'aperçu et le profil. Le serveur fournit
  déjà `tile_card_primitives`, `plan_preview_primitives` et `track_preview_primitives`.
- API : `GET /api/tiles`, `POST /api/parcours` (enregistre dans `parcours/`, **en local seulement**), et
  `GET /api/parcours/<nom>`.
- En ligne, l'éditeur peut servir à créer un parcours pour un salon. Il est alors gardé dans le salon, pas
  sur le disque de Render.

### Étape 4 : retrait de tkinter

- Supprimer `gui.py`, `menu.py`, `ui.py`, `editor.py`, `tour_screens.py` et l'option `--tk`.
- Dans `boardview.py`, garder seulement ce que le serveur utilise. Les fonctions de dessin qui n'ont plus
  d'appelant disparaissent.
- Adapter `tests/test_ui_smoke.py` (fenêtres tk) et `tests/test_views.py`. Les tests des primitives restent
  tant que la 2D les utilise.
- `play_human.py` et `play_random.py` (terminal) restent : ils ne dépendent pas de tkinter.

### Étape 5 : la scène en coordonnées du monde

- Nouveau `flamme_rouge/scene.py`, qui renvoie la route en JSON à partir de `geometry.layout_squares` et de
  `boardview.road_altitudes` : pour chaque case, ses quatre coins (x, y), son altitude, ses files, son
  terrain (montée, descente, pavés, ravitaillement, arrivée), plus les coureurs (case, file) et les zones de
  météo.
- `state()` l'envoie **une fois par course**, puis seulement les positions des coureurs. C'est plus léger
  que les primitives actuelles, qui sont recalculées à chaque version.
- `tests/test_scene.py` vérifie que les coins collent avec `SquareGeom` et que les altitudes collent avec le
  profil.

### Étape 6 : la vue Three.js

- `online/static/board3d.js` (module ES, sans build) :
  - la route est un maillage construit à partir des coins des cases, avec des côtés jusqu'au sol. La couleur
    dépend du terrain, et les lignes de files et le damier de l'arrivée sont dessinés en texture ;
  - les coureurs sont des modèles simples (vélo et coureur en quelques formes, aux couleurs de l'équipe) ;
    les maillots et les noms sont des étiquettes HTML posées au-dessus ;
  - la caméra est libre (rotation, zoom, déplacement avec la souris ou les doigts), avec des préréglages
    « vue d'ensemble », « suivre la tête » et « suivre le peloton » ;
  - les animations de mouvement et d'aspiration interpolent le long de la route, comme `roadPoint` dans
    `app.js` aujourd'hui ;
  - la météo devient des particules (pluie, vent) au-dessus des zones concernées.
- Le bouton « Vue 3D » ouvre cette vue à la place de l'isométrique. La 2D Canvas reste la vue par défaut :
  elle est plus lisible sur un petit téléphone.
- Quand la 3D est au point, supprimer `iso.py` et le code `proj` de `boardview.py`.
- Garder les visuels **faits maison** : pas d'images officielles de la boîte (voir `portage_bga.md`).

### Étape 7 (optionnelle) : TypeScript

À faire quand `app.js` et `board3d.js` dépassent quelques milliers de lignes. On passe le client en
TypeScript avec Vite. Il y a alors une étape de build, et la commande `buildCommand` de `render.yaml` doit
changer. Le moteur reste en Python. On ne le porte en TypeScript que pour jouer hors ligne sans serveur, ou
pour réutiliser ce code dans le portage BGA (côté client).

## 4. Ce qu'on ne change pas

- **L'interrogation du serveur deux fois par seconde** (`/api/state?since=`) suffit pour un jeu au tour par
  tour. Les WebSockets ne sont pas nécessaires.
- **Les salons restent en mémoire.** On ne leur ajoutera une sauvegarde que si les redémarrages de Render
  gênent vraiment.
- **Le moteur de règles** et ses tests ne bougent pas, sauf pour l'étape 2 (`Tour` dans un salon).

## 5. L'ordre et la taille

| Étape | Taille | Dépend de |
|---|---|---|
| 1. Local par le navigateur | petite | rien |
| 2. Grand Tour en ligne | moyenne | rien |
| 3. Éditeur web | moyenne | rien |
| 4. Retrait de tkinter | petite | 1, 2 et 3 |
| 5. Scène en coordonnées du monde | petite | rien |
| 6. Vue Three.js | grande | 5 |
| 7. TypeScript | moyenne | quand le besoin s'en fait sentir |

Les étapes 2, 3 et 5 sont indépendantes et peuvent avancer en parallèle. Pour une 3D le plus vite possible,
on peut faire 5 puis 6 d'abord : la vue Three.js fonctionne en ligne avant même que tkinter soit retiré.
