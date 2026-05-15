# Onboard — Prompt prochaine session

Prompt prêt-à-coller pour Claude Code quand on reprend le travail sur le wizard d'onboard.

---

## Contexte rapide

Le wizard d'onboarding TiBillet est **fonctionnel end-to-end** sur la branche `main-wizard` (commit `bf062a6a`). 22 tasks sur 24 du plan original sont faites. Tests : **52 passing / 2 skipped**.

**Ce qui reste** (cf. `04-followups.md` pour le détail) :
- Bloquants prod : F1 Fedow exception, F2 Playwright E2E, F3 CHANGELOG + i18n.
- Should-fix : captcha, rate-limit identity, heartbeat Celery, reprise brouillon.
- Must-have d'app moderne : Sentry, analytics, autosave, geocoder amélioré, accessibility audit.

---

## Prompt — copier-coller au début de la session

```
On reprend le travail sur le wizard d'onboard TiBillet.

## Contexte
- Branche : `main-wizard`. Dernier commit : `bf062a6a` (wizard complet end-to-end).
- 22 tasks sur 24 du plan original sont faites. Tests : 52 pytest passing / 2 skipped.
- Pattern de tests : pytest + pytest-django + `django_db_setup = pass` (DB dev partagée).
- Skill djc : compliance vérifiée sur tout le code livré.

## Skills obligatoires à charger en début de session
/using-superpowers
/djc

**Compliance TOTALE au skill djc requise** : ViewSet explicite (PAS de
ModelViewSet), Serializer DRF (PAS de Django Forms), HTMX server-side
rendering uniquement, commentaires bilingues FR/EN avec docstring
`LOCALISATION:` en début de fichier, `data-testid="<module>-<element>-<context>"`
sur tout élément interactif, `aria-live` sur zones HTMX dynamiques, cache
keys avec tenant_id, i18n (makemessages/compilemessages) à la fin.

## Documentation de référence
- Récap session précédente : `TECH_DOC/SESSIONS/ONBOARD/03-session-recap.md`
- Spec design : `TECH_DOC/SESSIONS/ONBOARD/01-design-spec.md`
- Plan d'implémentation : `TECH_DOC/SESSIONS/ONBOARD/02-implementation-plan.md`
- **Liste des follow-ups** : `TECH_DOC/SESSIONS/ONBOARD/04-followups.md` ← **LIRE EN ENTIER**

## Travail à faire cette session

Choisir une de ces options (à confirmer avec moi dès le départ) :

**Option A — Bloquants prod (F1+F2+F3)**
Régler en priorité ce qui empêche d'ouvrir le wizard au public :
1. F1 : capturer l'exception Fedow non configuré dans `create_tenant_from_draft`
   ou pre-configurer FedowConfig dans `create_empty_tenant`.
2. F2 : écrire les 3 tests Playwright E2E (golden / invitation / resume).
3. F3 : générer le CHANGELOG.md + `A TESTER et DOCUMENTER/onboard-wizard.md`
   + `makemessages -l fr -l en` + `compilemessages`.

**Option B — Sécurité / abuse (S1+S6+S7)**
Hardening prod :
1. S1 : ajouter un heartbeat Celery worker (banner dev si absent).
2. S6 : captcha sur identity POST pour anonymous users.
3. S7 : DRF AnonRateThrottle sur identity POST (5/min/IP via `get_client_ip`).

**Option C — UX brouillon (S4+S5)**
Améliorer l'expérience continue :
1. S4 : reprise du brouillon depuis identity (page intercalaire "Brouillon trouvé").
2. S5 : preview du tenant avant launch.

**Option D — Observabilité (M3)**
Outillage prod :
1. Sentry integration (capture exceptions Celery + 502 launch/status + erreurs Nominatim).
2. Audit log table dédiée.
3. Metrics Prometheus si infra ready.

**Option E — Refactor dette technique (N1+N2+N3)**
Cleanup :
1. N1 : décorateur `@require_confirmed_draft` pour factoriser le pattern dupliqué 6×.
2. N2 : refactor `events_draft` JSONField → modèle `OnboardEventDraft`.
3. N3 : templatetag `is_step_done` pour simplifier `progress_panel.html`.

## Méthode

1. **Charger les skills obligatoires** d'abord (`/using-superpowers`, `/djc`).
2. **Lire `03-session-recap.md` + `04-followups.md`** pour reprendre le contexte.
3. **Me proposer le choix d'option** (A/B/C/D/E) ou un mix raisonné. Attendre ma confirmation.
4. **Pour chaque tâche** :
   - Plan court (3-5 bullets) avant de coder.
   - Coder en suivant djc compliance stricte.
   - Tests pytest pour chaque nouvelle logique.
   - `manage.py check` + `pytest onboard/tests/` après chaque chunk.
   - Pas plus de 3 fichiers modifiés avant un test.
5. **Vérification finale** :
   - `manage.py check` ✅
   - `pytest onboard/tests/` ✅ (cible : 52+ passing)
   - Chrome browser vérification visuelle des changements UI.
6. **Bilan final** :
   - Update `03-session-recap.md` (nouvelle section "Session du <date>").
   - Update `04-followups.md` (marquer les items réglés, ajouter les nouveaux).
   - Message de commit suggéré au format conventional commits.

## Règle git ABSOLUE (à mettre en PREMIÈRE LIGNE de chaque prompt de subagent)

NE JAMAIS lancer de commande git (commit, push, add, checkout, stash,
reset, restore, clean, rebase, branch, worktree, tag). Le mainteneur
fait TOUS les commits lui-même. Si une tâche dit "commit", OUTPUTE le
message de commit suggéré dans le rapport final et STOP.

## Contexte technique projet

- Branche : `main-wizard` (NE JAMAIS changer).
- Lespass = Django multi-tenant (django-tenants), code dans `/DjangoFiles`
  dans le container Docker `lespass_django`.
- Manage commands : `docker exec lespass_django poetry run python /DjangoFiles/manage.py <cmd>`.
- Pytest : `docker exec lespass_django poetry run pytest /DjangoFiles/onboard/tests/ -v`.
- Migrations multi-tenant : `migrate_schemas --executor=multiprocessing`.
- Serveur dev : tenu par le mainteneur dans byobu sur port 8002 — ne PAS
  lancer `runserver_plus` toi-même.
- Convention specs : `TECH_DOC/SESSIONS/<TOPIC>/`.
- Admin test user : `admin@admin.com`.
- DEBUG=1 en dev : le wizard bypass la vérification OTP côté `verify`.

## Pièges à éviter (vécus en session précédente)

1. **bcrypt absent** sur main-wizard → on hash via `django.contrib.auth.hashers`
   (PBKDF2). Pas besoin d'installer bcrypt.
2. **`fedow_core.Federation` absent** → la FK `OnboardInvitation.federation`
   est commentée. À décommenter QUE quand fedow_core mergera.
3. **Tile provider OpenStreetMap renvoie 403** → utiliser CartoCDN
   `rastertiles/voyager/{z}/{x}/{y}.png` (le `voyager/` direct retourne 404).
4. **`{# ... #}` Django multi-ligne NE FONCTIONNE PAS** → utiliser
   `{% comment %}...{% endcomment %}`.
5. **`request.data.dict()` non portable DRF** → whitelist explicite par clé.
6. **Tests cleanup_clients** : NE PAS utiliser `Client.objects.filter(...).delete()`
   car la M2M reverse `BaseBillet_configuration_federated_with` cross-schema
   crashe. Utiliser raw SQL (cf. `onboard/tests/conftest.py::cleanup_clients`).
7. **`select_for_update` ne couvre PAS `wc.create_tenant()`** (DDL non
   rollback-able). Utiliser un claim Redis distribué via `cache.add()`.
8. **`@override_settings(DEBUG=False)`** obligatoire sur les tests qui
   testent la vraie vérification OTP (sinon DEBUG bypass kick in).
9. **HTMX swap target sur form POST** : le navigateur n'envoie pas les
   valeurs du form parent à un `hx-get` enfant. Utiliser `hx-include`.
10. **CSS Tailwind custom classes invisibles dans Unfold admin** : utiliser
    inline styles ou CSS variables.

## Démarrage

Lis les fichiers de référence ci-dessus, propose l'option à attaquer en
priorité, j'arbitre, puis on enchaîne.
```

---

## Annexes (pour Claude Code, hors prompt)

### Liste des sub-agents utiles
- **general-purpose** : pour les modifs Python multi-fichiers (vues + serializers + tests).
- **Explore** : pour les recherches code (`grep`, `rg`, file pattern matching).
- **Plan** : pour designer un refactor lourd avant code (ex: M2 modèle OnboardEventDraft).

### Sub-agents à éviter pour ce projet
- **Pas de subagent qui modifie git directement** (règle CLAUDE.md du projet).
- **Pas de subagent qui lance Celery worker** (mainteneur gère byobu).

### Commandes utiles
```bash
# Vérification rapide
docker exec lespass_django poetry run python /DjangoFiles/manage.py check

# Tests onboard (pattern V2, DB dev partagée, ~3min)
docker exec lespass_django poetry run pytest /DjangoFiles/onboard/tests/ -v

# Test ciblé
docker exec lespass_django poetry run pytest /DjangoFiles/onboard/tests/test_step_verify.py::test_verify_debug_bypass_accepts_any_code -v

# i18n workflow (Task 24)
docker exec lespass_django poetry run django-admin makemessages -l fr -l en
# Éditer locale/fr/LC_MESSAGES/django.po + locale/en/LC_MESSAGES/django.po
docker exec lespass_django poetry run django-admin compilemessages

# Pool tenant (avant tester Launch en dev)
docker exec lespass_django poetry run python /DjangoFiles/manage.py create_empty_tenant --count 3

# Worker Celery (avant tester création tenant async)
docker exec lespass_django poetry run celery -A TiBillet worker -l info

# Nettoyage WC de test
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import schema_context
from MetaBillet.models import WaitingConfiguration
with schema_context('meta'):
    WaitingConfiguration.objects.filter(email__contains='test').delete()
"
```
