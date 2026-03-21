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

```python
panier_a_billets = any(
    a['product'].methode_caisse == Product.BILLET_POS
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

Logique (dans `db_transaction.atomic()`) :
1. Filtrer les articles BI du panier
2. Pour chaque article BI, trouver l'Event lié
3. **VÉRIFICATION ATOMIQUE JAUGE** : compter les Ticket(status__in=['K','S']) pour cet event.
   Si places_vendues + qty > jauge_max → lever ValueError
4. Créer Reservation(user_commande=user_client, event=event, to_mail=bool(email))
5. Pour chaque unité (qty) : ProductSold → PriceSold → Ticket(status='K') → LigneArticle

**APRÈS le bloc atomic** : appeler `imprimer_billet()` (le stub console logger).

## TÂCHE 4 — Intégrer dans les fonctions de paiement

Dans `_payer_par_carte_ou_cheque()` et `_payer_en_especes()`, après l'appel
à `_creer_adhesions_depuis_panier()` :

```python
articles_billet = [a for a in articles_panier if a['product'].methode_caisse == Product.BILLET_POS]
if articles_billet:
    user_client = ...  # extraire du POST (tag_id → carte.user, ou email → get_or_create)
    email_client = request.POST.get("email_adhesion", "")
    _creer_billets_depuis_panier(articles_billet, user_client, email_client, moyen_paiement_code)
```

Le user_client peut venir de l'identification faite pour l'adhésion (même flow unifié).

## TÂCHE 5 — Tests unitaires

Crée `tests/pytest/test_billetterie_pos.py` :

```python
def test_construire_donnees_articles_avec_billet(tenant):
    """Un Product BI avec Event → article_dict contient 'event' avec jauge."""

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

Utilise les fixtures existantes de `create_test_pos_data` (Tâche 6 de Session 06).

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

## VÉRIFICATION

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_billetterie_pos.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
docker exec lespass_django poetry run pytest tests/e2e/test_pos_billetterie.py -v -s
docker exec lespass_django poetry run pytest tests/e2e/ -v -s
```

### Critère de succès

- [ ] `_creer_billets_depuis_panier()` crée Reservation + Ticket + LigneArticle
- [ ] Ticket.status = 'K' (NOT_SCANNED)
- [ ] Jauge atomique : ValueError si event complet
- [ ] Panier mixte (VT + BI + AD) fonctionne avec 1 seule identification
- [ ] 7+ tests pytest verts
- [ ] 7 scénarios E2E verts
- [ ] TOUS les tests laboutik existants passent (pas de régression)
