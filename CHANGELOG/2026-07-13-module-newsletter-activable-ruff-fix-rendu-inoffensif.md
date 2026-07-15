# Module Newsletter activable, et `ruff --fix` rendu inoffensif / Newsletter module toggle, and `ruff --fix` made harmless

**Date :** 2026-07-13
**Migration :** **Oui** — `BaseBillet.0221_configuration_module_newsletter`

### 1. Le module Newsletter s'active depuis le dashboard

Nouvelle carte **« Newsletter »** : *« Evènements, rappels d'adhésions, résumé de vos activités,
pilotez votre newsletter avec TiBillet ! »*

- **Désactivé par défaut**, et **activable par un superadmin seulement** : une instance Ghost
  doit d'abord être installée et **dimensionnée** (la charge serveur dépend du volume de mails).
- Un gestionnaire ordinaire qui clique ne reçoit **pas un refus sec** : une modale l'invite à
  contacter l'équipe TiBillet (email, Matrix, Discord) pour estimer la charge.
- **Le POST de bascule est protégé lui aussi** — la modale n'est que de l'affichage, une requête
  forgée la contournerait. On ne fait jamais confiance à l'interface pour appliquer une règle
  d'accès.
- Nouveau groupe **« Newsletter »** dans la sidebar Unfold, **visible seulement si le module est
  actif**. La config **Ghost y déménage** : elle était perdue dans « Outils externes », entre
  Webhook et Brevo.

### 2. `ruff check --fix` ne peut plus casser le projet

Le `CLAUDE.md` affirmait que `ruff check --fix` était « sans danger ». **C'est faux** : il a
supprimé un import à effet de bord **nu** (`from Administration.admin import products, prices`),
`ProductAdmin` n'était plus enregistré, Django a refusé de démarrer (`admin.E039`), et **319
tests sont partis en erreur** — la fixture `conftest.py` appelle `manage.py test_api_key`, qui ne
bootait plus. Le symptôme était à des kilomètres de la cause.

Audit : **141 imports F401 « fixables »** dans le projet, et **aucune configuration ruff**.

- **Ceinture** — `[tool.ruff.lint.per-file-ignores]` dans `pyproject.toml` : F401 est désormais
  ignoré sur `admin*.py`, `admin/*.py`, `apps.py`, `signals.py`, `triggers.py`, `settings.py`,
  `__init__.py`. `ruff --fix` **ne peut plus y toucher**.
- **Bretelles** — `tests/pytest/test_django_system_checks.py` : la suite échoue immédiatement si
  un enregistrement d'admin disparaît. Vérifié par sabotage.

### 3. Deux bugs corrigés

- **L'agenda affichait les événements archivés.** `federated_events_filter` ne filtrait pas
  `archived`, alors que `seo/services.py` le filtre à quatre endroits. Un événement archivé
  disparaissait de la carte mais **restait sur l'agenda**. Corrigé.
- **`Event.get_img()` : le troisième niveau de repli était inatteignable.** Le code écrivait
  `elif self.postal_address:` avec un `if` imbriqué — le `else` (image de la configuration) ne
  s'exécutait donc **que si l'événement n'avait aucune adresse**. Or `Event.save()` en assigne
  une d'office. Résultat : un événement sans image propre, dans un lieu sans image, n'avait
  **aucune** image. Sur les données de dev : **124 événements sur 136 étaient sans image ; ils en
  ont tous une maintenant.**
- **L'API v2 renvoyait les images en URL relative** (`/media/…`) — inexploitable par un client
  externe. Elles sont désormais **absolues**, sur le domaine du tenant, et passent par
  `get_img()` (le même repli que le moteur d'événements du site).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `Configuration.module_newsletter` (défaut **False**) · `Event.get_img()` : chaîne de repli réparée |
| `BaseBillet/views.py` | `federated_events_filter` : ajout du filtre `archived=False` |
| `api_v2/serializers.py` | `_url_absolue_du_media()` · images absolues + repli `get_img()` (Event **et** PostalAddress) |
| `Administration/admin/dashboard.py` | Carte du module · groupe sidebar « Newsletter » · Ghost déplacé |
| `Administration/admin_tenant.py` | Blocage superadmin dans la **modale** ET dans le **POST** |
| `Administration/templates/admin/dashboard_module_modal_contact.html` | **Nouveau** — la modale de contact |
| `pyproject.toml` | **Nouveau** — `[tool.ruff.lint.per-file-ignores]` |
| `tests/pytest/test_module_newsletter_activation.py` | **Nouveau** — 7 tests |
| `tests/pytest/test_django_system_checks.py` | **Nouveau** — 2 tests (le filet) |

### Migration
- **Migration nécessaire / Migration required : OUI**
  ```bash
  docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
  ```
- Le module est à **False** partout : aucun tenant n'est impacté tant qu'un superadmin ne
  l'active pas.

---
