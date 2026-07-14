# Session 13 — Clotures J/M/A + total perpetuel

> **DECISION POST-SESSION** : la cloture est **GLOBALE au tenant** (pas par PV).
> `point_de_vente` sur ClotureCaisse est nullable/informatif (d'ou declenchee).
> Le numero sequentiel est par niveau uniquement, pas par PV.
> Les references a `point_de_vente=pv` dans le code ci-dessous ont ete corrigees.
> Raison : contexte festival, 40 PV, impossible de cloturer un par un.
> La ventilation par PV est dans `rapport_json['ventilation_par_pv']`.

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune operation git.**

Le chainage HMAC et le service de calcul sont en place (Session 12).
Cette session enrichit `ClotureCaisse` pour la conformite LNE (exigences 6 et 7).

Lis le design spec : `docs/superpowers/specs/2026-03-30-conformite-lne-caisse-design.md`

## TACHE 1 — Enrichir `ClotureCaisse`

Dans `laboutik/models.py`, ajouter :

```python
NIVEAU_CHOICES = [('J', _('Daily')), ('M', _('Monthly')), ('A', _('Annual'))]
niveau = models.CharField(max_length=1, choices=NIVEAU_CHOICES, default='J')

numero_sequentiel = models.PositiveIntegerField(
    verbose_name=_("Sequential number"),
    help_text=_("Numero sequentiel par PV et par niveau, sans trou."),
)

total_perpetuel = models.IntegerField(
    default=0,
    verbose_name=_("Perpetual total (cents)"),
    help_text=_("Total cumule depuis la mise en service. Jamais remis a 0."),
)

hash_lignes = models.CharField(
    max_length=64, blank=True, default='',
    verbose_name=_("Lines integrity hash"),
    help_text=_("SHA-256 des LigneArticle couvertes (filet de securite)."),
)
```

Modifier la Meta :
```python
unique_together = [('point_de_vente', 'numero_sequentiel', 'niveau')]
```

Migration.

## TACHE 2 — `datetime_ouverture` calcule automatiquement

Dans `laboutik/views.py`, modifier `cloturer()` :

Le `datetime_ouverture` n'est plus fourni par le serializer.
Il est calcule = datetime de la 1ere LigneArticle apres la derniere cloture J du PV.

```python
derniere_cloture = ClotureCaisse.objects.filter(
    point_de_vente=pv, niveau='J'
).order_by('-datetime_cloture').first()

if derniere_cloture:
    datetime_ouverture = LigneArticle.objects.filter(
        sale_origin=SaleOrigin.LABOUTIK,
        datetime__gt=derniere_cloture.datetime_cloture,
        status=LigneArticle.VALID,
    ).order_by('datetime').values_list('datetime', flat=True).first()
else:
    datetime_ouverture = LigneArticle.objects.filter(
        sale_origin=SaleOrigin.LABOUTIK,
        status=LigneArticle.VALID,
    ).order_by('datetime').values_list('datetime', flat=True).first()

if not datetime_ouverture:
    # Aucune vente depuis la derniere cloture → rien a cloturer
    return Response({"error": "Aucune vente a cloturer"}, status=400)
```

Supprimer `datetime_ouverture` du `ClotureSerializer` (plus besoin).

**ATTENTION** : 12 tests pytest dans `test_cloture_caisse.py` envoient `datetime_ouverture`
dans le POST data. Les adapter (retirer le champ du payload).

Le `datetime_cloture` doit aussi etre **explicite** (pas `auto_now_add`) pour eviter
une fenetre de flottement entre le calcul du service et le save :
```python
datetime_cloture = timezone.now()
# ... calcul du service avec datetime_cloture ...
cloture = ClotureCaisse.objects.create(
    datetime_cloture=datetime_cloture,  # explicite, pas auto_now_add
    ...
)
```
Modifier le champ `datetime_cloture` de `auto_now_add=True` a `default=timezone.now`.

## TACHE 3 — Connecter `cloturer()` au service

Remplacer le calcul inline actuel par un appel au `RapportComptableService` :

```python
service = RapportComptableService(pv, datetime_ouverture, timezone.now())
rapport = service.generer_rapport_complet()
totaux = rapport['totaux_par_moyen']

# Numero sequentiel
# Numero sequentiel atomique (select_for_update pour eviter les doublons)
with transaction.atomic():
    dernier = ClotureCaisse.objects.select_for_update().filter(
        point_de_vente=pv, niveau='J',
    ).order_by('-numero_sequentiel').first()
    dernier_num = dernier.numero_sequentiel if dernier else 0

# Total perpetuel
config = LaboutikConfiguration.get_solo()
# Atomique avec F() pour eviter les race conditions
from django.db.models import F
LaboutikConfiguration.objects.filter(pk=config.pk).update(
    total_perpetuel=F('total_perpetuel') + totaux['total']
)
config.refresh_from_db()

cloture = ClotureCaisse.objects.create(
    point_de_vente=pv,
    responsable=request.user if request.user.is_authenticated else None,
    datetime_ouverture=datetime_ouverture,
    niveau='J',
    numero_sequentiel=dernier_num + 1,
    total_especes=totaux['especes'],
    total_carte_bancaire=totaux['carte_bancaire'],
    total_cashless=totaux['cashless'],
    total_general=totaux['total'],
    nombre_transactions=service.lignes.count(),
    rapport_json=rapport,
    hash_lignes=service.calculer_hash_lignes(),
    total_perpetuel=config.total_perpetuel,
)
```

## TACHE 4 — Clotures mensuelles et annuelles (Celery Beat)

Dans `laboutik/tasks.py`, ajouter :

```python
@shared_task
def generer_cloture_mensuelle():
    """Generee le 1er de chaque mois pour le mois precedent."""
    # Iterer sur les tenants actifs avec module_caisse
    # Pour chaque PV, agreger les clotures J du mois precedent
    # Creer ClotureCaisse(niveau='M')

@shared_task
def generer_cloture_annuelle():
    """Generee le 1er janvier pour l'annee precedente."""
    # Iterer sur les tenants actifs avec module_caisse
    # Pour chaque PV, agreger les clotures M de l'annee precedente
    # Creer ClotureCaisse(niveau='A')
```

Config Celery Beat (dans settings ou via django-celery-beat) :
- `generer_cloture_mensuelle` : crontab(day_of_month=1, hour=3)
- `generer_cloture_annuelle` : crontab(month_of_year=1, day_of_month=1, hour=4)

## TACHE 5 — Garde correction post-cloture

La garde sera utilisee en session 17 (`corriger_moyen_paiement()`), mais on la
prepare ici comme methode utilitaire :

```python
# laboutik/integrity.py
def ligne_couverte_par_cloture(ligne):
    """
    Verifie si une LigneArticle est couverte par une cloture existante.
    Retourne la ClotureCaisse si oui, None sinon.
    / Checks if a LigneArticle is covered by an existing closure.
    """
    from laboutik.models import ClotureCaisse
    return ClotureCaisse.objects.filter(
        niveau='J',
        datetime_ouverture__lte=ligne.datetime,
        datetime_cloture__gte=ligne.datetime,
    ).first()
```

## TACHE 6 — Admin Unfold enrichi

Dans `Administration/admin/laboutik.py`, enrichir `ClotureCaisseAdmin` :

- Ajouter `niveau`, `numero_sequentiel`, `total_perpetuel` dans list_display
- Filtre par `niveau`
- Section "Ventes" dans la sidebar (conditionnelle `module_caisse`)
- Lecture seule (document comptable immuable)
- Badge integrite : si `hash_lignes` ne correspond plus → badge "ALERTE"

## TACHE 7 — Tests

Dans `tests/pytest/test_cloture_enrichie.py` :

- `test_cloture_journal_numero_sequentiel` : 2 clotures J → numeros 1, 2
- `test_cloture_journal_total_perpetuel` : cloture 5000 + cloture 3000 → perpetuel 8000
- `test_cloture_mensuelle` : agrege les J du mois
- `test_datetime_ouverture_auto` : = datetime 1ere vente apres derniere cloture
- `test_pas_de_vente_pas_de_cloture` : retourne 400
- `test_garde_correction_post_cloture` : ligne couverte → retourne la cloture
- `test_rapport_json_12_cles` : le rapport stocke a bien 12 sections

## VERIFICATION

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
docker exec lespass_django poetry run python manage.py check
docker exec lespass_django poetry run pytest tests/pytest/test_cloture_enrichie.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Critere de succes

- [ ] ClotureCaisse enrichi (niveau, numero_sequentiel, total_perpetuel, hash_lignes)
- [ ] datetime_ouverture calcule automatiquement
- [ ] cloturer() utilise RapportComptableService
- [ ] Clotures M/A automatiques (Celery Beat tasks)
- [ ] Total perpetuel incremente atomiquement, jamais remis a 0
- [ ] Garde correction post-cloture prete
- [ ] Admin Unfold enrichi avec badge integrite
- [ ] 7+ tests pytest verts
- [ ] Tous les tests existants passent
