# Cas d'usage : association d'atelier partagé "La Fabrique"

Par Joris Rehm, le 8/4/2026


## Contexte

[La Fabrique](https://lafab.org) est un atelier partagé autour des
thématiques de création et de réparation.

C'est une association à but non lucratif et son but est de développer
et de gérer des communs physiques comme des espaces d'atelier, des
machines, des outils et des matériaux. Le but est également d'animer
une communauté de personnes souhaitant collaborer dans leurs pratiques,
transmissions et apprentissage dans le cadre de leur activité créatrice
personnelle, artisanale ou professionnelle.

L'accès aux ressources ou aux intervenants est régulé par les règles de
fonctionnement qui sont votées selon un processus de démocratie
représentative. La majorité des activités demande à être à jour de
cotisation dans l'association. La plupart des activités sont payantes.

En pratique, l'association dispose d'un local de 1500 m² comprenant
une menuiserie, une métallerie, un atelier de couture, une cordonnerie,
des imprimantes 3D, une découpeuse graveuse laser et un espace
électronique. Il y a également un espace bar, un bureau et une salle
de réunion.

Le lieu fonctionne toute l'année avec en général une fermeture en août
et une autre pour la fin de l'année. Il est fermé durant les jours
fériés.

L'accès à l'ensemble des ateliers se fait par sessions payantes de 3h.
Il y a 2 sessions le jeudi à partir de 10h, 2 sessions le vendredi à
13h et 3 sessions le samedi à partir de 10h. Un accès par abonnement
est aussi possible, dans ce cas l'usage est libre pendant toutes les
sessions.

La gestion des usagers pendant les sessions est assurée par des
bénévoles appelés « clé2fab ». Les clé2fab ouvrent et ferment le lieu,
accueillent les usagers et visiteurs, gèrent les paiements et
adhésions.

Il y a aussi des administrateurs, des formateurs et des bénévoles
responsables des ateliers ou des machines.

L'association organise des initiations payantes qui donnent le droit
d'usage pour certaines machines ou permettent aux adhérents d'apprendre
des techniques. Dans ce cadre, elle utilise
[TiBillet](https://tibillet.org/) pour définir un agenda avec des
événements pour les initiations et vendre les réservations payantes en
ligne. Les adhésions ne sont pas gérées par TiBillet mais sur place
avec [Paheko](https://paheko.cloud/) qui gère aussi la fiche de caisse
informatisée et la comptabilité.

En général, les usagers se partagent spontanément les machines durant
leur session de travail. Il n'y a pas de réservation ni de limite
définie en nombre d'usagers.

Une machine est néanmoins partagée différemment : la découpeuse laser
doit être réservée en avance. Le tarif est aussi spécifique avec des
créneaux d'une heure.


## Besoins critiques — réservation en ligne payante

Cette section définit le cas d'usage critique pour notre besoin.

Les règles pour la machine laser sont les suivantes :

- Usage par créneau payant (15 €) pour une heure
    - mêmes périodes d'ouverture que le reste des ateliers
- Réservation obligatoire en avance, un seul usager par créneau

Nous avons constaté qu'il arrivait souvent que des personnes
n'honoraient pas leurs réservations et bloquaient donc la machine
pour rien.

Nous souhaitons donc mettre en place un paiement en ligne qui
conditionnera la réservation. Idéalement, les usagers pourraient
annuler eux-mêmes leur réservation et avoir un remboursement (un avoir
peut aussi convenir). La réservation ne doit pas être possible au-delà
d'un délai configurable, a priori un mois. L'annulation doit être
possible jusqu'à un certain délai avant la session, a priori la veille.

Les clé2fab doivent pouvoir consulter les réservations de la session
qu'ils gèrent afin d'autoriser l'accès à une personne.

Il pourrait être pratique que les clé2fab puissent créer une
réservation sur place (moyens de paiement sur place habituels : 
espèce, carte CB et cheque enregistré dans Paheko).

Il existe des usagers avec un statut particulier qui ont le droit
d'utiliser la machine gracieusement suite à la campagne de financement
participatif. Ces usagers doivent en priorité utiliser la machine en
dehors des horaires publics et se la partager entre eux, mais ils
peuvent exceptionnellement bloquer un créneau normal. Il peut aussi
arriver que des groupes monopolisent la machine certains jours
(collaboration avec des écoles).


## Besoins souhaitables — réservation réservée aux usagers formés

Il est également obligatoire d'avoir suivi une initiation pour avoir
le droit d'utiliser la machine laser.

Un besoin souhaitable serait de pouvoir gérer la liste des usagers
formés et de restreindre la réservation à cette liste.

L'idéal serait de relier automatiquement cette liste à la gestion des
événements d'initiations. Après chaque initiation, le formateur
validera les personnes qui sont réellement venues et qui sont aptes
à l'usage.


## Besoins futurs — réservation d'autres ressources

Réservations des sessions de travail dans tout le reste de l'atelier.

Pour le moment, nous n'avons pas de régulation de la fréquentation en
général, mais celle-ci augmente chaque année et peut-être qu'un jour
nous serons contraints d'ajouter une réservation des sessions. Elles
durent 3h lorsqu'elles sont payées à l'unité (avec un système de
ticket physique) mais sont libres (dans les mêmes horaires d'ouverture)
pour les abonnés.


Réservation des remorques grand format pour vélo (remorques « Carla »).

Nous avons des liens avec une autre association nommée « Le Cambouis »
qui organise des moments festifs autour du monde du vélo. Ils stockent
des remorques vélo grand format qui sont accessibles aux adhérents de
leur association et de la nôtre. Pour le moment, la gestion des prêts
se fait avec un fichier partagé et des échanges de SMS. Il y a trois
remorques (discernable par leur couleur de peinture) et il est important
de savoir qui à emprunté quoi à tout moment.

