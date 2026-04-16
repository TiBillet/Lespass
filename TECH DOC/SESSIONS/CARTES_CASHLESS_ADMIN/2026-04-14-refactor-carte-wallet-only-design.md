# Refactor : `CarteCashless` wallet-only (suppression de `CarteCashless.user`)

**Date :** 14 avril 2026
**Statut :** Design à valider
**Préalables :** V2 pas encore en production → pas de data migration à craindre

---

## Contexte

Le modèle `CarteCashless` expose actuellement une dualité :

```python
class CarteCashless(models.Model):
    user = models.ForeignKey(TibilletUser, on_delete=models.PROTECT, null=True, blank=True)
    wallet_ephemere = models.OneToOneField(AuthBillet.Wallet, on_delete=models.SET_NULL, null=True, blank=True)
```

Avec la règle métier :
- Carte **anonyme** : `user=None`, `wallet_ephemere=Wallet(éphémère)`
- Carte **identifiée** : `user=USR`, `wallet_ephemere=None`, wallet effectif = `user.wallet`
- Transition anonyme → identifiée : Transaction FUSION (transfert tokens `wallet_ephemere → user.wallet`) + `wallet_ephemere=None; user=USR`

Ce design crée trois problèmes :

1. **3 helpers dupliqués** qui implémentent tous la même résolution `user.wallet > wallet_ephemere` :
   - `Administration/views_cards.py:58` — `_wallet_de_la_carte(carte)`
   - `laboutik/views.py:941` — `_obtenir_ou_creer_wallet(carte)`
   - `controlvanne/billing.py:52` — dans `obtenir_contexte_cashless(carte)`

2. **Deux chemins de données pour la même information** (à qui appartient la carte ? quel wallet ?) → risque d'incohérence et difficulté de raisonnement.

3. **Relation redondante** : la liaison user ↔ wallet est déjà centralisée sur `TibilletUser.wallet` (OneToOne). Dupliquer `user` sur la carte n'apporte qu'un raccourci applicatif.

---

## Design cible : wallet-only

```python
class CarteCashless(models.Model):
    wallet = models.ForeignKey(AuthBillet.Wallet, on_delete=models.SET_NULL, null=True, blank=True)
    # user supprimé
    # wallet_ephemere supprimé (remplacé par wallet pointant vers un wallet anonyme)
```

**Règles métier** :
- Carte **vierge** : `wallet=None`
- Carte **anonyme** : `wallet=Wallet(anonyme, sans user reverse)` — avant c'était `wallet_ephemere`
- Carte **identifiée** : `wallet=user.wallet` (le OneToOne permanent du TibilletUser)
- Identification (anonyme → identifiée) : on réassigne `carte.wallet = user.wallet` + transfert des tokens de l'ancien wallet vers `user.wallet` via Transaction FUSION
- Reset (vider carte + VV) : `carte.wallet = None`

**Accès user depuis la carte** : `carte.wallet.user if carte.wallet else None`
(via le reverse OneToOne `TibilletUser.wallet` → `Wallet.user`)

---

## Cartographie des références actuelles

### Python (lectures)

| Fichier:ligne | Usage | Criticité |
|---|---|---|
| `QrcodeCashless/models.py:69` | Définition du champ FK | — |
| `Administration/admin/cards.py:31,33,43,70,112` | `_user_link()`, `_wallet_status()`, `search_fields="user__email"`, `select_related("user")` | Moyen |
| `Administration/views_cards.py:58-62,112,149` | Helper `_wallet_de_la_carte` + usages dans `panel()`, `modal()` | Élevé |
| `laboutik/views.py:941-975` | `_obtenir_ou_creer_wallet(carte)` | Élevé |
| `laboutik/views.py:5808-5813` | `identifier_client()` : `user = carte.user` pour afficher formulaire ou non | Élevé |
| `laboutik/views.py:6044-6047` | Feedback carte : solde wallet | Élevé |
| `laboutik/views.py:6959-6974` | Adhésions actives : `Membership.objects.filter(user=carte.user)` | Moyen |
| `controlvanne/billing.py:52-64` | `obtenir_contexte_cashless()` | Élevé |
| `laboutik/reports.py:629-633` | Queryset stats `user__isnull=False, user__wallet__isnull=False` | Moyen |
| `fedow_core/services.py:543-544` | `rembourser_en_especes()` — résolution wallet | Élevé |

### Python (écritures)

| Fichier:ligne | Opération |
|---|---|
| `fedow_core/services.py:346,375,377,409-411` | `fusionner_wallet_ephemere()` — `carte.user = user; carte.wallet_ephemere = None` |
| `fedow_core/services.py:648-650` | `rembourser_en_especes(vider_carte=True)` — `carte.user = None; carte.wallet_ephemere = None` |
| `QrcodeCashless/views.py:446` | Classe legacy `WalletValidator._user()` — **à confirmer si encore active** |
| `laboutik/utils/test_helpers.py:67` | `reset_carte()` helper de test |

### Templates

| Fichier:ligne | Usage |
|---|---|
| `Administration/templates/admin/cards/refund_panel.html:12-13` | `{% if carte.user %}` + `{{ carte.user.email }}` |

### Tests (pytest + E2E)

- **7 pytest** : `test_admin_cards.py`, `test_card_refund_service.py`, `test_retour_carte_recharges.py`, `test_paiement_cashless.py`, `test_identification_unifiee.py`, `test_billetterie_pos.py`, `test_cascade_nfc.py`, `test_pos_vider_carte.py`
- **5 E2E** : `test_pos_adhesion_nfc.py`, `test_admin_card_refund.py`, `test_pos_paiement.py`, `test_pos_recharge_cashless.py`, `test_pos_vider_carte.py`

### Migrations

- `QrcodeCashless/migrations/0001_initial.py:39` — création champ `user`
- `QrcodeCashless/migrations/0003_auto_20221101_1820.py:54` — AlterField user
- `QrcodeCashless/migrations/0021_cartecashless_wallet_ephemere.py` — ajout `wallet_ephemere`

---

## Estimation RÉVISÉE (pas de prod V2)

### Ce qui change par rapport à l'estimation initiale

| Aspect | Avant (avec prod) | Après (pas de prod) |
|---|---|---|
| Data migration zero-downtime | Obligatoire, 3 phases | **Supprimée** — on peut reset les cartes de dev |
| Coexistence V1/V2 pendant migration | Nécessaire | **Supprimée** — on touche uniquement le code V2 ; V1 reste inchangé (utilise `fedow_connect/fedow_api.py`, pas `CarteCashless.user` directement en V2 logic) |
| Phases non-breaking intermédiaires | Phases A + B indispensables | **Supprimées** — breaking change direct |
| Migration Django | 3 migrations (add nullable → data migration → remove) | **1 migration** (RemoveField + AddField en même temps) |
| Tests adaptés en parallèle de la prod | Nécessaire | Le code et les tests évoluent ensemble |

### Nouvelle estimation

**MOYEN — 6 à 10 heures**

Découpage :

| Phase | Durée | Contenu |
|---|---|---|
| 1. Modèle + migration | 1h | Supprimer `user` et `wallet_ephemere`, ajouter `wallet` FK. Migration `RunPython` vide ou `RemoveField` + `AddField` |
| 2. Helper unifié | 0.5h | Créer `obtenir_wallet_carte(carte)` dans `fedow_core/services.py` — retourne `carte.wallet` (simple) |
| 3. Réécriture services | 2-3h | `fusionner_wallet_ephemere()` → `fusionner_wallet(carte, user)` ; `rembourser_en_especes()` ; `_obtenir_ou_creer_wallet` (laboutik) ; `obtenir_contexte_cashless` (controlvanne) |
| 4. Réécriture vues + admin | 1h | `identifier_client()` ; feedback carte ; `laboutik/reports.py` ; admin/cards.py ; views_cards.py ; template refund_panel |
| 5. Tests (pytest + E2E) | 2-3h | 7 pytest + 5 E2E à adapter — fixtures, assertions, `carte.user = ...` → `carte.wallet = ...` |
| 6. Validation | 0.5h | `manage.py check` + suite complète tests + test manuel browser |

---

## Plan d'implémentation suggéré

### Étape 1 : Modèle et migration

**`QrcodeCashless/models.py`** :
```python
class CarteCashless(models.Model):
    tag_id = models.CharField(db_index=True, max_length=8, unique=True, editable=False)
    uuid = models.UUIDField(blank=True, null=True, unique=True, editable=False, db_index=True)
    number = models.CharField(db_index=True, max_length=8, unique=True, editable=False)
    detail = models.ForeignKey(Detail, on_delete=models.CASCADE, null=True, blank=True)
    wallet = models.ForeignKey(
        'AuthBillet.Wallet',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cartes',
        help_text=_("Wallet associe a la carte. None si carte vierge. user.wallet si identifie, wallet anonyme sinon."),
    )
    # user et wallet_ephemere SUPPRIMES
```

Migration `QrcodeCashless/migrations/0022_refactor_wallet_only.py` :
- RemoveField `user`
- RemoveField `wallet_ephemere`
- AddField `wallet` (FK Wallet, SET_NULL, null=True)

**Point d'attention** : `on_delete=PROTECT` actuel doit être levé avant suppression du champ (les cartes de dev sont reset).

### Étape 2 : Helper unifié

**`fedow_core/services.py`** :
```python
def obtenir_wallet_carte(carte):
    """
    Retourne le wallet associe a la carte, ou None si carte vierge.
    Returns the wallet associated with the card, or None if blank.
    """
    return carte.wallet


def obtenir_user_carte(carte):
    """
    Retourne le user identifie sur la carte, ou None si carte anonyme/vierge.
    Via reverse OneToOne : Wallet.user pointe vers TibilletUser via related_name='user'.
    """
    if carte.wallet is None:
        return None
    # reverse OneToOne - peut lever DoesNotExist si wallet anonyme
    try:
        return carte.wallet.user
    except carte.wallet._meta.get_field('user').related_model.DoesNotExist:
        return None
```

Le `related_name` sur `TibilletUser.wallet` est `'user'` (voir `AuthBillet/models.py:133`).

### Étape 3 : Réécrire `fusionner_wallet_ephemere()`

Nouveau nom : `fusionner_wallet(carte, user, tenant, ip)`.

Logique :
- Si `carte.wallet is None` : `carte.wallet = user.wallet` (créer `user.wallet` si absent), save
- Si `carte.wallet == user.wallet` : no-op
- Si `carte.wallet` est un wallet anonyme (pas de reverse user) : transférer tous les Tokens de `carte.wallet → user.wallet` via Transaction FUSION, puis `carte.wallet = user.wallet`, save. L'ancien wallet anonyme reste en DB pour audit.
- Si `carte.wallet` est déjà un `user.wallet` d'un autre user : refuser (état incohérent).

### Étape 4 : Réécrire `rembourser_en_especes()`

Changement minimal : `_wallet_de_la_carte(carte)` remplacé par `obtenir_wallet_carte(carte)`. Pour le reset :
```python
if vider_carte:
    carte.wallet = None
    carte.save(update_fields=['wallet'])
```

### Étape 5 : Réécrire les 3 helpers dupliqués

Supprimer les 3 helpers (`Administration/views_cards.py`, `laboutik/views.py`, `controlvanne/billing.py`) et les remplacer par des appels directs `obtenir_wallet_carte(carte)` ou juste `carte.wallet`.

### Étape 6 : Adapter admin + template + reports + tests

- `Administration/admin/cards.py` : `_user_link()` → `_wallet_user_link()` basé sur `carte.wallet.user` (via helper) ; `search_fields=("tag_id", "number", "wallet__user__email")` ; `select_related("wallet__user", "detail__origine")`
- `Administration/templates/admin/cards/refund_panel.html` : `{% if carte.wallet.user %}` avec fallback template
- `laboutik/views.py` `identifier_client()` : `user = obtenir_user_carte(carte)` au lieu de `carte.user`
- `laboutik/reports.py` : queryset `wallet__user__isnull=False` au lieu de `user__isnull=False, user__wallet__isnull=False`
- Tests : fixtures `carte.wallet = user.wallet` ou `carte.wallet = Wallet.objects.create()` ; assertions `carte.wallet is None` au lieu de `carte.user is None`

---

## Risques résiduels

1. **Reverse OneToOne DoesNotExist** : `carte.wallet.user` lève `TibilletUser.DoesNotExist` si le wallet est anonyme (pas de user reverse). Nécessite un try/except ou un `getattr(carte.wallet, 'user', None)`. Le helper `obtenir_user_carte()` gère ça.
2. **Legacy V1 `WalletValidator`** (QrcodeCashless/views.py:446) : si encore active pour les tenants V1, elle écrit `carte_local.user = user`. À vérifier et désactiver/ignorer avant suppression du champ. Les tenants V1 passent par `fedow_connect/fedow_api.py` (HTTP vers server_cashless) et **ne devraient pas** toucher `CarteCashless.user` directement en V2. À confirmer par un test manuel.
3. **Sérialiseurs / API** : aucune API n'expose publiquement `CarteCashless.user` en REST. Risque faible mais à reverifier dans `ApiBillet/` et `api_v2/`.
4. **`search_fields="user__email"`** dans l'admin Unfold : remplacé par `"wallet__user__email"` — le join est plus coûteux mais reste raisonnable pour une recherche admin.

---

## Gains attendus

- **-1 champ** sur `CarteCashless` (`user` supprimé)
- **-1 champ** (`wallet_ephemere` supprimé, remplacé par `wallet`)
- **-3 helpers** dupliqués (unifiés en 1)
- **-1 chemin de lecture** (plus de dualité `user.wallet | wallet_ephemere`)
- **+1 helper** `obtenir_user_carte()` dans `fedow_core/services.py` (abstraction propre)
- Architecture plus normalisée : la relation user↔wallet n'existe qu'à un seul endroit (`TibilletUser.wallet`)

---

## Décision

À trancher par le mainteneur :
1. **Go / No-go** : vaut-il l'effort (6-10h) pour un gain essentiellement architectural ?
2. **Wallet anonyme vs wallet_ephemere** : on remplace `wallet_ephemere` par `wallet` qui peut pointer vers un wallet sans reverse user — est-ce que ce wallet doit avoir un flag `anonymous=True` pour disambiguer ? Ou suffit-il de vérifier l'absence de reverse user (`hasattr(wallet, 'user')`) ?
3. **Phasing** : le faire en une seule branche ou séparer modèle/services/tests en 3 PRs ?

---

## Journal

- 2026-04-14 : Design rédigé suite à la demande du mainteneur. Cartographie produite par un agent Explore sur le codebase V2. Estimation initiale 16-24h révisée à 6-10h après confirmation "pas de prod V2".
