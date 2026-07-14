# Phase -1, Etape 1 — Champs module_* sur Configuration

## Prompt

```
On travaille sur la Phase -1 du plan laboutik/doc/PLAN_INTEGRATION.md
(section 15, "Dashboard Groupware"). Etape 1 sur 3 : les champs module_*.

Lis le plan (section 3.1 + section 3.2 + section 15), le MEMORY.md,
et dis-moi ce que tu comprends avant de coder.

Contexte : Configuration est un SingletonModel (django-solo) dans
BaseBillet/models.py (ligne ~335). Pas de champs module_* pour l'instant.

Tache (1 seul fichier : BaseBillet/models.py) :

1. Ajouter 5 BooleanField sur Configuration :
   - module_billetterie (default=True)
   - module_adhesion (default=False)
   - module_crowdfunding (default=False)
   - module_monnaie_locale (default=False)
   - module_caisse (default=False)

2. Ajouter une methode clean() qui impose 2 regles :
   a) module_caisse=True → force module_monnaie_locale=True
      (pas de caisse sans cashless)
   b) Si server_cashless est renseigne → module_caisse reste False
      (ancien tenant V1, carte "Caisse V2" grisee)

3. Lancer :
   docker exec lespass_django poetry run python manage.py makemigrations BaseBillet
   docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
   docker exec lespass_django poetry run python manage.py check

Ne touche a rien d'autre. Pas de template, pas d'admin, pas de sidebar.
```

## Verification

- `manage.py check` passe
- Migration creee et appliquee
- En shell Django : `Configuration.get_solo().module_billetterie` retourne `True`
- En shell Django : tester le clean() avec server_cashless renseigne

## Modele recommande

Sonnet
