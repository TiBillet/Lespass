# Bénévolat, chantier 6 : API v2 allégée / Volunteering, step 6: light API v2

**Date :** 2026-10-16
**Migration :** Oui — `BaseBillet/0232_externalapikey_volunteering.py` (`ExternalApiKey.volunteering`)

## Resume / Summary
**Quoi / What :** quatre routes schema.org pour piloter le bénévolat sans l'admin, ouvertes par un nouveau droit de clé « Bénévolat » (`volunteering`) :
- `/api/v2/volunteer-tasks/` (DefinedTerm) : lire, créer, modifier, supprimer (409 si la tâche sert encore) ;
- `/api/v2/volunteer-plannings/` (EventSeries) : lire (par uuid ou slug, avec ses besoins), créer, modifier (nom, présentation, slug, publié, délai), supprimer ;
- `/api/v2/volunteer-needs/` (Event « Volunteering ») : lire (filtres planning, tâche, dates), créer, modifier, supprimer ;
- `/api/v2/volunteer-signups/` (RsvpAction) : lire (filtres besoin, planning), inscrire (mêmes règles que « Inscrire quelqu'un » : 201, ou 200 si rejoué), retirer sans mail.
/ Four schema.org routes under a new "volunteering" key right.

**Pourquoi / Why :** chantier 6 de `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` (§6 bis). Version **allégée** choisie par le mainteneur le 2026-10-16 : pas de répétition par l'API (l'admin le fait), pas de filtres email/dates des inscriptions, adhésions requises et calendrier de fermetures en lecture seule.

Points notables :
- heures : une heure sans décalage = heure locale du lieu ; avec décalage = convertie ; fin le jour même ou le lendemain, sinon 400 ; la sortie porte le décalage du lieu ;
- l'inscription partage avec la vue « Inscrire quelqu'un » la création du compte (`compte_d_une_personne_inscrite_par_l_equipe`, `booking/benevolat.py`) : nom écrit seulement s'il est vide ; un compte sans nom et une requête sans nom → 400, rien n'est créé (transaction annulée) ;
- les sorties sont des fonctions explicites (`api_v2/serializers_benevolat.py`), les entrées des `serializers.Serializer`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py`, `BaseBillet/migrations/0232_…` | `ExternalApiKey.volunteering`, quatre basenames dans `api_permissions()` |
| `Administration/admin_tenant.py` | Le droit « Bénévolat » dans l'admin des clés |
| `api_v2/views_benevolat.py`, `api_v2/serializers_benevolat.py` | Nouveaux : les quatre ViewSets, représentations et entrées |
| `api_v2/urls.py` | Quatre routes |
| `booking/benevolat.py`, `booking/views_benevolat.py` | `compte_d_une_personne_inscrite_par_l_equipe`, partagée avec la vue de l'équipe |
| `api_v2/openapi-schema.yaml` | 8 chemins, 8 schémas `Volunteer*` |
| `api_v2/GUIDELINES.md` | Section « Bénévolat » |
| `TECH_DOC/SKILLS/tibillet-api/` | `SKILL.md`, `references/recettes.md`, `scripts/creer_cle_api.py` (`--perms volunteering`) |
| `tests/pytest/test_benevolat_api.py` | 23 tests, vérifiés par mutation (22 mutations) |
| `TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md` | §6 bis allégé, D24 revue, statut |

i18n : nouvelles chaînes traduisibles (msgid en français), workflow i18n à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

1. Obtenir une clé : `python3 TECH_DOC/SKILLS/tibillet-api/scripts/creer_cle_api.py --tenant lespass --perms volunteering --name essai`
2. `curl -k -H "Authorization: Api-Key <clé>" https://lespass.tibillet.localhost/api/v2/volunteer-plannings/bar-demo/` → le planning et ses besoins (`subEvent`).
3. Créer une tâche, un planning, un besoin puis une inscription (exemples dans `api_v2/openapi-schema.yaml`, chemins `/api/v2/volunteer-*`) ; rejouer l'inscription → 200.
4. Sans le droit « Bénévolat » sur la clé (admin → Clés API) → 403.

### Verifs automatiques
- `docker exec -w /DjangoFiles lespass_django poetry run pytest tests/pytest/test_benevolat_api.py -q`
