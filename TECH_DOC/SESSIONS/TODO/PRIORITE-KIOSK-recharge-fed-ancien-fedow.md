# PRIORITÉ — Kiosque : la recharge doit rester un FED sur l'ancien Fedow

> **Label : PRIORITÉ.** À traiter **juste après le chantier 05 « montants entiers »**
> (décision du mainteneur, 2026-09-30).
> Constat fait à la fusion de `origin/main-fedow-import` dans la branche du chantier 05.

## Le problème en une phrase

Le comportement métier de la recharge au kiosque a changé : la carte est créditée en
**monnaie locale (TLF) dans la base locale** (`fedow_core`), alors que la règle est
**un FED sur l'ancien Fedow**.

## Ce qui était prévu (la règle)

`TECH_DOC/SESSIONS/KIOSK/SPEC.md` §1 et §8bis :

1. Le kiosque crée le paiement sur le terminal Stripe (compte Stripe **Root**), avec des
   métadonnées en clair (`fedow_place_uuid`, `tag_id`).
2. **L'ancien Fedow** reçoit le webhook Stripe et crédite la carte en **FED** (asset
   fédéré). Lespass n'écrit rien.

Ce crédit n'arrivait jamais : le patch côté ancien Fedow (« route TPE étendue », branche
Lespass sans signature, SPEC §8bis) n'a pas été livré, et le webhook n'arrive pas en local.

## Ce qui a changé

Commit `f47023f4` « [kiosk] Use local fedow to recharge cards » (2026-09-29, fusionné par
la PR #476). Son CHANGELOG : `CHANGELOG/2026-09-29-kiosk-credit-local.md`.

- Quand Stripe confirme le paiement, Lespass crédite la carte **en local**, en **TLF**,
  avec le produit « Recharge euros » (tarif libre) et la fonction de la caisse
  `_executer_recharges` (`kiosk/credit.py`, `crediter_la_carte_du_paiement`).
- Il écrit une `LigneArticle` payée « carte bancaire », origine « Caisse », **sans `Vente`
  ni `Reglement`**.
- Raison donnée par l'auteur : la borne est un module V2, la caisse V2 crédite en local ;
  borne et caisse doivent afficher le même solde.

## Les risques

1. **Mauvais asset.** Le client paie une recharge fédérée et reçoit de la monnaie locale du
   lieu : elle ne se dépense pas ailleurs dans la fédération.
2. **Double crédit.** Les métadonnées pour le webhook de l'ancien Fedow partent toujours
   (`kiosk/models.py`, `send_to_terminal`). Le jour où le patch de l'ancien Fedow est livré,
   la carte reçoit du FED **et** de la TLF pour un seul paiement.
3. **Comptabilité.** La ligne est comptée comme une vente CB **de la caisse**, alors que
   l'argent arrive sur le compte Stripe Root (celui de la fédération), pas chez le lieu.
4. **Chantier 05, fiche H.** Le crédit passe par la branche « vente absente » de
   `_creer_lignes_articles`, que la fiche H supprime : le kiosque casserait à ce moment-là.
   La docstring de `_executer_recharges` (« tous les chemins de la caisse passent une
   vente ») est devenue fausse.
5. **Aucun test ne protège la règle.** `tests/pytest/test_kiosk_credit.py` (7 tests,
   écrit par le même commit) vérifie le **nouveau** comportement (crédit local). Aucun test
   ne vérifie un crédit en FED sur l'ancien Fedow.

## La contrainte technique

Lespass ne peut pas créer de FED sur l'ancien Fedow sans Stripe : l'ancien Fedow refuse le
FED dans `refill_from_lespass` (`../Fedow/fedow_core/serializers.py` ~l.894-900, vu en
chantier 05, session B-2d). Le FED ne naît que d'un paiement Stripe vu **par l'ancien
Fedow**. Rester en FED demande donc que l'ancien Fedow crédite lui-même (le patch webhook
de la SPEC §8bis), ou une autre route à ouvrir côté ancien Fedow.

## À faire (session à ouvrir)

1. **Trancher avec l'auteur du commit** : FED sur l'ancien Fedow (la règle) — comment
   livrer le crédit côté ancien Fedow ?
2. Retirer le crédit local du kiosque, ou le garder en secours — **jamais les deux** (pas de
   double crédit), avec un test qui le prouve.
3. Tests : un test qui fige « la recharge au kiosque crédite du FED sur l'ancien Fedow »
   (faux ancien Fedow en pytest, E2E réel si possible, comme le chantier 05 B-2d).
4. Comptabilité : si Lespass écrit quelque chose, une `Vente` hors chiffre d'affaires comme
   la caisse (chantier 05, fiche D : « une vente par paiement »).

## Fichiers concernés

`kiosk/credit.py`, `kiosk/models.py` (`get_from_stripe`, `send_to_terminal`,
`crediter_la_carte_si_besoin`), `kiosk/carte.py` (solde affiché), `kiosk/tasks.py`,
`tests/pytest/test_kiosk_credit.py`, `TECH_DOC/SESSIONS/KIOSK/SPEC.md`,
`laboutik/views.py` (`_executer_recharges`), ancien Fedow (`../Fedow`, webhook Stripe TPE).
