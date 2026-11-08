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

## Choix faits faute d'information

- **Départ à 5–6 équipes** : la grille de la tuile de départ (2 files) ne suffit pas pour 12 coureurs ;
  quand il le faut, ses cases reçoivent une 3e file.
- **Paquets des fantômes** : quand le paquet est vide, on remélange les cartes déjà retournées
  (la règle ne dit rien ; sans cela, l'équipe n'aurait plus de cartes avant l'arrivée).
- **Tuiles Peloton** : leurs cases exactes ne sont pas encore décrites. En attendant, l'éditeur propose
  deux tuiles génériques marquées « provisoire » : une ligne droite de pavés et une ligne droite de ravitaillement.
- **Variante Échappée** : pas encore programmée, il faut la description de la tuile Échappée (tuile 2).

## Sources

- Règle officielle (FR) : https://cdn.1j1ju.com/medias/39/fd/d1-flamme-rouge-peloton-regle.pdf
- Fiches et critiques : https://boardgamegeek.com/wiki/page/thing:229941 ,
  https://islaythedragon.com/featured/review-flamme-rouge-peloton/
