# Phase 4 — Mode restaurant (commandes + tables)

## Prompt

```
On travaille sur la Phase 4 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 10.2 + section 15). Mode restaurant.

Phases 0-3 faites. Le POS fonctionne en service direct (paiement immediat).
Maintenant on ajoute le mode "commandes par table".

Lis le plan section 10.2 (CommandeSauvegarde, ArticleCommandeSauvegarde)
et le front existant dans les templates laboutik/ pour comprendre le flux.

⚠️ AVANT DE CODER : lire les templates JS qui gerent les tables.
Le front JS pour les tables existe dans les templates laboutik.
Verifier QUEL evenement JS est emis quand on clique sur une table,
quels endpoints HTMX sont appeles, et quelles donnees sont attendues.
NE PAS casser le front existant.

Tache :

PARTIE A — Modeles (laboutik/models.py)

1. CommandeSauvegarde :
   - uuid PK, service (UUIDField), responsable FK TibilletUser
   - table FK Table nullable, datetime auto_now_add
   - statut (CharField choices: OPEN/SERVED/PAID/CANCEL)
   - commentaire (TextField, blank=True), archive BooleanField
   - help_text avec _(), commentaires bilingues

2. ArticleCommandeSauvegarde :
   - commande FK (CASCADE), product FK Product, price FK Price
   - qty SmallIntegerField (default=1)
   - reste_a_payer IntegerField (centimes, default=0)
   - reste_a_servir SmallIntegerField (default=0)
   - statut (CharField choices: EN_ATTENTE/EN_COURS/PRET/SERVI/ANNULE)

3. Migrations :
   docker exec lespass_django poetry run python manage.py makemigrations laboutik
   docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing

PARTIE B — Serializers (laboutik/serializers.py)

4. CommandeSerializer :
   - table_uuid (UUIDField, nullable)
   - articles (ListField of ArticleCommandeSerializer)
   - ArticleCommandeSerializer : product_uuid, price_uuid, qty

PARTIE C — Vues (laboutik/views.py)

5. Creer un CommandeViewSet (ou actions sur CaisseViewSet — choisir le plus FALC) :

   ouvrir_commande(request) :
   - Valider avec CommandeSerializer
   - Table.objects.get(uuid=table_uuid) → statut = 'O' (Occupee)
   - CommandeSauvegarde.objects.create(statut='OPEN', table=table, ...)
   - Pour chaque article : ArticleCommandeSauvegarde.objects.create(...)
   - Retourner partial avec la commande creee

   ajouter_articles(request, commande_uuid) :
   - Ajouter des ArticleCommandeSauvegarde a une commande existante (OPEN)

   marquer_servie(request, commande_uuid) :
   - CommandeSauvegarde.statut → SERVED
   - ArticleCommandeSauvegarde.statut → SERVI (ceux qui sont PRET)

   payer_commande(request, commande_uuid) :
   - Reutiliser les methodes de paiement existantes (_payer_par_*, Phase 2-3)
   - CommandeSauvegarde.statut → PAID
   - Table.statut → 'L' (Libre)

   annuler_commande(request, commande_uuid) :
   - CommandeSauvegarde.statut → CANCEL
   - Table.statut → 'L' si la table n'a pas d'autre commande OPEN

6. URLs : ajouter les routes dans laboutik/urls.py

7. data-testid :
   - data-testid="commande-table-{uuid}"
   - data-testid="commande-articles-list"
   - data-testid="commande-btn-payer"
   - data-testid="commande-btn-servir"

8. aria-live="polite" sur la zone de commande (mise a jour par HTMX)

PARTIE D — Admin + templates

9. Admin Unfold (Administration/admin_tenant.py) :
   - CommandeSauvegarde : list_display = uuid, table, statut, responsable, datetime
     lecture seule (historique), pas de create/edit depuis l'admin
   - ArticleCommandeSauvegarde : inline dans CommandeSauvegarde

10. Section sidebar "Caisse" : ajouter "Commandes" (conditionnel module_caisse)

11. Templates : adapter les partials HTMX si necessaire pour le flux commande.
    LIRE les templates existants d'abord !

⚠️ NE PAS modifier les vues de paiement existantes — les REUTILISER.
⚠️ Le front JS pour les tables existe deja — le LIRE avant de coder.
⚠️ Ne pas oublier transaction.atomic() pour payer_commande().
```

## Tests

### pytest — tests/pytest/test_commandes_tables.py

```python
# Tests a ecrire :
#
# 1. test_ouvrir_commande — Table L→O, CommandeSauvegarde creee, ArticleCommandeSauvegarde crees
# 2. test_ajouter_articles — ajouter 2 articles a une commande OPEN
# 3. test_ajouter_a_commande_fermee — commande PAID → erreur
# 4. test_marquer_servie — statuts ArticleCommandeSauvegarde → SERVI
# 5. test_payer_commande_especes — CommandeSauvegarde → PAID, Table → L, LigneArticle crees
# 6. test_payer_commande_nfc — idem avec paiement cashless
# 7. test_annuler_commande — CommandeSauvegarde → CANCEL, Table → L
# 8. test_table_occupee_si_autre_commande — annuler 1 commande mais table reste O si autre commande OPEN
# 9. test_serializer_validation — articles vide → erreur, qty <= 0 → erreur
```

Lancer : `docker exec lespass_django poetry run pytest tests/pytest/test_commandes_tables.py -v`

### Playwright — tests/playwright/tests/34-laboutik-commandes.spec.ts

```
Scenario complet :
1. Login admin, naviguer vers /laboutik/caisse/
2. Scanner carte primaire → PV "Restaurant" (accepte_commandes=True)
3. Cliquer sur une table → table passe en "Occupee"
4. Ajouter 3 articles a la commande
5. Voir le recap de la commande
6. Marquer comme "Servie"
7. Payer (especes)
8. Verifier : table liberee, commande PAID, LigneArticle crees
```

Lancer : `yarn playwright test --project=chromium --headed --workers=1 tests/34-laboutik-commandes.spec.ts`

### Verification manuelle

- Ouvrir une table, ajouter des articles, payer, table liberee
- CommandeSauvegarde et ArticleCommandeSauvegarde crees en DB
- Le paiement reutilise les methodes existantes (especes, CB, NFC)
- Admin : commandes visibles en lecture seule

## Checklist fin d'etape

- [ ] `manage.py check` passe
- [ ] Migrations creees et appliquees
- [ ] 9 tests pytest verts
- [ ] Test Playwright vert
- [ ] Admin : CommandeSauvegarde visible dans section "Caisse"
- [ ] Le front JS tables n'est pas casse (verifier visuellement)
- [ ] i18n : makemessages + compilemessages
- [ ] Mettre a jour CHANGELOG.md
- [ ] Creer `A TESTER et DOCUMENTER/phase4-commandes-tables.md`

## Modele recommande

Sonnet
