# Session 19 — Envoi automatique rapports + identification version

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune operation git.**

L'archivage fiscal est en place (session 18). Cette session finalise la conformite
LNE avec l'envoi automatique des rapports et l'identification des versions (exigence 21).

## TACHE 1 — Envoi automatique Celery Beat

Dans `laboutik/tasks.py` :

```python
@shared_task
def generer_et_envoyer_rapport_periodique(periodicite='daily'):
    """Itere sur les tenants actifs, genere et envoie le rapport."""
    from Customers.models import Client
    for tenant in Client.objects.filter(categorie=Client.SALLE_SPECTACLE):
        with schema_context(tenant.schema_name):
            config = LaboutikConfiguration.get_solo()
            if not config.rapport_emails:
                continue
            # Calculer debut/fin selon periodicite
            # Generer rapport via RapportComptableService
            # Generer PDF + CSV
            # Envoyer par email avec PJ
```

Config Celery Beat :
- `rapport_periodique_daily` : crontab(hour=6, minute=0)
- `rapport_periodique_weekly` : crontab(day_of_week=1, hour=6)
- `rapport_periodique_monthly` : crontab(day_of_month=1, hour=6)

Chaque tenant choisit sa periodicite via `rapport_periodicite` dans la config.

## TACHE 2 — Identification version (Ex.21)

Le systeme doit etre identifie par un numero de version majeure et mineure.

### Empreinte du code source

Creer `laboutik/version.py` :

```python
VERSION_MAJEURE = "2"
VERSION_MINEURE = "0"
VERSION = f"{VERSION_MAJEURE}.{VERSION_MINEURE}"

def get_version_display():
    return f"TiBillet LaBoutik v{VERSION}"
```

L'empreinte SHA-256 du perimetre fiscal (fichiers du chapitre IV) sera generee
par un script separe et stockee dans un fichier `FISCAL_HASH.txt`.

### Visible dans l'interface

Ajouter la version dans le footer du POS (composant `<c-footer>`)
et dans l'admin (page "A propos" ou dashboard).

## TACHE 3 — Tests

- `test_envoi_rapport_periodique` : tache Celery s'execute sans erreur
- `test_version_affichee` : la version est presente dans le HTML du POS
- `test_version_coherente` : VERSION_MAJEURE et VERSION_MINEURE sont des strings numeriques

## VERIFICATION

```bash
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Critere de succes

- [ ] Envoi automatique rapport par email (Celery Beat)
- [ ] Config periodicite par tenant
- [ ] Version visible dans l'interface POS
- [ ] Empreinte SHA-256 du perimetre fiscal
- [ ] Tests verts, pas de regression
