---
slug: federation-part2
title: Fédération 2 - L'agenda partagé
authors: jonas
keywords: [cashless, fédération, portefeuille, wallet, openwallet, caisse enregistreuse, tibillet, réunion des tiers-lieux, RTLx, économie sociale et solidaire, ess]
tags: [cashless, fédération, portefeuille, wallet, openwallet, caisse enregistreuse, tibillet, réunion des tiers-lieux, RTLx, économie sociale et solidaire, ess]
image: /img/federons/07-tenant-part1.png
description: "Fédérer TiBillet, épisode 2 : construire un agenda culturel partagé entre les lieux d'un même réseau coopératif."
---

## Deconstruire pour decentraliser.

Fini le gros bloc PHP.
La billetterie, qui s'occupe de gérer
les paiements en ligne (recharge cashless via stripe),
les réservations et les ventes de billet
a été complètement repensée.

![/img/federons/06-blockcentral.png](/img/federons/06-blockcentral.png)

<!-- truncate -->

## Première étape : L'agenda fédéré.

En avant avec Django ! Le framework web en Python est déja utilisé coté cashless,
nous avons tout repensé depuis la base pour faire un modèle
dit de SaaS (Software as a service).
L'idée est de pouvoir utiliser la puissance combinée du moteur
de schéma PostgreSQL pour des applications multi-tenant.

Derrière ce vocabulaire un peu barbare se cache une idée toute
simple : **Un seul serveur pour gérer plusieurs instances** qui se partagent des **informations communes.**

Autrement dit, plutôt que d'avoir
plein de serveurs séparés qui stockent chacun peu ou prou
les mêmes données (carte, utilisateurs, évènements, etc... ),
nous mutualisons tout un territoire sur une seule "Stack".

![/img/federons/07-tenant-part1.png](/img/federons/07-tenant-part1.png)

Certaines données, comme
les utilisateurs et l'agenda sont
partagées entre tous les acteurs.

D'autre sont uniques
à chaque instance :
Évènements, adhésions, information générales, cartes cashless
etc ...

![/img/federons/08-samedata.png](/img/federons/08-samedata.png)

Mais surtout, ce système nous permet de faire une présentation
de TOUS les évènements présents dans l'instance:
Nous l'avions nommé la META, mais bon... Yen a un qui nous
a piqué le nom xD ...

Et hop ! Agenda Fédéré !

![/img/federons/09-agenda.png](/img/federons/09-agenda.png)

Ici nous parlons de concerts et d'artiste.
Mais il est tout à fait possible d'imaginer des réunions,
des marchés d’artisans, des festivals,
des locations de salle de répetes, des randonnées
etc etc ...

C'est un moteur évènementiel de données partagées.
Les idées qui permettent de l'exploiter sont nombreuses !

À l'heure où nous écrivons ces lignes
(octobre 2022), ce système est prêt
et mis en production depuis quelques jours.

A vous de le tester !
Venez discuter avec nous pour vos retours et vos idées !

## Et ma carte dans tout ça ?

![/img/federons/10-rapport.png](/img/federons/10-rapport.png)

On y vient !
C'est la suite logique, non ?
Et si nous ajoutions dans les données communes les
cartes NFC déja utilisées par les lieux ?

![/img/federons/11-cartecashless.png](/img/federons/11-cartecashless.png)

Après l'agenda, libérons les cartes NFC !

À suivre dans la 3ᵉ partie ...