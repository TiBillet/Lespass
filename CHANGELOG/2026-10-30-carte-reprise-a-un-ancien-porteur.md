# Carte passée à une autre personne chez Fedow : la copie locale suit / Card moved to someone else on Fedow: the local copy follows

**Date :** 2026-10-30
**Migration :** Non

## Resume / Summary
**Quoi / What :** quand Fedow attribue une carte à une personne et que `CarteCashless.user` garde un ancien porteur, Lespass détache la carte de cet ancien porteur en local, la retire des cartes primaires, puis la lie à la personne désignée par Fedow. Le cas passe par `relier_la_copie_locale_de_la_carte`, donc il couvre « Mon compte », `/qr/link/` et l'adhésion saisie dans l'admin. Rien ne bouge chez l'ancien porteur : ni argent, ni jetons, ni adhésion.
/ When Fedow gives a card to someone and `CarteCashless.user` keeps a former holder, Lespass detaches the card from that holder locally, removes it from the primary cards, and links it to the person named by Fedow. No money, token or membership moves.

**Pourquoi / Why :** Fedow fait foi pour le lien carte <-> personne. Une carte vidée dans un autre lieu que son lieu d'origine (VOID caisse V1) puis liée par quelqu'un d'autre gardait l'ancien nom en local : `CarteDejaLiee` à chaque visite (Sentry BILLETTERIE-COOP-VQ). L'alignement du 2026-10-15 ne réparait ce cas que si l'ANCIEN porteur revenait sur son compte.
/ Fedow is authoritative for the card <-> person link. A card voided elsewhere then linked by someone else kept the old name locally, and the repair needed the FORMER holder to come back.

**Limite / Limit :** la réparation se fait au prochain passage du nouveau porteur. Entre-temps, la caisse V2 lit encore l'ancien lien pour les jetons locaux d'un lieu V2. `declarer_la_carte_perdue` garde son alerte « à traiter à la main » : c'est une action humaine sur une autre personne.
/ Repair happens on the new holder's next visit. The lost-card button keeps its manual-fix alert.

**À faire / To do :** comparer `CarteCashless.user` à `Card.user` chez Fedow avant de passer un lieu en V2 (reste à faire du 2026-09-05, en lecture seule).
/ Compare `CarteCashless.user` with Fedow's `Card.user` before switching a venue to V2.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `QrcodeCashless/services.py` | `relier_la_copie_locale_de_la_carte` traite `CarteDejaLiee` : détache l'ancien porteur local, retire la carte des cartes primaires, relie. Docstrings mises à jour |
| `BaseBillet/views.py` | Commentaire de `ScanQrCode.link` : `CarteDejaLiee` n'y arrive plus |
| `tests/pytest/test_carte_perdue_cycle_complet.py` | 3 tests : « Mon compte » rend la carte sans toucher aux soldes de l'ancien porteur (Fedow et local V2), retrait des cartes primaires, liaison par QR code d'une carte vidée ailleurs |

---

## Comment tester (a la main) / Manual test
### Test 1 — « Mon compte » répare la copie locale
1. Une personne A a une carte liée des deux côtés. Une personne B a un compte.
2. Dans un `manage.py shell`, poser `carte.user = B` sur la `CarteCashless`.
3. Se connecter avec A, ouvrir `/my_account/`.
4. Attendu : `carte.user = A`, un warning « détachée de cet ancien porteur » dans les logs, aucune alerte « Divergence ».

### Test 2 — liaison par QR code d'une carte vidée ailleurs
1. Une carte est liée à B des deux côtés.
2. La détacher chez Fedow seulement : `FedowAPI().NFCcard.lost_my_card_by_signature(B, number_printed=carte.number)`.
3. Scanner le QR de la carte, saisir l'email de A.
4. Attendu : `carte.user = A`, aucune alerte « Divergence ».

### Test 3 — l'ancien porteur ne perd rien
1. Après le test 1 ou 2, comparer les soldes de B chez Fedow et dans `fedow_core` : ils sont identiques à avant.
2. Ses adhésions restent à son nom.

### Verifs DB / Playwright
- Pytest : `tests/pytest/test_carte_perdue_cycle_complet.py` (vrai Fedow de dev).
- Carte de production 55B0A867 : se répare à la prochaine visite de son porteur Fedow sur « Mon compte ».
