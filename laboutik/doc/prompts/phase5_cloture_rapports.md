# Phase 5 — Cloture de caisse et rapports

## Prompt

```
On travaille sur la Phase 5 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 10.2 + section 15). Cloture et rapports.

Phases 0-4 faites. Le POS fonctionne (service direct + commandes).

Lis le plan section 10.2 (ClotureCaisse) et memory/tests_validation.md Phase 5.

Tache :

PARTIE A — Modele (laboutik/models.py)

1. ClotureCaisse :
   - uuid PK, point_de_vente FK, responsable FK TibilletUser
   - datetime_ouverture, datetime_cloture (auto_now_add)
   - total_especes, total_carte_bancaire, total_cashless, total_general
     → tous IntegerField (centimes)
   - nombre_transactions IntegerField
   - rapport_json JSONField
   - Migration

PARTIE B — Vue de cloture (laboutik/views.py)

2. Ajouter une action `cloturer()` sur CaisseViewSet :
   - Calculer les totaux depuis LigneArticle :
     - Especes : LigneArticle.objects.filter(payment_method='CA', ...)
     - CB : payment_method='CC'
     - Cashless : payment_method='NFC'
   - Filtrer par datetime >= datetime_ouverture du service
   - Creer ClotureCaisse avec les totaux
   - Fermer toutes les tables ouvertes du PV
   - Retourner le rapport (template)

PARTIE C — Taches Celery (optionnel, a discuter)

3. Si pertinent, ajouter une tache Celery pour :
   - Cloture automatique a une heure configuree
   - Rapport quotidien par email
   ⚠️ Demander au mainteneur avant de creer des taches Celery.

PARTIE D — Admin + tests

4. Admin Unfold : ClotureCaisse (lecture seule)
5. Test : creer 3 paiements (espece, CB, NFC), cloturer, verifier les totaux

⚠️ Les totaux sont en centimes (int), pas en euros.
```

## Verification

- ClotureCaisse cree avec les bons totaux
- Les totaux matchent les LigneArticle de la periode
- Test de memory/tests_validation.md Phase 5 passe

## Modele recommande

Sonnet
