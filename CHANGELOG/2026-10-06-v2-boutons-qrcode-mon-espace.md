# Skin V2 : les boutons de paiement par QR code reviennent dans « Mon espace » / V2 skin: QR code payment buttons back in "My space"

**Date :** 2026-10-06
**Migration :** Non

## Résumé / Summary

**Quoi / What :**
- **« Initier un paiement »** (bandeau bleu clair, bouton jaune) est en tête du module
  « Mes responsabilités » de `/my_account/`, pleine largeur. Le module s'affiche aussi pour
  un·e caissier·e qui n'administre aucun lieu.
- **« Scanner un QR code de paiement »** (bouton bleu, bleu « lien » de V2) est sous le bloc
  « Ma carte », avec ou sans carte liée.
- En V2, `/my_account/balance/` n'a plus ces deux boutons (pas de doublon). Le skin classic
  garde les siens.
- Défauts corrigés au passage :
  - **D1** : la route morte `/my_account/tirelire_section/` est supprimée ; le partiel
    `tirelire_section.html` n'a plus de `</section>` orphelin ; ses icônes sont
    `aria-hidden` ; les commentaires des deux `balance.html` ne parlent plus de
    `#tirelire-section`.
  - **D2** : le scanner n'a plus de branche morte (`qrcode_processed`) ni de formulaire de
    repli (il répondait 405 et l'écran restait bloqué). Un QR code qui n'est pas une adresse
    web affiche « Ce QR code n'est pas un QR code de paiement TiBillet. » ; « Démarrer la
    caméra » relance le scan.
  - **D3** : le bouton « Initier un paiement » suit exactement la permission des routes du
    générateur (`CanInitiatePaymentPermissionWithRequest`) : un superuser absent de
    `client_admin` du lieu le voit désormais (index V2 et balance classic).
  - **D4** : « Please valid your email to scan a payment QR Code » est un bouton gris
    désactivé, plus un lien vide qui rechargeait la page (index V2 et partiel classic).

/ "Initiate a payment" heads the "My responsibilities" module; "Scan a payment QR Code" sits
under "My card", with or without a linked card. Both leave the V2 balance page (classic keeps
them). Fixed: dead route and orphan tag (D1), scanner fallback form that answered 405 (D2),
button rule aligned on the route permission, superuser included (D3), empty link replaced by
a disabled button (D4).

**Pourquoi / Why :** le raccourci « My wallet » a été retiré de l'index V2 (commit
`eb519112`). Les deux fonctions n'existaient que sur `/my_account/balance/`, atteinte seulement
par « Historique » quand une carte est liée : sans carte, impossible d'encaisser ou de payer
par QR code.
/ Both features lived only on the balance page, reachable only with a linked card.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `MyAccount.list` et `MyAccount.balance` posent `peut_initier_un_paiement` ; route `tirelire_section` supprimée |
| `pages/templates/pages/V2/vues/compte/index.html` | bandeau d'encaissement en tête de « Mes responsabilités », bouton scanner sous « Ma carte » |
| `pages/templates/pages/V2/vues/compte/balance.html` | plus de bandeau d'encaissement, scanner masqué (`masquer_le_bouton_scanner`), commentaires |
| `pages/templates/pages/classic/vues/compte/balance.html` | condition `peut_initier_un_paiement`, commentaires |
| `BaseBillet/templates/htmx/views/my_account/tirelire_section.html` | `</section>` orphelin, `aria-hidden`, `masquer_le_bouton_scanner`, bouton gris désactivé, `data-testid` |
| `BaseBillet/templates/fonctionnel/qrcode_scan_pay/scanner.html` | branche morte et formulaire de repli retirés, message « pas un QR code de paiement » |
| `pages/static/V2/css/V2.css` | `.compte__encaisser*`, `.compte__scanner` |
| `tests/pytest/test_mon_espace_v2_boutons_qrcode.py` | nouveau : 16 tests (rendu de l'index V2, balance V2 et classic, D1-D4) |

**Traductions :** une chaîne nouvelle, `Ce QR code n'est pas un QR code de paiement TiBillet.`
(workflow i18n à lancer par le mainteneur). Les autres libellés existaient déjà.

---

## Comment tester (à la main) / Manual test

### Test 1 — admin du lieu, skin V2 (`https://lespass.tibillet.localhost/my_account/`)
1. Se connecter avec un compte admin de `lespass`.
2. Le module « Mes responsabilités » commence par un bandeau bleu clair « Vous pouvez initier
   un paiement pour le compte de votre collectif : Lespass » et un bouton jaune « Initier un
   paiement ».
3. Clic sur le bouton → le générateur de paiement (`/qrcodescanpay/get_generator/`).
4. À 390 px de large : le texte et le bouton sont empilés, le bouton prend toute la largeur.

### Test 2 — le scanner sous « Ma carte »
1. Compte à l'email validé, sans carte liée : sous « Pas encore de carte… », un bouton bleu
   « Scanner un QR code de paiement » → `/qrcodescanpay/get_scanner/`.
2. Compte à l'email non validé : à la même place, un bouton gris pâle « Merci de valider votre
   adresse mail… ». Un clic ne fait rien (il ne recharge plus la page).

### Test 3 — caissier·e et autres profils
1. Compte avec le droit « Peut initier des paiements » sur le lieu, admin d'aucun lieu : le
   module « Mes responsabilités » s'affiche, sans compteur, avec le seul bandeau.
2. Simple adhérent : pas de module « Mes responsabilités ».
3. Admin d'un autre lieu seulement : le module liste ce lieu, sans bandeau.
4. Superuser absent de `client_admin` du lieu : le bandeau s'affiche.

### Test 4 — `/my_account/balance/`
1. Skin V2 (`lespass`) : plus de bandeau « Initier un paiement », plus de bouton scanner ;
   « Recharger » et « Demander un remboursement » restent.
2. Skin classic (ex. `festival`) : bandeau et bouton scanner toujours là.

### Test 5 — scanner, contenu qui n'est pas une adresse web (D2)
1. Sur `/qrcodescanpay/get_scanner/`, scanner un QR code qui contient du texte simple.
2. Attendu : « QR Code détecté » puis « Ce QR code n'est pas un QR code de paiement
   TiBillet. » ; « Démarrer la caméra » relance le scan.
3. Un QR code de paiement du même lieu redirige directement ; celui d'un autre lieu passe par
   `/login/<b64>/redirect_session_to_another_tenant/`.
(Le scan lui-même ne se teste pas par capture ni en pytest : caméra réelle nécessaire.)

### Test 6 — D1
1. `https://lespass.tibillet.localhost/my_account/tirelire_section/` → 404.

### Tests automatiques
```bash
make test ARGS="tests/pytest/test_mon_espace_v2_boutons_qrcode.py"
```

---

## Session 10-2 — E2E : les boutons cliqués de bout en bout, sur le vrai Fedow de dev / E2E: the buttons clicked end to end, against the real dev Fedow

**Migration :** Non. **Code de production :** aucun changement.

**Quoi / What :**
- `tests/e2e/test_adhesion_recompense_puis_qrcode.py` : l'étape 4 (« l'adhérent dépense sa
  monnaie par QR code ») se joue dans le navigateur, avec deux contextes (deux téléphones).
  L'encaisseur : `/my_account/` → « Initier un paiement » (bandeau) → montant → QR code et lien
  de paiement affichés → « Vérifier le paiement » répond « en attente ». L'adhérent :
  `/my_account/` → « Scanner un QR code de paiement » (sous « Ma carte ») → scanner → page de
  validation (montant affiché) → « Confirm Payment » → « Paiement confirmé ». L'encaisseur :
  « Paiement en attente. Vérifier maintenant » → « Paiement validé ». L'uuid de la demande se lit
  dans le lien affiché (plus dans « la dernière demande en attente en base »). Le test échoue au
  départ si `lespass` n'est pas en skin V2 (lu par `ConfigurationSite.objects.first()`).
- **Simulé : la caméra seulement.** L'adhérent ouvre le lien de paiement, contenu exact du QR
  code ; pour une adresse du même domaine (vérifié par le test), le scanner ne fait rien d'autre.
- `tests/e2e/test_mon_espace_v2_boutons_qrcode.py` (nouveau, sans émission de monnaie) : l'admin
  sur `/my_account/` à 375 et 1280 px : bandeau pleine largeur, bouton du bandeau cliquable (rien
  ne le couvre), libellés sans débordement, boutons dans l'écran, empilés à 375 px et côte à côte
  à 1280 px. Captures dans `tests/e2e/artefacts/captures/` (ignoré par git). L'admin des E2E a un
  email non validé : c'est la variante grise du bouton scanner (le libellé le plus long) qui est
  mesurée ; la bleue est cliquée par la greffe.

/ Step 4 of the membership-reward journey now clicks the "My space" buttons in two browser
contexts (cashier and member); only the camera is simulated. A new screenshot test checks the
V2 layout at 375 and 1280 px, without issuing money.

**Ce que la greffe émet sur le Fedow de dev, à chaque lancement :** comme avant, 100 MonaLocalim
versés au nouvel adhérent par la cotisation (émission du lieu), puis 1,50 € de cette monnaie
dépensés par QR code au lieu (une vente de 1,50 € de plus) — la greffe n'ajoute aucune émission.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/test_adhesion_recompense_puis_qrcode.py` | étape 4 par les clics, deux contextes, vérification du skin V2 |
| `tests/e2e/test_mon_espace_v2_boutons_qrcode.py` | nouveau : mise en page à 375 et 1280 px, captures |

### Lancer / Run
```bash
make e2e ARGS="tests/e2e/test_adhesion_recompense_puis_qrcode.py"   # émet sur le Fedow de DEV
make e2e ARGS="tests/e2e/test_mon_espace_v2_boutons_qrcode.py"      # sans émission
```
