# Phase 1, Etape 2 — Admin Unfold + donnees initiales

## Prompt

```
On travaille sur la Phase 1 du plan laboutik/doc/PLAN_INTEGRATION.md
Etape 2 sur 2 : admin Unfold + donnees de test.

Les modeles sont crees (etape 1 faite). Lis le plan section 13.

Contexte :
- Decision 16.9 : Product unifie. POSProduct est un proxy de Product.
- L'admin est centralise dans Administration/admin_tenant.py (pas laboutik/admin.py).
- Suivre le pattern exact de TicketProductAdmin / MembershipProductAdmin.
- Sidebar conditionnelle : section "Caisse" visible si module_caisse=True.

Tache :

PARTIE A — Admin Unfold (1 fichier : Administration/admin_tenant.py)

1. Enregistrer les modeles dans Unfold :

   POSProductAdmin (herite ProductAdmin) :
   - POSProductForm avec methode_caisse ChoiceField (10 choices)
   - get_queryset : filtre methode_caisse__isnull=False
   - fieldsets avec champs POS (name, methode_caisse, categorie_pos,
     couleurs, groupe_pos, fractionne, besoin_tag_id, icon_pos)
   - inlines = [PriceInline]

   CategorieProductAdmin :
   - list_display = name, icon, tva, poid_liste, cashless
   - search_fields = name

   PointDeVenteAdmin :
   - list_display = name, comportement, service_direct, hidden
   - filter_horizontal pour products et categories

   CartePrimaireAdmin :
   - list_display = carte, edit_mode, datetime
   - filter_horizontal pour points_de_vente

   Table + CategorieTable :
   - Admin minimal (list_display basique)
   - Pas prioritaire (mode restaurant = Phase 4)

2. Section menu Unfold : "Caisse" dans la sidebar
   Conditionner par module_caisse=True (meme pattern que "Adhesions", "Billetterie").
   Sous-items : POSProduct, CategorieProduct, PointDeVente

PARTIE B — Donnees de test (management command)

3. Creer laboutik/management/commands/create_test_pos_data.py
   Cree des donnees pour le tenant courant :
   - 2 CategorieProduct (Bar, Restauration)
   - 5 Product+Price :
     - Biere (methode_caisse=VT, prix=5.00 EUR)
     - Coca (methode_caisse=VT, prix=3.00 EUR)
     - Pizza (methode_caisse=VT, prix=12.00 EUR)
     - Cafe (methode_caisse=VT, prix=2.00 EUR)
     - Eau (methode_caisse=VT, prix=1.50 EUR)
   - 1 PointDeVente "Bar" (DIRECT, accepte tout)
   - 1 PointDeVente "Restaurant" (DIRECT, accepte_commandes=True)

   Si settings.TEST == True (env TEST=1), creer aussi :
   - 1 Detail (batch de cartes test, slug="test-pos-cards")
   - 1 CarteCashless + CartePrimaire (tag_id=DEMO_TAGID_CM, edit_mode=True, liee a tous les PV)
   - 2 CarteCashless client (DEMO_TAGID_CLIENT1, DEMO_TAGID_CLIENT2) — sans CartePrimaire,
     pour tester les paiements NFC en Phase 3

   Les tag_id viennent de settings (DEMO_TAGID_*), definis dans .env :
     DEMO_TAGID_CM='A49E8E2A'
     DEMO_TAGID_CLIENT1='52BE6543'
     DEMO_TAGID_CLIENT2='33BC1DAA'

   ⚠️ Prix sur Price.prix (DecimalField euros), PAS en centimes.
   ⚠️ Detail et CarteCashless sont en SHARED_APPS (schema public).
      Utiliser Client.objects.get(schema_name=...) pour la FK Detail.origine,
      pas connection.tenant (qui renvoie FakeTenant).

4. Lancer :
   docker exec lespass_django poetry run python manage.py check
   docker exec lespass_django poetry run python manage.py create_test_pos_data

⚠️ NE PAS modifier les vues ou les templates.
```

## Verification

- L'admin affiche POSProduct, CategorieProduct, PointDeVente dans le menu "Caisse"
- Section "Caisse" cachee quand module_caisse=False
- Les donnees de test sont creees (PointDeVente.objects.count() >= 2)
- POSProduct changelist affiche les produits avec methode_caisse non null
- Les proxy existants (TicketProduct, MembershipProduct) restent fonctionnels
- Si TEST=1 : CartePrimaire liee a tous les PV, 2 cartes client creees
- La commande est idempotente (relancer ne cree pas de doublons)

## Modele recommande

Sonnet
