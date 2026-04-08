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




--------------------------------------------------------------------------------

# Application des besoins avec la spécification v0.3

--------------------------------------------------------------------------------

## Configuration TiBillet — Besoins critiques : découpeuse laser

### Calendar « Calendrier La Fabrique »

+---------------------------------+------------+------------+
| label                           | start_date | end_date   |
+=================================+============+============+
| Fermeture estivale              | 2026-08-01 | 2026-08-31 |
+---------------------------------+------------+------------+
| Fermeture fin d'année           | 2026-12-24 | 2027-01-02 |
+---------------------------------+------------+------------+
| Jour de l'An                    | 2026-01-01 | 2026-01-01 |
+---------------------------------+------------+------------+
| Lundi de Pâques                 | 2026-04-06 | 2026-04-06 |
+---------------------------------+------------+------------+
| Fête du Travail                 | 2026-05-01 | 2026-05-01 |
+---------------------------------+------------+------------+
| Victoire 1945                   | 2026-05-08 | 2026-05-08 |
+---------------------------------+------------+------------+
| Ascension                       | 2026-05-14 | 2026-05-14 |
+---------------------------------+------------+------------+
| Lundi de Pentecôte              | 2026-05-25 | 2026-05-25 |
+---------------------------------+------------+------------+
| Fête Nationale                  | 2026-07-14 | 2026-07-14 |
+---------------------------------+------------+------------+
| Assomption                      | 2026-08-15 | 2026-08-15 |
+---------------------------------+------------+------------+
| Toussaint                       | 2026-11-01 | 2026-11-01 |
+---------------------------------+------------+------------+
| Armistice                       | 2026-11-11 | 2026-11-11 |
+---------------------------------+------------+------------+
| Noël                            | 2026-12-25 | 2026-12-25 |
+---------------------------------+------------+------------+

Notes :

- il faut encore ajouter les jours fériés spécifiques à l'Alsace - Moselle
- certain jours ne tombe pas sur une ouverture hebdo, mais on peut les garder


### SlotTemplate « Créneaux laser »

Les horaires d'ouverture des ateliers (2 sessions de 3h le jeudi à
partir de 10h, 2 le vendredi à 13h, 3 le samedi à partir de 10h) sont
découpés en créneaux d'1h pour la laser.

+----------+------------+---------+------------+------------------------------+
| weekday  | start_time | durée   | slot_count | Créneaux générés             |
+==========+============+=========+============+==============================+
| thu      | 10:00      | 60 min  | 6          | 10h–11h, 11h–12h, …, 15h–16h |
+----------+------------+---------+------------+------------------------------+
| fri      | 13:00      | 60 min  | 6          | 13h–14h, 14h–15h, …, 18h–19h |
+----------+------------+---------+------------+------------------------------+
| sat      | 10:00      | 60 min  | 9          | 10h–11h, 11h–12h, …, 18h–19h |
+----------+------------+---------+------------+------------------------------+

### Resource « Découpeuse laser »

+-----------------------------+--------------------------------------+
| Champ                       | Valeur                               |
+=============================+======================================+
| name                        | Découpeuse laser                     |
+-----------------------------+--------------------------------------+
| group                       | (aucun)                              |
+-----------------------------+--------------------------------------+
| capacity                    | 1                                    |
+-----------------------------+--------------------------------------+
| cancellation_deadline_hours | 24 heures                            |
+-----------------------------+--------------------------------------+
| booking_horizon_days        | 30 jours                             |
+-----------------------------+--------------------------------------+
| calendar                    | Calendrier La Fabrique               |
+-----------------------------+--------------------------------------+
| slot_template               | Créneaux laser                       |
+-----------------------------+--------------------------------------+
| pricing_rule                | → Price « Laser 15 € »               |
+-----------------------------+--------------------------------------+

### Price « Laser 15 € » (modèle TiBillet existant)

+----------------------+--------------------------------------------+
| Champ                | Valeur                                     |
+======================+============================================+
| prix                 | 15,00                                      |
+----------------------+--------------------------------------------+
| adhesion_obligatoire | FK → adhésion La Fabrique                  |
+----------------------+--------------------------------------------+
| max_per_user         | (non utilisé)                              |
+----------------------+--------------------------------------------+


--------------------------------------------------------------------------------


## Configuration TiBillet — Besoins futurs : autres ressources

### Sessions de travail en atelier

Même Calendar que la laser (« Calendrier La Fabrique »).

**SlotTemplate « Sessions atelier »**

+----------+------------+---------+------------+-----------------------------+
| weekday  | start_time | durée   | slot_count | Créneaux générés            |
+==========+============+=========+============+=============================+
| thu      | 10:00      | 180 min | 2          | 10h–13h, 13h–16h            |
+----------+------------+---------+------------+-----------------------------+
| fri      | 13:00      | 180 min | 2          | 13h–16h, 16h–19h            |
+----------+------------+---------+------------+-----------------------------+
| sat      | 10:00      | 180 min | 3          | 10h–13h, 13h–16h, 16h–19h  |
+----------+------------+---------+------------+-----------------------------+

**Resources** (une par espace d'atelier, capacité à définir selon la
surface et les équipements disponibles) :

+---------------------+----------+--------------------+
| name                | capacity | slot_template      |
+=====================+==========+====================+
| Menuiserie          | 6        | Sessions atelier   |
+---------------------+----------+--------------------+
| Métallerie          | 2        | Sessions atelier   |
+---------------------+----------+--------------------+
| Atelier couture     | 4        | Sessions atelier   |
+---------------------+----------+--------------------+
| Cordonnerie         | 3        | Sessions atelier   |
+---------------------+----------+--------------------+
| Imprimantes 3D      | 3        | Sessions atelier   |
+---------------------+----------+--------------------+
| Électronique        | 2        | Sessions atelier   |
+---------------------+----------+--------------------+

> ⚠️ **Limitation :** la spec prévoit un seul `pricing_rule` par
> ressource. Or les sessions sont payantes pour les non-abonnés et
> gratuites pour les abonnés. Ce cas de double tarification n'est pas
> couvert en l'état par le modèle de données.
> La gestion de ticket papier n'est pas possible non plus, le plus
> simple serait de ne pas faire la gestion du paiement du tout par
> TiBillet. Ou alors, il faudrait changer le fonctionnement du lieu.

Notes :

- les 3 imprimantes 3D mériteraient un tarif spécifique à l'heure


### Remorques Carla

Trois Resource distinctes, une par remorque identifiable à sa couleur,
pour savoir à tout moment qui a emprunté quoi. Capacity = 1 (une seule
personne peut emprunter une remorque donnée à la fois).
Un groupe de ressource peut être défini pour présenter ensemble les
remorques.

+---------------+----------+-------------------------------+
| name          | capacity | pricing_rule                  |
+===============+==========+===============================+
| Carla noire   | 1        | → Price « Emprunt Carla »     |
+---------------+----------+-------------------------------+
| Carla verte   | 1        | → Price « Emprunt Carla »     |
+---------------+----------+-------------------------------+
| Carla N&Verte | 1        | → Price « Emprunt Carla »     |
+---------------+----------+-------------------------------+

**Price « Emprunt Carla »** : `prix = 0`,
`adhesion_obligatoire` = FK → adhésion La Fabrique.

La durée d'emprunt est variable (a priori à la journée ou sur plusieurs
jours). Le modèle peut être approché avec des créneaux de 24h
(`slot_duration_minutes = 1440`) et un `slot_count > 1` pour les
emprunts multi-jours.

> ⚠️ **Limitations :**
>
> 1. Le SlotTemplate génère des créneaux récurrents par jour de la
>    semaine. Un emprunt commençant un mercredi pour 5 jours nécessite
>    que chaque jour de la semaine soit déclaré dans le template, ce
>    qui est inhabituel par rapport à l'usage prévu du modèle.
>
> 2. L'accès aux adhérents du Cambouis est explicitement hors scope v1
>    (cross-tenant resource sharing).
>    

Notes, il y a plusieurs problèmes :

- il faut que les adhérents du Cambouis puissent réserver. Le plus simple
  serait d'ouvrir la réservation à tous. La validation serait en personne
  sur place lorsque la remorque sort durant les horaires d'ouvertures.
  Le cambouis à accès a des clé du lieu et peut s'auto gérer.
- le modèle par session ne convient pas trop mais on peut problablement
  s'en accomoder en découpant tous les jours de la semaine par : matin,
  après-midi, soir et nuit.
- Il faudrait un calendrier spécial ouvert tout le temps pour ne pas
  restreindre la réservation.

==> Mais le modèle à l'air de pouvoir s'accomoder de ce cas également.
