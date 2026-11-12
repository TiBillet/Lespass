# Le scan d'une carte passe par le guichet / Scanning a card goes through the login desk

**Date :** 2026-11-11
**Migration :** Non

## Resume / Summary
**Quoi / What :**
1. Scanner le QR code d'une carte ne connecte plus personne. Une personne anonyme part au guichet de connexion (code à 6 chiffres, ou passage direct si ce navigateur a déjà une session au guichet), puis revient sur la carte.
2. Une carte vierge se lie par un bouton « Lier cette carte à mon compte » (`POST /qr/<uuid>/lier/`), toujours au compte connecté. Plus aucun email n'est tapé pour lier une carte.
3. Une carte liée à un autre compte affiche « Cette carte est liée à un autre compte. », sans dire lequel. Sa propre carte mène à « Mon compte ». Une personne qui a déjà une carte est invitée à déclarer l'ancienne perdue avant d'en lier une nouvelle.
4. L'ancienne route anonyme `POST /qr/link/`, son formulaire (`register.html`) et `LinkQrCodeValidator` sont supprimés. Avec eux disparaissent : le mail de connexion envoyé à n'importe quel email tapé, le passage `email_valid = False` (R-2 : la personne tournait en boucle sur « lien expiré » au guichet) et la liaison d'une carte au portefeuille d'un email non prouvé.
5. « Carte perdue » (dans « Mon compte » et dans l'admin) passe en POST : un simple lien ou une image ne peut plus détacher une carte.
6. La redirection vers le domaine d'origine de la carte compare l'hôte de la requête, plus une sous-chaîne de l'adresse.

/ 1. Scanning a card no longer logs anyone in; anonymous people go to the login desk. 2. A blank card is linked with a button (POST), always to the logged-in account; no email is typed anymore. 3. Another account's card is refused without saying whose. 4. The anonymous `POST /qr/link/`, its form and validator are removed (no more mail to any typed address, no more `email_valid = False`, no more card linked to an unproven email). 5. "Lost card" is POST only. 6. Origin-domain redirect compares the host.

**Pourquoi / Why :** relecture de sécurité (R-2) et simplification : une seule règle pour tout le site, « un anonyme passe par le guichet ». Spec : `TECH_DOC/SESSIONS/OTP/CHANTIER-07-qrcode-par-le-guichet.md`.
/ Security review (R-2) and simplification: one rule for the whole site.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `ScanQrCode` réécrit (`retrieve` sans effet de bord, action `lier` en POST connecté, `get_permissions` supprimé) ; `lost_my_card` et `admin_lost_my_card` en POST |
| `BaseBillet/templates/fonctionnel/lier_la_carte.html` | Nouveau : page de confirmation, bouton « Lier », phrase CGU |
| `BaseBillet/templates/fonctionnel/register.html` | Supprimé |
| `BaseBillet/validators.py` | `LinkQrCodeValidator` supprimé |
| `pages/templates/pages/{V2,classic}/vues/compte/...`, `Administration/templates/admin/membership/wallet_info.html` | Boutons « carte perdue » en `hx-post` |
| `tests/pytest/test_scan_qrcode_par_le_guichet.py` | Nouveau : 11 tests du parcours |
| `tests/pytest/test_carte_perdue_cycle_complet.py`, `test_vues_carte_branchees_sur_service.py`, `test_carte_liee_chez_fedow_fed_en_caisse.py`, `test_mon_espace_v2_boutons_qrcode.py`, `test_pos_adhesion_fusion_wallet_fedow.py` | Liaison par `POST /qr/<uuid>/lier/`, carte perdue en POST |
| `tests/e2e/test_carte_liee_par_qrcode_fed_en_caisse.py`, `test_carte_perdue_recharge_fed.py` | Liaison par le bouton, sans formulaire email ni lien « TEST MODE » |

Chaînes traduisibles ajoutées (msgid FR) : « Lier ma carte TiBillet », « Cette carte va être liée à votre compte <strong>%(email)s</strong>. », « Si la carte porte déjà de l'argent, il passe sur votre compte. Ensuite, elle paie avec l'argent de votre compte : liez-la seulement si vous l'avez en main. », « En liant cette carte, j'accepte <a …>les conditions générales</a>. », « Lier cette carte à mon compte », « Cette carte est liée à un autre compte. », « Vous avez déjà une carte. Pour la remplacer, déclarez-la perdue dans votre compte, puis scannez de nouveau la nouvelle carte. », « Votre carte est liée à votre compte. ». Chaînes du formulaire `register.html` devenues inutilisées. Le workflow i18n est à lancer.

---

## Comment tester (a la main) / Manual test
### Test 1 — anonyme
1. Se déconnecter. Ouvrir `/qr/<uuid d'une carte vierge>/`.
2. Attendu : le guichet de connexion. Après le code, retour sur la page « Lier ma carte ».

### Test 2 — lier une carte vierge
1. Connecté, sans carte. Ouvrir `/qr/<uuid d'une carte vierge>/`.
2. Attendu : la page « Lier ma carte », rien n'est lié tant qu'on n'a pas cliqué.
3. Cliquer « Lier cette carte à mon compte ». Attendu : « Mon compte », message « Votre carte est liée à votre compte. », la carte apparaît.

### Test 3 — la carte d'un autre
1. Connecté avec un autre compte, ouvrir `/qr/<uuid de la carte du test 2>/`.
2. Attendu : « Cette carte est liée à un autre compte. », sans email. On n'entre pas dans le compte du propriétaire.

### Test 4 — remplacer sa carte
1. Avec la carte du test 2, scanner une autre carte vierge. Attendu : message « Vous avez déjà une carte… ».
2. « Mon compte » → « carte perdue » (fenêtre de confirmation), puis rescanner la nouvelle carte : la page « Lier ma carte » s'affiche.

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_scan_qrcode_par_le_guichet.py"`.
- `make e2e ARGS="tests/e2e/test_carte_liee_par_qrcode_fed_en_caisse.py tests/e2e/test_carte_perdue_recharge_fed.py"` (vrai Fedow, vrai Stripe, `stripe listen` lancé).
