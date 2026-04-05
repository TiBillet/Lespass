# Optimisation des requêtes : éliminer les N+1 dans Lespass

## Sources

- "Django Scalability Best Practices" — codezup.com : https://codezup.com/django-scalability-best-practices/
- Documentation Django officielle : https://docs.djangoproject.com/en/stable/ref/models/querysets/#select-related

## C'est quoi le problème N+1 ?

Un N+1 se produit quand Django fait **1 requête pour récupérer une liste**,
puis **N requêtes supplémentaires** pour accéder à des relations sur chaque objet.

```python
# ❌ Exemple N+1 classique — 1 + N requêtes
tous_les_evenements = Evenement.objects.all()   # 1 requête : SELECT * FROM evenement

for evenement in tous_les_evenements:
    print(evenement.configuration.nom)          # N requêtes : SELECT * FROM configuration WHERE id = ?
    # → autant de requêtes SQL que d'événements dans la liste
```

Avec django-tenants, ce problème est **amplifié** : chaque accès à une relation
traverse le bon schema PostgreSQL, ce qui ajoute du overhead sur chaque requête N.

## Les deux outils Django pour régler ça

### `select_related()` — pour les relations ForeignKey et OneToOne

Fait une seule requête SQL avec un JOIN au lieu de N requêtes séparées.
À utiliser quand la relation pointe vers **un seul objet** (ForeignKey, OneToOne).

```python
# ✅ select_related — 1 seule requête SQL avec JOIN
tous_les_evenements = Evenement.objects.select_related(
    'configuration',          # ForeignKey vers Configuration
    'configuration__tenant',  # On peut chaîner les relations
).all()

for evenement in tous_les_evenements:
    print(evenement.configuration.nom)    # Pas de requête supplémentaire
    print(evenement.configuration.tenant) # Pas de requête supplémentaire
```

Le SQL généré ressemble à :
```sql
SELECT evenement.*, configuration.*, tenant.*
FROM evenement
INNER JOIN configuration ON evenement.configuration_id = configuration.id
INNER JOIN tenant ON configuration.tenant_id = tenant.id
```

### `prefetch_related()` — pour les relations ManyToMany et reverse ForeignKey

Fait **2 requêtes** au lieu de N : une pour la liste principale, une pour toutes
les relations en une seule fois. À utiliser quand la relation pointe vers
**plusieurs objets** (ManyToMany, reverse ForeignKey).

```python
# ✅ prefetch_related — 2 requêtes au lieu de N
tous_les_evenements = Evenement.objects.prefetch_related(
    'billets',         # reverse ForeignKey : tous les billets de chaque événement
    'tags',            # ManyToMany : tous les tags de chaque événement
).all()

for evenement in tous_les_evenements:
    print(evenement.billets.all())  # Pas de requête supplémentaire (déjà préchargé)
    print(evenement.tags.all())     # Pas de requête supplémentaire
```

### Combiner les deux

```python
# ✅ Combinaison select_related + prefetch_related
reservation = Reservation.objects.select_related(
    'evenement',               # ForeignKey → 1 objet
    'evenement__configuration', # ForeignKey chaînée → 1 objet
).prefetch_related(
    'billets',                 # reverse FK → plusieurs objets
    'billets__categorie',      # ForeignKey sur chaque billet → prefetch Prefetch
).get(pk=reservation_id)
```

## Anti-patterns fréquents à éviter dans Lespass

### Anti-pattern 1 : accès à une relation dans une list comprehension

```python
# ❌ N+1 caché dans une comprehension
noms_configurations = [
    evenement.configuration.nom
    for evenement in Evenement.objects.all()
]

# ✅ Correction
noms_configurations = [
    evenement.configuration.nom
    for evenement in Evenement.objects.select_related('configuration').all()
]
```

### Anti-pattern 2 : accès à une relation dans un template

Django évalue les relations en lazy-loading. Un accès dans un template
déclenche une requête SQL silencieusement.

```html
<!-- ❌ N+1 dans le template — une requête SQL par événement -->
{% for evenement in evenements %}
    {{ evenement.configuration.nom }}  <!-- requête SQL ici -->
{% endfor %}
```

```python
# ✅ Correction dans la vue : prefetch avant d'envoyer au template
def liste_evenements(request):
    tous_les_evenements = Evenement.objects.select_related('configuration').all()
    return render(request, 'evenements.html', {'evenements': tous_les_evenements})
```

### Anti-pattern 3 : `.count()` en boucle

```python
# ❌ Une requête COUNT par événement
for evenement in Evenement.objects.all():
    nb_billets = evenement.billets.count()  # SELECT COUNT(*) à chaque itération

# ✅ Correction avec annotate — une seule requête
from django.db.models import Count

evenements = Evenement.objects.annotate(
    nombre_billets=Count('billets')
).all()

for evenement in evenements:
    nb_billets = evenement.nombre_billets  # Déjà calculé, pas de requête
```

## Comment détecter les N+1 dans Lespass

### Option 1 : django-debug-toolbar (en développement)

```python
# settings/dev.py
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
INTERNAL_IPS = ['127.0.0.1']
```

Le panneau "SQL" de la toolbar montre toutes les requêtes exécutées
sur une page, avec les doublons mis en évidence.

### Option 2 : logger SQL dans la console (plus léger)

```python
# settings/dev.py — affiche toutes les requêtes SQL dans le terminal
LOGGING = {
    'version': 1,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

### Option 3 : `assertNumQueries` dans les tests

```python
# tests/test_views.py
from django.test import TestCase

class TestListeEvenements(TestCase):

    def test_liste_evenements_ne_fait_pas_de_n_plus_1(self):
        """
        Vérifier que la vue liste_evenements fait un nombre fixe de requêtes
        peu importe le nombre d'événements (pas de N+1).
        """
        # Créer 10 événements de test
        for i in range(10):
            EvenementFactory.create()

        # La vue doit faire exactement 2 requêtes (liste + prefetch),
        # pas 1 + 10 (N+1)
        with self.assertNumQueries(2):
            response = self.client.get('/evenements/')

        self.assertEqual(response.status_code, 200)
```

## Vues Lespass prioritaires à auditer

Les vues à fort trafic ou avec beaucoup de relations imbriquées sont
les plus à risque. À auditer en priorité :

| Vue | Relations à risque | Action recommandée |
|---|---|---|
| Liste des événements publics | `evenement.configuration`, `evenement.tags` | `select_related` + `prefetch_related` |
| Page programme / agenda | Relations multi-niveaux | Audit avec debug_toolbar |
| Liste des réservations (admin) | `reservation.evenement`, `reservation.billets` | `select_related` + `prefetch_related` |
| API v2 — liste des ventes | Jointures sur plusieurs modèles | Vérifier les queryset existants |
| Vues cashless | Modèles `Asset`, `Wallet` | Déjà cachés (TTL 24h/10s) — vérifier quand le cache est froid |

## Priorité

Haute — les N+1 sont souvent invisibles en développement (peu de données)
mais explosent en production avec un vrai volume. Un audit avec `debug_toolbar`
sur les 5 vues prioritaires ci-dessus est une journée de travail qui peut
diviser la charge DB par 5 ou 10.

À faire avant d'envisager PgBouncer ou la réplication : les N+1 sont
la cause la plus fréquente de ralentissement DB sur Django.
