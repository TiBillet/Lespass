# Session 06 — Tuiles billet dans la grille + données event

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django + HTMX + Cotton).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

Les articles billet (`Product.methode_caisse='BI'`, constante `Product.BILLET_POS`)
doivent s'afficher dans la grille standard avec un composant Cotton paysage
qui occupe 2 colonnes et affiche l'événement + jauge.

## TÂCHE 1 — Lire les modèles

1. Lis `BaseBillet/models.py` : trouve le modèle `Event`.
   Note les champs `products` (M2M), `jauge_max`, `published`, `archived`, `datetime`.
   Trouve la méthode `valid_tickets_count()` et `complet()`.

2. Lis `BaseBillet/models.py` : trouve `Product.BILLET_POS = 'BI'` et le champ `methode_caisse`.

3. Lis `laboutik/views.py` : trouve `_construire_donnees_articles()` pour comprendre
   comment les articles sont construits pour le template.

## TÂCHE 2 — Enrichir `_construire_donnees_articles()` pour les articles BI

Dans `laboutik/views.py`, dans la boucle qui construit `article_dict` pour chaque produit :

```python
from BaseBillet.models import Event

# Après la construction du article_dict standard...
if product.methode_caisse == Product.BILLET_POS:
    event = Event.objects.filter(
        products=product, published=True, archived=False,
    ).order_by('datetime').first()
    if event:
        places_vendues = event.valid_tickets_count()
        article_dict['event'] = {
            'uuid': str(event.uuid),
            'name': event.name,
            'datetime': event.datetime,
            'jauge_max': event.jauge_max,
            'places_vendues': places_vendues,
            'places_restantes': max(0, event.jauge_max - places_vendues) if event.jauge_max else None,
            'pourcentage': int(round(places_vendues / event.jauge_max * 100)) if event.jauge_max else 0,
            'complet': event.complet() if hasattr(event, 'complet') else False,
        }
```

**Attention aux N+1** : si le PV a beaucoup d'articles BI, chaque appel
`Event.objects.filter(products=product)` fait une requête. Optimiser avec un
`prefetch_related` si nécessaire.

## TÂCHE 3 — Composant Cotton `<c-billet-tuile>`

Crée `laboutik/templates/cotton/billet_tuile.html`.

Structure HTML paysage (flex-direction: row) :
- Zone gauche : image ou icône (120×120px)
- Zone droite : nom tarif, nom event, jauge (barre de progression), prix
- Badge quantité (coin haut-droit, masqué si 0)
- `data-uuid`, `data-price-uuid`, `data-event-uuid`
- `data-testid="billetterie-tuile-{price_uuid}"`
- `data-multi-tarif` selon le nombre de Price du produit

Crée `laboutik/static/css/billet_tuile.css` pour le style (pas inline).
La tuile fait `grid-column: span 2` dans le grid parent.

## TÂCHE 4 — Intégrer dans `cotton/articles.html`

Lis `laboutik/templates/cotton/articles.html`. Dans la boucle des articles,
ajoute une condition pour les articles BI :

```html
{% for article in articles %}
  {% if article.methode_caisse == 'BI' and article.event %}
    <c-billet-tuile
      product_uuid="{{ article.id }}"
      event_uuid="{{ article.event.uuid }}"
      nom_event="{{ article.event.name }}"
      prix_centimes="{{ article.prix }}"
      ... />
  {% else %}
    {# tuile standard existante (inchangée) #}
    <div class="article-container" ...>
  {% endif %}
{% endfor %}
```

## TÂCHE 5 — Action `jauge_event()` dans CaisseViewSet

Crée une action GET qui retourne le partial de jauge pour polling HTMX 30s :

```python
@action(detail=False, methods=['GET'], url_path='jauge_event')
def jauge_event(self, request):
    event_uuid = request.GET.get('event_uuid')
    event = Event.objects.get(uuid=event_uuid)
    places_vendues = event.valid_tickets_count()
    context = { ... }
    return render(request, "laboutik/partial/hx_jauge_event.html", context)
```

Crée `laboutik/templates/laboutik/partial/hx_jauge_event.html` :
- Barre de progression (width = pourcentage%)
- Texte "X/Y" ou "COMPLET"
- `hx-get` avec `hx-trigger="every 30s"` pour le polling

## TÂCHE 6 — Adapter `create_test_pos_data`

Ajoute des Products billet de test :
1. Crée un `Event` futur (date = demain)
2. Crée un Product avec `methode_caisse='BI'` et `categorie_article='B'` (BILLET)
3. Ajoute une Price (ex: 15€)
4. Lie le Product à l'Event via `event.products.add(product)`
5. Ajoute le Product au M2M d'un PV existant (ex: créer un PV "Accueil Festival")

## VÉRIFICATION

### Tests unitaires

```bash
docker exec lespass_django poetry run python manage.py create_test_pos_data
docker exec lespass_django poetry run pytest tests/pytest/test_pos_views_data.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Tests E2E

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_pos_tiles_visual.py -v -s
docker exec lespass_django poetry run pytest tests/e2e/ -v -s
```

### Vérification manuelle

Ouvrir un PV avec des articles billet :
- [ ] Tuiles BI en paysage (2 colonnes) visibles dans la grille
- [ ] Jauge affiche le bon nombre de places
- [ ] Clic sur une tuile BI → article ajouté au panier
- [ ] Catégorie "Billetterie" dans la sidebar filtre correctement
- [ ] Tuiles VT standard coexistent avec tuiles BI dans la même grille
- [ ] Polling jauge : la jauge se rafraîchit toutes les 30s
