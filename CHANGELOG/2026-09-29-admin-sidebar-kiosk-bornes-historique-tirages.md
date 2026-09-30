# Admin : bornes dans le module Kiosk, un seul historique des tirages, libellés clarifiés

**Date :** 2026-09-29
**Migration :** Oui / Yes — `kiosk/migrations/0004_borne.py` (modèle proxy, aucune table)

## 1. Kiosk : on crée ses bornes dans le module Kiosk

**Quoi / What :** nouvelle entrée « Bornes » dans le module Kiosk. On y crée une borne
(le rôle « Kiosk » est posé tout seul, le code PIN est fabriqué comme pour un terminal).
Les réglages de la borne (recharge active) sont un bloc de sa fiche : l'entrée
« Réglages des bornes » quitte la sidebar. « Paiements » passe dans l'onglet Analyser.
/ New "Kiosks" entry in the Kiosk module; settings are an inline; payments move to Analyse.

**Pourquoi / Why :** avant, le module Kiosk ne montrait que ses paiements et ses
réglages. Pour créer une borne, il fallait aller dans Lémachines → Terminaux matériels
→ Terminaux, et choisir le type « Kiosk ».
/ Creating a kiosk used to require another module.

**Comment / How :** `kiosk.Borne` est un proxy de `laboutik.Terminal`, filtré sur
`terminal_role = KI` (`BorneManager`). `BorneAdmin` hérite de `TerminalAdmin`
(colonne État/PIN, actions révoquer et nouveau PIN). La borne reste aussi visible
dans « Terminaux matériels ».

## 2. Tireuses : un seul historique des tirages

**Quoi / What :** « Sessions », « Historique tireuses » et « Historique cartes »
affichaient le même modèle (`RfidSession`). Il ne reste qu'« Historique des tirages »
(sessions de service, sans maintenance ni calibration). On suit une carte avec la
recherche (UID ou nom). Les deux autres admins restent enregistrés : les anciens liens
marchent encore. « Kiosk dashboard » devient « Écran public des tireuses ».
/ One pour history instead of three views of the same model.

**Correctif / Fix :** « Historique tireuses » et « Historique cartes » laissaient
supprimer une session facturée (liée à une `LigneArticle`). Seul `RfidSessionAdmin`
la protégeait. La règle est sortie dans deux fonctions de module partagées
(`_session_peut_etre_supprimee`, `_supprimer_les_sessions_non_facturees`).
/ Billed sessions could be deleted from the two history admins; now protected everywhere.

## 3. Libellés

| Avant / Before | Après / After |
|---|---|
| Agenda → Bookings | Réservations |
| Ressources → Bookings | Réservations de ressources |
| Caisse → Closures | Clôtures de caisse (tickets Z) |
| Ventes & compta → Rapports | Clôtures comptables |
| Monnaies → Federations | Réseaux de monnaie |

Nouvelles chaînes sans traduction EN pour l'instant (pas de makemessages dans cette session).
/ New strings not yet translated.

## Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `kiosk/models.py` | Proxy `Borne` + `BorneManager` |
| `kiosk/migrations/0004_borne.py` | Création du proxy |
| `kiosk/admin.py` | `BorneForm`, `ReglagesBorneInline`, `BorneAdmin` |
| `controlvanne/admin.py` | Fonctions de protection partagées, colonnes de l'historique |
| `Administration/admin/dashboard.py` | Entrées Kiosk et Tireuses, libellés, catégories, descriptions |
| `tests/pytest/test_admin_sidebar_kiosk_tireuses.py` | Nouveau : 7 tests |

## Tester / How to test

Voir `A TESTER et DOCUMENTER/admin-sidebar-kiosk-bornes-historique-tirages.md`.
