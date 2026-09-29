# laboutik : lecteur NFC muet sur le PV cashless, zone « Recharger » réservée aux caissiers cashless

**Date :** 2026-09-29
**Migration :** Non / No

## 1. PV cashless : le simulateur NFC n'apparaissait pas après VALIDER

**Quoi / What :** sur un point de vente CASHLESS, une recharge + VALIDER affichait
« Approchez la carte », mais sans bouton simulateur, et le lecteur ne démarrait pas.
/ On a cashless POS, VALIDATE showed the card wait, but the reader never started.

**Pourquoi / Why :** la réponse de `moyens_paiement` (`hx_display_type_payment.html`)
contient un champ hors bande (`hx-swap-oob`, clé d'idempotence). htmx déclenche
`htmx:afterSwap` d'abord sur ce champ. L'écouteur `nfcAfterSwap` de
`cotton/V2/read_nfc.html` se retirait à ce premier événement, sans trouver
`.nfc-container` : `initNfc()` n'était jamais appelé.
Les autres attentes de carte (tuile CASHLESS → `hx_read_nfc.html`) n'ont pas de
champ hors bande, d'où un bug limité au PV cashless.
/ The OOB field fired afterSwap first; the listener removed itself too early.

**Correctif / Fix :** `nfcAfterSwap` ignore les swaps sans `.nfc-container` et
ne se retire qu'après avoir trouvé le lecteur. Un seul écouteur à la fois
(`window.nfcEcouteurAfterSwap`) pour ne jamais appeler `initNfc()` deux fois.

## 2. Check carte : zone « Recharger » seulement si la carte primaire a un PV cashless

**Quoi / What :** avant, la zone « Recharger » de la popup check carte
s'affichait depuis n'importe quel PV. Maintenant, elle ne s'affiche que si la
carte primaire du caissier a au moins un point de vente CASHLESS.
Sans carte primaire (accès admin par session), pas de zone non plus.
La recharge reste enregistrée sur le PV courant.
/ The check card "Top up" zone now only shows when the primary card has a cashless POS.

**Comment / How :** `hx_check_card.html` envoie aussi `tag_id_cm` (hx-include).
`retour_carte()` appelle `_carte_primaire_a_un_point_de_vente_cashless()` ;
si la réponse est non, le PV passé à `_construire_contexte_recharge` vaut None.
Les étapes suivantes (`recharge_carte()`) ne sont pas re-filtrées : elles
n'écrivent rien, et `payer()` vérifie déjà l'accès de la carte primaire au PV.

## Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/cotton/V2/read_nfc.html` | `nfcAfterSwap` : ignore les swaps sans lecteur, un seul écouteur |
| `laboutik/templates/laboutik/partial/hx_check_card.html` | hx-include de `tag_id_cm` |
| `laboutik/views.py` | Helper `_carte_primaire_a_un_point_de_vente_cashless()`, garde dans `retour_carte()` |
| `tests/pytest/test_retour_carte_recharge.py` | Fixture PV cashless du caissier, 2 tests (sans PV cashless, sans carte primaire) |
| `tests/e2e/test_pos_cashless_simulateur_nfc.py` | Nouveau : le simulateur apparaît après VALIDER sur le PV cashless |

## Tester / How to test

1. Caisse, PV « Cashless » : toucher une recharge, un tarif, VALIDER.
   Le bouton simulateur apparaît sur « Approchez la carte ». Choisir « Carte client 1 ».
2. Check carte avec la carte primaire de démo (elle a le PV « Cashless ») :
   la zone « Recharger » s'affiche.
3. Admin : retirer le PV « Cashless » de la carte primaire, recharger la caisse,
   check carte : plus de zone « Recharger ». Remettre le PV ensuite.

Tests : `pytest tests/pytest/test_retour_carte_recharge.py tests/e2e/test_pos_cashless_simulateur_nfc.py -v`.
