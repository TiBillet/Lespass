# Plan opérationnel TiBillet × Taler

Nov 17, 2026 · @CCC

## Objectif et principes

Ajouter Taler à TiBillet comme moyen de paiement B2C, puis opérer un exchange fédéré TIBX pour un cashless événementiel sans carte NFC, en remplaçant Stripe Connect.

**Choix actés**

- **Paiement direct à la caisse du lieu** : chaque organisation a sa propre instance marchande. Il n'y a jamais de paiement unique à partager entre plusieurs organisateurs.
- **TIBX**, actif fédéré, 1 TIBX = 1 €. L'exchange est opéré par la coopérative qui édite et déploie l'instance fédérée (tibillet.coop).
- **Entrée en euros** par Wero, virement instantané, Stancer ou Smile&Pay, avec des plafonds de recharge.
- **Sortie** : l'exchange agrège par lieu, puis TiBillet vire en SEPA vers chaque organisation.
- **Pas de KYC usager.** Les paiements entre wallets sont désactivés sur l'exchange TIBX. Le KYC des organisations (SEPA, documents légaux) est géré dans TiBillet.
- **Exemption « réseau limité »** visée. Elle dépend de la nature du réseau ; au-delà d'1 M€ sur 12 mois, il faut se déclarer à l'ACPR, qui peut refuser.
- **Configuration dans l'interface TiBillet** : TVA, comptabilité et frais de l'exchange.
- **Fedow et la carte NFC** restent en place dans les 100+ lieux actuels. TIBX vient en plus, sans les remplacer.
- **Livrables réutilisables** : une lib Python indépendante et une app Django séparée, sous AGPLv3.

## Phases

Quatre phases, chacune ouverte par une condition de passage. La validation juridique conditionne la phase 3, pas les deux premières.

1. **Expérimentation technique en KUDOS**, sur l'exchange de démo et nos instances de test.
   - Paiement en ligne : réservation, location de ressource, adhésion, vente en ligne.
   - Paiement à la caisse : QR sur l'écran client (Sunmi D3 mini ou équivalent).
   - Remboursement en caisse, webhooks, rapprochement.
   - Banc de test docker-compose : exchange, backend marchand et libeufin.
   - *Passage* : parcours complets validés en test, lib et app Django en première version.
2. **Monnaie temps** (valorisation des bénévoles), sur un exchange dédié, non fiduciaire et exempt de licence.
   - Premier exchange opéré par la coop, sans euros en jeu : on rode l'exploitation (clés, sauvegardes, supervision).
   - Crédit des heures depuis TiBillet via la passerelle banque.
   - *Passage* : un pilote réel dans un lieu, et l'avis juridique sur le risque d'avantage en nature.
3. **Exchange TIBX en euros, sous exemption réseau limité.**
   - Compte cantonné de la coop, piloté en EBICS via libeufin-nexus : recharge par virement et virements de sortie.
   - Adaptateurs de paiement : Wero, virement instantané, Stancer, Smile&Pay. Plafonds de recharge.
   - Kiosque de recharge autonome : 1 € = 1 TIBX, QR de retrait vers le wallet.
   - Onboarding des festivals : une instance marchande par organisation, KYC dans TiBillet, délai de virement de fin d'événement.
   - Règle pour les TIBX non dépensés : remboursement, report ou expiration.
   - *Passage* : avis juridique favorable, accord des prestataires de paiement, compte cantonné ouvert.
4. **Migration vers un exchange en euros agréé**, quand il en existera un (Taler Operations Allemagne attend sa licence BaFin).
   - Les festivals deviennent marchands sur cet exchange et les wallets tiennent des EUR. La coop ne gère plus les euros.
   - Fin de vie des TIBX en circulation : rachat ou date limite, car le wallet ne convertit pas.
   - La passerelle et EBICS restent pour la monnaie temps et les autres actifs.

## Lots de travail

Cinq lots, dont deux de code et trois non techniques, qui comptent autant dans la valorisation du projet.

| Lot | Contenu | Phases |
| --- | --- | --- |
| **L1 — Code applicatif** | Lib Python, app Django, intégration Lespass (paiement en ligne) et LaBoutik (QR sur écran client, remboursement), passerelle banque et adaptateurs de paiement, onboarding des instances, configuration des frais dans l'interface TiBillet | 1 à 4 |
| **L2 — Code infra et sysadmin** | Banc de test docker-compose, déploiement Docker/Ansible de l'exchange et du backend marchand, génération des dénominations, rotation des clés, procédure de cérémonie des clés hors ligne, sauvegardes, supervision, libeufin-nexus en EBICS | 1 à 4 |
| **L3 — Documentation** | Doc utilisateur multilingue : festivalier (installer le wallet, recharger, payer), organisateur (onboarding, caisse, virements), opérateur d'exchange, développeur (lib et app). Contribution upstream à la doc Taler | 1 à 4 |
| **L4 — Design** | Kiosque de recharge autonome (objet, écran, parcours), signalétique sur site, parcours d'onboarding du festivalier, écran client de la caisse | 2 et 3 |
| **L5 — Suivi administratif** | Avis juridique (exemption réseau limité, déclaration ACPR, monnaie temps et URSSAF), ouverture du compte cantonné et contrat EBICS TS, contrats avec les prestataires de paiement, procédure KYC des organisations, CGU du TIBX, reporting NLnet | 2 à 4 |

## Périmètre de la lib Python et de l'app Django

La lib est indépendante de Django, pour être réutilisable par la caisse alimentaire, les épiceries ou tout projet Python. L'app Django l'emballe pour un projet Django.

**Lib Python**

1. **Cœur protocole** : format des montants (« TIBX:10.50 »), liens taler:// et QR de paiement et de retrait, modèles typés. À étudier : la spécification OpenAPI de Taler financée par NGI TALER.
2. **Paiement vers le wallet** : lien entre un paiement validé et l'émission de pièces dans le wallet. Il s'agit d'une implémentation serveur des API Wire Gateway et Bank Integration, avec un adaptateur par prestataire (Wero, Stancer, Smile&Pay, virement EBICS, Stripe).
3. **Checkout en ligne** : création de commande, suivi du statut, remboursement.
4. **Webhooks** : réception et vérification des événements du backend marchand.
5. **Administration du backend marchand** : création d'instance par organisation, compte bancaire, jetons d'accès par instance, délai de virement, frais.
6. **Ventilation des ventes** : la passerelle reçoit les ordres de virement de l'exchange, donc la ventilation par lieu, puis la croise avec les virements vus par chaque instance marchande.

**App Django**

- Modèles, admin et vues de checkout et de webhook.
- Endpoints de la passerelle banque.
- Tâches Celery : suivi des paiements et virements de fin d'événement.
- Templates : QR pour l'écran client de la caisse et pour le kiosque.
- Fixtures pytest branchées sur le banc de test docker-compose.

## Prérequis et risques

| Sujet | Risque | Réponse |
| --- | --- | --- |
| Exemption réseau limité | Un réseau ouvert de festivals sur plusieurs territoires peut ne pas y entrer ; au-delà d'1 M€ sur 12 mois, l'ACPR peut refuser | Avis juridique avant la phase 3 |
| Monnaie temps | Une requalification en avantage en nature ou en rémunération par l'URSSAF | Même avis juridique, en phase 2 |
| Réseau en festival | Le wallet et la caisse doivent être en ligne pour chaque paiement | Plan réseau dédié, repli carte NFC Fedow et espèces |
| Rétrofacturation carte | Un paiement contesté après dépense des TIBX, perte portée par la coop | Plafonds de recharge, 3D Secure, priorité à Wero et au virement |
| Conditions des prestataires | La vente de valeur stockée peut être refusée | Déclaration explicite de l'activité à chaque prestataire |
| Clés de l'exchange | Qui détient les clés hors ligne peut créer des TIBX | Cérémonie des clés, gouvernance coop, auditeur |
| TIBX non dépensés | Une dette de la coop envers les usagers | Règle de remboursement ou d'expiration, inscrite dans les CGU |
| Exchange euro agréé | Aucune date de lancement | La phase 4 reste conditionnelle, TIBX tient sans elle |

**Questions ouvertes**

- [ ] Quel kiosque : matériel et TPE certifiés pour borne sans caissier, à voir avec Smile&Pay ou Stancer.
- [ ] Quelle banque pour le compte cantonné, avec EBICS TS.
- [ ] Quel lieu ou festival pilote pour la phase 2, puis pour la phase 3.
