# SPEC — Visualisation historique transactions V2 (lecture fedow_core local)

**Date :** 2026-04-20
**Statut :** Design validé après brainstorm du 2026-04-20, prêt pour writing-plans
**Scope :** Affichage de l'historique des transactions d'un user sur `/my_account/balance/` pour les tenants V2.
Lit directement `fedow_core.Transaction` (DB locale) au lieu d'appeler `FedowAPI` (serveur Fedow distant).
Reconstitue également les transactions des wallets éphémères fusionnés dans `user.wallet` (historique
complet avant et après identification de la carte).
Les tenants V1 legacy (LaBoutik externe) et les users à wallet legacy conservent leur flow V1 inchangé.

---

## 1. Contexte et problème

### Situation actuelle (Sessions 31 et 32 livrées)

- **Session 31** : flow de recharge FED V2 complet (création `Transaction(action=REFILL)` + crédit `Token` local).
- **Session 32** : `tokens_table` V2 — affichage des soldes `fedow_core.Token` sur `/my_account/balance/`, dispatch via `peut_recharger_v2(user)`.

**Ce qui manque** : l'historique des transactions (`transactions_table`, `views.py:1260`) utilise exclusivement
`FedowAPI().transaction.paginated_list_by_wallet_signature(user)` (serveur distant). Un user qui recharge
en V2 voit son solde mis à jour (Session 32) mais **ne voit pas** la transaction de recharge dans son
historique local. Incohérence : les tokens sont en local, les transactions sont lues à distance.

### Décision stratégique

Même dispatch que Sessions 31-32 via `peut_recharger_v2(user)`. Verdict `"v2"` → lecture
`fedow_core.Transaction` local. Les 3 autres verdicts (`"feature_desactivee"`, `"v1_legacy"`,
`"wallet_legacy"`) conservent le flow `FedowAPI()` distant, inchangé.

**Particularité Session 33** : on reconstitue l'historique des **wallets éphémères** fusionnés dans
`user.wallet` via les `Transaction(action=FUSION, receiver=user.wallet)`. Ainsi un user qui a utilisé
une carte anonyme avant identification voit ses transactions d'époque carte anonyme ET d'époque
carte identifiée dans un seul historique chronologique.

### Coexistence V1/V2 (identique Sessions 31-32)

| Verdict | Flow de lecture |
|---|---|
| `"v2"` | `fedow_core.Transaction` (DB locale, cette spec) |
| `"v1_legacy"` | `FedowAPI()` distant (inchangé) |
| `"wallet_legacy"` | `FedowAPI()` distant (les tx V1 de l'user sont sur serveur Fedow) |
| `"feature_desactivee"` | `FedowAPI()` distant (par cohérence) |

---

## 2. Décisions architecturales validées

| Décision | Valeur | Raison |
|---|---|---|
| **Dispatch** | Seul verdict `"v2"` lit `fedow_core.Transaction` | Symétrie Sessions 31-32, zéro régression V1 |
| **Template V2 séparé** | `reunion/partials/account/transaction_history_v2.html` (nouveau) | V1 `transaction_history.html` intact, évite spaghetti conditionnel |
| **Méthode vue** | `MyAccount._transactions_table_v2(request)` privée, dispatch inline dans `transactions_table` | Cohérence avec `_tokens_table_v2` (Session 32) |
| **Reconstitution wallets historiques** | `wallets_historiques_pks = {user.wallet.pk} ∪ {tx.sender_id for tx in FUSIONs(receiver=user.wallet)}` | Permet d'afficher les tx d'avant identification (UX essentielle) |
| **Query** | `Transaction.objects.filter(Q(sender_id__in=...) | Q(receiver_id__in=...)).exclude(action__in=[FIRST, CREATION, BANK_TRANSFER])` avec `select_related('asset', 'sender__origin', 'receiver__origin', 'card')` | Zéro N+1 sur le mapping Structure |
| **Actions cachées** | `FIRST`, `CREATION`, `BANK_TRANSFER` | Actions techniques sans intérêt user-facing. `FUSION` est **gardée** (marque visuelle du rattachement) |
| **Pagination** | `django.core.paginator.Paginator`, **40 items/page** | Comme V1 (paginator Fedow distant). HTMX swap sur `#transactionHistory` |
| **Colonnes** | Date \| Action \| Montant ±signé \| Structure | 4 colonnes comme V1, mais avec signe + couleur et colonne "Structure" (renommée depuis "Path") |
| **Signe & couleur montant** | `+` vert (text-success) si `receiver ∈ wallets_historiques`, `−` rouge (text-danger) si `sender ∈ wallets_historiques` | Direction immédiatement lisible |
| **Label asset FED** | `"TiBillets"` (nom propre, pas traduit) via `asset_name_affichage` | Cohérence Session 32 |
| **Label Structure REFILL** | `"TiBillet"` (nom propre, pas traduit) | Convention mainteneur : pas "Pot central" ni "Lèspass platform" — simplement "TiBillet" |
| **Label Structure FUSION** | `Carte #{tx.card.number}` | `CarteCashless.number` = 8 caractères imprimés sur la carte (= V1 `number_printed`) |
| **Label Structure SALE/QRCODE_SALE** | nom du collectif payé : `tx.receiver.origin` → `Configuration.organisation` (via cache `tenant_info_v2`) | Plus lisible que "LaBoutik register" générique |
| **Label Structure REFUND/VOID/DEPOSIT/TRANSFER** | nom du collectif concerné (cf. §3.3) | Cohérent avec SALE |
| **Cache `tenant_info_v2`** | Réutilise le helper `_get_tenant_info_cached` de Session 32 | Zéro duplication, cache global cross-tenant 3600s |
| **Helpers vue** | Module-level `_enrichir_transaction_v2(tx, wallet_user, wallets_historiques_pks)` dans `BaseBillet/views.py` | FALC, testable isolément, zéro mutation ORM |
| **Structure données template** | Liste de dicts explicite `[{datetime, action, action_display, amount_euros, signe, asset_name_affichage, structure}, ...]` | Pas de mutation ORM, explicite |
| **Accessibility** | `aria-live="polite"` sur `#transactionHistory`, `aria-hidden="true"` sur icônes, `aria-label` sur la `<nav>` de pagination | Corrige un manque de V1, djc compliance |
| **Fallback no-JS** | `<a href="?page=N">` sur les boutons pagination + hx-get | Lien fonctionnel sans JS (accessibilité) |
| **Workflow djc obligatoire** | CHANGELOG.md + `makemessages`/`compilemessages` + fichier `A TESTER et DOCUMENTER/visu-historique-transactions-v2.md` | Conformité stack djc |

---

## 3. Architecture

### 3.1 Dispatch dans `MyAccount.transactions_table`

```
                   GET /my_account/transactions_table/[?page=N]
                              │
                              ▼
                   MyAccount.transactions_table(request)
                              │
                  ┌───────────┴───────────┐
                  │ peut_recharger_v2(user)│
                  └───────────┬───────────┘
                              │
       ┌──────────────────────┼──────────────────────────┐
       │                      │                          │
       ▼                      ▼                          ▼
   "v1_legacy"           "wallet_legacy"               "v2"
   "feature_desactivee"                                  │
       │                      │                          │
       ▼                      ▼                          ▼
   Code V1 actuel       Code V1 actuel         _transactions_table_v2(request)
   (FedowAPI distant)   (FedowAPI distant)              │
       │                      │                          ▼
       ▼                      ▼                 Reconstitue wallets_historiques
   transaction_history.html   transaction_history.html   │
                                                         ▼
                                              Query + exclude + paginator 40/page
                                                         │
                                                         ▼
                                              Enrichir (structure, signe, asset_name)
                                                         │
                                                         ▼
                                              transaction_history_v2.html
```

### 3.2 Vue Python (squelette)

```python
@action(detail=False, methods=['GET'])
def transactions_table(self, request):
    """
    Historique des transactions du user connecte.
    / User transaction history.

    LOCALISATION : BaseBillet/views.py

    Dispatch V1/V2 selon peut_recharger_v2(user) :
    - Verdict "v2" -> lecture locale fedow_core.Transaction (Session 33)
    - Autres verdicts -> flow V1 FedowAPI (inchange depuis Session 31)
    / V1/V2 dispatch based on peut_recharger_v2(user).
    """
    user = request.user
    verdict_ok, verdict = peut_recharger_v2(user)

    if verdict == "v2":
        return self._transactions_table_v2(request)

    # --- V1 code inchange ---
    # / V1 code unchanged
    config = Configuration.get_solo()
    fedowAPI = FedowAPI()
    paginated_list_by_wallet_signature = fedowAPI.transaction.paginated_list_by_wallet_signature(
        request.user).validated_data

    transactions = paginated_list_by_wallet_signature.get('results')
    next_url = paginated_list_by_wallet_signature.get('next')
    previous_url = paginated_list_by_wallet_signature.get('previous')

    context = {
        'actions_choices': TransactionSimpleValidator.TYPE_ACTION,
        'config': config,
        'transactions': transactions,
        'next_url': next_url,
        'previous_url': previous_url,
    }
    return render(request, "reunion/partials/account/transaction_history.html", context=context)
```

```python
def _transactions_table_v2(self, request):
    """
    Branche V2 de transactions_table : lit fedow_core.Transaction en base locale
    et reconstitue l'historique des wallets ephemeres fusionnes dans user.wallet.
    / V2 branch: reads fedow_core.Transaction from local DB and reconstitutes
    history of ephemeral wallets merged into user.wallet.

    LOCALISATION : BaseBillet/views.py

    Pagination Django 40/page. HTMX swap sur #transactionHistory.
    """
    user = request.user
    config = Configuration.get_solo()

    # Garde : wallet absent -> aucune transaction.
    # / Guard: no wallet -> no transaction.
    if user.wallet is None:
        return render(
            request,
            "reunion/partials/account/transaction_history_v2.html",
            {
                "config": config,
                "transactions": [],
                "paginator_page": None,
                "aucune_transaction": True,
            },
        )

    # 1. Reconstituer les wallets historiques (user.wallet + ephemeres fusionnes).
    # / 1. Reconstitute historical wallets.
    wallets_historiques_pks = {user.wallet.pk}
    fusions_passees = Transaction.objects.filter(
        action=Transaction.FUSION,
        receiver=user.wallet,
    ).values_list('sender_id', flat=True)
    wallets_historiques_pks.update(fusions_passees)

    # 2. Query filtre + exclude actions techniques + tri desc.
    # / 2. Query filter + exclude technical actions + desc sort.
    actions_techniques_a_cacher = [
        Transaction.FIRST,
        Transaction.CREATION,
        Transaction.BANK_TRANSFER,
    ]
    tx_queryset = (
        Transaction.objects
        .filter(
            Q(sender_id__in=wallets_historiques_pks)
            | Q(receiver_id__in=wallets_historiques_pks)
        )
        .exclude(action__in=actions_techniques_a_cacher)
        .select_related(
            'asset',
            'sender__origin',
            'receiver__origin',
            'card',
        )
        .order_by('-datetime')
    )

    # 3. Pagination 40/page.
    # / 3. Paginate 40/page.
    from django.core.paginator import Paginator
    paginator = Paginator(tx_queryset, 40)
    numero_page = request.GET.get('page', 1)
    page = paginator.get_page(numero_page)

    # 4. Enrichir chaque transaction avec des cles explicites pour le template.
    # / 4. Enrich each transaction with explicit keys for template.
    transactions_enrichies = [
        _enrichir_transaction_v2(tx, user.wallet, wallets_historiques_pks)
        for tx in page.object_list
    ]

    return render(
        request,
        "reunion/partials/account/transaction_history_v2.html",
        {
            "config": config,
            "transactions": transactions_enrichies,
            "paginator_page": page,
            "aucune_transaction": len(transactions_enrichies) == 0,
        },
    )
```

### 3.3 Helper module-level `_enrichir_transaction_v2`

```python
def _enrichir_transaction_v2(tx, wallet_user, wallets_historiques_pks):
    """
    Transforme une fedow_core.Transaction en dict explicite pour le template.
    / Turns a fedow_core.Transaction into an explicit dict for the template.

    LOCALISATION : BaseBillet/views.py (helper module-level)

    Calcule :
    - signe : "+" si receiver est un wallet historique, "-" sinon
    - amount_euros : amount / 100 (centimes -> euros)
    - asset_name_affichage : "TiBillets" pour FED, sinon asset.name
    - action_display : tx.get_action_display() (label traduit)
    - structure : mapping selon l'action (cf. tableau)

    Mapping Structure :
    - REFILL          -> "TiBillet" (pot central)
    - FUSION          -> "Carte #{tx.card.number}" (ou "-" si card None)
    - SALE/QRCODE_SALE -> nom du collectif receiver (via cache tenant_info_v2)
    - REFUND          -> nom du collectif sender
    - VOID            -> nom du collectif concerne (sender.origin)
    - DEPOSIT         -> nom du collectif sender
    - TRANSFER        -> nom de l'autre wallet (origine)
    """
    # Signe et signe_couleur.
    # / Sign and sign color.
    receiver_est_historique = (
        tx.receiver_id is not None
        and tx.receiver_id in wallets_historiques_pks
    )
    signe = "+" if receiver_est_historique else "-"

    # Label asset : "TiBillets" pour FED (nom propre), sinon nom de l'asset.
    # / Asset label: "TiBillets" for FED, else asset name.
    if tx.asset.category == Asset.FED:
        asset_name_affichage = "TiBillets"
    else:
        asset_name_affichage = tx.asset.name

    # Structure : depend de l'action.
    # / Structure: depends on action.
    structure = _structure_pour_transaction(tx, receiver_est_historique)

    return {
        "uuid": str(tx.uuid),
        "datetime": tx.datetime,
        "action": tx.action,
        "action_display": tx.get_action_display(),
        "amount_euros": tx.amount / 100,
        "amount_brut": tx.amount,
        "signe": signe,
        "asset_name_affichage": asset_name_affichage,
        "structure": structure,
    }


def _structure_pour_transaction(tx, receiver_est_historique):
    """
    Retourne le libelle de la colonne "Structure" selon l'action de tx.
    / Returns the "Structure" column label based on tx action.

    LOCALISATION : BaseBillet/views.py (helper module-level)

    Utilise _get_tenant_info_cached (Session 32) pour resoudre le nom d'un
    collectif a partir de son Client.pk (cache global 3600s).

    Cas particuliers :
    - REFILL : "TiBillet" (convention : la monnaie federee unique)
    - FUSION : "Carte #{card.number}" ou "-" si card None (anormal, log warning)
    - Autres : nom du collectif (sender ou receiver selon le sens)
    """
    if tx.action == Transaction.REFILL:
        return "TiBillet"

    if tx.action == Transaction.FUSION:
        if tx.card is None:
            logger.warning(
                f"Transaction FUSION #{tx.id} sans card : affichage fallback"
            )
            return "—"
        return f"Carte #{tx.card.number}"

    # Pour les autres actions : afficher le nom du collectif "autre partie".
    # Si user est receiver (receveur_est_historique=True), la contrepartie
    # est le sender. Sinon, c'est le receiver.
    # / For other actions: the "other party" name.
    # If receiver is historical, counterpart is sender. Otherwise receiver.
    if receiver_est_historique:
        tenant_contrepartie = getattr(tx.sender, "origin", None)
    else:
        tenant_contrepartie = getattr(tx.receiver, "origin", None) if tx.receiver else None

    if tenant_contrepartie is None:
        return "—"

    info = _get_tenant_info_cached(tenant_contrepartie.pk)
    if info is None:
        return "—"

    return info.get("organisation") or "—"
```

### 3.4 Template `transaction_history_v2.html`

Voir design brainstorm — structure 4 colonnes, pagination HTMX sur `#transactionHistory`,
couleurs `text-success` / `text-danger` sur le montant, `aria-live="polite"`.

Conteneur root : `<section id="transactionHistory" aria-live="polite">` — **même id que V1**
pour réutiliser l'infrastructure de swap déjà en place dans `balance.html`.

---

## 4. Cas limites

| Cas | Comportement |
|---|---|
| `user.wallet is None` | `aucune_transaction=True` → message "No transaction yet." |
| Tokens V1 sur Fedow distant (user en migration) | **Hors scope** : les tx V1 restent distantes, ne s'affichent pas en V2. Migration wallet_legacy future |
| `tx.card is None` sur FUSION (anormal) | `structure = "—"` + log warning. La ligne reste affichée |
| `tx.receiver is None` sur REFUND/VOID (admin force refund sans receiver) | `structure = "—"` |
| Transaction avec asset archivé ou inactif | Affiché quand même (l'historique est immuable) |
| User arrive sur `?page=999` mais n'a que 3 pages | `paginator.get_page()` clamp à la dernière page (comportement Django natif) |
| Wallets historiques avec FUSIONs imbriquées (ex: wallet_ephemere_A fusionné dans wallet_ephemere_B fusionné dans user.wallet) | **Scénario théorique** : `fusionner_wallet_ephemere` ne permet pas la chaîne (carte.wallet_ephemere devient None après fusion). Recursion non nécessaire |
| Multi-onglet simultané | Pas de problème : query read-only, pas de mutation |

---

## 5. Tests pytest

Fichier : `tests/pytest/test_transactions_table_v2.py` (nouveau, ~8 tests).

Fixtures réutilisées (à factoriser dans un `conftest.py` local ou duplication depuis `test_tokens_table_v2.py`) :
- `tenant_federation_fed` (module) — `bootstrap_fed_asset` + `Client.get(schema_name='federation_fed')`
- `tenant_lespass` (module)
- `user_v2` — TibilletUser avec wallet origine=federation_fed
- `config_v2` — forces `module_monnaie_locale=True` + `server_cashless=None` sur lespass + restore

| Test | Ce qui est vérifié |
|---|---|
| `test_dispatch_branche_v2` | Verdict `"v2"` → template `transaction_history_v2.html` rendu. `data-testid="tx-v2-table"` dans le HTML |
| `test_dispatch_branche_v1_legacy` | Tenant avec `server_cashless` → template V1 rendu (pas V2). Non-régression |
| `test_wallet_absent` | User sans wallet → `aucune_transaction=True`, `data-testid="tx-v2-empty"` dans HTML |
| `test_tri_chronologique_desc` | 3 Transactions créées avec datetimes différents → ordre desc dans le rendu |
| `test_exclusion_actions_techniques` | FIRST, CREATION, BANK_TRANSFER créés sur le wallet user → **absents** du résultat. SALE/REFILL/FUSION présents |
| `test_reconstitution_wallets_historiques_via_fusion` | Créer wallet_ephemere + FUSION(receiver=user.wallet) + SALE(sender=wallet_ephemere) → le SALE apparaît dans l'historique user |
| `test_signe_entrant_sortant` | SALE (sender=user) → dict a `signe='-'`. REFILL (receiver=user) → `signe='+'` |
| `test_pagination_40_par_page` | Créer 45 tx → page 1 = 40 rows, page 2 = 5 rows, `paginator_page.has_other_pages == True` |

**Pas de test Playwright** cette session : la vue est un simple partial HTMX rendu sans interaction multi-étapes. Tests pytest + validation manuelle suffisent.

---

## 6. Fichiers touchés

**Modifiés :**

| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | Dispatch V2 dans `MyAccount.transactions_table` + méthode `_transactions_table_v2` + 2 helpers module-level (`_enrichir_transaction_v2`, `_structure_pour_transaction`) |
| `CHANGELOG.md` | Entrée bilingue FR/EN en tête |
| `locale/{fr,en}/LC_MESSAGES/django.po` + `.mo` | ~7 nouvelles strings i18n (cf. §7) |

**Créés :**

| Fichier | Rôle |
|---|---|
| `BaseBillet/templates/reunion/partials/account/transaction_history_v2.html` | Partial V2 dédié |
| `tests/pytest/test_transactions_table_v2.py` | 8 tests pytest DB-only |
| `A TESTER et DOCUMENTER/visu-historique-transactions-v2.md` | Guide mainteneur (scénarios manuels + commandes DB) |

**Intacts :**

| Fichier | Note |
|---|---|
| `BaseBillet/templates/reunion/partials/account/transaction_history.html` | Template V1 inchangé |
| `fedow_core/services.py` | Pas de nouveau service, query directement `Transaction.objects` |
| `BaseBillet/views.py:transactions_table` code V1 | Inchangé, juste précédé par le dispatch V2 |

**Pas de migration DB.**

---

## 7. Workflow djc obligatoire

1. **CHANGELOG.md** — entrée bilingue FR/EN :
   - Titre : `Session 33 — Visualisation historique transactions V2`
   - Quoi/What, Pourquoi/Why
   - Fichiers modifiés
   - Migration : Non
2. **i18n** (~7 strings) :
   ```bash
   docker exec lespass_django poetry run django-admin makemessages -l fr
   docker exec lespass_django poetry run django-admin makemessages -l en
   # éditer les .po
   docker exec lespass_django poetry run django-admin compilemessages
   ```
   Strings : `"No transaction yet."`, `"Structure"`, `"Amount"`, `"Pagination historique transactions"`, `"Previous"`, `"Next"`, `"Page X / Y"` (en blocktranslate).
3. **`A TESTER et DOCUMENTER/visu-historique-transactions-v2.md`** — guide mainteneur avec :
   - Scénario 1 : user nominal V2 avec recharge → voit la ligne REFILL dans l'historique
   - Scénario 2 : user avec carte fusionnée → voit les tx d'avant identification + ligne FUSION
   - Scénario 3 : user neuf sans wallet → voit le message vide
   - Scénario 4 : non-régression tenant V1 legacy → voit l'ancien tableau
   - Commandes DB shell pour inspecter `Transaction.objects.filter(...)`
4. **Ruff** : `ruff check --fix` sur nouveaux fichiers. Pas de `ruff format` sur `views.py` (fichier legacy non conforme, hors scope).
5. **Tests** :
   - `pytest tests/pytest/test_transactions_table_v2.py -v`
   - Non-régression Session 31 + 32 : `pytest tests/pytest/test_refill_service.py tests/pytest/test_tokens_table_v2.py -v`

---

## 8. Hors scope

**Explicitement pas dans Session 33** :

- Migration des users `wallet_legacy` vers fedow_core local (tx V1 restent sur Fedow distant — chantier dédié)
- Suppression de `FedowAPI` (36 usages non gardés, Phase E du plan mono-repo)
- Filtres avancés sur l'historique (par date, par asset, par action) — YAGNI, ajouter plus tard si demandé
- Export CSV/PDF de l'historique — YAGNI
- Affichage de la hash chain / vérification d'intégrité — feature future (cf. `verify_transactions` command existante)
- Regroupement par date (ex: "Aujourd'hui", "Hier", "Cette semaine") — YAGNI MVP
- Filtrage des TRANSFER internes (entre 2 wallets de lieux) — YAGNI, peu fréquent côté user
- Animations de transition HTMX lors du swap de page — YAGNI

**Sessions futures probables** :

- Migration wallet_legacy → fedow_core (avec import des tx historiques)
- Fin de vie `FedowAPI`
- Export comptable ou export user de son historique
