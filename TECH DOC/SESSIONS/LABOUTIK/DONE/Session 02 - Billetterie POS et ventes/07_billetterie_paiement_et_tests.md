# Session 07 — Paiement billet + jauge atomique + tests complets

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django + HTMX).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

Les tuiles billet sont visibles dans la grille (Session 06).
Il faut maintenant implémenter la création de Reservation + Ticket au paiement,
la vérification atomique de la jauge, et écrire tous les tests.

## TÂCHE 1 — Lire les modèles BaseBillet

**OBLIGATOIRE avant de coder.** Lis dans `BaseBillet/models.py` :

1. `Reservation` : quels champs ? `user_commande` FK, `event` FK, `to_mail`, `status`...
2. `Ticket` : quels champs ? `reservation` FK, `pricesold` FK, `status`...
   - Codes status : `'C'`=CREATED, `'N'`=NOT_ACTIV, `'K'`=NOT_SCANNED, `'S'`=SCANNED, `'R'`=CANCELED
   - **Utiliser `Ticket.NOT_SCANNED` (='K')** pour les billets vendus
3. `ProductSold` : champs ? `product` FK, `event` FK, `categorie_article`...
4. `PriceSold` : champs ? `productsold` FK, `price` FK, `prix`...
5. `LigneArticle` : champs ? `pricesold` FK, `sale_origin`, `payment_method`, `status`...

**Ne PAS deviner les champs.** Les lire dans le code source.

## TÂCHE 2 — Ajouter `panier_a_billets` au flow identification

Dans `laboutik/views.py`, `moyens_paiement()` :

**ATTENTION** : les articles billet dans le panier ont `methode_caisse='BI'` dans le dict
(mis par `_construire_donnees_articles()`) mais l'ID est le **Price UUID** (pas le Product UUID).
La détection doit se faire sur le dict article reconstruit depuis les `repid-*` du POST,
pas sur `product.methode_caisse` (le Product n'a pas forcément `methode_caisse='BI'` — c'est
le type du PV BILLETTERIE qui détermine le chargement, pas un flag sur l'article).

Option la plus fiable : vérifier si l'UUID du `repid-*` correspond à une Price liée à un
Product qui est lié à un Event futur publié.

```python
# Detecter les articles billet dans le panier
# Un article billet a un repid-{price_uuid} où la Price est liée à un Product
# qui est lié à un Event futur publié.
# / Detect ticket articles in the cart
panier_a_billets = any(
    a.get('est_billet', False)
    for a in articles_panier
)

panier_necessite_client = (
    _panier_contient_recharges(articles_panier)
    or panier_a_adhesions
    or panier_a_billets  # AJOUT
)
```

Passer `panier_a_billets` au contexte. Adapter `hx_identifier_client.html` (Session 05)
pour afficher "Billet → envoyé par email (optionnel)" si `panier_a_billets`.

## TÂCHE 3 — `_creer_billets_depuis_panier()`

Crée cette fonction dans `laboutik/views.py`.
Appelée par `_payer_par_carte_ou_cheque()` et `_payer_en_especes()` après les adhésions.

**IMPORTANT** : l'article billet dans le panier a `id = str(price.uuid)` (Price UUID, pas Product UUID).
Les `repid-{uuid}` dans le POST contiennent donc le Price UUID.
Pour retrouver le Product et l'Event :
```python
price = Price.objects.select_related('product').get(uuid=price_uuid)
product = price.product
event = Event.objects.filter(products=product, published=True, datetime__gte=now).first()
```

Logique (dans `db_transaction.atomic()`) :
1. Filtrer les articles billet du panier (ceux qui ont `est_billet=True`)
2. Pour chaque article billet, retrouver Price → Product → Event
3. **VÉRIFICATION ATOMIQUE JAUGE** : `select_for_update()` sur l'Event, compter les
   Ticket(status__in=['K','S']). Si places_vendues + qty > jauge_max → lever ValueError.
   Si `Price.stock` défini, vérifier aussi `Price.out_of_stock(event)`.
4. Créer Reservation(user_commande=user_client, event=event, to_mail=bool(email))
5. Pour chaque unité (qty) : ProductSold → PriceSold → Ticket(status='K') → LigneArticle

**APRÈS le bloc atomic** : appeler `imprimer_billet()` (le stub console logger).

## TÂCHE 4 — Intégrer dans les fonctions de paiement

Dans `_payer_par_carte_ou_cheque()` et `_payer_en_especes()`, après l'appel
à `_creer_adhesions_depuis_panier()` :

```python
articles_billet = [a for a in articles_panier if a.get('est_billet', False)]
if articles_billet:
    user_client = ...  # extraire du POST (tag_id → carte.user, ou email → get_or_create)
    email_client = request.POST.get("email_adhesion", "")
    _creer_billets_depuis_panier(articles_billet, user_client, email_client, moyen_paiement_code)
```

Le user_client peut venir de l'identification faite pour l'adhésion (même flow unifié).

## TÂCHE 5 — Tests unitaires

Crée `tests/pytest/test_billetterie_pos.py` :

```python
def test_construire_donnees_articles_pv_billetterie(tenant):
    """PV BILLETTERIE avec Event futur → article_dict contient 'event' avec jauge."""

def test_creer_billet_espece_sans_email(tenant):
    """Paiement espèces → Reservation + Ticket créés, to_mail=False."""

def test_creer_billet_avec_email(tenant):
    """Paiement avec email → to_mail=True, user créé."""

def test_jauge_bloque_vente(tenant):
    """Jauge pleine → ValueError levée, aucun Ticket créé (rollback)."""

def test_panier_mixte_billet_et_vente(tenant):
    """Bière + Billet → 2 LigneArticle, 1 Ticket."""

def test_panier_mixte_billet_et_adhesion(tenant):
    """Adhésion + Billet → 1 Membership + 1 Ticket, même user."""

def test_ticket_status_not_scanned(tenant):
    """Le Ticket créé a status='K' (NOT_SCANNED)."""
```

**IMPORTANT** : `create_test_pos_data` ne crée plus d'Events ni de Products billet.
Le PV BILLETTERIE charge les events existants de demo_data_v2.
Les tests doivent créer leurs propres Events + Products billet dans les fixtures
(avec `schema_context` ou `FastTenantTestCase`).

## TÂCHE 6 — Tests E2E

Crée `tests/e2e/test_pos_billetterie.py` :

Scénarios :
1. Affichage tuile billet avec jauge dans la grille
2. Ajouter un billet au panier → panier affiche le bon prix
3. VALIDER → identification client (panier_necessite_client car BI)
4. Payer en espèces sans email → Ticket(status='K') en DB
5. Payer en espèces avec email → Reservation(to_mail=True) en DB
6. Panier mixte (bière + billet) → les 2 traités correctement
7. Event complet → tuile désactivée, paiement refusé si tenté

## CE QUI A ÉTÉ FAIT

### ID composite `{event_uuid}__{price_uuid}`

Le problème central : un Product (et sa Price) peut être dans plusieurs Events.
Avec juste `repid-{price_uuid}`, on ne sait pas quel Event le client visait.

Solution : `"id": f"{event.uuid}__{price.uuid}"` dans `_construire_donnees_articles()`.
Le JS traite `data-uuid` comme une string opaque → aucune modif JS.
Le séparateur `__` ne conflicte pas avec `--` (multi-tarif).

### Fichiers modifiés

| Fichier | Changement |
|---------|-----------|
| `laboutik/views.py` | ID composite dans `_construire_donnees_articles()`, parser `__` dans `_extraire_articles_du_panier()`, `panier_a_billets` dans `moyens_paiement()`, branche billet dans `identifier_client()`, NOUVEAU `_creer_billets_depuis_panier()` + `imprimer_billet()` stub + `_envoyer_billets_par_email()`, intégration dans `_payer_par_carte_ou_cheque()` et `_payer_en_especes()` |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | Titre "Billetterie", texte "(email optionnel)", propagation `panier_a_billets` dans query params |
| `laboutik/templates/laboutik/partial/hx_lire_nfc_client.html` | Hidden input `panier_a_billets` |
| `laboutik/templates/laboutik/partial/hx_formulaire_identification_client.html` | Hidden input `panier_a_billets` |
| `BaseBillet/models.py` | `LigneArticle.user_email()` : ajout branche `reservation.user_commande.email` |
| `Administration/admin/sales.py` | `select_related` + `search_fields` avec `reservation__user_commande` |
| `tests/pytest/test_billetterie_pos.py` | NOUVEAU — 12 tests (8 unitaires + 4 HTTP) |
| `tests/e2e/test_pos_billetterie.py` | NOUVEAU — 5 tests E2E Playwright |

### Pièges rencontrés (documentés dans TESTS_README.md 9.36-9.42)

- `_, _created = get_or_create()` masque `_()` (gettext) → utiliser `_created`
- `PointDeVente.objects.first()` perturbé par les PV de test → `poid_liste=9999`
- Flow récapitulatif client → paiement direct (pas d'écran confirmation)
- `#bt-retour-layer1` en double dans le DOM → scoper au container succès
- `Reservation.objects.create(status=VALID)` ne déclenche pas les signaux → appel Celery explicite
- `LigneArticle.user_email()` ne couvrait pas `reservation.user_commande.email`

## VÉRIFICATION

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_billetterie_pos.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -q
docker exec lespass_django poetry run pytest tests/e2e/test_pos_billetterie.py -v -s
```

### Critère de succès

- [x] `_creer_billets_depuis_panier()` crée Reservation + Ticket + LigneArticle
- [x] Ticket.status = 'K' (NOT_SCANNED)
- [x] Jauge atomique : ValueError si event complet
- [x] Panier mixte (VT + BI) fonctionne avec 1 seule identification
- [x] 12 tests pytest verts (8 unitaires + 4 HTTP)
- [x] 5 scénarios E2E verts
- [x] 218 tests pytest existants passent (0 régression)
- [x] Email billet visible dans l'admin LigneArticle
- [x] Envoi email Celery déclenché après paiement (webhook + PDF)
