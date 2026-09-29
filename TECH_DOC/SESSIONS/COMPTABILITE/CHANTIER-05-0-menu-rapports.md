# Chantier 05-0 — Ranger les deux rapports dans « Ventes & comptabilité »

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28)
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — Décision D25
> Effort : 0,25 j — Dépend de : rien. Aucune migration.

## 1. Le besoin

Aujourd'hui, le menu « Ventes & comptabilité » (`Administration/admin/dashboard.py`
~l.827-870) contient « Rapports » (la clôture **en ligne**, `comptabilite`) et
« Entries ». La clôture **caisse** (`laboutik`) est rangée ailleurs (~l.477). Un
usager ne comprend pas pourquoi ses ventes de caisse n'apparaissent pas dans
« Rapports ».

En attendant la clôture unique (fiche F), on range les deux, l'un sous l'autre,
**sans modifier les rapports**.

## 2. Le changement

Section « Ventes & comptabilité », dans cet ordre :

| Titre (FR, `_()`) | Lien | Icône |
|---|---|---|
| « Rapport ventes en ligne » | `staff_admin:comptabilite_cloturecaisse_changelist` | `lock` |
| « Rapport ventes caisse » | `staff_admin:laboutik_cloturecaisse_changelist` | `point_of_sale` |
| « Entries » (inchangé) | `staff_admin:BaseBillet_lignearticle_changelist` | `receipt_long` |

- L'entrée caisse est **retirée** de son ancienne section (~l.477), pas dupliquée.
- La permission et la condition d'affichage de l'entrée caisse (module caisse actif)
  sont **reprises telles quelles** de l'ancienne entrée : un lieu sans caisse ne voit
  pas « Rapport ventes caisse ».
- Le texte d'aide du tableau de bord (~l.1289, ~l.1360) suit l'entrée.

## 3. Tests

Fichier : `tests/pytest/test_menu_rapports.py` (base partagée, lit seulement la
navigation construite pour une requête admin).

| Test | Vérifie |
|---|---|
| `test_menu_ventes_comptabilite_range_les_deux_rapports` | un seul test, trois assertions : les liens « en ligne » puis « caisse » sont présents, dans l'ordre, dans la section « Ventes & comptabilité » ; aucune autre section ne pointe vers `laboutik_cloturecaisse_changelist` ; module caisse inactif → l'entrée caisse est absente |

Vu rouge sur le code actuel.

Mutations : inverser l'ordre des deux entrées ; remettre l'entrée caisse dans
l'ancienne section ; retirer la condition « module caisse actif » — chacune fait tomber
le test.

Vérification visuelle dans Chrome : `https://lespass.tibillet.localhost/admin/`.

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-0-menu-rapports.md`, 2 nouvelles
chaînes i18n à signaler.
