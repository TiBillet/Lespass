# Tirelire V2 : bandeau « Initier un paiement » / V2 wallet: "Initiate a payment" banner

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** `/my_account/balance/` (skin V2) affiche le bandeau « Initier un paiement », celui du module « Mes responsabilités » de `/my_account/`, au-dessus du bouton scanner. Il apparaît avec la même règle : `peut_initier_un_paiement`, calculé par la vue avec `CanInitiatePaymentPermissionWithRequest`. Ont le droit : un admin du lieu, un utilisateur avec le droit `initiate_payment` sur le lieu, ou un superuser.
/ The V2 wallet page shows the "Initiate a payment" banner from `/my_account/`, with the same permission rule.

**Pourquoi / Why :** un admin ou un caissier doit pouvoir encaisser depuis sa tirelire sans revenir à `/my_account/`.
/ Admins/cashiers can collect a payment straight from the wallet page.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/vues/compte/balance.html` | bandeau `compte-initier-paiement` en tête de `.compte-tirelire` |
| `pages/static/V2/css/V2.css` | `.compte-tirelire .compte__encaisser` : sans marge latérale, espace avant le scanner |
| `tests/pytest/test_mon_espace_v2_boutons_qrcode.py` | admin : bandeau présent ; adhérent sans droit : absent (vérifié par mutation) |

---

## Comment tester (a la main) / Manual test
### Test 1 — admin
1. Se connecter avec `admin@admin.com` sur un lieu au skin V2.
2. Ouvrir `/my_account/balance/` : le bandeau bleu « Vous pouvez initier un paiement… » apparaît au-dessus du bouton scanner, avec le bouton jaune « Initier un paiement ».
3. Le bouton mène au générateur de QR code (`/qrcodescanpay/get_generator/`).
4. Sur mobile, le bandeau s'empile et le bouton prend toute la largeur.

### Test 2 — adhérent sans droit
1. Se connecter avec un compte qui n'administre pas le lieu et n'a pas le droit « initier un paiement ».
2. `/my_account/balance/` : pas de bandeau, seulement le scanner.

`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_mon_espace_v2_boutons_qrcode.py -q`
