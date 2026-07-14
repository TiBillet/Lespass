# Session 19 — Envoi auto rapports + version visible : Plan d'implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Brancher les champs `rapport_emails` et `rapport_periodicite` dans la tache Celery existante, les exposer dans l'admin, et afficher la version du logiciel dans le footer POS.

**Architecture:** Modifications mineures sur 4 fichiers existants. Pas de nouveau modele, pas de migration. La tache Celery `envoyer_rapports_clotures_recentes()` existe deja — on ajoute le filtrage par periodicite et la lecture de `rapport_emails`. Le fichier `VERSION` a la racine (`VERSION=1.7.9`) est deja present.

**Tech Stack:** Django 4.2, Celery, django-tenants, HTMX, Cotton templates.

---

## Fichiers

| Action | Fichier | Responsabilite |
|--------|---------|----------------|
| Modifier | `laboutik/tasks.py` (~ligne 128-170) | Brancher `rapport_emails` + `rapport_periodicite` |
| Modifier | `Administration/admin/laboutik.py` (~ligne 46-73) | Ajouter fieldset rapports dans LaboutikConfigurationAdmin |
| Modifier | `laboutik/views.py` (~ligne 161) | Lire VERSION depuis fichier racine |
| Modifier | `laboutik/templates/cotton/footer.html` | Afficher la version |
| Creer | `tests/pytest/test_envoi_rapports_version.py` | 6 tests |

---

## Task 1 : Brancher `rapport_emails` + `rapport_periodicite` dans la tache Celery

**Files:**
- Modify: `laboutik/tasks.py` (fonction `envoyer_rapports_clotures_recentes`, lignes 128-340)

La tache existe deja et fonctionne. Elle tourne toutes les heures et envoie a 7h locale.
Actuellement elle :
1. Lit `config.email` comme destinataire (champ Configuration de BaseBillet, pas LaboutikConfiguration)
2. Ignore completement `rapport_emails` et `rapport_periodicite` de LaboutikConfiguration

Modifications :

- [ ] **Step 1: Lire `rapport_emails` depuis LaboutikConfiguration**

Dans `envoyer_rapports_clotures_recentes()`, apres la ligne `config = Configuration.get_solo()` (~ligne 154), ajouter la lecture de LaboutikConfiguration :

```python
                # Lire la configuration des rapports automatiques
                # rapport_emails = liste d'emails destinataires (JSONField, ex: ["admin@bar.fr", "compta@bar.fr"])
                # rapport_periodicite = frequence choisie par le gerant (daily, weekly, monthly, yearly)
                # / Read automatic report configuration
                from laboutik.models import LaboutikConfiguration
                laboutik_config = LaboutikConfiguration.get_solo()

                # Destinataires : rapport_emails si configure, sinon config.email en fallback
                # / Recipients: rapport_emails if set, otherwise config.email as fallback
                destinataires = laboutik_config.rapport_emails
                if not destinataires:
                    # Fallback sur l'email du lieu (Configuration de BaseBillet)
                    # / Fallback to venue email (BaseBillet Configuration)
                    if config.email:
                        destinataires = [config.email]
                    else:
                        continue
```

Remplacer l'ancien bloc :
```python
                # ANCIEN — a supprimer :
                destinataire = config.email
                if not destinataire:
                    continue
```

Et plus bas, dans l'envoi du mail, remplacer `to=[destinataire]` par `to=destinataires`.

- [ ] **Step 2: Filtrer par periodicite**

Apres la lecture de `laboutik_config`, ajouter le filtre par periodicite.
La tache tourne toutes les heures. Le filtre decide si c'est le bon moment d'envoyer :

```python
                # Verifier si c'est le bon moment d'envoyer selon la periodicite
                # La tache tourne toutes les heures a 7h locale du tenant.
                # On verifie le jour de la semaine / du mois / de l'annee.
                # / Check if it's the right time to send based on frequency
                from django.utils import timezone as dj_timezone
                maintenant_local = dj_timezone.now().astimezone(tz_tenant)
                periodicite = laboutik_config.rapport_periodicite or 'daily'

                doit_envoyer = False
                if periodicite == 'daily':
                    # Tous les jours / Every day
                    doit_envoyer = True
                elif periodicite == 'weekly':
                    # Le lundi seulement (weekday() == 0)
                    # / Monday only
                    doit_envoyer = (maintenant_local.weekday() == 0)
                elif periodicite == 'monthly':
                    # Le 1er du mois seulement
                    # / 1st of the month only
                    doit_envoyer = (maintenant_local.day == 1)
                elif periodicite == 'yearly':
                    # Le 1er janvier seulement
                    # / January 1st only
                    doit_envoyer = (maintenant_local.month == 1 and maintenant_local.day == 1)

                if not doit_envoyer:
                    continue
```

Ce bloc s'insere APRES le check `heure_locale != 7` et AVANT la recherche des clotures.

- [ ] **Step 3: Ajuster la periode de recherche des clotures**

Actuellement la tache cherche les clotures des 24 dernieres heures. Pour weekly/monthly, il faut chercher plus loin :

```python
                # Calculer la periode de recherche selon la periodicite
                # / Calculate the search period based on frequency
                from datetime import timedelta
                if periodicite == 'daily':
                    seuil = dj_timezone.now() - timedelta(hours=24)
                elif periodicite == 'weekly':
                    seuil = dj_timezone.now() - timedelta(days=7)
                elif periodicite == 'monthly':
                    seuil = dj_timezone.now() - timedelta(days=31)
                elif periodicite == 'yearly':
                    seuil = dj_timezone.now() - timedelta(days=366)
                else:
                    seuil = dj_timezone.now() - timedelta(hours=24)
```

Remplacer l'ancien `seuil = dj_timezone.now() - timedelta(hours=24)` (~ligne 179).

- [ ] **Step 4: Adapter le sujet de l'email**

Ajouter la periodicite dans le sujet pour que le destinataire sache quel type de recapitulatif c'est :

```python
                # Labels de periodicite pour le sujet / Frequency labels for subject
                labels_periodicite = {
                    'daily': _("quotidien"),
                    'weekly': _("hebdomadaire"),
                    'monthly': _("mensuel"),
                    'yearly': _("annuel"),
                }
                label_periodicite = labels_periodicite.get(periodicite, _("quotidien"))

                sujet = _("Rapports de cloture (%(freq)s) — %(org)s — %(date)s") % {
                    "freq": label_periodicite,
                    "org": config.organisation or tenant.schema_name,
                    "date": dj_timezone.now().astimezone(tz_tenant).strftime("%d/%m/%Y"),
                }
```

- [ ] **Step 5: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 2 : Exposer `rapport_emails` + `rapport_periodicite` dans l'admin

**Files:**
- Modify: `Administration/admin/laboutik.py` (LaboutikConfigurationAdmin, lignes 46-73)

- [ ] **Step 1: Ajouter un fieldset "Rapports automatiques"**

Dans `LaboutikConfigurationAdmin.fieldsets`, ajouter apres le fieldset "Ticket de vente" :

```python
        (_('Rapports automatiques / Automatic reports'), {
            'fields': (
                'rapport_emails',
                'rapport_periodicite',
            ),
            'description': _(
                "Configuration de l'envoi automatique des rapports de cloture par email. "
                "Les emails sont envoyes a l'heure configuree (7h locale). "
                "/ Automatic closure report email configuration. "
                "Emails are sent at the configured time (7am local)."
            ),
        }),
```

- [ ] **Step 2: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 3 : Afficher la version dans le footer POS

**Files:**
- Modify: `laboutik/views.py` (~ligne 161) — lire VERSION depuis fichier racine
- Modify: `laboutik/templates/cotton/footer.html` — afficher la version

- [ ] **Step 1: Lire VERSION depuis le fichier racine**

Le fichier `/DjangoFiles/VERSION` contient `VERSION=1.7.9`. Creer une fonction utilitaire dans `laboutik/views.py` (au debut du fichier, section utilitaires) :

```python
def _lire_version():
    """
    Lit le numero de version depuis le fichier VERSION a la racine du projet.
    Format attendu : VERSION=X.Y.Z sur la premiere ligne.
    Retourne la version ou '?' si le fichier est introuvable.
    / Reads the version number from the VERSION file at the project root.
    Expected format: VERSION=X.Y.Z on the first line.
    Returns the version or '?' if the file is not found.

    LOCALISATION : laboutik/views.py
    """
    try:
        chemin_version = os.path.join(settings.BASE_DIR, 'VERSION')
        with open(chemin_version, 'r') as fichier:
            for ligne in fichier:
                ligne = ligne.strip()
                if ligne.startswith('VERSION='):
                    return ligne.split('=', 1)[1]
    except FileNotFoundError:
        pass
    return '?'
```

Verifier que `os` et `settings` sont deja importes en haut du fichier (ils le sont).

- [ ] **Step 2: Utiliser dans `_construire_state()`**

Remplacer `"version": "0.9.11"` (ligne 161) par :

```python
        "version": _lire_version(),
```

- [ ] **Step 3: Passer la version au template footer**

Dans `_construire_state()`, la version est deja dans le state. Le state est passe comme `stateJson` au template. Mais le footer Cotton est un composant statique sans acces au state JS.

Ajouter la version dans le contexte Django. Dans `CaisseViewSet.point_de_vente()` (la vue qui rend `common_user_interface.html`), la version est deja dans `state["version"]`. Il faut la passer au contexte template :

Chercher ou `context` est construit pour la vue point_de_vente et ajouter :

```python
            "version_logiciel": _lire_version(),
```

- [ ] **Step 4: Afficher dans le footer Cotton**

Dans `laboutik/templates/cotton/footer.html`, ajouter apres le dernier `</div>` du bouton VALIDER (avant `</footer>`) :

```html
	<!-- Version du logiciel — petit texte discret a droite -->
	<!-- / Software version — small discrete text on the right -->
	{% if version_logiciel %}
	<div style="position: absolute; bottom: 4px; right: 8px; font-size: 0.6rem;
	            color: rgba(255,255,255,0.25); font-family: 'Luciole-regular';
	            pointer-events: none;"
	     data-testid="footer-version">
		v{{ version_logiciel }}
	</div>
	{% endif %}
```

Le footer a `position: relative` ? Sinon ajouter `style="position: relative;"` sur `<footer>`.

- [ ] **Step 5: Propager `version_logiciel` dans les vues qui utilisent le footer**

Le composant Cotton `<c-footer>` est utilise dans `common_user_interface.html`. La variable `version_logiciel` doit etre dans le contexte template. Verifier que la vue `point_de_vente()` la passe bien.

Aussi verifier `ventes.html` qui n'utilise pas le footer (pas de version a afficher la).

- [ ] **Step 6: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 4 : Tests

**Files:**
- Create: `tests/pytest/test_envoi_rapports_version.py`

- [ ] **Step 1: Creer le fichier de test**

```python
"""
tests/pytest/test_envoi_rapports_version.py — Session 19 : envoi auto rapports + version.
/ Session 19: automatic report sending + version display.

Couvre :
- Lecture de rapport_emails et rapport_periodicite depuis LaboutikConfiguration
- Filtrage par periodicite (daily/weekly/monthly)
- Lecture du fichier VERSION
- Version dans le state JSON

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_envoi_rapports_version.py -v
"""
import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

from django.db import connection
from django_tenants.test.cases import FastTenantTestCase

from laboutik.models import LaboutikConfiguration


class TestRapportEmailsConfig(FastTenantTestCase):
    """Tests pour la configuration des rapports automatiques.
    / Tests for automatic report configuration."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_rapports'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-rapports.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test Rapports'

    def setUp(self):
        connection.set_tenant(self.tenant)
        self.config = LaboutikConfiguration.get_solo()

    def test_rapport_emails_default_vide(self):
        """Le champ rapport_emails est une liste vide par defaut.
        / rapport_emails defaults to an empty list."""
        assert self.config.rapport_emails == []

    def test_rapport_periodicite_default_daily(self):
        """Le champ rapport_periodicite est 'daily' par defaut.
        / rapport_periodicite defaults to 'daily'."""
        assert self.config.rapport_periodicite == 'daily'

    def test_rapport_emails_accepte_liste(self):
        """rapport_emails accepte une liste d'emails.
        / rapport_emails accepts a list of emails."""
        emails = ['admin@test.fr', 'compta@test.fr']
        self.config.rapport_emails = emails
        self.config.save()
        self.config.refresh_from_db()
        assert self.config.rapport_emails == emails

    def test_rapport_periodicite_accepte_weekly(self):
        """rapport_periodicite accepte 'weekly'.
        / rapport_periodicite accepts 'weekly'."""
        self.config.rapport_periodicite = 'weekly'
        self.config.save()
        self.config.refresh_from_db()
        assert self.config.rapport_periodicite == 'weekly'


class TestVersion(FastTenantTestCase):
    """Tests pour la version du logiciel.
    / Tests for software version."""

    @classmethod
    def get_test_schema_name(cls):
        return 'test_version'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-version.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test Version'

    def test_lire_version_retourne_string(self):
        """_lire_version() retourne une string non vide.
        / _lire_version() returns a non-empty string."""
        from laboutik.views import _lire_version
        version = _lire_version()
        assert isinstance(version, str)
        assert len(version) > 0
        assert version != '?'

    def test_version_dans_state(self):
        """La version est presente dans le state JSON.
        / Version is present in the state JSON."""
        from laboutik.views import _construire_state
        state = _construire_state()
        assert 'version' in state
        assert state['version'] != '0.9.11'  # Plus hardcode
        assert '.' in state['version']  # Format X.Y.Z
```

- [ ] **Step 2: Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_envoi_rapports_version.py -v
```

Expected: 6 tests verts.

- [ ] **Step 3: Non-regression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_archivage_fiscal.py tests/pytest/test_corrections_fond_sortie.py tests/pytest/test_envoi_rapports_version.py -v
```

---

## Task 5 : Verification finale

- [ ] **Step 1: Ruff**

```bash
docker exec lespass_django poetry run ruff check --fix laboutik/tasks.py laboutik/views.py Administration/admin/laboutik.py
docker exec lespass_django poetry run ruff format laboutik/tasks.py laboutik/views.py Administration/admin/laboutik.py
```

- [ ] **Step 2: Django check**

```bash
docker exec lespass_django poetry run python manage.py check
```

- [ ] **Step 3: Tests complets laboutik**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_archivage_fiscal.py tests/pytest/test_corrections_fond_sortie.py tests/pytest/test_cloture_caisse.py tests/pytest/test_cloture_enrichie.py tests/pytest/test_cloture_export.py tests/pytest/test_envoi_rapports_version.py -v
```
