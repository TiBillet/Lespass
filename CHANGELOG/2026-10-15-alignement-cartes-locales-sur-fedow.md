# Cartes locales alignées sur Fedow / Local cards aligned on Fedow

**Date :** 2026-10-15
**Migration :** Non

## Resume / Summary
**Quoi / What :** à la liaison d'une carte par QR code (`/qr/link/`) et à l'ouverture de « Mon compte » (`/my_account/`, les deux skins), Lespass lit les cartes de la personne chez l'ancien Fedow et recopie cet état dans `CarteCashless` : une carte liée en local mais absente chez Fedow est détachée, une carte de Fedow non liée en local est reliée. Fedow injoignable : la page s'affiche, rien n'est touché en local.
/ When linking a card by QR code and when opening "My account", Lespass reads the person's cards on the old Fedow and copies that state into `CarteCashless`: local cards Fedow no longer has are detached, Fedow cards missing locally are linked. Fedow down: the page renders, nothing changes locally.

**Pourquoi / Why :** la caisse V1 (LaBoutik) vide une carte en mode VOID (carte perdue) : Fedow la détache de la personne sans prévenir Lespass. La copie locale gardait l'ancienne personne, et la liaison d'une nouvelle carte était refusée en local (`UserADejaCarte`, alerte Sentry « Divergence Fedow/Lespass »). Fedow fait foi pour le lien carte <-> personne : toute liaison côté Lespass passe d'abord par lui.
/ The V1 register VOIDs a card: Fedow detaches it without telling Lespass. The local copy kept the old owner and the next card's local link was refused. Fedow is authoritative for the card <-> person link.

**Limite / Limit :** la réparation se fait au prochain passage de la personne (`/qr/link/` ou `/my_account/`). Entre-temps, la caisse V2 lit encore le lien local pour les jetons locaux d'un lieu V2 (piste : vérifier Fedow au scan en caisse V2, non faite). L'argent tenu par Fedow (FED, monnaies des lieux V1) n'est pas concerné : Fedow vide toujours le portefeuille actuel de la carte.
/ Repair happens on the person's next visit. Meanwhile the V2 register still reads the local link for a V2 venue's local tokens. Money held by Fedow is not affected.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `QrcodeCashless/services.py` | **Nouvelles** fonctions `aligner_les_cartes_locales_sur_fedow(utilisateur, cartes_chez_fedow, ip)` et `retirer_la_carte_des_cartes_primaires(carte)` (une carte détachée ne doit plus ouvrir de caisse, dans aucun lieu) |
| `BaseBillet/views.py` (`declarer_la_carte_perdue`) | Le retrait des cartes primaires passe par `retirer_la_carte_des_cartes_primaires` (même comportement) |
| `BaseBillet/views.py` | `ScanQrCode.link` : alignement avant la liaison locale de la nouvelle carte, dans son propre `try` (un échec sur une autre carte n'empêche pas la liaison de la nouvelle). `MyAccount.list` : lecture des cartes chez Fedow + alignement ; le skin V2 réutilise cette lecture |
| `tests/pytest/test_carte_perdue_cycle_complet.py` | 5 tests : liaison par QR code après un VOID V1, « Mon compte » après un VOID V1, « Mon compte » après un VOID V1 retire la carte de caissier, « Mon compte » garde une carte liée des deux côtés, « Mon compte » avec Fedow injoignable. Texte du xfail strict mis à jour (le trou reste ouvert entre le VOID et le prochain passage) |
| `tests/pytest/test_vues_carte_branchees_sur_service.py`, `test_carte_liee_chez_fedow_fed_en_caisse.py`, `test_mon_espace_v2_boutons_qrcode.py`, `test_kiosk_security.py` | Le faux Fedow rend aussi les cartes de la personne (`retrieve_card_by_signature`), cohérentes avec ses cartes locales. Un `MagicMock` nu rendait une liste vide : l'alignement aurait détaché ses cartes locales |
| `tests/pytest/test_admin_fil_ariane_et_rail.py` | Hors chantier : le domaine d'admin « Lespass » s'appelle « Espace en ligne » depuis la réécriture des textes de l'admin (`Administration/admin/dashboard.py`) ; les deux assertions suivent |

**À savoir / Known :** une personne qui a deux cartes chez Fedow (Fedow l'accepte quand son portefeuille n'a aucun jeton) n'en garde qu'une en local (anti-vol `UserADejaCarte`) : chaque ouverture de « Mon compte » journalise alors une erreur « Divergence Fedow/Lespass », à traiter à la main.
/ A person with two cards on Fedow keeps only one locally: each "My account" visit logs a divergence error.

---

## Comment tester (a la main) / Manual test
### Test 1 — nouvelle carte après un VOID en caisse V1
1. Une personne a une carte A liée (des deux côtés).
2. Simuler le VOID V1 : dans un `manage.py shell`, sur le tenant, `FedowAPI().NFCcard.lost_my_card_by_signature(user, number_printed=A.number)` (détache chez Fedow seulement).
3. Vérifier : `CarteCashless` A a toujours `user = la personne`.
4. Scanner le QR d'une carte vierge B, saisir l'email de la personne.
5. Attendu : B liée à la personne en local, A détachée (`user = None`), aucune alerte « Divergence » dans les logs.

### Test 2 — « Mon compte » répare seul
1. Mêmes étapes 1 à 3.
2. Se connecter avec la personne, ouvrir `/my_account/`.
3. Attendu : A détachée en local ; un warning « détachée chez Fedow mais encore liée en local » dans les logs.

### Test 3 — Fedow en panne
1. Couper l'accès à Fedow (ou le conteneur Fedow de dev).
2. Ouvrir `/my_account/` : la page s'affiche, un warning « cartes ... illisibles chez Fedow », les cartes locales ne bougent pas.

### Verifs DB / Playwright
- Pytest : `tests/pytest/test_carte_perdue_cycle_complet.py` (vrai Fedow de dev).
- Diagnostic d'une personne en prod (lecture seule) : comparer `user.cartecashless_set.all()` avec `FedowAPI().NFCcard.retrieve_card_by_signature(user)`.
