# Plan : Bouton "Je m'inscris" pour les events FREERES (user connecte)

## Contexte

Sur la page detail d'un evenement (`retrieve.html` + `booking.html`), quand :
- L'utilisateur est **connecte** (`user.is_authenticated`)
- L'event ne contient **que** des produits `FREERES` (categorie_article == 'F')

On affiche un bouton **"Je m'inscris"** qui enverra directement la reservation sans passer par l'offcanvas.

Le code commente dans `booking.html` (lignes 5-22) montre qu'un mecanisme `easy_reservation` etait prevu mais jamais termine. On s'en inspire.

## Fichiers a modifier

1. `BaseBillet/templates/reunion/views/event/partial/booking.html`

## Etape 1 — Ajouter le bouton front (sans back)

Dans `booking.html`, avant le bouton existant (ligne 24), ajouter une condition :

```html
{% if user.is_authenticated and event.is_free_reservation_only %}
    <div class="col-md">
        <button
                class="btn btn-lg btn-primary w-100 my-3"
                type="button"
                disabled
                data-testid="booking-easy-reservation">
            {% translate "Je m'inscris" %}
        </button>
        <p class="text-secondary">
            {% translate "Free booking - one click registration (coming soon)" %}
        </p>
    </div>
{% else %}
    {# ... bouton offcanvas existant ... #}
{% endif %}
```

Le bouton est `disabled` pour l'instant — le back viendra dans un second temps.

## Etape 2 — Ajouter `is_free_reservation_only` sur Event

Propriete calculee sur le modele `Event` :

```python
@property
def is_free_reservation_only(self):
    """
    True si l'event n'a que des produits FREERES (reservation gratuite).
    """
    products = self.products.all()
    if not products:
        return False
    return all(p.categorie_article == Product.FREERES for p in products)
```

## Etape 3 — Verifier que le contexte passe `user`

Le template a deja acces a `user` via le context processor `django.contrib.auth.context_processors.auth`. Rien a faire.

## Ce qui n'est PAS dans ce plan

- Pas de refactoring de `booking_form` ou `retrieve()`
- Pas de back-end (`easy_reservation` action)
- Pas de nouvelle route DRF

Le back sera code dans un plan ulterieur. Pour l'instant on pose juste le bouton visible (disabled).

## Verification

```bash
docker exec lespass_django poetry run python manage.py check

# Manuellement :
# 1. Se connecter
# 2. Aller sur /event/<slug>/ d'un event avec uniquement des produits FREERES
# 3. Le bouton "Je m'inscris" (disabled) s'affiche a la place du bouton offcanvas
# 4. Sur un event avec des produits BILLET, le bouton offcanvas classique s'affiche toujours
```
