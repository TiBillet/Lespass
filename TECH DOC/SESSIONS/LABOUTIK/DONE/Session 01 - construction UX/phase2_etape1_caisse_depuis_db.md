# Phase 2, Etape 1 — Caisse depuis la DB (carte primaire + PV)

## Prompt

```
On travaille sur la Phase 2 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 12 + section 15). Etape 1 sur 2 : les vues de navigation.

Les modeles existent (Phase 0 + Phase 1 faites). Lis le plan section 12
et les vues actuelles dans laboutik/views.py.

Contexte :
- CaisseViewSet a 3 actions : list(), carte_primaire(), point_de_vente()
- Actuellement tout est mocke (utils/mockData.py)
- On remplace les appels mock par des queries ORM
- Pattern FALC (skill /django-htmx-readable) : explicite, verbeux
- Validation des POST : utiliser des serializers.Serializer (DRF),
  PAS request.POST brut (regle stack-ccc)

Tache (1 fichier principal : laboutik/views.py) :

1. Creer un serializer pour carte_primaire (dans laboutik/serializers.py) :
   - CartePrimaireSerializer(serializers.Serializer)
   - tag_id = serializers.CharField(max_length=20)
   - Validation : strip, pas vide

2. carte_primaire() (POST) — remplacer le mock par :
   a) Valider avec CartePrimaireSerializer
   b) CarteCashless.objects.get(tag_id=tag_id) — la carte NFC
   c) CartePrimaire.objects.get(carte=carte_cashless) — est-ce une carte maitresse ?
   d) carte_primaire.points_de_vente.all() — PV autorises
   e) Si 1 seul PV → redirect. Si plusieurs → choix.
   f) Si pas CartePrimaire → erreur (pas autorise)

3. point_de_vente() (GET) — remplacer le mock par :
   a) PointDeVente.objects.prefetch_related('categories', 'products').get(uuid=uuid_pv)
   b) Construire le stateJson depuis Configuration.get_solo() + donnees PV reelles
   c) Tables si accepte_commandes=True : Table.objects.filter(archive=False)

4. Le `state` global mutable (dict en haut du fichier) doit etre remplace par
   une fonction _construire_state(request, point_de_vente) appelee a chaque requete.

5. Nettoyer : supprimer les imports de mockData dans les fonctions modifiees.
   NE PAS supprimer mockData.py (encore utilise par les vues de paiement).

6. Adapter les templates SI les noms de variables du contexte changent
   (verifier les templates views/ask_primary_card.html et views/pv_route.html).

7. Ajouter data-testid sur les elements dynamiques modifies :
   - data-testid="caisse-carte-primaire-form"
   - data-testid="caisse-pv-list"
   - data-testid="caisse-pv-interface"

8. Ajouter aria-live="polite" sur les zones remplacees par HTMX
   (feedback carte, liste PV).

Verification :
docker exec lespass_django poetry run python manage.py check
Lancer le serveur, naviguer vers /laboutik/caisse/ avec une API key valide.

⚠️ NE PAS toucher aux vues de paiement (PaiementViewSet) — c'est l'etape 2.
⚠️ Garder la compatibilite avec HasLaBoutikAccess (permission existante).
⚠️ Les noms de variables dans le contexte template peuvent changer — verifier
   que le JS (addition.js, articles.js) recoit toujours les bonnes donnees.
```

## Tests

### pytest — tests/pytest/test_caisse_navigation.py

```python
# Tests a ecrire dans cette session :
# 1. test_carte_primaire_valide — POST tag_id connu → redirect vers le PV
# 2. test_carte_primaire_inconnue — tag_id inconnu → erreur (404 ou message)
# 3. test_carte_non_primaire — carte existante mais pas CartePrimaire → 403
# 4. test_point_de_vente_charge_vrais_produits — GET PV → produits depuis DB (pas mock)
# 5. test_sans_api_key_403 — requete sans auth → 403
# 6. test_serializer_tag_id_vide — POST tag_id="" → erreur validation
```

Lancer : `docker exec lespass_django poetry run pytest tests/pytest/test_caisse_navigation.py -v`

### Playwright — tests/playwright/tests/32-laboutik-caisse-db.spec.ts

```
Scenario :
1. Login admin
2. Activer module_caisse (+ module_monnaie_locale force)
3. Lancer create_test_pos_data (donnees de test)
4. Naviguer vers /laboutik/caisse/
5. Scanner une carte primaire (simuler POST avec tag_id de test)
6. Verifier que l'interface PV affiche les vrais produits (noms depuis DB)
7. Verifier data-testid present sur les elements cles
```

Lancer : `yarn playwright test --project=chromium --headed --workers=1 tests/32-laboutik-caisse-db.spec.ts`

### Verification manuelle

- GET /laboutik/caisse/ → page d'attente carte primaire (200)
- POST carte_primaire avec un tag_id valide → redirect vers le PV
- GET point_de_vente → interface POS avec les vrais produits depuis la DB
- Sans API key → 403

## Checklist fin d'etape

- [ ] `manage.py check` passe
- [ ] Pas de traceback dans les logs serveur
- [ ] Tests pytest verts
- [ ] Test Playwright vert
- [ ] i18n : `docker exec lespass_django poetry run django-admin makemessages -l fr -l en`
- [ ] Mettre a jour CHANGELOG.md
- [ ] Creer `A TESTER et DOCUMENTER/phase2-etape1-caisse-db.md`

## Modele recommande

Sonnet
