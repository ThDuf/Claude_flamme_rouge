# Extension Peloton : règles et implémentation

Synthèse rédigée à partir de la règle officielle française (PDF Gigamic, © 2017 Lautapelit,
auteur Asger Harding Granerud). Ce texte résume la règle avec nos mots ; il ne la remplace pas.

## Matériel

- Deux nouvelles couleurs d'équipe (rose et blanche) : on peut jouer à **5 ou 6 équipes**.
- 9 tuiles recto-verso : pavés, zones d'approvisionnement (ravitaillement), tuile Échappée (tuile 2),
  tuile bonus (tuile 9, pour 5–6 équipes).
- 6 cartes Muscle, 2 cartes Attaque, 6 cartes Étape (un côté 5–6 équipes, un côté 2–4 équipes).

## Règles de piste

- Une case peut avoir **1 à 3 files** (au lieu de 2). On peut toujours traverser des coureurs,
  mais on ne s'arrête pas sur une case pleine : on se place derrière, dans la première case avec une file libre.
- **Pavés** : sections à une seule file ; comme en montée, **pas d'aspiration** sur les pavés.
- **Zone d'approvisionnement** (ravitaillement) : sections larges de **3 files** ; un coureur qui
  **commence son tour** dans la zone avance d'**au moins 4 cases**. L'aspiration s'applique normalement.
- Sortie d'une zone à 3 files vers une zone plus étroite (aspiration) : les coureurs des files de droite
  avancent d'abord ; celui qui ne trouve plus de place reste sur sa case, ramené dans la file de droite.

## Variante Échappée

- La 2e tuile (juste après le départ) est la tuile Échappée.
- Avant le premier tour, chaque joueur choisit un de ses coureurs et fait deux enchères :
  il pioche 4 cartes de ce coureur, en pose une face cachée, défausse les autres, puis on révèle ; deux fois.
- À 2–4 équipes, le meilleur total part en échappée ; à 5–6, les deux meilleurs (le plus haut à droite).
  Égalité : le coureur le plus en arrière (puis le plus à gauche) gagne.
- Les gagnants retirent du jeu leurs cartes misées et prennent 2 cartes Fatigue ; les perdants
  défaussent leurs mises. Puis chaque paquet est remélangé.

## Équipes fantômes (jouées par le jeu)

- **Équipe Peloton** (une seule) : un seul paquet, celui du Rouleur, plus 2 cartes **Attaque**.
  À chaque tour, une carte est retournée et les deux coureurs avancent de sa valeur.
  Carte Attaque : le coureur de tête de l'équipe avance de 2, celui de derrière de 9.
- **Équipe Muscle** (autant qu'on veut) : les deux paquets de l'équipe, plus une carte **Muscle**
  (un 5) dans celui du Sprinteur. À chaque tour, chaque coureur retourne la carte du dessus de son paquet.
- Les équipes fantômes **ne prennent jamais de carte Fatigue** mais profitent de l'aspiration ;
  elles ne participent pas aux enchères de l'échappée.
- Elles se placent au départ **avant** les joueurs, au plus près de la ligne : le Peloton d'abord
  (ses coureurs l'un devant l'autre), puis Muscle (Sprinteur devant le Rouleur).

## Ce qui est programmé

- 5 et 6 équipes (avec l'extension Peloton), couleurs rose et blanche.
- Cases de 1 à 3 files ; pavés (1 file, pas d'aspiration) ; ravitaillement (3 files, minimum 4 cases) ;
  aspiration qui respecte la place disponible en sortie de zone large.
- Équipes Peloton et Muscle, à choisir sur l'écran « Qui joue ? » (en plus de Joueur et IA).
- Les 9 tuiles, numérotées comme sur les cartes étape : 1 nouveau départ (5–6 équipes), 2 Échappée,
  3 et 4 zones à 3 files (ravitaillement), 5 à 8 pavés, 9 tuile bonus (5–6 équipes).
- Les 12 cartes étape (étapes 7 à 12, côtés 2–4 et 5–6 équipes), dans la rubrique « Extension Peloton » du menu.
- Variante Échappée : interrupteur sur l'écran « Qui joue ? » (seulement si le parcours a la tuile 2).
  Chaque équipe choisit un coureur ou passe ; l'IA enchérit avec son Rouleur ; les fantômes ne participent pas.

## Choix faits faute d'information

- **Cases des tuiles Peloton** : relevées sur une photo trop petite, donc PROVISOIRES
  (`PELOTON_TILE_DEFS` dans `flamme_rouge/official.py`) :
  1 `ssssff`, 2 `fffxff` (zone d'échappée sur la 4e case), 3 et 4 `rrrrrr`, 5 `ffpppp`, 6 `pppppp`,
  7 `ppppff`, 8 `pppppf`, 9 `ffffff`. Les deux faces d'une tuile ne sont pas encore distinguées
  (sur les cartes, un chiffre encadré désigne l'autre face).
- **Départ à 5–6 équipes** : quand la grille ne suffit pas, ses cases reçoivent une 3e file.
- **Tuile bonus** : supposée être une ligne droite de 6 cases.
- **Paquets des fantômes** : quand le paquet est vide, on remélange les cartes déjà retournées.
- **Mise de l'IA** : sa plus grosse carte si elle vaut au moins 6, sinon sa plus petite.

## Sources

- Règle officielle (FR) : https://cdn.1j1ju.com/medias/39/fd/d1-flamme-rouge-peloton-regle.pdf
- Fiches et critiques : https://boardgamegeek.com/wiki/page/thing:229941 ,
  https://islaythedragon.com/featured/review-flamme-rouge-peloton/
