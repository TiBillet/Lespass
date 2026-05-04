# Tests E2E à faire — Scan QR carte V2 (Session 34)

**Statut :** À implémenter ultérieurement (reporté après validation fonctionnelle manuelle).
**Raison du report :** Les teardowns Playwright sur DB réelle ont montré des effets de bord destructifs (Configuration vidée, cascades FK imprévues). À refaire avec une approche **sans teardown** (fixtures 100% idempotentes) ou dans un environnement DB jetable dédié.

**Lanceur cible :**
```bash
docker exec lespass_django poetry run pytest tests/e2e/test_scan_qr_carte_v2.py -v -s
```

---

## Principe de base pour CHAQUE test E2E

- **Setup idempotent** : `get_or_create(tag_id='E2E_SCAN_<NUM>')` + reset `carte.user = None; carte.wallet_ephemere = None; carte.save()`. Pas de création de User/Wallet/Transaction manuelle en fixture.
- **Zéro teardown agressif** : on accepte une DB dev légèrement polluée (users `e2e-scan-*@test.local`, Transactions FUSION, etc.) plutôt que de risquer une cascade destructive.
- **UUID déterministe par scénario** : `CARTE_E2E_<N>_UUID = "XXXX..."` pour que chaque test ait SA carte, pas de conflit entre tests.
- **Pattern `django_shell`** pour setup/verif en DB, identique à `test_admin_card_refund.py`.
- **Filtres exact-match** si vraiment on veut nettoyer : `tag_id='E2E_SCAN_001'` exact, JAMAIS `startswith`, JAMAIS queryset `.delete()` sur User.

---

## Scénario 1 — GET `/qr/<uuid>/` sur carte vierge → formulaire

**Objectif :** vérifier que scanner une carte jamais scannée crée un wallet_ephemere en base et affiche le formulaire `register.html`.

**Setup :**
- CarteCashless vierge (user=None, wallet_ephemere=None) avec UUID déterministe
- `Configuration.server_cashless = None` (V2 actif)

**Étapes :**
1. `page.goto("/qr/<uuid>/")`
2. `page.wait_for_load_state("domcontentloaded")`

**Assertions :**
- Le formulaire `#linkform` est visible
- L'input hidden `qrcode_uuid` contient le bon UUID
- En base : `carte.wallet_ephemere` est désormais non-null
- En base : `carte.wallet_ephemere.origin == tenant d'origine`
- En base : `carte.wallet_ephemere.name == "Wallet ephemere carte <number>"`

---

## Scénario 2 — GET `/qr/<uuid>/` sur carte déjà scannée (anonyme) → formulaire

**Objectif :** idempotence côté wallet_ephemere : un 2e scan ne recrée pas le wallet.

**Setup :**
- CarteCashless avec wallet_ephemere déjà attaché (pré-rempli par scan précédent)

**Étapes :**
1. Récupérer l'ID du wallet_ephemere actuel
2. `page.goto("/qr/<uuid>/")`

**Assertions :**
- Formulaire toujours affiché
- `carte.wallet_ephemere.pk` **inchangé** (même wallet qu'avant)

---

## Scénario 3 — GET `/qr/<uuid>/` sur carte identifiée → login automatique

**Objectif :** scanner sa propre carte identifiée log l'user et redirige vers `/my_account`.

**Setup :**
- CarteCashless avec `user = <alice>`, wallet_ephemere=None
- Alice a un `email_valid = True`

**Étapes :**
1. `page.goto("/qr/<uuid>/")`

**Assertions :**
- URL finale contient `/my_account` OU `/emailconfirmation` (en mode TEST avec le lien TEST MODE)
- En base : `alice.is_active == True`

---

## Scénario 4 — Flow complet nouveau user (happy path)

**Objectif :** scan → formulaire → saisie email + nom → soumission → carte liée.

**Setup :**
- Carte vierge
- Email unique : `e2e-flow-<timestamp>@test.local`

**Étapes :**
1. `page.goto("/qr/<uuid>/")`
2. `page.fill("input[name='email']", email)`
3. `page.fill("input[name='emailConfirmation']", email)` (si présent)
4. `page.fill("input[name='firstname']", "Alice")` (si `config.need_name=True`)
5. `page.fill("input[name='lastname']", "TestE2E")` (idem)
6. `page.check("input[name='cgu']")`
7. `page.click("button[type='submit']")`
8. Attendre redirect HTMX → GET `/qr/<uuid>/` → redirect Django → `/my_account` ou message TEST MODE

**Assertions :**
- En base : `carte.user.email == email`
- En base : `carte.wallet_ephemere is None`
- En base : `carte.user.wallet` existe (nouveau wallet créé)

---

## Scénario 5 — Flow avec tokens → fusion

**Objectif :** scan d'une carte anonyme avec des tokens puis identification → fusion.

**Setup :**
- Carte anonyme avec `wallet_ephemere` contenant 2000 centimes TLF
- Nouveau user (email unique)

**Étapes :**
- Mêmes que scénario 4 (soumission formulaire)

**Assertions :**
- En base : `Transaction.objects.filter(action=FUSION, card=carte).count() == 1`
- En base : `Transaction.amount == 2000`
- En base : `alice.wallet` a désormais 2000 centimes TLF
- En base : `wallet_ephemere` existe toujours (détaché, pour audit) mais à 0 token

---

## Scénario 6 — Anti-vol (user a déjà une carte)

**Objectif :** refus si l'user possède déjà une autre carte.

**Setup :**
- User Alice avec carte 1 liée
- Carte 2 vierge

**Étapes :**
1. `page.goto("/qr/<uuid_carte_2>/")`
2. Remplir formulaire avec l'email d'Alice
3. Soumettre

**Assertions :**
- Message d'erreur visible contenant "déjà une carte TiBillet"
- En base : carte 2 reste `user=None`, `wallet_ephemere` toujours rattaché

---

## Scénario 7 — Lien sur carte déjà liée à un autre user

**Objectif :** refus si la carte est déjà liée à un autre compte.

**Setup :**
- Carte 1 liée à Alice
- Nouveau user Bob tente de scanner carte 1

**Étapes :**
1. `page.goto("/qr/<uuid_carte_1>/")` → devrait afficher login Alice (retriever_wallet_user)
2. Comme on est pas loggé, on voit le formulaire

Actually — quand la carte est identifiée, le GET `/qr/<uuid>/` log automatiquement l'user existant. Donc Bob ne peut pas soumettre avec son email, puisque le flow envoie Alice sur `/my_account`.

**Ce scénario n'est pas facilement atteignable via le GET**. Il couvre le cas où le POST `/qr/link/` arrive sur une carte entretemps liée (race condition). **À couvrir par les tests pytest uniquement**, pas E2E.

---

## Scénario 8 — Redirection cross-domain

**Objectif :** scanner une carte depuis un tenant autre que son origine → 302 vers le tenant d'origine.

**Setup :**
- Carte rattachée au tenant `lespass` (`detail.origine = lespass`)
- Accès depuis `chantefrein.tibillet.localhost` ou tout autre tenant

**Étapes :**
1. `page.goto("https://chantefrein.tibillet.localhost/qr/<uuid>/")`

**Assertions :**
- URL finale : `https://lespass.tibillet.localhost/qr/<uuid>/` (redirect 302 suivi)
- Formulaire ou login selon état de la carte

**Blocker infra :** nécessite **2 tenants actifs** avec Traefik. Sur dev mono-tenant, à skipper.

---

## Scénario 9 — Perte de carte via `/my_account/`

**Objectif :** un user connecté peut déclarer sa carte perdue.

**Setup :**
- User Alice loggé avec carte liée
- Carte a des tokens sur son wallet user

**Étapes :**
1. Login Alice (via `/emailconfirmation/<token>/` ou autre mécanisme de login E2E)
2. `page.goto("/my_account/")`
3. Cliquer sur le bouton "Carte perdue" / lien `lost_my_card`
4. Confirmer

**Assertions :**
- Message succès visible ("Your wallet has been detached from this card...")
- En base : `carte.user is None`
- En base : `carte.wallet_ephemere is None`
- En base : `alice.wallet` existe toujours avec tokens intacts

**Prérequis :** flow de login E2E (via token `emailconfirmation` ou fixture de session authentifiée). À factoriser si possible.

---

## Scénario 10 — Perte de carte via admin

**Objectif :** un admin tenant peut déclarer une carte perdue pour un user.

**Setup :**
- User Alice avec carte liée
- Admin loggé sur le tenant d'origine de la carte

**Étapes :**
1. Login admin
2. Naviguer vers l'action `admin_lost_my_card/<user_pk>:<number>/`

**Assertions :**
- Message succès
- En base : carte détachée
- Wallet Alice intact

---

## Scénario 11 — Cohabitation V1 (tenant legacy `server_cashless` set)

**Objectif :** sur un tenant avec `server_cashless` renseigné, le scan passe par `fedow_connect` (V1) et non `fedow_core` (V2).

**Setup :**
- Tenant avec `Configuration.server_cashless = "https://fake-fedow.local"`
- Mock du serveur Fedow (ou test en mode "on vérifie juste la branche prise")

**Étapes :**
1. `page.goto("/qr/<uuid>/")`

**Assertions :**
- Pas facile à vérifier en E2E sans mock HTTP. **Mieux fait en pytest** avec mock `fedow_connect.NFCcardFedow.qr_retrieve`.
- Alternativement : vérifier dans les logs serveur qu'une requête HTTP outbound a été faite (trop fragile).

**À skipper en E2E** — couvrir par test pytest avec mock.

---

## Scénario 12 — Rattrapage d'adhésions anonymes

**Objectif :** une adhésion créée en anonyme (user=None, card_number=X) est rattrapée au link.

**Setup :**
- Carte anonyme, wallet_ephemere set
- `Membership(user=None, card_number=carte.number, first_name="", last_name="")` en base sur le tenant d'origine
- Nouveau user avec email unique

**Étapes :**
- Flow complet happy path (scénario 4)

**Assertions :**
- En base : `Membership.user == alice`
- En base : `Membership.first_name == alice.first_name`
- En base : `Membership.last_name == alice.last_name`

---

## Scénario 13 — Multi-assets sur wallet_ephemere

**Objectif :** un wallet_ephemere avec plusieurs assets (TLF + TNF) fusionne correctement.

**Setup :**
- Carte anonyme avec `wallet_ephemere` contenant :
  - Token TLF valeur 1000
  - Token TNF valeur 500
- Nouveau user

**Étapes :**
- Flow happy path

**Assertions :**
- En base : `Transaction.objects.filter(action=FUSION, card=carte).count() == 2`
- En base : alice.wallet a 1000 TLF ET 500 TNF

---

## Scénario 14 — UUID invalide

**Objectif :** scanner `/qr/not-a-uuid/` → 404.

**Étapes :**
1. `page.goto("/qr/pas-un-uuid/")`

**Assertions :**
- HTTP 404 (ou page d'erreur Django équivalente)

---

## Scénario 15 — UUID inexistant

**Objectif :** scanner un UUID qui ne correspond à aucune carte → 404.

**Étapes :**
1. `page.goto("/qr/99999999-9999-9999-9999-999999999999/")`

**Assertions :**
- HTTP 404

---

## Scénario 16 — Carte sans `detail.origine`

**Objectif :** carte mal configurée (detail=None ou detail.origine=None) → 404 avec log.

**Setup :**
- Carte avec `detail = None`

**Étapes :**
1. `page.goto("/qr/<uuid>/")`

**Assertions :**
- HTTP 404

---

## Scénario 17 — Validation formulaire (email invalide)

**Objectif :** soumission avec email invalide → message d'erreur, carte non liée.

**Setup :**
- Carte vierge

**Étapes :**
1. `page.goto("/qr/<uuid>/")`
2. `page.fill("input[name='email']", "pas-un-email")`
3. Soumettre (si le JS client le permet)

**Assertions :**
- La validation HTML5 `type="email"` devrait bloquer la soumission côté navigateur
- Si la soumission passe : message d'erreur serveur visible, carte reste `user=None`

---

## Scénario 18 — CGU non cochée

**Objectif :** soumission sans cocher CGU → échec validation.

**Setup :**
- Carte vierge

**Étapes :**
1. Flow normal SANS `page.check("input[name='cgu']")`
2. Soumettre

**Assertions :**
- Message d'erreur sur CGU
- Carte reste `user=None`

---

## Scénario 19 — Relink après perte (idempotence recovery)

**Objectif :** après qu'Alice a perdu sa carte, elle peut lier une NOUVELLE carte au même compte.

**Setup :**
- Alice a perdu carte 1 (user=None, wallet_ephemere=None sur carte 1)
- Carte 2 vierge
- Alice.wallet conserve ses tokens

**Étapes :**
1. Scanner carte 2 → formulaire
2. Saisir email Alice
3. Soumettre

**Assertions :**
- Pas d'anti-vol (car carte 1 n'est plus liée à Alice)
- carte 2 devient `user=alice`
- Alice.wallet conserve ses tokens (pas de perte)

---

## Récapitulatif priorité d'implémentation

| # | Scénario | Priorité | Faisable en E2E ? | Notes |
|---|----------|----------|-------------------|-------|
| 1 | Scan vierge → formulaire | **Haute** | Oui | Base du flow |
| 2 | Scan idempotent | Moyenne | Oui | Couvert par pytest |
| 3 | Scan carte identifiée → login | **Haute** | Oui | Validation login auto |
| 4 | Flow complet happy path | **Haute** | Oui | Scénario clé |
| 5 | Fusion avec tokens | **Haute** | Oui | Validation métier importante |
| 6 | Anti-vol | **Haute** | Oui | Sécurité critique |
| 7 | Carte déjà liée autre user | Basse | Non | Pytest avec mock |
| 8 | Redirection cross-domain | Moyenne | Infra 2 tenants | Skip par défaut |
| 9 | Perte via MyAccount | **Haute** | Oui (si login E2E) | Feature demandée |
| 10 | Perte via admin | Moyenne | Oui (si login admin E2E) | Feature secondaire |
| 11 | Cohabitation V1 legacy | Basse | Non | Pytest avec mock |
| 12 | Rattrapage adhésions | Moyenne | Oui | Déjà couvert pytest |
| 13 | Multi-assets fusion | Moyenne | Oui | Déjà couvert pytest |
| 14 | UUID invalide → 404 | Basse | Oui | Simple |
| 15 | UUID inexistant → 404 | Basse | Oui | Simple |
| 16 | Carte sans détail → 404 | Basse | Oui | Edge case |
| 17 | Email invalide | Basse | Oui | Validation form |
| 18 | CGU non cochée | Basse | Oui | Validation form |
| 19 | Relink après perte | Moyenne | Oui | Recovery |

**Scénarios haute priorité à implémenter en premier (6 tests) :** 1, 3, 4, 5, 6, 9.
**Scénarios à reporter sur pytest uniquement :** 7, 11.
**Scénarios à skipper sans infra dédiée :** 8 (2 tenants).

---

## Fixtures réutilisables à créer

```python
@pytest.fixture
def carte_v2_vierge_e2e(django_shell, uuid_suffix):
    """Carte vierge avec UUID unique par run. Zéro teardown (idempotent)."""
    ...

@pytest.fixture
def alice_loggee_e2e(page, django_shell):
    """Session Alice logguée via token emailconfirmation (pour tests 9/10)."""
    ...

@pytest.fixture
def admin_tenant_loggee_e2e(page, django_shell):
    """Session admin loggée pour tests 10."""
    ...
```

---

## Commande de nettoyage ponctuel (hors CI)

Pour un mainteneur qui veut nettoyer sa DB dev après plusieurs runs E2E :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import schema_context
with schema_context('lespass'):
    from QrcodeCashless.models import CarteCashless, Detail
    from AuthBillet.models import Wallet, TibilletUser
    from fedow_core.models import Transaction, Token

    # Supprimer les transactions de test (filtrage exact par comment)
    Transaction.objects.filter(comment__startswith='Fusion ephemere vers e2e-').delete()

    # Supprimer les users E2E et leurs wallets (exact match email)
    users = TibilletUser.objects.filter(email__regex=r'^e2e-(scan|flow|test)-[a-z0-9]+@test\.local\$')
    for u in users:
        if u.wallet:
            Token.objects.filter(wallet=u.wallet).delete()
            w = u.wallet
            u.wallet = None
            u.save()
            w.delete()
        u.delete()

    # Supprimer les cartes E2E (tag_id strict)
    cartes = CarteCashless.objects.filter(tag_id__regex=r'^E2E[A-Z0-9]+\$')
    for c in cartes:
        if c.wallet_ephemere:
            Token.objects.filter(wallet=c.wallet_ephemere).delete()
            w = c.wallet_ephemere
            c.wallet_ephemere = None
            c.save()
            w.delete()
        Transaction.objects.filter(card=c).delete()
        c.delete()

    # Details E2E
    Detail.objects.filter(base_url__startswith='E2E_').delete()
    print('Cleanup E2E OK')
"
```

**À ne JAMAIS lancer en CI sans revue.** Filtres regex strictes, pas de `startswith` vague sur email. Usage : post-debug manuel uniquement.

---

## Ce qui est déjà couvert par les tests pytest DB-only

| Scénario E2E | Équivalent pytest |
|--------------|-------------------|
| 1 (scan vierge) | `test_scan_carte_vierge_cree_wallet_ephemere` |
| 2 (idempotence) | `test_scan_idempotent_sur_carte_vierge` |
| 3 (carte identifiée) | `test_scan_carte_identifiee_retourne_wallet_user` |
| 4 (flow happy) | `test_lier_carte_nouveau_user_sans_tokens` |
| 5 (fusion tokens) | `test_lier_carte_avec_tokens_cree_transaction_fusion` |
| 6 (anti-vol) | `test_lier_carte_antivol_user_deja_carte` |
| 7 (autre user) | `test_lier_carte_refus_autre_user` |
| 9 (perte) | `test_declarer_perdue_nullify_carte` + `test_declarer_perdue_preserve_wallet_user` |
| 12 (rattrapage) | `test_lier_rattrape_adhesions_anonymes` |
| 13 (multi-assets) | `test_lier_carte_multi_assets` |

**Les tests E2E ajoutent :** la validation du flow HTML/HTMX (formulaire, CSRF, redirections, mode TEST) et la validation du login auto — choses que pytest ne peut pas tester.

**Ce qu'ils n'apportent pas vs pytest :** la logique métier pure (déjà 100% couverte).

**Recommandation finale :** implémenter uniquement les 6 scénarios haute priorité (1, 3, 4, 5, 6, 9) quand on revient sur Task 8. Ignorer les autres (redondants avec pytest ou infra complexe).
