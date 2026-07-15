# Test carte NFC ↔ wallet Fedow : rendu autonome (plus de skip) / Fedow card test made self-contained

**Date :** 2026-06-29
**Migration :** Non / No

**Quoi / What :** Le test d'intégration `test_membership_card_wallet_fedow` ne
**skippe plus** : sa fixture fabrique elle-même une carte NFC éphémère chez Fedow
si aucune n'est disponible. Il résiste désormais à un reset complet (`down -v`,
qui vide la base Fedow) et ne dépend plus d'une carte renseignée dans `.env`.

**Pourquoi / Why :** Les cartes NFC vivent dans le serveur Fedow (`fedow_django`),
dont le `start.sh` ne crée aucune carte au démarrage (les cartes de démo sont
dans `demo_data`, jamais lancé). Après un `down -v`, plus aucune carte → le test
skippait. Solution : créer la carte **via l'API Fedow** depuis Lespass.

**Fix / Fix :** nouvelle méthode `NFCcardFedow.create_cards(cards_data)` dans
`fedow_connect/fedow_api.py` — POST signé par la place du tenant vers l'endpoint
Fedow `card` (`CardAPI.create`, `HasKeyAndPlaceSignature`), idempotent (201/409).
La fixture `carte_fedow_ephemere` réutilise `FEDOW_TEST_CARD_NUMBER` s'il pointe
une carte encore éphémère, sinon **fabrique une carte fraîche** (numéro/tag
aléatoires). Prérequis : place Fedow signable (cas par défaut en dev).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `fedow_connect/fedow_api.py` | + `NFCcardFedow.create_cards()` (POST signé `card`) |
| `tests/pytest/test_membership_card_wallet_fedow.py` | fixture autonome + test `create_cards` (TDD) |

### Migration
- **Migration nécessaire / Migration required :** Non / No.
