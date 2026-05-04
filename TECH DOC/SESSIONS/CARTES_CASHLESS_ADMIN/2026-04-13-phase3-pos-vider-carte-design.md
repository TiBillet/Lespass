# Phase 3 — Bouton POS Cashless « Vider Carte / Void Carte »

**Date** : 2026-04-13
**Statut** : design validé en brainstorming, à revoir par le mainteneur avant plan d'implémentation
**Branche cible** : V2
**Specs précédents** : Phase 1 (`2026-04-13-phase1-admin-cartes-design.md`), Phase 2 (`2026-04-13-phase2-bank-transfer-design.md`)

## Contexte

Les caissier·es doivent pouvoir vider la carte NFC d'un·e client·e au comptoir : rendre le solde en
espèces (TLF du lieu + FED), avec option de réinitialisation (détacher user + wallet + carte primaire).

Cette Phase 3 expose le service métier `WalletService.rembourser_en_especes()` implémenté en Phase 1
à l'interface POS, en court-circuitant le panier (c'est un flow opérationnel distinct des ventes).

## Scope de la Phase 3

**In :**
- Tile « Vider Carte » dans les PV où l'admin a ajouté le Product `methode_caisse=VC` au M2M.
- Flow dédié : clic tile → overlay scan NFC → récap tokens éligibles → confirmation avec
  checkbox VV → exécution via `WalletService.rembourser_en_especes()` → écran de succès.
- Paramètre additif `primary_card` sur `WalletService.rembourser_en_especes()` (trace le·a caissier·e
  dans les Transactions REFUND).
- Protection self-refund (`tag_id == tag_id_cm` rejette).
- Contrôle d'accès via `pv.cartes_primaires` M2M (pattern POS existant).
- Impression de reçu optionnelle via bouton sur l'écran de succès.
- Formatter dédié `formatter_recu_vider_carte()`.
- Tests pytest DB-only (10) + E2E Playwright (3).

**Out :**
- Pas de nouvelle action `Transaction` (REFUND existe depuis l'ancien Fedow, déjà géré par le service Phase 1).
- Pas de nouveau `Product` système (VIDER_CARTE créé par Phase 1).
- Pas de modification `BankTransferService` (Phase 2) — les LigneArticles CASH générées au POS
  intègrent directement les rapports caisse ; la dette FED côté pot central est calculée par Phase 2.
- Pas de permission supplémentaire type `edit_mode` — l'admin contrôle uniquement via M2M PV.
- Pas de nouveau flag `PointDeVente.vider_carte_active` — la présence du Product VC dans le M2M suffit.

## Architecture

Découpage en modules à responsabilités isolées. **100 % de la logique métier reste dans Phase 1**
via `WalletService.rembourser_en_especes()`. Phase 3 n'ajoute que de l'orchestration POS.

| Module | Action | Responsabilité |
|---|---|---|
| `fedow_core/services.py` | PATCH léger | Ajouter paramètre `primary_card=None` à `WalletService.rembourser_en_especes()` et le propager à `TransactionService.creer()`. **Additif** : Phase 1 et 2 non impactées. |
| `laboutik/serializers.py` | NEW ou PATCH | `ViderCarteSerializer` (tag_id, tag_id_cm, uuid_pv, vider_carte). |
| `laboutik/views.py` | PATCH | 3 endpoints : `/laboutik/vider_carte/preview/` (GET-like POST, calcul récap), `/laboutik/vider_carte/` (POST exécution), `/laboutik/vider_carte/imprimer_recu/` (POST impression). |
| `laboutik/urls.py` | PATCH | Router DRF intègre les actions via `@action` sur le ViewSet existant. |
| `laboutik/templates/laboutik/partial/hx_vider_carte_overlay.html` | NEW | Overlay scan NFC. |
| `laboutik/templates/laboutik/partial/hx_vider_carte_confirm.html` | NEW | Récap tokens + checkbox VV + boutons Confirmer/Annuler. |
| `laboutik/templates/laboutik/partial/hx_vider_carte_success.html` | NEW | Écran succès + bouton imprimer + retour. |
| `laboutik/static/js/vider_carte.js` | NEW | Handler JS : détection `methode_caisse === "VC"` dans routeur d'articles, enchaîne overlay NFC → confirm → POST. |
| `laboutik/templates/laboutik/common_user_interface.html` | PATCH léger | Charger `vider_carte.js`. |
| `laboutik/printing/formatters.py` | PATCH | `formatter_recu_vider_carte(transactions)` pour payload imprimante. |
| `tests/pytest/test_pos_vider_carte.py` | NEW | Tests backend : permissions, service appel, erreurs, atomicité. |
| `tests/e2e/test_pos_vider_carte.py` | NEW | Flow E2E : POS login, scan simulé, confirmer, vérifier DB + impression. |

**Principe d'isolation :**
- Aucune logique métier ajoutée côté `laboutik/views.py` — juste de l'orchestration (collecte inputs,
  appel service, rendu template).
- Frontend `vider_carte.js` isolé, utilise le pattern `sendEvent()` existant pour s'enchaîner avec
  `<c-read-nfc>` et `eventsOrganizer`.
- Backend : 3 endpoints à responsabilités distinctes (preview/exécution/impression) pour suivre
  le pattern REST du POS existant.

## Composants

### Patch `WalletService.rembourser_en_especes()` (léger)

Ajout d'un paramètre optionnel `primary_card=None` :

```python
@staticmethod
def rembourser_en_especes(
    carte,
    tenant,
    receiver_wallet,
    ip: str = "0.0.0.0",
    vider_carte: bool = False,
    primary_card=None,  # NEW : carte caissier POS (Phase 3)
) -> dict:
    ...
    tx = TransactionService.creer(
        sender=wallet_carte,
        receiver=receiver_wallet,
        asset=token.asset,
        montant_en_centimes=token.value,
        action=Transaction.REFUND,
        tenant=tenant,
        card=carte,
        primary_card=primary_card,  # propage
        ip=ip,
        comment="Remboursement especes",
        metadata={"vider_carte": vider_carte},
    )
```

`TransactionService.creer()` accepte déjà `primary_card=None`. Phase 1 (admin web) et Phase 2
(dashboard virement) passent `primary_card=None` implicitement — aucune régression.

### `ViderCarteSerializer`

```python
class ViderCarteSerializer(serializers.Serializer):
    tag_id = serializers.CharField(max_length=8)
    tag_id_cm = serializers.CharField(max_length=8)
    uuid_pv = serializers.UUIDField()
    vider_carte = serializers.BooleanField(required=False, default=False)

    def validate_tag_id(self, value):
        return value.strip().upper()

    def validate_tag_id_cm(self, value):
        return value.strip().upper()
```

### Endpoint preview — `/laboutik/vider_carte/preview/`

```python
@action(detail=False, methods=["POST"], url_path="vider_carte/preview", url_name="vider_carte_preview")
def vider_carte_preview(self, request):
    """
    POST /laboutik/vider_carte/preview/
    Calcule les tokens eligibles pour la carte scannee et renvoie l'overlay de confirmation.
    Pas de mutation DB.
    """
    tag_id = request.POST.get("tag_id", "").strip().upper()
    tag_id_cm = request.POST.get("tag_id_cm", "").strip().upper()
    uuid_pv = request.POST.get("uuid_pv", "")

    # Protection self-refund
    if tag_id == tag_id_cm:
        return _render_erreur_toast(
            request, _("Ne peut pas vider une carte primaire.")
        )

    try:
        carte = CarteCashless.objects.get(tag_id=tag_id)
    except CarteCashless.DoesNotExist:
        return _render_erreur_toast(request, _("Carte client inconnue."))

    wallet = _obtenir_ou_creer_wallet(carte)  # helper Phase 1
    if wallet is None:
        return _render_erreur_toast(request, _("Carte vierge."))

    # Calcule tokens eligibles (memes criteres que Phase 1 admin web)
    from django.db.models import Q
    tokens = list(
        Token.objects.filter(
            wallet=wallet, value__gt=0,
        ).filter(
            Q(asset__category=Asset.TLF, asset__tenant_origin=connection.tenant)
            | Q(asset__category=Asset.FED)
        ).select_related('asset', 'asset__tenant_origin').order_by('asset__category')
    )

    if not tokens:
        return _render_erreur_toast(
            request, _("Aucun solde remboursable sur cette carte.")
        )

    total_tlf = sum(t.value for t in tokens if t.asset.category == Asset.TLF)
    total_fed = sum(t.value for t in tokens if t.asset.category == Asset.FED)

    contexte = {
        "carte": carte,
        "tokens": tokens,
        "total_centimes": total_tlf + total_fed,
        "total_tlf_centimes": total_tlf,
        "total_fed_centimes": total_fed,
        "tag_id": tag_id,
        "tag_id_cm": tag_id_cm,
        "uuid_pv": uuid_pv,
    }
    return render(request, "laboutik/partial/hx_vider_carte_confirm.html", contexte)
```

### Endpoint exécution — `/laboutik/vider_carte/`

```python
@action(detail=False, methods=["POST"], url_path="vider_carte", url_name="vider_carte")
def vider_carte(self, request):
    """
    POST /laboutik/vider_carte/
    Execute le remboursement via WalletService.rembourser_en_especes.
    """
    serializer = ViderCarteSerializer(data=request.POST)
    serializer.is_valid(raise_exception=True)

    tag_id_client = serializer.validated_data["tag_id"]
    tag_id_cm = serializer.validated_data["tag_id_cm"]
    uuid_pv = serializer.validated_data["uuid_pv"]
    vider_carte_flag = serializer.validated_data["vider_carte"]

    # Protection self-refund (rappel, meme check qu'en preview)
    if tag_id_client == tag_id_cm:
        return _render_erreur_toast(
            request, _("Ne peut pas vider une carte primaire.")
        )

    try:
        carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
    except CarteCashless.DoesNotExist:
        return _render_erreur_toast(request, _("Carte client inconnue."))

    carte_primaire_obj, erreur_cp = _charger_carte_primaire(tag_id_cm)
    if erreur_cp:
        return _render_erreur_toast(request, erreur_cp)

    pv = PointDeVente.objects.filter(uuid=uuid_pv).first()
    if pv is None:
        return _render_erreur_toast(request, _("PV introuvable."))

    # Controle d'acces : la carte primaire doit pouvoir operer sur ce PV
    if not pv.cartes_primaires.filter(pk=carte_primaire_obj.pk).exists():
        return _render_erreur_toast(
            request, _("Cette carte caissier n'a pas acces a ce PV.")
        )

    receiver_wallet = WalletService.get_or_create_wallet_tenant(connection.tenant)

    try:
        resultat = WalletService.rembourser_en_especes(
            carte=carte_client,
            tenant=connection.tenant,
            receiver_wallet=receiver_wallet,
            ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
            vider_carte=vider_carte_flag,
            primary_card=carte_primaire_obj.carte,  # CarteCashless physique
        )
    except NoEligibleTokens:
        return _render_erreur_toast(
            request, _("Aucun solde remboursable (solde a pu changer).")
        )

    contexte = {
        "total_centimes": resultat["total_centimes"],
        "total_tlf_centimes": resultat["total_tlf_centimes"],
        "total_fed_centimes": resultat["total_fed_centimes"],
        "lignes_articles": resultat["lignes_articles"],
        "transaction_uuids": [str(tx.uuid) for tx in resultat["transactions"]],
        "uuid_pv": uuid_pv,
        "vider_carte": vider_carte_flag,
    }
    return render(request, "laboutik/partial/hx_vider_carte_success.html", contexte)
```

### Endpoint impression — `/laboutik/vider_carte/imprimer_recu/`

```python
@action(detail=False, methods=["POST"], url_path="vider_carte/imprimer_recu", url_name="vider_carte_imprimer_recu")
def vider_carte_imprimer_recu(self, request):
    """
    POST /laboutik/vider_carte/imprimer_recu/
    Lance l'impression Celery du recu pour les transactions_uuids donnees.
    """
    transaction_uuids = request.POST.getlist("transaction_uuids")
    uuid_pv = request.POST.get("uuid_pv", "")

    if not transaction_uuids or not uuid_pv:
        return _render_erreur_toast(request, _("Parametres manquants."))

    pv = PointDeVente.objects.select_related("printer").filter(uuid=uuid_pv).first()
    if pv is None or pv.printer is None or not pv.printer.active:
        return _render_erreur_toast(
            request, _("Pas d'imprimante configuree sur ce PV.")
        )

    transactions = Transaction.objects.filter(
        uuid__in=transaction_uuids,
    ).select_related("asset")

    from laboutik.printing.formatters import formatter_recu_vider_carte
    from laboutik.printing.tasks import imprimer_async

    recu_data = formatter_recu_vider_carte(list(transactions))
    imprimer_async.delay(
        str(pv.printer.pk),
        recu_data,
        connection.schema_name,
    )
    return render(request, "laboutik/partial/hx_impression_ok.html")
```

### Frontend `vider_carte.js`

Handler JS qui s'intègre au routeur d'articles POS. Détecte `methode_caisse === "VC"` avant
l'appel à `addArticle()` et court-circuite vers le flow dédié.

Étapes :
1. Clic sur tile → intercepté avant `addArticle()`.
2. Injecter le HTML de `hx_vider_carte_overlay.html` (fourni par un endpoint trivial
   `/laboutik/vider_carte/overlay/` ou pré-rendu dans la page et toggle display).
3. `<c-read-nfc event-manage-form="viderCarteManageForm" submit-url="{% url 'laboutik-vider-carte-preview' %}">`
   active la lecture. Pattern identique à `hx_read_nfc.html`, `hx_check_card.html`, `hx_lire_nfc_client.html`.
4. Le form registered avec l'event `viderCarteManageForm` porte les hidden fields :
   - `tag_id` (rempli par `nfc.js:SendTagIdAndSubmit` sur `#nfc-tag-id`)
   - `tag_id_cm` (pré-rempli depuis `{{ card.tag_id }}`, même pattern qu'`addition.html:31`)
   - `uuid_pv` (pré-rempli depuis le contexte POS)
5. Au scan, `nfc.js` submit le form vers `/laboutik/vider_carte/preview/`.
6. Backend renvoie `hx_vider_carte_confirm.html`, injecté dans `#messages` ou overlay container.
7. Au submit HTMX du form confirm, `hx-post /laboutik/vider_carte/` → écran succès.

### Templates

**`hx_vider_carte_overlay.html`** :
- Full-screen overlay semi-transparent.
- Message « Scannez la carte du client ».
- Form caché avec hidden fields : `tag_id_cm` (valeur `{{ card.tag_id }}`), `uuid_pv`, `tag_id` (vide, rempli par le scan).
- `<c-read-nfc event-manage-form="viderCarteManageForm" submit-url="{% url 'laboutik-vider-carte-preview' %}">` qui active la lecture et submit le form au scan.
- Bouton « Annuler ».

**`hx_vider_carte_confirm.html`** :
- Titre « Vider la carte {{ carte.tag_id }} ».
- Total en gros : « À rendre : **{{ total_centimes|centimes_en_euros }} €** ».
- Tableau :
  - Ligne TLF : « {{ asset_tlf.name }} : {{ total_tlf_centimes|centimes_en_euros }} € ».
  - Ligne FED : « Fiduciaire fédérée : {{ total_fed_centimes|centimes_en_euros }} € ».
- Checkbox « Réinitialiser la carte après remboursement (détache user, wallet, carte primaire) ».
- Formulaire HTMX :
  - `hx-post="{% url 'laboutik-vider-carte' %}"`
  - `hx-target="#messages"`, `hx-swap="innerHTML"`
  - Hidden : `tag_id`, `tag_id_cm`, `uuid_pv`.
  - Checkbox name : `vider_carte`, value : `true`.
- Bouton vert « Confirmer le remboursement ».
- Bouton gris « Annuler » qui ferme l'overlay.

**`hx_vider_carte_success.html`** :
- Titre « Remboursement effectué ».
- Montant rendu en gros : « **{{ total_centimes|centimes_en_euros }} €** ».
- Détail TLF + FED (plus petit).
- Si `vider_carte=True` : ligne info « La carte a été réinitialisée. ».
- Bouton « Imprimer reçu » (`hx-post /laboutik/vider_carte/imprimer_recu/` avec hidden
  `transaction_uuids` et `uuid_pv`).
- Bouton « Retour » (hx-get vers l'accueil POS).

### Formatter impression

`laboutik/printing/formatters.py` :
```python
def formatter_recu_vider_carte(transactions):
    """
    Construit le payload de recu pour impression thermique d'un vider carte.
    / Builds the receipt payload for thermal printing of a card refund.

    Retourne un dict compatible avec imprimer_async :
    {
        "titre": "REMBOURSEMENT CARTE",
        "lignes": [
            {"texte": "Date : ...", "style": "normal"},
            {"texte": "Total rembourse : X,YZ EUR", "style": "bold"},
            {"texte": "TLF : A,BC EUR", "style": "normal"},
            {"texte": "FED : D,EF EUR", "style": "normal"},
            {"texte": "References : ...", "style": "small"},
        ],
        "qrcode": None,
    }
    """
```

Structure exacte à aligner sur les formatters existants (`formatter_ticket_billet`, etc.).

## Data flow

### Flow nominal — Carte 1000c TLF + 500c FED, sans VV

```
[1] Caissier·e ouvre un PV "Cashless" (Product VIDER_CARTE dans M2M)
    → Tile "Vider Carte" visible (methode_caisse=VC)

[2] Clic tile
    → vider_carte.js detecte data-methode-caisse="VC"
    → Affiche overlay scan NFC (<c-read-nfc>)

[3] Scan carte client
    → tag_id capture → POST /laboutik/vider_carte/preview/
      avec {tag_id, tag_id_cm (session), uuid_pv}

[4] Backend preview :
    a. tag_id != tag_id_cm (OK)
    b. CarteCashless.objects.get(tag_id)
    c. _obtenir_ou_creer_wallet(carte)
    d. _tokens_eligibles → [TLF 1000c, FED 500c]
    e. Render hx_vider_carte_confirm.html

[5] Overlay confirm :
    "À rendre : 15,00 €"
    [TLF : 10,00 €] [FED : 5,00 €]
    [ ] Reinitialiser la carte
    [Confirmer] [Annuler]

[6] Clic Confirmer (VV non coche)
    → POST /laboutik/vider_carte/
      avec {tag_id, tag_id_cm, uuid_pv, vider_carte=false}

[7] Backend executer :
    a. Serializer valid
    b. self-refund check (OK)
    c. carte_primaire_obj = _charger_carte_primaire(tag_id_cm)
    d. pv = PointDeVente.objects.get(uuid_pv)
    e. access check : pv.cartes_primaires contient carte_primaire_obj (OK)
    f. receiver_wallet = WalletService.get_or_create_wallet_tenant(tenant)
    g. WalletService.rembourser_en_especes(
           carte=carte_client, tenant=..., receiver_wallet=...,
           vider_carte=False, primary_card=carte_primaire_obj.carte)
       → Atomic :
         - Transaction REFUND TLF 1000c (primary_card=carte_caissier)
         - Transaction REFUND FED 500c (primary_card=carte_caissier)
         - LigneArticle FED +500c (payment_method=STRIPE_FED, sale_origin=ADMIN)
         - LigneArticle CASH -1500c (payment_method=CASH, sale_origin=ADMIN)
    h. Render hx_vider_carte_success.html

[8] Ecran succes :
    "Remboursement effectue : 15,00 €"
    [Imprimer recu] [Retour]

[9a] Clic Imprimer → POST /laboutik/vider_carte/imprimer_recu/
     → formatter_recu_vider_carte(transactions) + imprimer_async.delay
     → hx_impression_ok partial (toast)

[9b] Clic Retour → hx-get accueil POS, overlay fermé
```

### Flow VV (checkbox cochée)

Identique au nominal, avec `vider_carte=True` :
- `WalletService.rembourser_en_especes()` en plus :
  - `CartePrimaire.objects.filter(carte=carte).delete()`
  - `carte.user = None`, `carte.wallet_ephemere = None`, `carte.save(update_fields=...)`
- Écran succès affiche « La carte a été réinitialisée. ».

## Error handling

| Cas | Détection | Réaction |
|---|---|---|
| Tag NFC scanné inexistant | `CarteCashless.DoesNotExist` dans preview | Toast rouge « Carte client inconnue. » + retour POS. |
| Carte scannée = carte primaire (self-refund) | Check `tag_id == tag_id_cm` | Toast rouge « Ne peut pas vider une carte primaire. » |
| Carte sans wallet | `_obtenir_ou_creer_wallet() is None` | Toast rouge « Carte vierge. » |
| Tokens uniquement non-éligibles (TNF/TIM/FID ou TLF autre lieu) | `_tokens_eligibles()` vide | Toast rouge « Aucun solde remboursable sur cette carte. » |
| Carte primaire inconnue ou pas liée au PV | Helpers `_charger_carte_primaire()` + check `pv.cartes_primaires` | Toast rouge « Cette carte caissier n'a pas accès à ce PV. » |
| `NoEligibleTokens` levée au confirm (race : tokens vidés entre preview et confirm) | Try/except dans `vider_carte()` view | Toast rouge « Aucun solde remboursable (solde a pu changer). » |
| Scan NFC timeout / permission refusée navigateur | Gestion côté JS (`<c-read-nfc>` existant) | Overlay ferme, retour POS silencieux. |
| Double-clic sur Confirmer (race) | `select_for_update` interne + `NoEligibleTokens` sur le 2e appel | Toast rouge. Pas de double remboursement. |
| Impression : imprimante absente ou inactive | `pv.printer is None or not pv.printer.active` | Toast info « Pas d'imprimante configurée. ». L'opération reste valide (DB déjà enregistrée). |
| Celery indisponible (queue down) | `imprimer_async.delay()` fail silently | Le reçu n'est pas imprimé mais l'opération DB reste valide. |

## Sécurité

- **Pas de double-traitement** : `transaction.atomic()` + `select_for_update` via `WalletService.debiter()` interne (Phase 1). Le 2e POST simultané lève `NoEligibleTokens` ou `SoldeInsuffisant`.
- **Permissions** : accès via M2M `pv.cartes_primaires` — l'admin décide qui scanner sur quel PV.
- **Audit trail** : chaque `Transaction` REFUND porte `primary_card = carte_caissier`. Qui a vidé quelle carte et quand → traçable.
- **Protection self-refund** : check `tag_id != tag_id_cm` en preview ET en confirm (défense en profondeur).
- **Isolation tenant** : `_tokens_eligibles` filtre par `asset.tenant_origin == connection.tenant` pour les TLF. Les FED sont partagés par nature.

## Testing

### Tests pytest DB-only (`tests/pytest/test_pos_vider_carte.py`)

```
test_vider_carte_preview_retourne_recap_tokens
test_vider_carte_preview_carte_inconnue_toast_erreur
test_vider_carte_preview_carte_sans_solde_toast_erreur
test_vider_carte_preview_tag_identique_primary_rejette
test_vider_carte_execute_remboursement_complet
test_vider_carte_execute_avec_vv
test_vider_carte_controle_acces_carte_primaire_pas_liee_pv_rejette
test_vider_carte_primary_card_tracee_dans_transaction
test_vider_carte_race_no_eligible_tokens_gere_proprement
test_vider_carte_imprimer_recu_sans_imprimante_toast_info
```

### Test E2E Playwright (`tests/e2e/test_pos_vider_carte.py`)

```
test_e2e_pos_vider_carte_flow_complet
test_e2e_pos_vider_carte_avec_vv
test_e2e_pos_vider_carte_imprimer_recu
```

### Pièges anticipés

- **`schema_context('lespass')`** + **`tenant_context`** pour les opérations sur `CarteCashless`
  (SHARED_APPS).
- **`<c-read-nfc>` component** utilise les attributs `event-manage-form` + `submit-url` pour
  router le tag scanné vers le bon form (cf. `cotton/read_nfc.html` et `static/js/nfc.js`).
  Pour Vider Carte, on crée un form dédié `viderCarteManageForm` — pas besoin de réutiliser
  `#addition-form` (PIEGES 9.33 ne s'applique pas ici).
- **`tag_id` et `number` max 8 caractères** (PIEGES 9.31).
- **Fixtures fonctions-scope** pour les cartes avec tokens (chaque test consomme le solde).
- **Cleanup rigoureux** : Transactions, LigneArticles, Wallets, CarteCashless de test à supprimer
  (cf. expérience Phases 1/2).
- **Celery mock** pour les tests d'impression : éviter de lancer de vraies tâches.

## Compatibilité V1/V2

- V1 (anciens tenants avec `Configuration.server_cashless` renseigné) : Product VIDER_CARTE pas créé
  (pas de Phase 1), donc pas de tile POS. Le legacy LaBoutik standalone gère ses propres remboursements.
- V2 (nouveaux tenants) : flow complet fonctionnel dès que l'admin ajoute le Product VC au M2M du PV.

## Migration

- Pas de migration DB.
- Pas de data migration (le Product VIDER_CARTE est créé à la demande par `get_or_create_product_remboursement()` de Phase 1).

## i18n

Toutes les chaînes user-facing utilisent `_()`. Strings Phase 3 à traduire :
- « Scannez la carte du client »
- « Vider la carte %(tag_id)s »
- « À rendre : %(amount)s EUR »
- « Réinitialiser la carte après remboursement »
- « Confirmer le remboursement »
- « Annuler »
- « Remboursement effectué »
- « La carte a été réinitialisée. »
- « Imprimer reçu »
- « Retour »
- « Ne peut pas vider une carte primaire. »
- « Carte client inconnue. »
- « Carte vierge. »
- « Aucun solde remboursable sur cette carte. »
- « Aucun solde remboursable (solde a pu changer). »
- « Cette carte caissier n'a pas accès à ce PV. »
- « PV introuvable. »
- « Pas d'imprimante configurée sur ce PV. »
- « Paramètres manquants. »

Lancer après implémentation :
```
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
docker exec lespass_django poetry run django-admin compilemessages
```

## Décisions transversales (rappel du brainstorming)

- Flow dédié qui court-circuite le panier (option A).
- Checkbox VV sur l'écran de confirmation (option A).
- Pas de permission additionnelle — admin contrôle via M2M PV (option A).
- Tile générée automatiquement via Product `methode_caisse=VC` + détection frontend (option A).
- Affichage : total + détail par asset (TLF + FED) (option B).
- Erreurs : toast rouge + retour immédiat (option A).
- Impression : optionnelle via bouton sur écran succès (option B).

## Roadmap suivante

Phase 3 est la **dernière** phase du chantier « Cartes NFC admin + flux de remboursement ». Après
livraison :
- Phase 1 (admin web cartes + refund) ✅
- Phase 2 (dette pot central + BANK_TRANSFER) ✅
- Phase 3 (bouton POS Cashless Vider Carte) ← cette spec

Améliorations possibles hors scope :
- Export CSV des BANK_TRANSFER + historique VC pour la compta du pot central.
- Rapports agrégés multi-tenant côté superuser.
- Archivage fiscal des reçus VC (si réglementation l'exige).

## Notes pour l'implémenteur

- **`<c-read-nfc>` component** (`cotton/read_nfc.html` + `static/js/nfc.js`) : pattern
  `event-manage-form="<nom>"` + `submit-url="<url>"`. Au scan, `nfc.js:SendTagIdAndSubmit`
  populate `#nfc-tag-id` dans le form enregistré sous `<nom>`, change son URL, et submit.
  Identique aux flows existants (`hx_read_nfc.html`, `hx_check_card.html`, `hx_lire_nfc_client.html`).
- **Pattern `sendEvent`/`eventsOrganizer`** utilisé partout dans laboutik JS (cf. `addition.js`,
  `articles.js`) — suivre ce pattern pour `vider_carte.js`.
- **`tag_id_cm`** (tag caissier) est disponible via `{{ card.tag_id }}` dans tous les templates
  POS (propagé via URL query param `?tag_id_cm=X` puis hidden `<input name="tag_id_cm">` dans
  `addition.html:31` et les `hx-vals` des autres flows). Pas d'ajout au state nécessaire.
- **Service Phase 1** (`WalletService.rembourser_en_especes`) fait tout le gros œuvre — Phase 3
  ne doit pas dupliquer la logique de calcul de dette, de création de LigneArticle, ou de
  réinitialisation de carte.
- **Test fixtures** : réutiliser le pattern `carte_avec_solde_tlf` et `carte_avec_solde_fed` de
  Phase 1 (`tests/pytest/test_card_refund_service.py`), les adapter pour le contexte POS
  (ajouter une `CartePrimaire` caissier + un `PointDeVente` avec le Product VC en M2M).
