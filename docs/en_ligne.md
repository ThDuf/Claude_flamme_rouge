# Jouer à distance

Le jeu tourne sur ton PC : un petit serveur Python (bibliothèque standard, rien à installer) sert une page web
et garde l'état des parties. Tes amis jouent depuis leur navigateur. Le site n'existe que tant que ton PC et le
serveur tournent.

## Lancer

1. Une seule fois, installer le tunnel Cloudflare (gratuit, sans compte) :

   ```
   winget install --id Cloudflare.cloudflared
   ```

2. Double-cliquer sur `lancer_en_ligne.bat`. Il démarre le serveur, puis le tunnel, et affiche une adresse
   `https://….trycloudflare.com` : c'est le lien à envoyer. Elle change à chaque lancement.
3. Toi, tu joues sur `http://127.0.0.1:8770`.
4. Pour arrêter : fermer la fenêtre du tunnel (ou Ctrl+C).

Sans tunnel, `python -m online.server --lan` rend le jeu joignable depuis les appareils du réseau local
(`http://<adresse-du-PC>:8770`).

## Une partie

- **Créer une partie** : tu deviens l'hôte. Envoie le lien du salon (il contient le code à 4 lettres) ou le code.
- Chacun **prend une place** (une équipe). L'hôte choisit le parcours, le nombre d'équipes, les extensions et,
  pour chaque équipe : Joueur, IA, ou équipe fantôme Peloton / Muscle (extension Peloton).
  Une place « Joueur » restée libre au départ est jouée par l'IA.
- Pendant la course, chacun ne voit **que sa main** ; les coureurs choisissent leur carte chacun à leur tour,
  puis n'importe quel joueur lance le mouvement, l'aspiration et la fatigue.
- Caméra : tout le parcours, zoom peloton ou zoom tête de course (chacun la sienne), ou cadrage libre : molette,
  boutons ＋/－, glisser la carte. Le navigateur agrandit tout de suite ce qu'il a, puis le serveur envoie un dessin
  net de ce cadrage. Les canvas ont autant de pixels qu'ils en occupent à l'écran : la carte reste nette.
- Recharger la page ramène dans la partie (le navigateur garde ta place). À l'arrivée, l'hôte peut revenir au
  salon pour une revanche.

## Sécurité

- Le serveur n'écoute que sur ton PC (`127.0.0.1`) ; le tunnel Cloudflare s'y branche. Ton adresse IP n'est pas
  montrée et aucun port n'est ouvert sur ta box.
- Il ne sert que trois fichiers (`online/static`) et l'API du jeu : aucun accès à tes dossiers.
- Toute personne qui a le lien peut ouvrir la page ; pour entrer dans une partie, il faut son code.

- Animations (bouton « Animations », réglage de chaque navigateur) : les coureurs roulent pendant le mouvement
  (l'un après l'autre, du premier au dernier) et l'aspiration ; pluie, vent et soleil animés sur la carte et le
  profil (extension Météo). Elles ne se rejouent pas quand on recharge la page.

- Variante Échappée (extension Peloton, parcours avec une tuile Échappée) : l'hôte la coche dans le salon. Avant
  le départ, chaque équipe à son tour choisit un coureur (ou passe) et mise deux cartes ; l'IA enchérit seule,
  les équipes fantômes ne participent pas.

## Pas encore en ligne

Grand Tour, éditeur de parcours (les parcours enregistrés sur le PC hôte sont bien proposés dans le salon).

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
