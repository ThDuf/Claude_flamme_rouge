# Jouer à distance

Le jeu en ligne est hébergé sur **Render** : un petit serveur Python (bibliothèque standard, rien à installer)
sert une page web et garde l'état des parties. Tout le monde joue depuis son navigateur, ordinateur ou
téléphone, à une adresse fixe, sans que ton PC soit allumé.

## Héberger sur Render (gratuit)

Le site tourne chez Render, à une adresse fixe (`https://flamme-rouge-xxxx.onrender.com`). Le fichier
`render.yaml` décrit le service ; le serveur prend le port donné par Render (variable `PORT`) et écoute alors
pour tout Internet.

1. Créer un compte sur render.com (gratuit, sans carte) en se connectant avec GitHub.
2. **New** → **Blueprint**, choisir le dépôt `Claude_flamme_rouge` et la branche à déployer, puis **Apply**.
   Render lit `render.yaml` et crée le service web `flamme-rouge` (offre Free).
3. Au bout d'une minute ou deux, l'adresse du site apparaît en haut de la page du service : c'est le lien à
   ouvrir sur le téléphone et à envoyer.
4. Chaque push sur la branche choisie redéploie le site (les parties en cours sont alors perdues).

Limites de l'offre gratuite : sans visite pendant ~15 minutes, le serveur s'endort ; la visite suivante le
réveille en ~30 secondes à 1 minute. Pendant une partie, les navigateurs interrogent le serveur deux fois par
seconde, donc il reste éveillé. S'il s'endort ou redémarre, les salons sont perdus (ils ne vivent qu'en
mémoire). Les parcours enregistrés avec l'éditeur sur ton PC ne sont pas proposés sur Render.

Pour essayer une modification sur ton PC avant de la pousser : `python -m online.server`, puis
`http://127.0.0.1:8770` (le serveur n'écoute alors que ce PC).

## Jouer sur ce PC

`python main.py` démarre le serveur sur ce PC seulement (un port libre) et ouvre la page dans le navigateur.
Les parcours enregistrés avec l'éditeur (dossier `parcours/`) y sont proposés.

**Plusieurs joueurs sur un seul écran** : dans le salon, « + Ici aussi » ajoute une équipe jouée depuis le même
appareil (« Lâcher » la rend). Les mains restent cachées : chaque équipe voit ses cartes (et son deck) seulement
après un écran « passe l'appareil ». On peut mélanger : deux équipes sur le PC, une troisième sur un téléphone
qui rejoint avec le code.

## Une partie

- **Créer une partie** : tu deviens l'hôte. Envoie le lien du salon (il contient le code à 4 lettres) ou le code.
- Chacun **prend une place** (une équipe). L'hôte choisit le parcours, le nombre d'équipes, les extensions et,
  pour chaque équipe : Joueur, IA, ou équipe fantôme Peloton / Muscle (extension Peloton).
  Une place « Joueur » restée libre au départ est jouée par l'IA.
- Pendant la course, chacun ne voit **que ses mains**. Au début du tour, tous les coureurs piochent en même
  temps : chaque joueur voit les mains de son rouleur et de son sprinteur ensemble, touche une carte dans
  chacune (on peut changer d'avis), puis **Valider mes cartes**. Tous les joueurs choisissent en même temps ;
  quand toutes les cartes sont posées, n'importe quel joueur lance le mouvement, l'aspiration et la fatigue.
  (Les enchères de la variante Échappée restent une équipe après l'autre.)
- **Deck** : l'onglet sur le bord droit de l'écran ouvre ou cache le deck de départ de tes coureurs (cartes et
  nombre d'exemplaires). Le navigateur se souvient s'il est ouvert.
- **📺 Écran partagé** (salon et course) : ouvre une fenêtre avec le plateau seulement, sans main, sans deck et
  sans bouton de jeu, à mettre sur une télé, un vidéoprojecteur ou en partage d'écran. Son adresse
  (`…?code=CODE&watch=1`) s'ouvre sur n'importe quel appareil, sans prendre de place dans le salon.
- Vue 3D (option, la 2D par défaut ; réglage de chaque navigateur) : bouton « Vue 3D », une vraie scène 3D
  (Three.js) avec le relief (la route posée sur des collines qui la suivent), des coureurs qui pédalent (en danseuse en montée, en roue libre en descente), le rouleur
  et le sprinteur reconnaissables, l'aspiration et les chutes visibles,
  au clic sur « Fatigue », ceux qui prennent une carte Fatigue en rouge avec un halo, et la météo animée. Clic gauche = déplacer, clic molette (ou droit) = tourner,
  molette ou ＋/－ = zoom, ⟲ ⟳ = tourner de 30° ; les zooms peloton et tête de course suivent le groupe. La météo y
  est en 3D : nuage, pluie, éclaboussures et route mouillée ; filets de vent et manche à air
  tournée dans le sens du vent. Dans le salon, le même bouton montre en 3D le parcours choisi.
- Sur un grand écran (1500 px et plus) : la main à gauche du plateau, le bouton d'action et le journal à droite. Three.js est servi par le site
  lui-même (`online/static/vendor/`) : la 3D marche aussi sans internet, en local.
- Caméra : tout le parcours, zoom peloton, zoom tête de course ou vue course (tous les coureurs dans le cadre
  et les 5 prochaines cases ;
  chacun la sienne), ou cadrage libre : molette,
  boutons ＋/－, glisser la carte. Le navigateur agrandit tout de suite ce qu'il a, puis le serveur envoie un dessin
  net de ce cadrage. Les canvas ont autant de pixels qu'ils en occupent à l'écran : la carte reste nette.
- Recharger la page ramène dans la partie (le navigateur garde ta place). À l'arrivée, l'hôte peut revenir au
  salon pour une revanche.

## Sécurité

- Le serveur tourne chez Render, pas sur ton PC : ton adresse IP n'est pas montrée et aucun port n'est ouvert
  sur ta box.
- Il ne sert que les pages du jeu et de l'éditeur (`online/static`) et l'API du jeu : aucun accès au reste du dépôt ;
  sur Render, l'éditeur n'écrit aucun fichier.
- Toute personne qui a le lien peut ouvrir la page ; pour entrer dans une partie, il faut son code.

- Animations (bouton « Animations », réglage de chaque navigateur) : les coureurs roulent pendant le mouvement
  (l'un après l'autre, du premier au dernier) et l'aspiration ; pluie, vent et soleil animés sur la carte et le
  profil (extension Météo). Elles ne se rejouent pas quand on recharge la page.

- Variante Échappée (extension Peloton, parcours avec une tuile Échappée) : l'hôte la coche dans le salon. Avant
  le départ, chaque équipe à son tour choisit un coureur (ou passe) et mise deux cartes ; l'IA enchérit seule,
  les équipes fantômes ne participent pas.

## Grand Tour

Dans le salon, l'hôte choisit **Grand Tour** au lieu de **Course unique**, puis compose le Tour : « Ajouter ce
parcours au Tour » ajoute le parcours affiché, ▲ ▼ changent l'ordre, ✕ enlève une étape, « 6 officielles » met
les six cartes étape du jeu. Il faut au moins 3 étapes (21 au plus) ; un jour de repos peut suivre une étape.

Pendant une étape, un bandeau rappelle l'étape, les maillots et le haut du général. À l'arrivée, n'importe quel
joueur ouvre les **résultats de l'étape** (arrivée, jetons, général, maillots, Points de Tour, sprint, montagne),
puis lance l'étape suivante. Après la dernière étape : bonus des classements et classement final du Tour. L'hôte
peut abandonner le Tour depuis l'écran des résultats (retour au salon).

## Éditeur de parcours

Lien « ✎ Éditeur de parcours » sur l'accueil et dans le salon (adresse `/editeur`). Comme l'éditeur de bureau : la
palette des tuiles de la boîte (faces plate, montagne, Peloton), « À la fin », « Après la sélection »,
« Remplacer » (double-clic : pose la tuile), la liste du parcours (◀ ▶ pour déplacer, Supprimer, Annuler, Tout
effacer), l'aperçu, le profil et les messages (erreurs, quantités de la boîte). « Ouvrir » reprend l'exemple, une
étape officielle, un circuit de base ou un de tes parcours ; « Importer » et « Télécharger » passent par un
fichier `.json` (le même format que l'éditeur de bureau).

**Enregistrer dans « Mes parcours »** n'existe que sur ton PC (`python main.py`) : le fichier va dans
`parcours/` et le parcours apparaît dans le salon (recharger la page d'un salon déjà ouvert). Sur Render, rien
n'est écrit sur le serveur : on télécharge le fichier.

## Technique

- `online/rooms.py` : salons, places, déroulement (sans réseau, testé dans `tests/test_online.py`).
- `online/server.py` : serveur HTTP ; le navigateur demande l'état environ deux fois par seconde
  (`/api/state?since=<version>` ne renvoie rien si rien n'a changé).
- `online/static/` : les pages du jeu et de l'éditeur ; `draw.js` dessine les formes de `boardview.py` sur des
  `<canvas>`.
- Animations : le serveur envoie la route sans les coureurs, la géométrie de la route en pixels (bords droit et
  gauche de chaque case : `road_geometry`) et celle du profil (`profile_geometry`), les zones météo et le dernier
  déplacement. `app.js` fait glisser les coureurs et anime la météo sur un calque
  transparent, à ~30 images par seconde.
- Le serveur refuse de démarrer si le port est déjà pris (sous Windows, deux serveurs pourraient sinon écouter le
  même port sans erreur).
