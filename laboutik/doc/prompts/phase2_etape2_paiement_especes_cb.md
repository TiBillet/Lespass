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

Tache (1 fichier principal : laboutik/views.py) :

1. moyens_paiement() + confirmer() — remplacer le mock par :
   - Lire les articles du panier depuis la requete POST
   - Product.objects.get(uuid=uuid) pour chaque produit du panier
   - Price.objects.get(uuid=uuid_price) pour le tarif choisi
   - Calculer le total en centimes : int(round(price.prix * 100))
   - Passer au template

2. payer() — remplacer le mock pour especes et CB :

   _payer_par_carte_ou_cheque() :
   - transaction.atomic()
   - Boucle sur les articles du panier
   - LigneArticle.objects.create(sale_origin='LB', payment_method='CC', ...)
   - Montant en centimes

   _payer_en_especes() :
   - Idem avec payment_method='CA'

3. Pour le paiement NFC : garder le mock ou retourner un message
   "Paiement NFC non disponible — Phase 3". NE PAS integrer fedow_core.

4. lire_nfc() + verifier_carte() + retour_carte() — garder les mocks
   pour l'instant (ou les desactiver avec un message).

5. Nettoyer les imports mock dans les fonctions modifiees.

Verification :
docker exec lespass_django poetry run python manage.py check
Tester un paiement especes via l'interface.
Verifier en shell : LigneArticle.objects.filter(sale_origin='LB').count()

⚠️ NE PAS integrer fedow_core. Pas de Transaction, pas de Token.
⚠️ Les templates de paiement peuvent necessiter des ajustements mineurs
   si les noms de variables du contexte changent.
```

## Verification

- Paiement especes → LigneArticle cree avec payment_method='CA'
- Paiement CB → LigneArticle cree avec payment_method='CC'
- Le total est correct en centimes
- Pas de traceback dans les logs

## Modele recommande

Sonnet
