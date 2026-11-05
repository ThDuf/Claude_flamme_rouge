# Extension Météo : règles et plan d'implémentation

Synthèse rédigée à partir de la règle officielle française (PDF Gigamic, © 2018 Lautapelit,
auteur Asger Harding Granerud), recoupée avec des comptes rendus de joueurs. Ce texte résume
la règle avec nos mots ; il ne la remplace pas.

## Matériel

- 13 jetons Météo : 4 jetons d'effet (vent de travers, vent arrière, vent de face, pluie, un de chaque)
  et 9 jetons « beau temps » (sans effet).
- 4 panneaux, un par effet, posés le long de la tuile concernée pour la repérer.

## Mise en place

1. Après avoir construit le parcours, et avant de placer les coureurs, on mélange les 13 jetons.
2. On en pose un au hasard, face visible, sur chaque **ligne droite**, sauf le départ et l'arrivée.
   Avec le jeu de base, il y a 7 lignes droites, donc 7 jetons posés. Les 6 autres retournent dans la boîte.
3. Chaque jeton d'effet est remplacé par son panneau. Les « beau temps » ne font rien.

Conséquence : sur une étape du jeu de base, on a de 0 à 4 effets, et chaque effet au plus une fois.

## Effets (sur les 6 cases de la ligne droite concernée)

| Effet | Qui est concerné | Ce qui change |
|---|---|---|
| **Vent de travers** | un coureur **sur** la tuile | ne profite pas de l'aspiration et n'en fait pas profiter les autres |
| **Vent arrière** | un coureur qui **commence le tour** sur la tuile | pioche **5** cartes Énergie au lieu de 4 |
| **Vent de face** | un coureur qui **commence le tour** sur la tuile | pioche **3** cartes Énergie au lieu de 4 |
| **Pluie** | un coureur qui **finit son mouvement** sur la tuile **après avoir été bloqué** | subit un **accident** |

« Bloqué » veut dire la règle habituelle : la case visée est pleine, donc le coureur s'arrête plus
tôt, sur la première case qui a une file libre. Si cette case est sous la pluie, il y a accident.

## Accident

- Le coureur est couché dans sa file et y reste.
- **Aspiration** : une case qui contient un coureur accidenté ne reçoit pas et ne donne pas d'aspiration.
- **Case bloquée** : si toutes les files d'une case ont un coureur accidenté, personne ne peut la traverser.
  Un coureur qui devait passer par là s'arrête dans la file libre la plus proche derrière.
  Si cette case-là est aussi sous la pluie, il subit lui aussi un accident (chute en chaîne).
- **Se relever** : au tour suivant, au moment du déplacement, le coureur se relève et sa carte vaut **2 de moins**.
  - Avec une carte de 2 (une carte Fatigue par exemple), il se relève sans avancer. On le remet dans la bonne file si besoin.
  - Le −2 s'applique **après** les ajustements de descente (minimum 5) et de ravitaillement (minimum 4, extension Peloton).
    Exemple : une carte de 2 en descente compte 5, puis 5 − 2 = 3 cases.
  - Le plafond de la **montée** (5 cases au maximum) reste le même. Il faut une carte de 7 pour avancer de 5 en montée après une chute.

## Où c'est programmé

- `flamme_rouge/weather.py` : tirage des 13 jetons sur les lignes droites (`Track.straights`, ou des tronçons
  de 6 cases pour un parcours qui n'est pas fait de tuiles), et effet de chaque case.
- `flamme_rouge/game.py` : taille de la main (vents), aspiration (vent de travers, coureur à terre),
  mouvement (case barrée, chute sous la pluie, relève avec −2 entre la descente et le plafond de montée).
- `flamme_rouge/controller.py` : lignes du journal (« pioche 5 cartes », « se relève : −2 », « CHUTE sous la pluie »).
- `flamme_rouge/boardview.py` : panneaux colorés le long des lignes droites, coureurs à terre,
  bandes météo sous le profil.
- Menu : l'interrupteur « Meteo » active tout cela ; la météo est tirée au début de chaque course.

## Points à trancher

- **Parcours personnalisés** avec plus de 13 lignes droites : les lignes droites au-delà de 13 n'ont pas de jeton (proposition).
- **Effet affiché à l'avance** : dans le jeu physique, les panneaux sont visibles dès le départ. On les affiche donc dès le départ.
- **Variantes de joueurs** (météo pour toute l'étape, brouillard, canicule…) : non officielles, pas prévues pour l'instant.

## Sources

- Règle officielle (FR), Gigamic : https://www.gigamic.com/index.php?controller=attachment&id_attachment=189
- Fiche Gigamic : https://www.gigamic.com/jeux-de-strategie/499-flamme-rouge-extension-meteo.html
- Passion Ludique, présentation de l'extension : https://www.passionludique.fr/article/flamme-rouge-m%C3%A9t%C3%A9o
- Forum Tric Trac (règles résumées et variante de joueur) : https://forum.trictrac.net/t/flamme-rouge-meteo-weather
- Board-game.co.uk, résumé : https://www.board-game.co.uk/product/meteo-flamme-rouge/
