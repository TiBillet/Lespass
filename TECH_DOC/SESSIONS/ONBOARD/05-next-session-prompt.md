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
- Branche : `main-wizard`. Dernière session marathon (2026-05-15) : ~9h de polish + features manquantes.
- 22 tasks sur 24 du plan original + ~30 tasks supplémentaires de polish/UX/refacto faites.
- Tests : **56 pytest onboard passing / 2 skipped** + 6 widget form_field. Migrations : MetaBillet 0014 (otp_sent_at) + 0015 (events_creation_warnings).
- Widget GPS réutilisable créé dans `templates/widgets/` + `static/widgets/` (full client, leaflet-geosearch + reverse Nominatim direct browser).
- Step 03_place complètement refondue (search bar live + drag marqueur + auto-fill 4 champs adresse).
- Pattern de tests : pytest + pytest-django + `django_db_setup = pass` (DB dev partagée).
- Skill djc : compliance vérifiée sur tout le code livré.
- Pour pytest : `docker exec -e API_KEY=dummy lespass_django bash -c "cd /DjangoFiles && poetry run python -m pytest ..."`

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

**État** : il reste **~5-6h de travail** pour passer prod. Détail dans `04-followups.md` section "Synthèse priorités". 4 items bloquants restants (F1 Fedow validé non-bloquant après audit code 2026-05-15) :

| # | Item | Effort |
|---|---|---|
| **F2** | Tests Playwright E2E (8 scénarios listés dans followups F2) | ~3-4h |
| **F3** | i18n `makemessages -l fr -l en` + `compilemessages` (strings session étendue) | ~30 min |
| **S6** | Captcha anti-abuse sur identity POST (`django-simple-captcha`) | ~1h |
| **S7** | Rate-limit identity POST (`AnonRateThrottle 5/min/IP`) | ~30 min |

**Prérequis infra prod** : lancer `./manage.py root_fedow` une fois pour générer la `create_place_apikey` du tenant root. Sans ça, le `PlaceFedow.create_place()` (auto-déclenché à chaque nouveau tenant) plantera. Pas du code onboard, juste un setup ops.

Choisir une option ou un mix raisonné :

**Option PROD (recommandée) — F3+S6+S7+i18n**
Tout ce qui est bloquant prod sauf les Playwright E2E (qui peuvent attendre une session dédiée). ~2h total.
1. F3 : workflow i18n complet (vérifier qu'aucune string session étendue n'est en français hardcodé en EN).
2. S6 : captcha sur identity POST (`django-simple-captcha` déjà dans pyproject).
3. S7 : rate-limit identity POST (`AnonRateThrottle 5/min/IP` via `get_client_ip`).

**Option E2E — F2 seul**
Session dédiée Playwright, 8 scénarios listés dans followups F2.
1. Setup Playwright (`docker exec lespass_django poetry run playwright install chromium`).
2. Écrire les 8 scénarios un à un, vérifier visuellement chacun.
3. Documenter les pièges Playwright dans `tests/PIEGES.md` au fur et à mesure.

**Option UX — S4+S5**
Confort utilisateur post-prod :
1. S4 : reprise du brouillon depuis identity.
2. S5 : preview tenant avant launch.

**Option WIDGET 2e usage — Event admin + frontend ajout event**
Mettre à profit le widget GPS créé dans cette session pour 2 usages supplémentaires :
1. Intégrer dans `Event admin` Unfold.
2. Intégrer dans le sous-form "ajouter un event" frontend (step 5 wizard).

**Option OBSERVABILITÉ — M3**
1. Sentry integration (Celery exceptions + 502 launch/status).
2. Audit log table dédiée.

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

## Pièges à éviter (vécus en sessions précédentes)

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
11. **Conftest `tests/pytest/` exige `API_KEY=dummy`** env var.
    `docker exec -e API_KEY=dummy lespass_django bash -c "cd /DjangoFiles && poetry run python -m pytest ..."`
12. **`django.test.Client(HTTP_HOST=...)` triggers django-tenants middleware DB lookup**
    → "Database access not allowed" sur tests endpoint pure DRF.
    Utiliser `APIRequestFactory` + appel direct au ViewSet.
13. **Django ne re-scanne pas les `templatetags/` ni les routes URL à chaud.**
    Restart `runserver_plus` requis après ajout d'un nouveau module templatetags
    ou d'une nouvelle URL.
14. **`Client.save()` (django-tenants) échoue hors du schema `public`** :
    `Can't create tenant outside the public schema`. Wrap avec
    `with schema_context("public"):` dans les tests.
15. **`BaseBillet/urls.py` est inclus QUE dans `urls_tenants.py`** (tenants),
    PAS dans `urls_public.py` (ROOT). Une feature qui doit marcher sur ROOT
    (cas wizard onboard) doit avoir sa route ailleurs ou via duplication.
    Cf. revert architecture widget GPS (full client au lieu de proxy serveur).
16. **`events_draft` JSONField stocke datetime en string ISO 8601** :
    `Event.objects.create(datetime="...")` ne convertit PAS la string.
    `Event.save()` plante avec `'str' has no attribute 'astimezone'`.
    Toujours `datetime.fromisoformat(...)` avant.
17. **leaflet-geosearch crée 2 instances `.leaflet-control-geosearch`** :
    1 placeholder Leaflet invisible (0x0) + 1 visible (style "bar"). Normal.
    La navbar TiBillet a son propre input search vers `/explorer/` qui peut
    être visuellement confondu avec la search bar du widget.
18. **Browser bloque les fetch POST avec X-CSRFToken via `claude-in-chrome.javascript_tool`**
    pour raisons de sécurité MCP. Tester l'endpoint avec `curl` côté serveur
    plutôt qu'en console JS browser.

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
