# Stabilisation tests E2E panier (2026-04-19)

## Ce qui a ete fait

Refonte de la suite E2E panier pour atteindre 5 tests fiables qui passent en
moins de 25 secondes, avec fondations reutilisables pour les futurs E2E :

1. **Endpoint `force_login_for_e2e`** (test-only, triple-gate DEBUG + token +
   header). Remplace le flow UI de connexion 6 etapes par 1 POST + 1 injection
   de cookie. ~100ms au lieu de ~5s par login.
2. **Seed `_seed_e2e_fixtures`** dans `demo_data_v2` : cree 4 fixtures stables
   dans le tenant lespass (event gratuit, event payant, adhesion gratuite,
   event gated par l'adhesion). Prefixe "E2E Test —" pour identification admin.
3. **Fixture `e2e_slugs`** session-scoped qui lit les slugs/UUIDs des fixtures
   E2E via `django_db_blocker.unblock()` — compatible avec les E2E (pas de
   rollback DB, indispensable contre un serveur Django reel derriere Traefik).
4. **2 tests casses reecrits** + **2 nouveaux tests Stripe** (checkout direct
   via `/panier/` et chainage `booking-add-and-pay` depuis page event).

### Modifications

| Fichier | Changement |
|---|---|
| `.env` | +`E2E_TEST_TOKEN` (secret dev, gate l'endpoint force_login) |
| `AuthBillet/views_test_only.py` | Nouveau — endpoint force_login_for_e2e |
| `AuthBillet/urls.py` | +URL `/__test_only__/force_login/` conditionnelle `if settings.DEBUG` |
| `Administration/management/commands/demo_data_v2.py` | +methode `_seed_e2e_fixtures` + appel section 4b |
| `tests/e2e/conftest.py` | Refonte `login_as` (HTTP+cookie) + fixture `e2e_slugs` + fixture `e2e_test_token` |
| `tests/e2e/test_panier_flow.py` | 2 tests reecrits + 2 tests ajoutes, suppression fixture `event_gratuit_publie` |
| `tests/TESTS_README.md` | +section "Variables d'environnement E2E" |
| `tests/PIEGES.md` | +pieges 9.101 a 9.106 |
| `CHANGELOG.md` | Entree "Stabilisation tests E2E panier" |

## Tests a realiser

### Test 1 : Lancement complet E2E panier

```bash
# Si .env a ete modifie apres le dernier `docker compose up`, passer les
# variables explicitement :
docker exec \
  -e ADMIN_EMAIL=admin@admin.com \
  -e E2E_TEST_TOKEN='e2e-dev-only-pGk3xVqLz8R4nFw2' \
  lespass_django poetry run pytest tests/e2e/test_panier_flow.py -v
```

**Resultat attendu** : `5 passed` en ~20-25s.

```
tests/e2e/test_panier_flow.py::TestPanierFlow::test_ajout_au_panier_et_checkout_gratuit PASSED
tests/e2e/test_panier_flow.py::TestPanierFlow::test_adhesion_dans_panier_debloque_tarif_gate PASSED
tests/e2e/test_panier_flow.py::TestPanierFlow::test_checkout_redirects_to_stripe PASSED
tests/e2e/test_panier_flow.py::TestPanierFlow::test_add_to_cart_and_pay_chains_checkout PASSED
tests/e2e/test_panier_flow.py::TestPanierMembershipFlow::test_admin_ajoute_adhesion_au_panier_puis_vide PASSED
```

### Test 2 : Securite de l'endpoint force_login

```bash
# 1. Sans header → 404 silencieux
curl -ks -o - -w "\nHTTP %{http_code}\n" -X POST \
  -H "Host: lespass.tibillet.localhost" \
  --data "email=admin@admin.com" \
  https://172.17.0.1/api/user/__test_only__/force_login/
# Attendu : {"detail": "Not Found"} HTTP 404

# 2. Avec token invalide → 404 silencieux
curl -ks -o - -w "\nHTTP %{http_code}\n" -X POST \
  -H "X-Test-Token: wrong" -H "Host: lespass.tibillet.localhost" \
  --data "email=admin@admin.com" \
  https://172.17.0.1/api/user/__test_only__/force_login/
# Attendu : {"detail": "Not Found"} HTTP 404

# 3. Avec token valide → sessionid
curl -ks -o - -w "\nHTTP %{http_code}\n" -X POST \
  -H "X-Test-Token: e2e-dev-only-pGk3xVqLz8R4nFw2" \
  -H "Host: lespass.tibillet.localhost" \
  --data "email=admin@admin.com" \
  https://172.17.0.1/api/user/__test_only__/force_login/
# Attendu : {"sessionid": "...", "session_cookie_name": "sessionid", "user_email": "admin@admin.com"} HTTP 200
```

### Test 3 : Seed idempotent (demo_data_v2)

```bash
# Lancer le seed une seconde fois — aucun doublon, aucun crash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from Administration.management.commands.demo_data_v2 import Command
from Customers.models import Client
Command()._seed_e2e_fixtures(list(Client.objects.all()))
"
# Attendu : log "[E2E] OK : events=..., ..." sans erreur
```

### Test 4 : Verification des donnees seedees

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py \
  tenant_command shell -s lespass -c "
from BaseBillet.models import Event, Product, Price
print('Events E2E:', Event.objects.filter(name__startswith='E2E Test').count())
print('Products E2E:', Product.objects.filter(name__startswith='E2E Test').count())
print('Prices gated:', Price.objects.filter(
    product__name='E2E Test — Billet gated'
).first().adhesions_obligatoires.count())
"
# Attendu : Events E2E: 3, Products E2E: 4, Prices gated: 1
```

### Test 5 : Admin voit les fixtures E2E (identification)

1. Aller sur `https://lespass.tibillet.localhost/admin/BaseBillet/event/`
2. Verifier qu'il y a 3 events avec le prefixe "E2E Test —" visibles
3. Verifier que leur description courte contient "Fixture E2E — ne pas supprimer"

## Compatibilite

- **Pas de migration** — juste du code additif et 1 fichier .env.
- **Endpoint force_login** : invisible en prod (url pattern sous `if settings.DEBUG`).
- **Seed E2E** : lance a chaque `demo_data_v2` (donc a chaque `flush.sh` en dev).
  Idempotent via `get_or_create` — aucun doublon au 2e run.
- **Fixtures de test existantes** : les tests autres que `test_panier_flow.py`
  continuent d'utiliser `login_as_admin` qui a garde la meme signature. Le
  changement est transparent, juste plus rapide.

## Points d'attention

- La variable `E2E_TEST_TOKEN` doit etre presente **a la fois** dans le process
  pytest ET dans le process runserver. Sinon : pytest `pytest.fail` explicite,
  ou endpoint 404 silencieux. Cf. PIEGES 9.101.
- Au prochain `docker compose up` ou restart container, `.env` sera picked up
  automatiquement et plus besoin de passer `-e` au `docker exec`.
- Si un jour les fixtures "E2E Test —" sont supprimees accidentellement par
  l'admin, la fixture `e2e_slugs` fail explicitement avec le message :
  "Relancer le seed : docker exec lespass_django poetry run python manage.py demo_data_v2".
