# Session 04 — Refonte typage : l'article détermine le comportement, pas le PV

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django + HTMX).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

### Pourquoi cette refonte

Actuellement, `PointDeVente.comportement` détermine ce qu'on vend :
- ADHESION ('A') → charge dynamiquement les produits adhésion
- CASHLESS ('C') → aucune logique spécifique dans le code
- KIOSK ('K') → template différent (légitime)
- DIRECT ('D') → standard

Le problème : on ne peut pas créer un PV mixte (goodies + recharges + adhésions + billets).
La vraie logique est déjà pilotée par l'article (`Product.methode_caisse` et `categorie_article`),
pas par le PV. Le code d'identification adhésion, la garde NFC recharges, etc. détectent
le type d'article dans le panier, pas le type du PV.

### Décision

`comportement` ne garde que DIRECT ('D') et KIOSK ('K').
ADHESION ('A') et CASHLESS ('C') sont supprimés.
Les produits adhésion rejoignent le M2M `products` du PV.

## TÂCHE 1 — Lire le code existant

Lis ces fichiers pour comprendre ce qui utilise `comportement` :

1. `laboutik/models.py` : `PointDeVente.COMPORTEMENT_CHOICES`
2. `laboutik/views.py` : cherche `comportement` — note chaque occurrence
3. `laboutik/views.py` : cherche `if.*comportement.*ADHESION` — c'est ce qu'on supprime
4. `laboutik/management/commands/create_test_pos_data.py` : le PV "Adhésions"
5. `tests/playwright/tests/laboutik/44-laboutik-adhesion-identification.spec.ts` : les fixtures

## TÂCHE 2 — Migration

Crée `laboutik/migrations/0003_refonte_typage.py` :

1. **Data migration** : tous les PV avec `comportement='A'` ou `'C'` passent à `'D'`
   ```python
   def forwards(apps, schema_editor):
       PointDeVente = apps.get_model('laboutik', 'PointDeVente')
       PointDeVente.objects.filter(comportement__in=['A', 'C']).update(comportement='D')
   ```

2. **AlterField** : réduire les choix à `[('D', 'Direct'), ('K', 'Kiosk')]`

3. Applique la migration :
   ```bash
   docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
   ```

## TÂCHE 3 — Supprimer le code conditionnel ADHESION dans views.py

1. Dans `_construire_donnees_articles()` (~ligne 185-200) : supprimer le bloc
   `if point_de_vente_instance.comportement == PointDeVente.ADHESION:` qui charge
   dynamiquement les produits adhésion. Garder uniquement le chargement depuis le M2M.

2. Dans `_extraire_articles_du_panier()` (~ligne 1088-1100) : même chose,
   supprimer le bloc conditionnel ADHESION.

3. Supprimer les constantes `ADHESION = 'A'` et `CASHLESS = 'C'` du modèle
   (ne pas casser le code qui référence `PointDeVente.DIRECT` ou `PointDeVente.KIOSK`).

4. Vérifier qu'aucun autre fichier ne référence les anciens types :
   ```bash
   grep -rn "ADHESION\|CASHLESS\|comportement.*'A'\|comportement.*'C'" laboutik/ --include="*.py"
   ```

## TÂCHE 4 — Adapter create_test_pos_data

Le PV "Adhésions" passe de `comportement=ADHESION` à `comportement=DIRECT`.
Les produits adhésion sont ajoutés au M2M `products` :

```python
pdv_adhesion, _ = PointDeVente.objects.update_or_create(
    name="Adhesions",
    defaults={"comportement": PointDeVente.DIRECT, "service_direct": True, ...},
)
produits_adhesion = Product.objects.filter(categorie_article=Product.ADHESION, publish=True)
pdv_adhesion.products.add(*produits_adhesion)
```

Lancer le management command pour recréer les données :
```bash
docker exec lespass_django poetry run python manage.py create_test_pos_data
```

## TÂCHE 5 — Adapter les tests Playwright

Dans `44-laboutik-adhesion-identification.spec.ts`, les fixtures créent probablement
un PV avec `comportement: 'A'`. Adapter pour `comportement: 'D'` et vérifier que
les produits adhésion sont dans le M2M du PV.

Si le test utilise l'API pour créer le PV, adapter les données envoyées.
Si le test utilise un PV existant (créé par `create_test_pos_data`), c'est déjà OK
(la Tâche 4 corrige les données).

## VÉRIFICATION

### Check Django

```bash
docker exec lespass_django poetry run python manage.py check
```

Doit afficher 0 issues.

### Tests unitaires

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pos_models.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_caisse_navigation.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py -v
```

### Tests E2E

```bash
cd /home/jonas/TiBillet/dev/Lespass/tests/playwright

# LE test le plus impacté (adhésion)
npx playwright test tests/laboutik/44-laboutik-adhesion-identification.spec.ts

# Tous les tests laboutik
npx playwright test tests/laboutik/ --reporter=list
```

### Critère de succès

- [ ] Migration 0003 appliquée sans erreur
- [ ] `manage.py check` : 0 issues
- [ ] Plus de `comportement='A'` ni `'C'` dans la DB
- [ ] Plus de code `if comportement == ADHESION` dans views.py
- [ ] `create_test_pos_data` crée le PV adhésion avec comportement='D' + M2M products
- [ ] TOUS les tests pytest passent
- [ ] TOUS les tests Playwright passent (y compris 44-adhesion)
