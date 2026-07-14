# Phase 2, Etape 2 — Paiement especes et carte bancaire

## Prompt

```
On travaille sur la Phase 2 du plan laboutik/doc/PLAN_INTEGRATION.md
Etape 2 sur 2 : les vues de paiement (hors NFC).

L'etape 1 est faite : carte_primaire et point_de_vente lisent la DB.
Lis le plan section 12 (PaiementViewSet).

Contexte :
- PaiementViewSet a 6 actions, toutes mockees
- On remplace les mocks par des queries ORM + creation de LigneArticle
- Le paiement NFC (fedow_core) est Phase 3, PAS maintenant
- LigneArticle existe dans BaseBillet, champ sale_origin, payment_method

⚠️ IMPORTANT — LigneArticle utilise PriceSold + ProductSold :
LigneArticle.pricesold pointe vers PriceSold (pas Price directement).
PriceSold pointe vers ProductSold (pas Product directement).
LIRE les modeles PriceSold et ProductSold dans BaseBillet/models.py AVANT de coder.
Il faudra creer PriceSold + ProductSold pour chaque vente, ou utiliser les methodes
existantes si elles existent. Verifier d'abord !

Tache (1 fichier principal : laboutik/views.py + laboutik/serializers.py) :

1. Creer PanierSerializer (dans laboutik/serializers.py) :
   - articles = serializers.ListField(child=ArticleSerializer)
   - ArticleSerializer : product_uuid, price_uuid, quantity
   - Validation : UUIDs valides, quantites > 0

2. moyens_paiement() + confirmer() — remplacer le mock par :
   - Valider avec PanierSerializer
   - Product.objects.get(uuid=uuid) pour chaque produit du panier
   - Price.objects.get(uuid=uuid_price) pour le tarif choisi
   - Calculer le total en centimes : int(round(price.prix * 100))
   - Passer au template

3. payer() — remplacer le mock pour especes et CB :

   _payer_par_carte_ou_cheque() :
   - transaction.atomic()
   - Boucle sur les articles du panier
   - Creer ProductSold + PriceSold (ou utiliser le pattern existant)
   - LigneArticle.objects.create(sale_origin='LB', payment_method='CC', ...)
   - Montant en centimes : int(round(price.prix * 100))

   _payer_en_especes() :
   - Idem avec payment_method='CA'

4. Pour le paiement NFC : retourner un partial HTML avec message
   "Paiement NFC disponible en prochaine mise a jour".
   NE PAS integrer fedow_core.

5. lire_nfc() + verifier_carte() + retour_carte() — garder les mocks
   pour l'instant.

6. Nettoyer les imports mock dans les fonctions modifiees.

7. Ajouter data-testid sur les elements de paiement :
   - data-testid="paiement-total"
   - data-testid="paiement-btn-especes"
   - data-testid="paiement-btn-cb"
   - data-testid="paiement-confirmation"

Verification :
docker exec lespass_django poetry run python manage.py check
Tester un paiement especes via l'interface.
Verifier en shell : LigneArticle.objects.filter(sale_origin='LB').count()

⚠️ NE PAS integrer fedow_core. Pas de Transaction, pas de Token.
⚠️ LIRE PriceSold/ProductSold dans BaseBillet/models.py avant de creer des LigneArticle.
⚠️ Les templates de paiement peuvent necessiter des ajustements mineurs
   si les noms de variables du contexte changent.
```

## Tests

### pytest — tests/pytest/test_paiement_especes_cb.py

```python
# Tests a ecrire dans cette session :
# 1. test_paiement_especes_cree_ligne_article — payer CA → LigneArticle(payment_method='CA')
# 2. test_paiement_cb_cree_ligne_article — payer CC → LigneArticle(payment_method='CC')
# 3. test_total_centimes_correct — int(round(prix * 100)) == montant dans LigneArticle
# 4. test_pricesold_et_productsold_crees — verifier que les intermediaires existent
# 5. test_panier_vide_refuse — POST panier vide → erreur validation serializer
# 6. test_product_uuid_inexistant — UUID inconnu → 404
# 7. test_paiement_atomique — si erreur mid-paiement, aucune LigneArticle creee
# 8. test_paiement_nfc_desactive — retourne message "non disponible"
```

Lancer : `docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py -v`

### Playwright — tests/playwright/tests/32-laboutik-caisse-db.spec.ts (suite)

```
Ajouter au test existant (ou creer 32b) :
1. Depuis l'interface PV (deja chargee dans le test etape 1)
2. Ajouter 2 articles au panier (clic sur les boutons produits)
3. Cliquer "Valider"
4. Choisir "Especes"
5. Confirmer le paiement
6. Verifier le message de succes
7. Verifier en DB : LigneArticle.objects.filter(sale_origin='LB').count() >= 2
```

### Verification manuelle

- Paiement especes → LigneArticle cree avec payment_method='CA'
- Paiement CB → LigneArticle cree avec payment_method='CC'
- Le total est correct en centimes
- PriceSold et ProductSold sont crees
- Pas de traceback dans les logs

## Checklist fin d'etape

- [ ] `manage.py check` passe
- [ ] Tests pytest verts (8 tests)
- [ ] Test Playwright vert
- [ ] Pas de traceback dans les logs serveur
- [ ] PriceSold + ProductSold correctement crees pour chaque vente
- [ ] i18n : `docker exec lespass_django poetry run django-admin makemessages -l fr -l en && compilemessages`
- [ ] Mettre a jour CHANGELOG.md
- [ ] Creer `A TESTER et DOCUMENTER/phase2-etape2-paiement-especes-cb.md`
- [ ] **Checkpoint securite Phase 2** : sans API key → 403, mauvais tenant → 403

## Modele recommande

Sonnet
