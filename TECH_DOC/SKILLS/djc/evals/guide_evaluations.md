# 📋 Guide des Évaluations pour django-htmx-readable

Ce document explique les 6 évaluations créées pour tester le skill "django-htmx-readable".

## 🎯 Objectif des Évaluations

Chaque évaluation teste un aspect spécifique du skill pour s'assurer qu'il produit du code :
- ✅ **Lisible** - Facile à comprendre pour un humain
- ✅ **Explicite** - Pas de "magie" Django cachée
- ✅ **Verbeux** - Noms de variables qui expliquent leur contenu
- ✅ **Bilingue** - Commentaires en français ET en anglais
- ✅ **Conforme** - Suit les patterns du skill (ViewSet, DRF Serializers, HTMX)

---

## 📝 Détail des 6 Évaluations

### Eval 1️⃣ : ViewSet Basique
**Ce qui est testé :**
- Création d'un ViewSet avec `viewsets.ViewSet` (pas ModelViewSet)
- Méthodes `list()` et `retrieve()` explicites
- Requêtes SQL explicites avec select_related
- Utilisation de `get_object_or_404()`
- Noms de variables verbeux

**Pourquoi c'est important :**
C'est la base du skill. Si le ViewSet n'est pas explicite, tout le reste échouera.

**Exemple de nom de variable attendu :**
```python
# ❌ Mauvais (trop court)
products = Product.objects.filter(in_stock=True)

# ✅ Bon (explicite)
products_available_in_stock_for_display = Product.objects.filter(in_stock=True)
```

---

### Eval 2️⃣ : Validation avec DRF Serializers
**Ce qui est testé :**
- Utilisation de `serializers.Serializer` (jamais Django Forms)
- Messages d'erreur bilingues FR/EN
- Validation personnalisée avec `validate_<field>()`
- Méthode `create()` explicite

**Pourquoi c'est important :**
Le skill INTERDIT Django Forms. Cette eval vérifie que le code utilise bien DRF pour la validation.

**Anti-pattern détecté :**
```python
# ❌ INTERDIT par le skill
from django import forms
class ProductForm(forms.ModelForm):
    ...

# ✅ CORRECT
from rest_framework import serializers
class ProductCreateSerializer(serializers.Serializer):
    ...
```

---

### Eval 3️⃣ : Intégration HTMX
**Ce qui est testé :**
- Attributs HTMX corrects : `hx-get`, `hx-target`, `hx-swap`
- Token CSRF pour les requêtes HTMX
- Conteneur avec ID pour recevoir le contenu dynamique
- URLs Django avec `{% url %}`
- Commentaires bilingues FR/EN

**Pourquoi c'est important :**
HTMX est au cœur du skill. Le code doit générer du HTML server-rendered, pas du JSON.

**Pattern attendu :**
```html
<!-- ✅ Bon : chargement HTMX avec fallback -->
<button 
    hx-get="{% url 'product-detail' pk=product.id %}"
    hx-target="#product-container"
    hx-swap="innerHTML"
>
    Voir détails
</button>

<div id="product-container">
    <!-- Le contenu sera injecté ici -->
    <!-- Content will be injected here -->
</div>
```

---

### Eval 4️⃣ : Actions Personnalisées (@action)
**Ce qui est testé :**
- Utilisation du décorateur `@action`
- Logique explicite avec if/else (pas de one-liner)
- Noms de variables ultra-verbeux
- Retour de partials HTML (pas JSON)
- Utilisation de `save(update_fields=[...])`

**Pourquoi c'est important :**
Les actions personnalisées sont courantes en Django. Le skill doit produire du code explicite et traçable.

**Pattern attendu :**
```python
@action(detail=True, methods=["POST"])
def mark_as_promotion(self, request, pk=None):
    """
    Marquer un produit en promotion.
    Mark a product as on promotion.
    """
    product = get_object_or_404(Product, uuid=pk)
    
    # Vérification explicite, pas de one-liner
    # Explicit check, no one-liner
    product_already_in_promotion = product.is_promotion
    
    if product_already_in_promotion:
        return render(request, "products/partials/already_promotion.html", {
            'product': product
        })
    
    # Mise à jour explicite
    # Explicit update
    product.is_promotion = True
    product.promotion_started_at = timezone.now()
    product.save(update_fields=['is_promotion', 'promotion_started_at'])
    
    return render(request, "products/partials/promotion_badge.html", {
        'product': product
    })
```

---

### Eval 5️⃣ : Notifications Toast
**Ce qui est testé :**
- Utilisation de Django `messages` framework
- Variable explicite pour sauvegarder les données AVANT suppression
- Header HTMX `HX-Trigger` avec payload JSON
- Code JavaScript minimal pour écouter l'événement
- Structure de données correcte pour les toasts

**Pourquoi c'est important :**
Les notifications sont essentielles pour l'UX. Le skill doit montrer comment les implémenter proprement avec HTMX.

**Pattern attendu :**
```python
def delete(self, request, pk=None):
    product = get_object_or_404(Product, uuid=pk)
    
    # ✅ Variable explicite AVANT suppression
    # Explicit variable BEFORE deletion
    product_title_for_notification_message = product.title
    
    product.delete()
    
    messages.add_message(
        request,
        messages.SUCCESS,
        f'"{product_title_for_notification_message}" a été supprimé / has been deleted'
    )
    
    # Récupération des messages pour le toast
    # Get messages for toast
    messages_from_django_framework = get_messages(request)
    toast_payload_for_frontend = [
        {"level": msg.level_tag, "text": str(msg)}
        for msg in messages_from_django_framework
    ]
    
    response = render(request, "products/partials/empty.html")
    response["HX-Trigger"] = json.dumps({"toast": {"items": toast_payload_for_frontend}})
    return response
```

---

### Eval 6️⃣ : ViewSet Complet CRUD
**Ce qui est testé :**
- ViewSet complet avec list(), retrieve(), create(), update()
- Action search() avec `@action(detail=False)`
- `select_related()` pour optimiser les requêtes
- Validation via serializer
- Gestion explicite des erreurs
- Noms de variables ultra-verbeux
- Docstrings bilingues
- Code FALC (Facile À Lire et à Comprendre)

**Pourquoi c'est important :**
C'est l'évaluation finale qui teste TOUT. Si elle passe, le skill fonctionne parfaitement.

**Critères de qualité :**
```python
# ✅ Code FALC : même un débutant peut comprendre

# Nom de variable explicite qui raconte une histoire
blog_posts_published_and_visible_to_current_user = BlogPost.objects.filter(
    is_published=True,
    is_draft=False
).select_related('author')

# Évite les comprehensions complexes
# ❌ Mauvais
results = [p.title for p in posts if p.published and len(p.title) > 10]

# ✅ Bon (for loop simple et verbeux)
blog_post_titles_that_are_long_enough = []
for blog_post in blog_posts_published_and_visible_to_current_user:
    post_is_published = blog_post.is_published
    post_title_is_long_enough = len(blog_post.title) > 10
    
    if post_is_published and post_title_is_long_enough:
        blog_post_titles_that_are_long_enough.append(blog_post.title)
```

---

## 🎯 Comment Utiliser Ces Évaluations

### Option 1 : Évaluation Manuelle
1. Ouvrez le fichier `evals.json`
2. Copiez le prompt d'une évaluation
3. Testez avec Claude en activant le skill
4. Vérifiez manuellement les expectations

### Option 2 : Avec skill-creator (Automatisé)
```bash
# Lancer une évaluation spécifique
claude --skill skill-creator "Run eval 1 on django-htmx-readable"

# Lancer toutes les évaluations
claude --skill skill-creator "Run all evals on django-htmx-readable"

# Comparer avec/sans le skill
claude --skill skill-creator "Benchmark django-htmx-readable"
```

---

## 📊 Interprétation des Résultats

### ✅ Succès
Si toutes les expectations passent, le skill :
- Produit du code lisible et maintenable
- Respecte les patterns Django + HTMX
- Suit la philosophie "readable first"

### ⚠️ Échecs Fréquents
- **Eval 1** : Utilisation de ModelViewSet au lieu de ViewSet
- **Eval 2** : Utilisation de Django Forms au lieu de DRF Serializers
- **Eval 4** : Retour de JSON au lieu de HTML pour HTMX
- **Eval 5** : Oubli de sauvegarder les données avant suppression

### 🔄 Amélioration Itérative
Si des evals échouent :
1. Identifiez les expectations qui ont échoué
2. Modifiez le skill pour corriger le problème
3. Relancez les evals
4. Répétez jusqu'à 100% de réussite

---

## 🚀 Prochaines Étapes

Une fois ces évaluations en place, vous pouvez :

1. **Tester le skill** : Lancez les evals pour voir comment le skill performe
2. **Améliorer le skill** : Utilisez les résultats pour identifier les faiblesses
3. **Ajouter des evals** : Créez de nouvelles évaluations pour couvrir plus de cas
4. **Benchmark** : Comparez les performances avec/sans le skill

---

## 📚 Ressources

- **Skill principal** : `/mnt/skills/user/django-htmx-readable/SKILL.md`
- **Évaluations** : `evals/evals.json`
- **Documentation skill-creator** : `/mnt/skills/examples/skill-creator/SKILL.md`

---

## ✨ Philosophie FALC

Ces évaluations suivent la philosophie **FALC** (Facile À Lire et à Comprendre) :

- **Noms de variables** : Racontent une histoire complète
- **Commentaires bilingues** : Expliquent le "pourquoi" ET le "quoi"
- **Code linéaire** : Pas besoin de sauter entre 5 fichiers
- **Logique explicite** : Évite la "magie" et les abstractions cachées
- **For loops simples** : Plutôt que des comprehensions complexes

Cette approche rend le code accessible même aux développeurs débutants. 🎓
