# SPEC — Scan QR carte cashless V2 (fedow_core, sans Fedow distant)

**Date :** 2026-04-20
**Statut :** Design validé après brainstorm 2026-04-20, prêt pour writing-plans
**Scope :** Bascule du flow public "scan QR carte cashless" de `fedow_connect/fedow_api.py` vers `fedow_core/services.py`. Inclut : scan QR, identification user (link), fusion wallet éphémère → user.wallet, perte de carte.

---

## 1. Contexte et problème

### Flow concerné

URL publique : `https://<tenant>.tibillet.localhost/qr/<qrcode_uuid>/`

Côté V1 actuel :
- Client : `BaseBillet/views.py:394 ScanQrCode` (ViewSet)
- GET `/qr/<uuid>/` → `fedowAPI.NFCcard.qr_retrieve()` (HTTP vers Fedow distant)
- POST `/qr/link/` → `fedowAPI.wallet.get_or_create_wallet()` + `fedowAPI.NFCcard.linkwallet_cardqrcode()` (fusion)
- Perte : `BaseBillet/views.py:1134 lost_my_card()` + `admin_lost_my_card()` → `fedowAPI.NFCcard.lost_my_card_by_signature()`

### Problèmes V1

1. **HTTP + RSA inter-service** : latence réseau, double signature RSA, race conditions sur fusion multi-tokens.
2. **Source de vérité dupliquée** : `CarteCashless` (Lespass, SHARED_APPS) et `Card` (Fedow distant) sont deux miroirs. Risque de désynchro sur `user`/`wallet_ephemere`.
3. **Aucune tenant isolation côté Fedow distant** : protection anti-vol implicite, difficile à auditer.

### Décision

Bascule totale du flow scan QR public vers `fedow_core`. Le serveur Fedow legacy n'est plus consulté pour ce flow. Les tenants V2 (nouveau déploiement) utilisent uniquement `fedow_core/services.py`. **Coexistence V1/V2 par tenant** : les tenants legacy avec `Configuration.server_cashless` renseigné continuent d'appeler `fedow_connect` (inchangé).

---

## 2. Périmètre

### Dans le scope

- GET `/qr/<qrcode_uuid>/` — scan public (redirection cross-domain, login si user identifié, formulaire si carte anonyme).
- POST `/qr/link/` — identification email → anti-vol → get_or_create user + wallet → fusion wallet éphémère → update carte.user.
- GET `/my_account/lost_my_card/<number>/` — déclaration de perte par le user lui-même.
- GET `/admin/.../admin_lost_my_card/<user_pk>:<number>/` — déclaration de perte par l'admin tenant.
- Transaction `action=FUSION` dans `fedow_core` (déjà en place dans `TransactionService`).
- Rattrapage adhésions anonymes après fusion (`Membership.objects.filter(user__isnull=True, card_number=...)`).

### Hors scope (autres sessions)

- Recharge FED V2 (Session 31 ✅)
- Refill TLF en caisse (sessions POS 01-06 ✅)
- Vente (SALE, QRCODE_SALE) déjà V2 ✅
- Adhésions (`MembershipFedow.create`) — session future
- Bootstrap place (`PlaceFedow.create_place`) — session future
- Transactions list/history (`TransactionFedow`) — Session 33 partielle
- Asset management (`AssetFedow.create_*`, `archive_asset`) — session future

---

## 3. Décisions architecturales

| Décision | Valeur | Raison |
|---|---|---|
| **Modèle CarteCashless** | Aucun changement de schema (YAGNI) | Scope A n'a besoin de rien de nouveau |
| **Identifiant QR public** | `CarteCashless.uuid` (déjà utilisé comme qrcode_uuid en V1 via `/qr/<uuid>/`) | Pas de nouveau champ `qrcode_uuid` séparé |
| **Redirection cross-domain** | Conservée (302 vers primary_domain du tenant d'origine) | UX V1 préservée : "scanner une carte ramène toujours sur son festival d'origine" |
| **Résolution tenant d'origine** | `carte.detail.origine` (FK `Customers.Client`) | SHARED_APPS permet accès direct, pas besoin de recherche par `SALLE_SPECTACLE` |
| **Wallet éphémère** | `CarteCashless.wallet_ephemere` (FK `AuthBillet.Wallet`, SET_NULL) | Déjà présent depuis Phase 0 |
| **Création wallet éphémère** | Lazy : à la première lecture d'une carte vierge, on crée le wallet et on l'attache | Reproduction du comportement `Card.get_wallet()` Fedow V1 |
| **Tenant d'attribution Wallet éphémère** | `carte.detail.origine` | Cohérence comptable : le wallet est "du" festival d'origine |
| **Action `FUSION`** | Déjà dans `Transaction.ACTION_CHOICES`, gérée par `TransactionService.creer()` | Aucun ajout modèle nécessaire |
| **Tenant de la transaction FUSION** | `carte.detail.origine` (tenant d'origine de la carte) | Cohérent avec précédent Session 31 (tenant = lieu d'exécution de la transaction) |
| **Anti-vol** | Avant fusion : si `user.cartecashless_set.exclude(pk=carte.pk).exists()` → refus | Reproduction V1 : empêcher qu'un email récupère plusieurs cartes |
| **Rattrapage adhésions** | Après fusion réussie : `Membership.objects.filter(user__isnull=True, card_number=carte.number).update(user=user, first_name=..., last_name=...)` | Comportement V1 conservé |
| **Perte carte** | `carte.user = None ; carte.wallet_ephemere = None ; carte.save()` | Reproduction V1. Wallet user et ses tokens restent intacts. |
| **Cohabitation V1/V2** | Condition `Configuration.get_solo().server_cashless` dans `ScanQrCode.retrieve()` : si renseigné → `fedow_connect`, sinon → `fedow_core` | Les anciens tenants restent sur V1 jusqu'à leur migration |
| **Templates HTML** | Inchangés (`reunion/views/register.html` + `htmx/views/inscription.html`) | Le contract vue → template reste le même |
| **Suppression de `fedow_connect.NFCcard.*`** | Différée à la roadmap finale (suppression totale de `fedow_connect/`) | YAGNI : on ne supprime pas tant que les anciens tenants l'utilisent |

---

## 4. Architecture cible

```
┌─────────────────────────────────────────────────────────────┐
│  VUE — BaseBillet/views.py:ScanQrCode                       │
│  - GET  /qr/<uuid>/    (retrieve)                           │
│  - POST /qr/link/      (link)                               │
│  - GET  /my_account/lost_my_card/<num>/    (lost_my_card)   │
│  - GET  /admin/.../admin_lost_my_card/...  (admin_lost...)  │
└─────────────────────────────────────────────────────────────┘
                             │
                  Dispatch V1/V2 selon tenant :
                  - si server_cashless renseigné → fedow_connect (V1)
                  - sinon → fedow_core (V2)
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  SERVICE — fedow_core/services.py                           │
│                                                             │
│  CarteService (NOUVEAU) :                                   │
│   - scanner_carte(qrcode_uuid)                              │
│        → résout tenant d'origine + wallet + is_ephemere     │
│        → crée wallet_ephemere si carte vierge               │
│   - lier_a_user(carte, user, tenant, ip)                    │
│        → anti-vol                                           │
│        → get_or_create user.wallet                          │
│        → délégation à WalletService.fusionner_wallet_... ✅ │
│        → rattrapage adhésions                               │
│   - declarer_perdue(user, number_printed)                   │
│        → nullify carte.user + carte.wallet_ephemere         │
│                                                             │
│  WalletService (EXISTANT, méthodes réutilisées) :           │
│   - fusionner_wallet_ephemere(carte, user, tenant, ip) ✅   │
│   - (+ helper get_or_create_wallet_pour_user à ajouter)     │
│                                                             │
│  TransactionService (EXISTANT) :                            │
│   - creer(action=FUSION, ...) ✅                            │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
           Modèles : CarteCashless, Wallet, Token,            
           Transaction, Membership — tous déjà en place       
```

---

## 5. Flow utilisateur V2 (détaillé)

### 5.1 GET `/qr/<qrcode_uuid>/` — scan public

**Signature vue :**
```python
def retrieve(self, request, pk=None):
    # pk = qrcode_uuid (str, validé en UUID)
```

**Étapes :**

1. **Validation UUID** : `uuid.UUID(pk)`. Sinon 404.
2. **Résolution carte + tenant d'origine** :
   ```python
   carte = CarteCashless.objects.select_related("detail__origine").get(uuid=qrcode_uuid)
   tenant_origine = carte.detail.origine
   ```
   Sinon 404.
3. **Redirection cross-domain** :
   ```python
   primary_domain = tenant_origine.get_primary_domain()
   if primary_domain.domain not in request.build_absolute_uri():
       return HttpResponseRedirect(f"https://{primary_domain.domain}/qr/{qrcode_uuid}/")
   ```
4. **Dispatch V1/V2** :
   ```python
   config = Configuration.get_solo()
   if config.server_cashless:
       # V1 legacy — code existant inchangé (fedow_connect)
       ...
   else:
       # V2
       resultat = CarteService.scanner_carte(carte, tenant_origine, ip=...)
   ```
5. **Résultat V2** :
   - Si `resultat.is_wallet_ephemere` → logout + render `reunion/views/register.html` avec `qrcode_uuid` en contexte.
   - Sinon → `login(request, carte.user)` + redirect `/my_account`.

**Méthode `CarteService.scanner_carte(carte, tenant_origine, ip)` :**
```python
@staticmethod
def scanner_carte(carte, tenant_origine, ip="0.0.0.0"):
    """
    Résout le wallet d'une carte. Crée un wallet_ephemere si carte vierge.
    Retourne un objet simple : (wallet, is_wallet_ephemere).
    """
    if carte.user and carte.user.wallet:
        # Carte identifiée : wallet user
        return ScanResult(wallet=carte.user.wallet, is_wallet_ephemere=False)

    if carte.wallet_ephemere:
        return ScanResult(wallet=carte.wallet_ephemere, is_wallet_ephemere=True)

    # Carte vierge : créer un wallet_ephemere (sans user reverse) et l'attacher
    nouveau_wallet = Wallet.objects.create(
        origin=tenant_origine,
        name=f"Wallet ephemere carte {carte.number}",
    )
    carte.wallet_ephemere = nouveau_wallet
    carte.save(update_fields=["wallet_ephemere"])
    return ScanResult(wallet=nouveau_wallet, is_wallet_ephemere=True)
```

### 5.2 POST `/qr/link/` — identification + fusion

**Signature vue :**
```python
@action(detail=False, methods=['POST'])
def link(self, request):
    # body : qrcode_uuid, email, firstname?, lastname?, newsletter?
```

**Étapes :**

1. **Validation DRF** : `LinkQrCodeValidator` (existant).
2. **get_or_create_user** + envoi mail de confirmation (`force_mail=True`).
3. **Dispatch V1/V2** : même condition que 5.1.
4. **Appel service V2** :
   ```python
   CarteService.lier_a_user(
       qrcode_uuid=validated["qrcode_uuid"],
       user=user,
       ip=get_request_ip(request),
   )
   ```
5. **Newsletter** : `send_to_ghost_email.delay(email)` si coché (inchangé).
6. **Redirect HTMX** vers Referer (= page `/qr/<uuid>/` qui refait le GET → login).

**Méthode `CarteService.lier_a_user(qrcode_uuid, user, ip)` :**
```python
@staticmethod
@transaction.atomic
def lier_a_user(qrcode_uuid, user, ip="0.0.0.0"):
    """
    Lie une carte à un user. Effectue la fusion du wallet éphémère.
    Anti-vol. Rattrape les adhésions anonymes.
    """
    carte = CarteCashless.objects.select_for_update().select_related(
        "detail__origine", "user", "wallet_ephemere",
    ).get(uuid=qrcode_uuid)

    tenant_origine = carte.detail.origine

    # --- Garde : carte déjà liée à ce user ---
    if carte.user and carte.user.pk == user.pk:
        return carte  # idempotent

    # --- Garde : carte liée à un autre user ---
    if carte.user and carte.user.pk != user.pk:
        raise CarteDejaLiee(_("Cette carte est déjà liée à un autre compte."))

    # --- Anti-vol : user a déjà une autre carte ---
    user_a_deja_une_autre_carte = (
        user.cartecashless_set.exclude(pk=carte.pk).exists()
    )
    if user_a_deja_une_autre_carte:
        raise UserADejaCarte(_(
            "Vous avez déjà une carte TiBillet liée à votre compte. "
            "Déclarez-la perdue avant d'en associer une nouvelle."
        ))

    # --- Fusion (délègue à WalletService existant) ---
    WalletService.fusionner_wallet_ephemere(
        carte=carte,
        user=user,
        tenant=tenant_origine,
        ip=ip,
    )

    # --- Rattrapage adhésions anonymes ---
    Membership.objects.filter(
        user__isnull=True,
        card_number=carte.number,
    ).update(
        user=user,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    return carte
```

### 5.3 GET `/my_account/lost_my_card/<number>/` — perte de carte

**Étapes :**

1. **Garde** : `request.user.email_valid` doit être True.
2. **Dispatch V1/V2** : `Configuration.get_solo().server_cashless`.
3. **Appel service V2** :
   ```python
   CarteService.declarer_perdue(user=request.user, number_printed=pk)
   ```
4. **Message + redirect** `/my_account/`.

**Méthode `CarteService.declarer_perdue(user, number_printed)` :**
```python
@staticmethod
def declarer_perdue(user, number_printed):
    """
    Détache la carte du user. Le wallet user conserve ses tokens.
    """
    try:
        carte = CarteCashless.objects.get(user=user, number=number_printed)
    except CarteCashless.DoesNotExist:
        raise CarteIntrouvable(_("Carte introuvable ou non liée à votre compte."))

    carte.user = None
    carte.wallet_ephemere = None
    carte.save(update_fields=["user", "wallet_ephemere"])

    return carte
```

### 5.4 Admin `admin_lost_my_card` — perte par l'admin tenant

Même logique que 5.3, avec :
- Vérification `admin.is_tenant_admin(request.tenant)` (existant).
- Résolution `user = get_object_or_404(HumanUser, pk=user_pk)`.
- Appel : `CarteService.declarer_perdue(user=user, number_printed=number_printed)`.

---

## 6. Exceptions métier

Nouveau fichier (ou extension) `fedow_core/exceptions.py` :

```python
class CarteIntrouvable(Exception):
    """Carte non trouvée ou pas liée au user."""

class CarteDejaLiee(Exception):
    """Carte déjà liée à un autre compte."""

class UserADejaCarte(Exception):
    """Le user a déjà une autre carte — anti-vol."""
```

---

## 7. Impact code existant

| Fichier | Changement |
|---|---|
| `fedow_core/services.py` | **NOUVEAU** `CarteService` avec 3 méthodes (`scanner_carte`, `lier_a_user`, `declarer_perdue`) |
| `fedow_core/exceptions.py` | Ajouter 3 exceptions métier |
| `BaseBillet/views.py:ScanQrCode.retrieve` | Dispatch V1/V2 sur `config.server_cashless` ; V2 = `CarteService.scanner_carte` |
| `BaseBillet/views.py:ScanQrCode.link` | Dispatch V1/V2 ; V2 = `CarteService.lier_a_user` |
| `BaseBillet/views.py:lost_my_card` | Dispatch V1/V2 ; V2 = `CarteService.declarer_perdue` |
| `BaseBillet/views.py:admin_lost_my_card` | Idem |
| Templates | Aucun changement — le contrat vue → template reste inchangé |

**Aucune migration Django nécessaire.**

---

## 8. Tests

### 8.1 Pytest DB-only (`tests/pytest/test_scan_qr_carte_v2.py`)

1. `test_scan_carte_vierge_cree_wallet_ephemere` — 1er GET crée wallet_ephemere, résultat `is_wallet_ephemere=True`.
2. `test_scan_carte_anonyme_avec_tokens` — GET retourne wallet_ephemere avec tokens existants.
3. `test_scan_carte_identifiee_retourne_wallet_user` — GET avec `carte.user` set → `is_wallet_ephemere=False`.
4. `test_scan_idempotent_sur_carte_vierge` — deux GET successifs ne recréent pas de wallet.
5. `test_lier_carte_nouveau_user_sans_tokens` — user tout neuf, wallet_ephemere vide → `carte.user=user`, aucune Transaction FUSION.
6. `test_lier_carte_avec_tokens_cree_transaction_fusion` — wallet_ephemere a 2000 TLF → `Transaction(FUSION)` créée, user.wallet crédité, wallet_ephemere vidé.
7. `test_lier_carte_multi_assets` — wallet_ephemere a TLF + TNF → 2 transactions FUSION distinctes.
8. `test_lier_carte_antivol_user_deja_carte` — user a déjà une autre carte → lève `UserADejaCarte`.
9. `test_lier_carte_idempotent_meme_user` — relink sur carte déjà liée au même user → pas d'erreur.
10. `test_lier_carte_refus_autre_user` — carte liée à user A, tentative user B → lève `CarteDejaLiee`.
11. `test_lier_rattrape_adhesions_anonymes` — `Membership(user=None, card_number=X)` → après link : `Membership.user = user`.
12. `test_declarer_perdue_nullify_carte` — `carte.user` et `carte.wallet_ephemere` deviennent None.
13. `test_declarer_perdue_preserve_wallet_user` — user.wallet et tokens inchangés.
14. `test_declarer_perdue_carte_autre_user` — lève `CarteIntrouvable`.
15. `test_dispatch_v1_si_server_cashless` — mock : config.server_cashless set → appelle `fedow_connect` (pas `fedow_core`).

### 8.2 E2E Playwright (`tests/e2e/test_scan_qr_carte_v2.py`)

1. `test_scan_qr_flow_complet` — scan carte vierge → formulaire email → soumission → retour sur /qr/ → login automatique → /my_account visible.
2. `test_scan_qr_redirection_crossdomain` — GET sur tenant B d'une carte tenant A → 302 vers tenant A.
3. `test_perte_carte_from_my_account` — click bouton "Carte perdue" → message succès → carte détachée en DB.

---

## 9. Points d'attention

1. **`TransactionService.creer()` gère déjà FUSION** — vérifié dans le code existant (services.py:404 déjà utilisé par `fusionner_wallet_ephemere`).
2. **`Wallet.origin` tenant** — le wallet_ephemere est créé avec `origin=carte.detail.origine`. Si `carte.detail` est None (cas edge : carte de dev sans Detail), fallback sur tenant courant ou lever erreur explicite.
3. **Cross-schema lookup** — `CarteCashless` est SHARED_APPS : accessible depuis tous les schemas. `Wallet` est dans `AuthBillet` (SHARED_APPS aussi, cf. `TiBillet/settings.py`). Pas de problème multi-tenant.
4. **Verrou `select_for_update` sur carte** — dans `lier_a_user`, on verrouille la ligne carte pour éviter double-link concurrent.
5. **Tenant de la transaction FUSION** — choix : `tenant_origine` (carte.detail.origine). Raison : la transaction "appartient" au festival d'origine de la carte, pas au tenant où l'user a cliqué. Cohérent avec Session 31 (`Transaction.tenant = federation_fed` pour les recharges FED).
6. **Rattrapage adhésions** — `Membership` est TENANT_APP. Le filtre `Membership.objects.filter(...)` s'exécute dans le tenant courant. Si l'user a des adhésions orphelines sur plusieurs tenants, seules celles du tenant courant sont rattrapées. **Acceptable** : la requête POST `/qr/link/` est servie depuis le tenant d'origine (après redirection cross-domain), donc les adhésions anonymes liées à cette carte sont bien dans ce tenant.
7. **Template `reunion/views/register.html`** — existe déjà, reçoit `qrcode_uuid` et `base_template`. Pas de changement nécessaire.

---

## 10. Workflow djc obligatoire

- [ ] **CHANGELOG.md** : entrée "Scan QR carte V2 — bascule fedow_core"
- [ ] **makemessages + compilemessages** FR/EN (3 nouvelles chaînes `_()` dans les exceptions + logs user-visible)
- [ ] **Fichier `A TESTER et DOCUMENTER/scan-qr-carte-v2.md`** avec scénarios manuels
- [ ] **Doc `fedow_core/CARTES.md`** — mécanique wallet éphémère + fusion + anti-vol (à créer, peut servir aussi aux futures sessions)

---

## 11. Estimation

| Phase | Durée | Contenu |
|---|---|---|
| 1. `CarteService` + exceptions | 2h | 3 méthodes + tests unitaires service |
| 2. Dispatch V1/V2 dans vues | 1h | 4 vues à patcher |
| 3. Tests pytest DB-only | 3h | 15 tests |
| 4. Tests E2E Playwright | 2h | 3 scénarios |
| 5. CHANGELOG + i18n + doc A TESTER | 1h | Workflow djc |
| 6. Validation finale | 1h | `manage.py check` + suite pytest + test manuel navigateur |

**Total : 10h** — 1 session longue ou 2 sessions courtes.

---

## 12. Non-objectifs (YAGNI)

Explicitement **HORS** de cette session :

- ❌ Renommer `tag_id` → `first_tag_id`, `number` → `number_printed` (refactor cosmétique)
- ❌ Ajouter `qrcode_uuid` séparé de `uuid` sur `CarteCashless`
- ❌ Ajouter `primary_places` M2M (utile seulement pour POS/SALE, pas scope A)
- ❌ Refactor wallet-only (suppression `CarteCashless.user` + `wallet_ephemere` → `wallet` unique) — chantier dédié
- ❌ Suppression de `fedow_connect/fedow_api.py:NFCcardFedow` — tant que des tenants V1 existent
- ❌ Import des anciennes transactions Fedow (migration batch) — hors scope
- ❌ Ajouter visualisation admin des fusions — séparé

---

## 13. Journal

- **2026-04-20** : Brainstorm complet. Périmètre = A (scan QR + perte + fusion). Modèle = Option 3 YAGNI (zéro migration). Redirection cross-domain conservée. Pédagogie wallet_ephemere/user discutée. Spec rédigée.
