# controlvanne : facturation fiabilisée (stock, réservoir, montants, requêtes, refus)

**Date :** 2026-09-28
**Migration :** Non / No (`makemigrations --check` : « No changes detected »)

## Résumé / Summary

**Quoi / What :** points 2.1 à 2.6 de l'audit du 2026-09-26 (lot 2,
facturation). Ils sont retirés de
`CHANGELOG/a traiter/controlvanne-audit-securite-facturation.md`.

- **2.1 — Une erreur de stock n'annule plus la facture.** Le décrément de
  stock (`billing.py`, étape 5 de `facturer_tirage`) était entouré d'un
  `except Exception: pass`, **sans savepoint**. Une erreur SQL dans
  `StockService` cassait la transaction Postgres. L'erreur était cachée, puis la
  requête suivante levait `current transaction is aborted` : réponse 500, et
  transactions, `LigneArticle` et fermeture de session annulées. Désormais :
  - on ne décrémente que si le produit a un stock (`hasattr`) ;
  - l'appel se fait dans un `transaction.atomic()` imbriqué (savepoint) ;
  - l'erreur est journalisée (`logger.exception`) ;
  - la facture est conservée.
  **Contre-épreuve faite :** avec l'ancien code, le test échoue sur cette
  même erreur ; avec le nouveau, il passe.
- **2.2 — Réservoir décrémenté sur la valeur à jour.** Avant, le code lisait
  `tireuse.reservoir_ml` sans verrou, puis réécrivait le résultat : deux
  fermetures simultanées perdaient une décrémentation. Désormais,
  `update(reservoir_ml=Greatest(F("reservoir_ml") - volume, 0))` fait la
  soustraction dans la base, puis `refresh_from_db`. `update()` ne déclenchant
  pas `post_save`, l'envoi de l'état aux kiosks est extrait dans
  `pousser_etat_de_la_tireuse` (`signals.py`) et appelé explicitement.
- **2.3 — Montants calculés par le serveur.** Nouvelles fonctions communes dans
  `billing.py`, utilisées par la facture ET par les messages du kiosk :
  `calculer_montant_centimes`, `calculer_nombre_de_verres` et `formater_euros`.
  Les messages WebSocket portent `solde_affiche`, `nombre_verres`,
  `prix_servi_centimes` et `prix_servi_affiche`. En fin de service,
  `prix_servi_*` est le montant **réellement facturé** (il peut être inférieur
  si le solde manquait). `ecran_tireuse.js` ne calcule plus rien (plus de
  `prix_litre × 0,25`, plus de `formaterEuros`) : il écrit ces valeurs. Les
  attributs `data-prix-litre` des templates sont retirés.
- **2.4 — `pour_update` : de 18 à 8 requêtes SQL** (environ un appel par seconde
  et par tireuse) :
  - `select_related("terminal", "fut_actif")` sur la tireuse ;
  - `select_related("carte__user")` sur la session ;
  - `prix_litre` lu une seule fois et passé au constructeur du message ;
  - le solde lu à l'`authorize` est gardé en cache (clé avec le lieu, 6 h) et
    sert à estimer le solde pendant le tirage, au lieu de relire la cascade
    TNF → TLF → FED à chaque seconde. Si le cache est vide, on relit. Rien
    n'est débité avant le `pour_end`, donc l'estimation est la même.
- **2.5 — Cartes maintenance limitées à certaines tireuses.** Le réglage
  `CarteMaintenance.tireuses` (« vide = toutes ») n'était jamais vérifié. Une
  carte limitée à d'autres tireuses est maintenant refusée, et le refus est
  poussé au kiosk (« Carte maintenance non autorisée sur cette tireuse. »).
- **2.6 — Refus sur tireuse désactivée affiché.** Une carte normale sur une
  tireuse hors service est refusée, et le refus est maintenant **poussé au
  kiosk** (« Tireuse hors service. »). Avant, seul le Pi le recevait.
- **Au passage :** `_push_refus` est réécrit (indentation irrégulière,
  commentaire périmé sur un délai de 4 s qui n'existe plus). Il prend
  `solde_centimes` au lieu d'une chaîne `balance`.

/ 2.1 stock error no longer cancels the bill (savepoint). 2.2 reservoir
decremented in SQL. 2.3 money computed server-side, kiosk JS only writes.
2.4 pour_update from 18 to 8 SQL queries. 2.5 maintenance card tap
restriction enforced. 2.6 disabled-tap refusal shown on the kiosk.

## Fichiers / Files

| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/billing.py` | `calculer_montant_centimes`, `calculer_nombre_de_verres`, `formater_euros` ; stock dans un savepoint |
| `controlvanne/viewsets.py` | Réservoir en SQL (`F` + `Greatest`) ; `_champs_du_solde`, `_lire_le_solde_de_la_carte`, cache du solde ; constructeur du message avec les montants ; `select_related` ; refus 2.5 et 2.6 ; `_push_refus` réécrit |
| `controlvanne/signals.py` | `pousser_etat_de_la_tireuse` (extrait du `post_save`) |
| `controlvanne/ws_payloads.py` | Champs `solde_affiche`, `nombre_verres`, `prix_servi_centimes`, `prix_servi_affiche` |
| `controlvanne/static/controlvanne/js/ecran_tireuse.js` | Plus de calcul d'argent : écrit les valeurs du serveur (`?v=7`) |
| `controlvanne/templates/controlvanne/partial/tireuse_ecran.html`, `tireuse_vignette.html` | `data-prix-litre` et `{% load l10n %}` retirés |
| `tests/pytest/test_controlvanne_facturation_lot2.py` | Nouveau : 9 tests (fonctions d'argent, erreur de stock, réservoir à jour, montants des messages, nombre de requêtes, refus 2.5 et 2.6) |

## À tester / To test

1. **Montants** : badger, verser, retirer la carte. Le bilan « Tu as tiré X cl
   pour Y € » affiche **exactement** le montant débité (à vérifier dans
   l'historique de la carte).
2. **Solde insuffisant en cours de tirage** : le bilan affiche le montant
   réellement facturé (partiel), pas le prix théorique du volume.
3. **Carte maintenance** : dans l'admin, limiter une carte maintenance à la
   tireuse A. Sur la tireuse B hors service → écran « Carte refusée ». Retirer
   la limite → rinçage accepté.
4. **Tireuse hors service** : badger une carte client → écran « Carte refusée »
   avec « Tireuse hors service. », puis retour à l'écran maintenance au retrait.

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_*.py -q
```
