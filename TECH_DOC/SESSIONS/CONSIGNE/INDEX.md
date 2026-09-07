# CONSIGNE — Hub

Consigne et retour de consigne au point de vente V2 (parité V1), et réparation de
la ventilation comptable du chèque.

## Documents
- [SPEC.md](SPEC.md) — spécification validée en brainstorming (2026-09-07)
- Implémentation faite le 2026-09-07 ; voir `CHANGELOG/2026-09-07-consigne-et-ventilation-cheque.md`

## En une phrase
Le retour de consigne devient une opération réelle — ligne comptable négative en
espèces, **recharge du wallet** en cashless — détectée par
`methode_caisse=RETOUR_CONSIGNE` et non plus par un UUID mort ; et le chèque
cesse de disparaître de la clôture et de l'archive fiscale.

## Décisions clés
- Espèces **et** NFC (parité V1) · détection par méthode, `UUID_ARTICLE_CONSIGNE`
  supprimée · asset via `Product.asset` en catégorie **TLF** (jamais `Price.asset`) ·
  refus **serveur** du remboursement par CB/chèque · **panier mixte refusé** (l'`abs()`
  du total n'a de sens que sur un panier entièrement négatif) · crédit Fedow **DANS**
  l'`atomic()` avec la ligne comptable · un article `CR` **ne touche pas au stock** ·
  colonne `laboutik.ClotureCaisse.total_cheque` + migration, remplie aux **trois**
  sites de clôture.

## Corrections issues de la relecture adverse (Fable, 2026-09-07)
Trois erreurs de la première version, vérifiées dans le code avant correction :
1. « crédit hors atomic » était **faux et dangereux** — `creer_recharge` est une
   écriture DB locale (aucun import réseau dans `fedow_core/services.py`), appelée
   dans l'`atomic()` à ses 5 sites. La consigne inverse fabriquait le cas « argent
   crédité sans ligne comptable ».
2. **Trois** sites créent une `ClotureCaisse` (`views.py:2041` manuelle,
   `tasks.py:489` journalière, `tasks.py:774` agrégats), pas un seul.
3. Le **stock** est décrémenté « toujours » (`inventaire/services.py:29`) : un retour
   de consigne aurait décrémenté le stock au retour du gobelet, et aurait été bloqué
   à stock zéro.

## Les deux bugs à l'origine
1. `UUID_ARTICLE_CONSIGNE` (`laboutik/views.py:152`) ne correspond à **aucun
   produit** : la consigne V2 n'a jamais pu se déclencher.
2. `archivage.py:236` écrivait **`total_cheque = '0'` en dur** — l'archive fiscale
   LNE est fausse dès qu'un chèque est encaissé.

## Hors périmètre (chantiers séparés)
- Double webhook Stripe sur `invoice.paid` — garde non atomique
  (`ApiBillet/views.py:1409`), diagnostiquée le 2026-09-07, voir SPEC §10.
- Cashback et fidélité (`Product.FIDELITE` déclaré, jamais utilisé).
