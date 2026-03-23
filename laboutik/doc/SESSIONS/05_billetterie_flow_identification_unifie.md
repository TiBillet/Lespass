# Session 05 — Flow d'identification unifié (1 panier = 1 client)

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django + HTMX).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

### Le problème actuel

Dans `laboutik/templates/laboutik/partial/hx_display_type_payment.html`, le code
utilise un `elif` mutuellement exclusif :

```
if consigne → flow consigne
elif panier_a_recharges → flow recharge (scan NFC client)
elif panier_a_adhesions → flow adhésion (wizard identification)
else → flow normal
```

Un panier avec `Recharge 10€ + Adhésion annuelle` ne fonctionne pas. C'est soit l'un, soit l'autre.

### La solution : 1 panier = 1 client

Quand le panier contient des articles qui nécessitent un client (recharge, adhésion,
ou billet dans une session future), le système demande UNE SEULE identification.
Ce client est utilisé pour tout : recharge → sa carte, adhésion → son user.

L'identification se fait **AVANT** le choix du moyen de paiement (plus logique UX :
on sait d'abord pour qui on paie, puis on choisit comment).

## TÂCHE 1 — Lire le code existant

1. Lis `laboutik/views.py`, fonction `moyens_paiement()` (~ligne 1574).
   Note les flags `panier_a_recharges` et `panier_a_adhesions` et comment ils sont
   passés au template.

2. Lis `laboutik/templates/laboutik/partial/hx_display_type_payment.html` en entier.
   Note le `elif` et les 3 branches (consigne, recharge, adhesion, normal).

3. Lis les templates d'identification adhésion existants :
   - `laboutik/templates/laboutik/partial/hx_adhesion_choose_id.html`
   - `laboutik/templates/laboutik/partial/hx_read_nfc_adhesion.html`
   - `laboutik/templates/laboutik/partial/hx_adhesion_form.html`
   - `laboutik/templates/laboutik/partial/hx_adhesion_confirm.html`

4. Lis les actions ViewSet adhésion dans views.py :
   - `adhesion_choisir_identification()` (ligne 2208)
   - `lire_nfc_adhesion()` (ligne 2221)
   - `adhesion_formulaire()` (ligne 2232)
   - `identifier_membre()` (ligne 2243)

## TÂCHE 2 — Nouveau flag unifié dans views.py

Dans `moyens_paiement()`, remplace les flags séparés par un flag unifié :

```python
panier_necessite_client = (
    _panier_contient_recharges(articles_panier)
    or panier_a_adhesions
)
```

Garde aussi les sous-flags individuels (`panier_a_recharges`, `panier_a_adhesions`)
pour que le template puisse adapter le texte explicatif.

Passe `panier_necessite_client` dans le contexte template.

> **Note** : `panier_a_billets` sera ajouté dans la session 07 (billetterie).
> Le flag est conçu pour être extensible.

## TÂCHE 3 — Renommer les actions ViewSet

Renommer les actions pour refléter leur rôle unifié (pas seulement adhésion) :

| Ancien nom | Nouveau nom | URL |
|---|---|---|
| `adhesion_choisir_identification()` | `choisir_identification_client()` | `paiement/choisir_identification_client/` |
| `lire_nfc_adhesion()` | `lire_nfc_client()` | `paiement/lire_nfc_client/` |
| `adhesion_formulaire()` | `formulaire_identification_client()` | `paiement/formulaire_identification_client/` |
| `identifier_membre()` | `identifier_client()` | `paiement/identifier_client/` |

Renommer aussi les templates correspondants :

| Ancien template | Nouveau template |
|---|---|
| `hx_adhesion_choose_id.html` | `hx_identifier_client.html` (tâche 4) |
| `hx_read_nfc_adhesion.html` | `hx_lire_nfc_client.html` |
| `hx_adhesion_form.html` | `hx_formulaire_identification_client.html` |
| `hx_adhesion_confirm.html` | `hx_recapitulatif_client.html` (tâche 5) |

Mettre à jour toutes les références dans views.py, les templates, et les tests.

## TÂCHE 4 — Nouveau template `hx_identifier_client.html`

Remplace `hx_adhesion_choose_id.html`.
Crée `laboutik/templates/laboutik/partial/hx_identifier_client.html`.

Ce template remplace les branches séparées. Il affiche :

1. Un titre "Identifier le client"
2. Un texte explicatif adaptatif :
   - Si `panier_a_recharges` : "Recharge → carte NFC requise"
   - Si `panier_a_adhesions` : "Adhésion → identification requise"
   - Si les deux : les deux lignes
3. Bouton "SCANNER CARTE NFC" (toujours présent)
4. Bouton "SAISIR EMAIL/NOM" (masqué si `panier_a_recharges` car carte physique requise)
5. Bouton RETOUR

Les boutons font des `hx-get` vers les actions renommées :
- Scanner → `lire_nfc_client`
- Email → `formulaire_identification_client`

`data-testid` : `identifier-client`, `identifier-btn-nfc`, `identifier-btn-email`

## TÂCHE 5 — Nouveau template `hx_recapitulatif_client.html`

Remplace `hx_adhesion_confirm.html`.
Crée `laboutik/templates/laboutik/partial/hx_recapitulatif_client.html`.

### Ce que le template affiche

```
┌──────────────────────────────────────────────────────────┐
│  ✅ Marie Dupont — marie@example.com                      │
│  Carte : 52BE6543 │ Solde : 45,00€                       │
│                                                            │
│  Bière × 2                              7,00€             │
│  Recharge 10€ → carte de Marie         10,00€             │
│  Adhésion annuelle → rattachée à Marie 20,00€             │
│  ─────────────────────────────────────────────            │
│  TOTAL                                 37,00€             │
│                                                            │
│  [ESPÈCE]  [CB]  [CHÈQUE]                                │
└──────────────────────────────────────────────────────────┘
```

1. Nom/email du client identifié
2. Solde wallet (si carte NFC scannée)
3. **Récap des articles avec ce qui sera fait** — article par article avec prix :
   - Article VT : `"{nom} × {quantité} — {prix}€"`
   - Article RE : `"Recharge {prix}€ → carte de {client}"`
   - Article AD : `"Adhésion {nom_prix} → rattachée à {client}"`
4. Total en euros
5. Boutons moyens de paiement (espèces, CB, chèque — PAS NFC si recharges)
6. Bouton RETOUR

`data-testid` : `client-recapitulatif`, `client-recapitulatif-user`,
`client-recapitulatif-articles`, `client-btn-especes`, `client-btn-cb`,
`client-btn-cheque`, `client-btn-cashless`

### Comment `identifier_client()` reconstruit le panier

Le formulaire `#addition-form` (soumis par le NFC reader ou le formulaire HTMX)
contient déjà les `repid-<uuid>` des articles et le `uuid_pv`. La vue
`identifier_client()` peut donc reconstruire le panier avec les helpers existants :

```python
# Dans identifier_client(), AVANT l'identification :
uuid_pv = request.POST.get("uuid_pv")
point_de_vente = PointDeVente.objects.get(uuid=uuid_pv)
articles_panier = _extraire_articles_du_panier(request.POST, point_de_vente)
total_centimes = _calculer_total_panier_centimes(articles_panier)
total_en_euros = total_centimes / 100
```

Les articles sont ensuite enrichis pour le template avec le contexte client :

```python
articles_pour_recapitulatif = []
for article in articles_panier:
    produit = article['product']
    prix_euros = article['prix_centimes'] / 100
    quantite = article['quantite']

    # Texte adaptatif selon le type d'article
    if produit.methode_caisse in ('RE', 'RC', 'TM'):
        description = f"Recharge {prix_euros:.2f}€ → carte de {user_prenom}"
    elif produit.categorie_article == Product.ADHESION:
        description = f"{article['price'].name} → rattachée à {user_prenom} {user_nom}"
    else:
        description = f"{produit.name} × {quantite}"

    articles_pour_recapitulatif.append({
        'description': description,
        'prix_euros': prix_euros * quantite,
    })
```

Le contexte du récapitulatif inclut `articles_pour_recapitulatif` et `total_en_euros`.

> **Note** : `_extraire_articles_du_panier()` nécessite `point_de_vente`.
> Le `uuid_pv` est dans `#addition-form` (champ caché existant).
> Pas besoin de le propager séparément.

### Propagation des données du panier

Le NFC reader soumet `#addition-form` qui contient déjà :
- `uuid_pv` (le PV sélectionné)
- `repid-<uuid>` (les articles du panier avec quantités)
- `tag_id` (injecté par le NFC reader JS)

Le formulaire email (`hx_formulaire_identification_client.html`) fait un `hx-post`
séparé. Il ne contient PAS les articles du panier. Deux solutions :

**Solution implémentée** : le formulaire email n'est plus un `<form hx-post>` séparé.
Le bouton VALIDER appelle `soumettreIdentificationEmail()` (JS inline) qui :
1. Lit les champs email/prénom/nom du formulaire local
2. Les injecte dans `#addition-form` via `setHiddenInput()`
3. Soumet `#addition-form` vers `identifier_client` via `sendEvent('additionManageForm')`

Les `repid-*` et `uuid_pv` sont déjà dans `#addition-form` → tout arrive dans le POST.
Même pattern que `payerAvecClient()` et l'ancien `confirmerAdhesion()`.

## TÂCHE 6 — Modifier `hx_display_type_payment.html`

Remplace le `elif` par :

```html
{% if deposit_is_present %}
  {# flow consigne (inchangé) #}
{% elif panier_necessite_client %}
  {% include "laboutik/partial/hx_identifier_client.html" %}
{% else %}
  {# flow normal — boutons paiement standards (inchangé) #}
{% endif %}
```

Les branches `panier_a_recharges` et `panier_a_adhesions` disparaissent.

## TÂCHE 7 — Adapter `identifier_client()` pour reconstruire le panier

L'action `identifier_client()` doit :

1. **Reconstruire le panier** depuis le POST (les `repid-*` + `uuid_pv` sont dans le
   formulaire soumis). Utiliser `_extraire_articles_du_panier()` et
   `_calculer_total_panier_centimes()` — mêmes helpers que `moyens_paiement()`.

2. **Enrichir les articles** avec le contexte client (texte adaptatif par type).

3. **Passer le panier enrichi au template** `hx_recapitulatif_client.html` :
   `articles_pour_recapitulatif` (liste de dicts `description` + `prix_euros`) +
   `total_en_euros`.

4. **Stocker le `tag_id`** dans le récapitulatif. Le `tag_id` est déjà dans
   `#addition-form` (injecté par le NFC reader). Il sera utilisé par
   `_payer_par_carte_ou_cheque()` pour créditer le wallet si le panier a des recharges.

### Propagation des articles du panier dans le flow email — RÉSOLU

**Flow NFC** : `#addition-form` est soumis directement → les `repid-*` arrivent.

**Flow email** : le formulaire ne fait plus de `hx-post` séparé. Le bouton VALIDER
injecte email/prénom/nom dans `#addition-form` (qui contient déjà les `repid-*`)
puis soumet via `sendEvent('additionManageForm', ... submit)`.
Pas de JSON, pas de propagation complexe. Même pattern que `payerAvecClient()`.

## TÂCHE 8 — Écrire les tests

### Tests unitaires : `tests/pytest/test_identification_unifiee.py`

```python
def test_panier_necessite_client_vente_seule():
    """Panier avec seulement des articles VT → pas d'identification."""

def test_panier_necessite_client_recharge():
    """Panier avec recharge → identification requise."""

def test_panier_necessite_client_adhesion():
    """Panier avec adhésion → identification requise."""

def test_panier_necessite_client_mixte():
    """Panier recharge + adhésion → identification requise (1 seule fois)."""

def test_panier_recharge_bloque_email():
    """Panier avec recharge → le bouton email est masqué (carte physique requise)."""
```

### Tests E2E : adapter `tests/e2e/test_pos_adhesion_nfc.py`

Les chemins 1-5 de l'adhésion doivent toujours fonctionner, mais avec les noms
renommés (`identifier-client` au lieu de `adhesion-choose-id`, etc.).
Adapter les sélecteurs `data-testid`.

Ajouter un test pour un panier mixte (recharge + adhésion) :
- Prérequis : un PV de test contenant des articles RE + AD (à ajouter dans
  `create_test_pos_data` ou dans une fixture dédiée)
- Ajouter Recharge 10€ + Adhésion au panier
- VALIDER → écran identification client (NFC seulement, pas d'email)
- Scanner NFC → récapitulatif avec :
  - "Recharge 10€ → carte de {client}" dans la liste des articles
  - "Adhésion annuelle → rattachée à {client}" dans la liste des articles
  - Total correct
- Payer en espèces → succès
- Vérifier en DB : LigneArticle créée + Membership créée + Token crédité

## VÉRIFICATION

### Tests unitaires

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_identification_unifiee.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Tests E2E

```bash
# Adhésion (le plus impacté)
docker exec lespass_django poetry run pytest tests/e2e/test_pos_adhesion_nfc.py -v -s

# Paiement standard (ne doit pas régresser)
docker exec lespass_django poetry run pytest tests/e2e/test_pos_paiement.py -v -s

# Tous les tests E2E
docker exec lespass_django poetry run pytest tests/e2e/ -v -s
```

### Critère de succès

- [x] Actions renommées (3 renommées + 1 supprimée, URLs mises à jour)
- [x] Templates renommés (4 templates : noms cohérents avec les actions)
- [x] Écran identification intégré dans `hx_display_type_payment.html`
- [x] `hx_recapitulatif_client.html` affiche le récap article par article avec prix
- [x] `identifier_client()` reconstruit le panier depuis les `repid-*` du POST
- [x] Le `elif` mutuellement exclusif est supprimé de `hx_display_type_payment.html`
- [x] Panier VT seul → pas d'identification
- [x] Panier RE seul → identification NFC obligatoire (pas d'email)
- [x] Panier AD seul → identification NFC ou email
- [x] Panier RE + AD → identification NFC (1 seul scan) + récap mixte + paiement OK
- [x] Articles du panier propagés dans le flow email (soumission via `#addition-form`)
- [x] Verrouillage par groupe JS supprimé (paniers mixtes autorisés)
- [x] PV "Mix" créé dans `create_test_pos_data` (Biere VT + Recharge 10€ RE + Adhesion Test Mix AD)
- [x] Vérification LigneArticle en DB (email, carte, payment_method, sale_origin, amount, qty, status)
- [x] TOUS les tests pytest passent (28/28)
- [x] TOUS les tests E2E passent (8/8 + 8/8 régression)
- [x] Test E2E panier mixte sur PV "Mix" (VT + RE + AD → NFC → espèces → 3 LigneArticle vérifiées en DB)
