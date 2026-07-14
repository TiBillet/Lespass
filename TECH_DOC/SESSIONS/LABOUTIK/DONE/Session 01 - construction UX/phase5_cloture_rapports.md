# Phase 5 — Cloture de caisse et rapports

## Prompt

```
On travaille sur la Phase 5 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 10.2 + section 15). Cloture et rapports.

Phases 0-4 faites. Le POS fonctionne (service direct + commandes).

Lis le plan section 10.2 (ClotureCaisse) et laboutik/models.py.

Tache :

PARTIE A — Modele (laboutik/models.py)

1. ClotureCaisse :
   - uuid PK
   - point_de_vente FK PointDeVente (PROTECT)
   - responsable FK TibilletUser (SET_NULL, nullable)
   - datetime_ouverture DateTimeField — debut du service
   - datetime_cloture DateTimeField (auto_now_add) — moment de la cloture
   - total_especes IntegerField (centimes, default=0)
   - total_carte_bancaire IntegerField (centimes, default=0)
   - total_cashless IntegerField (centimes, default=0)
   - total_general IntegerField (centimes, default=0)
   - nombre_transactions IntegerField (default=0)
   - rapport_json JSONField (default=dict) — detail par categorie, par produit, etc.
   - help_text avec _(), commentaires bilingues

2. Migration :
   docker exec lespass_django poetry run python manage.py makemigrations laboutik
   docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing

PARTIE B — Serializer (laboutik/serializers.py)

3. ClotureSerializer :
   - datetime_ouverture (DateTimeField) — le debut du service a cloturer

PARTIE C — Vue de cloture (laboutik/views.py)

4. Ajouter une action `cloturer()` sur CaisseViewSet :
   - Valider avec ClotureSerializer
   - Calculer les totaux depuis LigneArticle :
     - Especes : LigneArticle.objects.filter(
         sale_origin='LB', payment_method='CA',
         datetime__gte=datetime_ouverture
       ).aggregate(total=Sum('amount'))
     - CB : payment_method='CC'
     - Cashless : payment_method='NFC'
   - Compter le nombre de transactions (LigneArticle.count)
   - Construire le rapport_json :
     {
       "par_categorie": {...},
       "par_produit": {...},
       "par_moyen_paiement": {"especes": X, "cb": Y, "nfc": Z},
       "commandes": {"total": N, "annulees": M}
     }
   - Creer ClotureCaisse avec les totaux
   - Fermer toutes les tables ouvertes du PV (statut → L)
   - Fermer toutes les commandes OPEN du PV (statut → CANCEL ou PAID selon)
   - Retourner le rapport (template partial)

5. data-testid :
   - data-testid="cloture-btn"
   - data-testid="cloture-rapport"
   - data-testid="cloture-total-general"
   - data-testid="cloture-total-especes"
   - data-testid="cloture-total-cb"
   - data-testid="cloture-total-nfc"

PARTIE D — Taches Celery (OPTIONNEL — demander au mainteneur)

6. Si le mainteneur valide, ajouter dans laboutik/tasks.py :
   - cloture_automatique() : a une heure configuree, cloturer tous les PV
   - rapport_quotidien() : envoyer un email avec le rapport du jour
   ⚠️ NE PAS creer de taches Celery sans validation du mainteneur.
   ⚠️ Si pas valide, laisser un commentaire TODO dans le code.

PARTIE E — Admin

7. Admin Unfold (Administration/admin_tenant.py) :
   - ClotureCaisse : list_display = point_de_vente, responsable, datetime_cloture,
     total_general, nombre_transactions
   - Lecture seule (pas de create/edit)
   - Section sidebar "Caisse" : ajouter "Clotures"

⚠️ Les totaux sont en centimes (int), pas en euros.
⚠️ Verifier le champ amount de LigneArticle — est-il en centimes ou euros ?
   LIRE le modele AVANT de faire les aggregations.
```

## Tests

### pytest — tests/pytest/test_cloture_caisse.py

```python
# Tests a ecrire :
#
# 1. test_cloture_totaux_corrects
#    Setup : creer 3 LigneArticle (1 espece 500c, 1 CB 1000c, 1 NFC 2000c)
#    Action : cloturer()
#    Verify : total_especes=500, total_cb=1000, total_nfc=2000, total_general=3500
#
# 2. test_cloture_nombre_transactions
#    Verify : nombre_transactions == 3
#
# 3. test_cloture_ferme_tables
#    Setup : 2 tables OCCUPEE
#    Action : cloturer()
#    Verify : les 2 tables passent a LIBRE
#
# 4. test_cloture_rapport_json_complet
#    Verify : rapport_json contient par_categorie, par_produit, par_moyen_paiement
#
# 5. test_cloture_filtre_par_datetime
#    Setup : LigneArticle hier + LigneArticle aujourd'hui
#    Action : cloturer(datetime_ouverture=aujourd'hui)
#    Verify : seules les LigneArticle d'aujourd'hui sont comptees
#
# 6. test_cloture_pv_specifique
#    Setup : LigneArticle de 2 PV differents
#    Action : cloturer PV1
#    Verify : seules les LigneArticle du PV1 comptees
#
# 7. test_double_cloture_meme_periode
#    Action : cloturer 2 fois la meme periode
#    Verify : 2 ClotureCaisse creees (pas de blocage, c'est un rapport)
```

Lancer : `docker exec lespass_django poetry run pytest tests/pytest/test_cloture_caisse.py -v`

### Playwright — tests/playwright/tests/35-laboutik-cloture.spec.ts

```
Scenario :
1. Login admin, activer module_caisse
2. Creer 3 ventes via l'interface POS (1 espece, 1 CB, 1 NFC si dispo)
3. Aller dans la vue cloture
4. Cliquer "Cloturer"
5. Verifier le rapport affiche (totaux par moyen de paiement)
6. Verifier en DB : ClotureCaisse creee avec les bons montants
7. Verifier : tables liberees
```

Lancer : `yarn playwright test --project=chromium --headed --workers=1 tests/35-laboutik-cloture.spec.ts`

### Verification manuelle

- ClotureCaisse cree avec les bons totaux (en centimes)
- Les totaux matchent les LigneArticle de la periode
- Les tables sont liberees
- Le rapport JSON est exploitable

## Checklist fin d'etape

- [ ] `manage.py check` passe
- [ ] Migrations creees et appliquees
- [ ] 7 tests pytest verts
- [ ] Test Playwright vert
- [ ] Admin : ClotureCaisse visible en lecture seule
- [ ] Les totaux sont coherents (verifier manuellement en shell)
- [ ] i18n : makemessages + compilemessages
- [ ] Mettre a jour CHANGELOG.md
- [ ] Creer `A TESTER et DOCUMENTER/phase5-cloture-rapports.md`

## Modele recommande

Sonnet
