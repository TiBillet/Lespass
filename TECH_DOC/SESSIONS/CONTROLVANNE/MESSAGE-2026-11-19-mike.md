# Message à Mike — coupure de la vanne et client Pi

Salut Mike,

Suite à notre discussion sur la coupure de la vanne, j'ai relu tout le code du Pi : le
contrôleur, le matériel et le client réseau. J'ai aussi relu la partie serveur :
`authorize`, `event`, la facturation et la calibration. Deux relectures indépendantes sont
passées derrière. La spec complète est ici :
`TECH_DOC/SESSIONS/CONTROLVANNE/CHANTIER-05-fiabilite-client-pi.md`.

Voici le résumé.

## Tu as raison sur ces points

- **La période de grâce est nécessaire.** Le RC522 rate des lectures. Sans grâce, la vanne
  s'ouvrirait et se fermerait en boucle. Fermer à la première lecture manquée serait une
  mauvaise idée : on l'a écartée.
- **La lecture de la carte côté Pi est rapide.** La lenteur au badge vient bien du réseau.
- **La coupure au retrait prend environ 3 s**, pas plus.
- **Le débordement au plafond n'est pas facturé au client.** Il ne paie jamais plus que son solde.

## Mais « ce qui est mesuré est facturé » a des trous

1. **`card_removed` part toujours avec 0 ml** (`tibeer_controller.py:204`). Le serveur le traite
   comme un `pour_end` et ne facture que si le volume est supérieur à 0. Si le `pour_end` s'est
   perdu en 4G, la session est close **sans facture**. Correctif simple côté serveur : facturer
   `max(volume reçu, dernier_volume_ml)`. Il protège aussi les Pi déjà installés.
2. **Une nouvelle calibration n'est pas appliquée par le Pi.** « Appliquer » écrit en base
   seulement. Le Pi garde l'ancien facteur jusqu'au redémarrage, ou jusqu'au passage d'une carte
   de maintenance. La série de calibration suivante est donc fausse aussi. Proposition :
   renvoyer `calibration_factor` dans la réponse d'`authorize`, et l'appliquer avant
   `session_start_vol`.
3. **Le plafond n'est contrôlé qu'une fois par seconde.** Le `return` des lignes 166-167 passe
   avant le contrôle de la ligne 172. La vanne se coupe donc jusqu'à une seconde après le
   plafond, plus le temps d'un `pour_update` bloqué. Ce débordement n'est pas facturé : la perte
   est pour le lieu.
4. **Le facteur par défaut est 6,5**, alors que la fiche courante du YF-S201 donne 7,5. Si c'est
   bien ce capteur, l'écart est d'environ 15 % sans calibration. Tu sais d'où vient le 6,5 ?

## Ce que Jonas a ressenti au salon

Le ressenti est juste, mais la grâce n'en est pas la cause. Avec un robinet mécanique, elle se
voit peu. Ce qui gêne vraiment :

- l'attente au badge, sans retour visible pendant l'`authorize` ;
- l'écran en retard sur la vanne, car il passe par Pi → 4G → serveur → WebSocket ;
- le temps entre deux clients, car `pour_end` attend une lecture du solde sur l'ancien Fedow,
  juste pour l'affichage.

Le réseau peut être bien plus rapide :

- **Il n'y a pas de `requests.Session`.** Chaque appel refait DNS, TCP et TLS : 4 à 5
  allers-retours 4G au lieu d'un.
- **Les délais d'attente ne bornent pas l'appel entier.** Avec `requests`, `timeout=2.0` vaut
  2 s pour se connecter, puis 2 s pour la réponse, et le DNS n'est pas borné.

## Deux plantages possibles à vérifier dans les logs du salon

`pour_start` (ligne 152) et `pour_end` au plafond (ligne 175) ne sont pas dans un `try`. Une
erreur réseau fait sortir le programme. systemd le relance, mais avec un `git pull` à chaque
fois, ce qui peut prendre longtemps en 4G. **Tu peux chercher `Erreur fatale` dans
`~/tibeer/logs/tibeer.log` du Pi du salon ?** Ça expliquerait peut-être une partie de ce qu'on a
vu.

## Autres points relevés

- Après un `authorize` raté, la carte est ignorée tant qu'elle n'est pas retirée, et l'écran
  peut afficher « autorisé » alors que la vanne est fermée.
- Si le débitmètre est en panne, il n'y a aucune impulsion, donc aucun plafond : la vanne reste
  ouverte sans limite. Proposition : fermer après N secondes sans impulsion.
- `FlowMeter.update()` ne sert à rien, et sa formule donne un débit 60 fois trop grand. Elle est
  recopiée dans le README.
- Les imports des lignes 16-19 empêchent de tester le contrôleur sans Pi.

## Proposition d'ordre de travail

1. **Mesurer d'abord :** les logs du salon, puis la durée des appels HTTP et le taux de lectures
   manquées du RC522.
2. **Monter un harnais de tests :** des faux objets pour la carte, la vanne, le débitmètre et le
   client, et une fonction `un_tour_de_boucle(maintenant)` pour piloter le temps.
3. **Faire les correctifs courts**, chacun avec un test : `card_removed`, calibration, `try`,
   plafond à chaque tour, `requests.Session`, nouvelle tentative d'`authorize`, délai sans
   impulsion.
4. **Côté serveur :** sortir la lecture du solde de `pour_end`, puis aligner `simu_pi.js` sur le
   vrai Pi.
5. **Seulement si les mesures le justifient :** un fil d'envoi séparé pour les appels réseau.
   Attention au piège : un `pour_end` encore en file pourrait fermer la session suivante du même
   client.
6. **La doc utilisateur :** tutoriel, schéma de câblage complet avec la puissance (diode de roue
   libre, signal 5 V du débitmètre sur des GPIO 3,3 V), calibration.

## Mes questions pour toi

1. Quelle est la référence exacte du débitmètre, et d'où vient le facteur 6,5 ?
2. As-tu encore les logs du Pi du salon ?
3. Le lecteur VMA405 est-il utilisé sur une vraie tireuse ?
4. Combien de secondes sans impulsion avant de couper la vanne ? Cela dépend du temps qu'un
   client met à ouvrir le robinet.
5. Y a-t-il déjà une diode de roue libre sur la vanne, et un pont diviseur sur le signal du
   débitmètre ?

Rien n'est codé pour l'instant. Dis-moi ce que tu en penses avant qu'on attaque.

Jonas
