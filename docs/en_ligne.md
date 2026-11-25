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
- Caméra : tout le parcours, zoom peloton ou zoom tête de course (chacun la sienne), ou cadrage libre : molette,
  boutons ＋/－, glisser la carte. Le navigateur agrandit tout de suite ce qu'il a, puis le serveur envoie un dessin
  net de ce cadrage. Les canvas ont autant de pixels qu'ils en occupent à l'écran : la carte reste nette.
- Recharger la page ramène dans la partie (le navigateur garde ta place). À l'arrivée, l'hôte peut revenir au
  salon pour une revanche.

## Sécurité

- Le serveur tourne chez Render, pas sur ton PC : ton adresse IP n'est pas montrée et aucun port n'est ouvert
  sur ta box.
- Il ne sert que trois fichiers (`online/static`) et l'API du jeu : aucun accès au reste du dépôt.
- Toute personne qui a le lien peut ouvrir la page ; pour entrer dans une partie, il faut son code.

- Animations (bouton « Animations », réglage de chaque navigateur) : les coureurs roulent pendant le mouvement
  (l'un après l'autre, du premier au dernier) et l'aspiration ; pluie, vent et soleil animés sur la carte et le
  profil (extension Météo). Elles ne se rejouent pas quand on recharge la page.

- Variante Échappée (extension Peloton, parcours avec une tuile Échappée) : l'hôte la coche dans le salon. Avant
  le départ, chaque équipe à son tour choisit un coureur (ou passe) et mise deux cartes ; l'IA enchérit seule,
  les équipes fantômes ne participent pas.

## Pas encore en ligne

Grand Tour, éditeur de parcours, vue 3D.

## Technique

- `online/rooms.py` : salons, places, déroulement (sans réseau, testé dans `tests/test_online.py`).
- `online/server.py` : serveur HTTP ; le navigateur demande l'état environ deux fois par seconde
  (`/api/state?since=<version>` ne renvoie rien si rien n'a changé).
- `online/static/` : la page ; elle dessine les formes de `boardview.py` sur des `<canvas>`, comme `ui.paint`
  le fait dans Tkinter.
- Animations : le serveur envoie la route sans les coureurs, la géométrie de la route en pixels (bords droit et
  gauche de chaque case : `road_geometry`) et celle du profil (`profile_geometry`), les zones météo et le dernier
  déplacement. `app.js` refait les calculs de `animation.py` et des effets météo de `boardview.py` sur un calque
  transparent, à ~30 images par seconde.
- Le serveur refuse de démarrer si le port est déjà pris (sous Windows, deux serveurs pourraient sinon écouter le
  même port sans erreur).
