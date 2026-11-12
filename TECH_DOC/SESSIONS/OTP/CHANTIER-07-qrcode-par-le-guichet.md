# CHANTIER 07 — Le scan d'une carte passe par le guichet / Scanning a card goes through the desk

**Date :** 2026-11-11
**Statut :** relue par Fable 5.2, codée le 2026-11-11 (sauf §3.3, en attente).
**Remplace :** la décision D2 de CHANTIER-02 (« `/qr/link/` hors chantier, inchangé »).

---

## 1. Le problème

Aujourd'hui, `ScanQrCode` (`BaseBillet/views.py`) a deux portes d'entrée sans code de connexion.

| Route | Ce qu'elle fait aujourd'hui | Le défaut |
|---|---|---|
| `GET /qr/<uuid>/`, carte qui a un propriétaire | `login(request, user)` : on entre dans le compte du propriétaire | **A.** Une photo du QR code suffit pour entrer dans « Mon compte » (billets, adhésions, données personnelles). Le paiement en ligne par QR (`QrCodeScanPay`) ne demande que `email_valid`. |
| `GET /qr/<uuid>/`, carte vierge | `logout()`, puis le formulaire `fonctionnel/register.html` (email, noms, CGU, newsletter) | — |
| `POST /qr/link/` (anonyme, `AllowAny`) | Retrouve ou crée le compte de l'email tapé, lui envoie un lien magique, passe `email_valid = False`, puis lie la carte au portefeuille de cet email | **B.** La carte est liée au portefeuille d'un email que la personne n'a pas prouvé. Seule protection : refus si le compte a déjà une carte. **R-2.** `email_valid = False` est posé AVANT tout contrôle de la carte, même avec un UUID inventé. Le guichet donne alors un ticket que le lieu refuse : la personne tourne en boucle sur « lien expiré », on ne lui demande jamais de code. N'importe qui peut le provoquer avec l'email de quelqu'un, et chaque essai envoie un mail. |

## 2. La règle

**Une seule règle, la même que pour réserver ou adhérer (D-AVANT) : un anonyme passe d'abord par le guichet.**
Le guichet demande un code, sauf si ce navigateur a déjà une session au guichet (la personne a pris un billet il y a quelques jours avec ce téléphone : elle passe directement).

Plus aucune connexion automatique au scan. Plus aucun email tapé pour lier une carte.

## 3. Le parcours (codé le 2026-11-11)

### 3.1 `GET /qr/<uuid>/` (`ScanQrCode.retrieve`) — ne lie jamais rien

1. UUID mal formé → 404. Fedow ne connaît pas la carte → 404.
2. L'**hôte** de la requête n'est pas le domaine principal du lieu d'origine de la carte → redirection vers `https://<domaine principal>/qr/<uuid>/`. On compare l'hôte, jamais une sous-chaîne de l'adresse (`?x=<domaine>` n'évite pas la redirection).
3. **Anonyme** → `/connexion/?next=/qr/<uuid>/`.
4. **Connecté** (portefeuille créé s'il manque : `get_or_create_wallet`) :

| La carte… | Ce que fait la vue |
|---|---|
| est la sienne (`wallet_uuid` = son portefeuille) | `/my_account/` |
| est à quelqu'un d'autre | message « Cette carte est liée à un autre compte. », `/my_account/`. On ne dit jamais à qui. |
| est vierge, la personne a déjà une carte | message « Vous avez déjà une carte. Pour la remplacer, déclarez-la perdue dans votre compte, puis scannez de nouveau la nouvelle carte. », `/my_account/` |
| est vierge | page `fonctionnel/lier_la_carte.html` : bouton « Lier cette carte à mon compte » et phrase CGU |

**Pourquoi un bouton (décision du mainteneur, après relecture).** Si le GET liait la carte, deux cas tournent mal :
- sans malveillance : Paul, connecté et sans carte, scanne la carte d'une amie pour l'aider. Fedow vire tout le solde de la carte vers le portefeuille de Paul (`LinkWalletCardQrCode.fusion`). L'amie ne peut plus lier sa carte, et « carte perdue » ne lui rend pas l'argent ;
- avec malveillance : le parcours anonyme → guichet → retour n'est fait que de GET. Un lien, ou une image sur la page d'un autre lieu (cookies `SameSite=Lax`, même site `*.tibillet.coop`), lierait la carte d'un inconnu au compte de la victime. L'inconnu paierait ensuite au bar avec son argent.

### 3.2 `POST /qr/<uuid>/lier/` (`ScanQrCode.lier`)

`IsAuthenticated`, CSRF (formulaire classique avec `{% csrf_token %}`). La carte est liée à `request.user`, aucun email n'est lu. Dans l'ordre :
1. la carte est relue chez Fedow : si elle n'est plus vierge (liée entre l'affichage et le clic), refus ;
2. une seule carte par compte (`has_user_card` chez Fedow) ;
3. `linkwallet_cardqrcode` : Fedow fusionne le portefeuille de la carte dans celui de la personne ;
4. `aligner_les_cartes_locales_sur_fedow` puis `relier_la_copie_locale_de_la_carte` (non bloquants, `logger.error` en cas de divergence) ;
5. les adhésions prises en caisse avec ce numéro de carte passent sur le compte.

Une carte déjà liée à un autre compte ne peut pas être liée : refus à l'étape 1, puis chez Fedow (`LinkWalletCardQrCode`, `Card.objects.filter(user__isnull=True)`), puis en local (`CarteService.lier_a_user` → `CarteDejaLiee`).

### 3.3 Remplacer une carte

**En attente d'une décision du mainteneur** : code à taper, ou bouton « Remplacer » sans code.
En attendant, le chemin existant suffit : « carte perdue » dans « Mon compte », puis scan de la nouvelle carte (§3.1, carte vierge).

La relecture Fable déconseille le code :
- il se contourne : « carte perdue » (sans code) puis scan de la nouvelle carte ;
- juste après le code du guichet, le service répond `"attendre"` (60 s) : aucun mail ne part ;
- sur un téléphone prêté, la boîte mail est souvent dans le même téléphone, et la session permet déjà de payer en ligne.
Si un bouton « Remplacer » est fait : relire chez Fedow que la nouvelle carte est vierge AVANT de détacher l'ancienne ; lire l'ancienne carte chez Fedow (`retrieve_card_by_signature`), jamais dans le formulaire ; boucle `for` sur toutes les anciennes cartes.

## 4. Ce qui a disparu

- `login(request, user)` et `user.is_active = True` au scan ; le `logout()` au scan d'une carte vierge ; le lien « TEST MODE ».
- L'action `ScanQrCode.link` et la route `POST /qr/link/`.
- `fonctionnel/register.html` (email, confirmation, noms, CGU, newsletter). Le nom et la newsletter ne sont plus demandés à la liaison : `Configuration.need_name` n'est plus lu nulle part (champ mort, à retirer un jour).
- `LinkQrCodeValidator`.
- `get_or_create_user(email, force_mail=True)` et `email_valid = False` dans ce parcours : R-2 disparaît.
- `ScanQrCode.get_permissions` (renvoyait `AllowAny` pour toutes les actions et aurait écrasé le `IsAuthenticated` de `lier`). Les permissions sont posées par action.
- `MyAccount.lost_my_card` et `admin_lost_my_card` passent en POST (`hx-post` dans `pages/templates/pages/{V2,classic}/vues/compte/...` et `Administration/templates/admin/membership/wallet_info.html`). En GET, un lien ou une image pouvait détacher la carte.

## 5. Ce qui ne bouge pas

- La caisse, la borne, le paiement au bar avec la carte NFC sans compte.
- La liaison par email tapé **par le personnel** : adhésion en caisse V2 (`laboutik/views.py`, `_declarer_adherent_au_reseau`, carte anonyme + email → `linkwallet_card_number` puis `CarteService.lier_a_user`), adhésion dans l'admin (`MembershipAddForm`), commande `lier_carte`. Ce n'est pas une preuve de l'email : c'est la responsabilité du personnel, assumée.
- Les QR déjà imprimés (et la redirection `/<uuid>` → `/qr/<uuid>/`).
- Le lien magique `/emailconfirmation/` : chantier I-3, à part.

## 6. Points tranchés

| # | Question | Décision |
|---|---|---|
| Q1 | Liaison immédiate au GET ? | Non : page de confirmation + bouton POST (§3.1). |
| Q2 | CGU ? | Le guichet n'en fait accepter aucune. Une phrase avec le lien CGU au-dessus du bouton « Lier », pas de case. |
| Q3 | Plafonds du code de remplacement ? | Sans objet tant que le remplacement n'a pas de code (§3.3). |

## 7. Tests

- `tests/pytest/test_scan_qrcode_par_le_guichet.py` (11 tests, Fedow simulé, chacun vu en échec par mutation) : anonyme → guichet ; le scan ne connecte pas au compte du propriétaire ; carte à soi → `/my_account/` ; carte d'un autre jamais liée ; carte vierge → bouton, rien de lié au GET ; une seule carte par compte ; POST anonyme → 403 ; carte devenue liée entre-temps → refus ; hôte comparé (pas de sous-chaîne) ; `POST /qr/link/` n'existe plus ; `GET lost_my_card` → 405.
- Repris : `test_carte_perdue_cycle_complet.py`, `test_vues_carte_branchees_sur_service.py`, `test_carte_liee_chez_fedow_fed_en_caisse.py`, `test_mon_espace_v2_boutons_qrcode.py`, `test_pos_adhesion_fusion_wallet_fedow.py`.
- E2E contre le vrai Fedow : `test_carte_liee_par_qrcode_fed_en_caisse.py` (liaison par le bouton, recharge FED, café au bar) et `test_carte_perdue_recharge_fed.py` (carte perdue en POST, la personne qui reprend la carte n'hérite de rien).
