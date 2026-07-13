# 📋 Evaluation Guide for django-htmx-readable

This document explains the 6 evaluations created to test the "django-htmx-readable" skill.

## 🎯 Evaluation Objectives

Each evaluation tests a specific aspect of the skill to ensure it produces code that is:
- ✅ **Readable** - Easy for humans to understand
- ✅ **Explicit** - No hidden Django "magic"
- ✅ **Verbose** - Variable names that explain their content
- ✅ **Bilingual** - Comments in French AND English
- ✅ **Compliant** - Follows skill patterns (ViewSet, DRF Serializers, HTMX)

---

## 📝 Details of the 6 Evaluations

### Eval 1️⃣ : Basic ViewSet
**What is tested:**
- Creating a ViewSet with `viewsets.ViewSet` (not ModelViewSet)
- Explicit `list()` and `retrieve()` methods
- Explicit SQL queries with select_related
- Use of `get_object_or_404()`
- Verbose variable names

**Why it matters:**
This is the foundation of the skill. If the ViewSet isn't explicit, everything else will fail.

**Expected variable naming example:**
```python
# ❌ Bad (too short)
products = Product.objects.filter(in_stock=True)

# ✅ Good (explicit)
products_available_in_stock_for_display = Product.objects.filter(in_stock=True)
```

---

### Eval 2️⃣ : Validation with DRF Serializers
**What is tested:**
- Use of `serializers.Serializer` (never Django Forms)
- Bilingual FR/EN error messages
- Custom validation with `validate_<field>()`
- Explicit `create()` method

**Why it matters:**
The skill FORBIDS Django Forms. This eval verifies the code properly uses DRF for validation.

**Anti-pattern detected:**
```python
# ❌ FORBIDDEN by the skill
from django import forms
class ProductForm(forms.ModelForm):
    ...

# ✅ CORRECT
from rest_framework import serializers
class ProductCreateSerializer(serializers.Serializer):
    ...
```

---

### Eval 3️⃣ : HTMX Integration
**What is tested:**
- Correct HTMX attributes: `hx-get`, `hx-target`, `hx-swap`
- CSRF token for HTMX requests
- Container with ID to receive dynamic content
- Django URLs with `{% url %}`
- Bilingual FR/EN comments

**Why it matters:**
HTMX is at the core of the skill. Code must generate server-rendered HTML, not JSON.

**Expected pattern:**
```html
<!-- ✅ Good: HTMX loading with fallback -->
<button 
    hx-get="{% url 'product-detail' pk=product.id %}"
    hx-target="#product-container"
    hx-swap="innerHTML"
>
    View details
</button>

<div id="product-container">
    <!-- Content will be injected here -->
    <!-- Le contenu sera injecté ici -->
</div>
```

---

### Eval 4️⃣ : Custom Actions (@action)
**What is tested:**
- Use of `@action` decorator
- Explicit logic with if/else (no one-liner)
- Ultra-verbose variable names
- Return HTML partials (not JSON)
- Use of `save(update_fields=[...])`

**Why it matters:**
Custom actions are common in Django. The skill must produce explicit and traceable code.

**Expected pattern:**
```python
@action(detail=True, methods=["POST"])
def mark_as_promotion(self, request, pk=None):
    """
    Mark a product as on promotion.
    Marquer un produit en promotion.
    """
    product = get_object_or_404(Product, uuid=pk)
    
    # Explicit check, no one-liner
    # Vérification explicite, pas de one-liner
    product_already_in_promotion = product.is_promotion
    
    if product_already_in_promotion:
        return render(request, "products/partials/already_promotion.html", {
            'product': product
        })
    
    # Explicit update
    # Mise à jour explicite
    product.is_promotion = True
    product.promotion_started_at = timezone.now()
    product.save(update_fields=['is_promotion', 'promotion_started_at'])
    
    return render(request, "products/partials/promotion_badge.html", {
        'product': product
    })
```

---

### Eval 5️⃣ : Toast Notifications
**What is tested:**
- Use of Django `messages` framework
- Explicit variable to save data BEFORE deletion
- HTMX `HX-Trigger` header with JSON payload
- Minimal JavaScript code to listen for the event
- Correct data structure for toasts

**Why it matters:**
Notifications are essential for UX. The skill must show how to implement them cleanly with HTMX.

**Expected pattern:**
```python
def delete(self, request, pk=None):
    product = get_object_or_404(Product, uuid=pk)
    
    # ✅ Explicit variable BEFORE deletion
    # Variable explicite AVANT suppression
    product_title_for_notification_message = product.title
    
    product.delete()
    
    messages.add_message(
        request,
        messages.SUCCESS,
        f'"{product_title_for_notification_message}" has been deleted / a été supprimé'
    )
    
    # Get messages for toast
    # Récupération des messages pour le toast
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

### Eval 6️⃣ : Complete CRUD ViewSet
**What is tested:**
- Complete ViewSet with list(), retrieve(), create(), update()
- Search action with `@action(detail=False)`
- `select_related()` to optimize queries
- Validation via serializer
- Explicit error handling
- Ultra-verbose variable names
- Bilingual docstrings
- Easy-to-read code

**Why it matters:**
This is the final evaluation that tests EVERYTHING. If it passes, the skill works perfectly.

**Quality criteria:**
```python
# ✅ Easy-to-read code: even a beginner can understand

# Explicit variable name that tells a story
blog_posts_published_and_visible_to_current_user = BlogPost.objects.filter(
    is_published=True,
    is_draft=False
).select_related('author')

# Avoid complex comprehensions
# ❌ Bad
results = [p.title for p in posts if p.published and len(p.title) > 10]

# ✅ Good (simple and verbose for loop)
blog_post_titles_that_are_long_enough = []
for blog_post in blog_posts_published_and_visible_to_current_user:
    post_is_published = blog_post.is_published
    post_title_is_long_enough = len(blog_post.title) > 10
    
    if post_is_published and post_title_is_long_enough:
        blog_post_titles_that_are_long_enough.append(blog_post.title)
```

---

## 🎯 How to Use These Evaluations

### Option 1: Manual Evaluation
1. Open the `evals.json` file
2. Copy an evaluation prompt
3. Test with Claude with the skill enabled
4. Manually verify the expectations

### Option 2: With skill-creator (Automated)
```bash
# Run a specific evaluation
claude --skill skill-creator "Run eval 1 on django-htmx-readable"

# Run all evaluations
claude --skill skill-creator "Run all evals on django-htmx-readable"

# Compare with/without the skill
claude --skill skill-creator "Benchmark django-htmx-readable"
```

---

## 📊 Interpreting Results

### ✅ Success
If all expectations pass, the skill:
- Produces readable and maintainable code
- Respects Django + HTMX patterns
- Follows the "readable first" philosophy

### ⚠️ Common Failures
- **Eval 1**: Using ModelViewSet instead of ViewSet
- **Eval 2**: Using Django Forms instead of DRF Serializers
- **Eval 4**: Returning JSON instead of HTML for HTMX
- **Eval 5**: Forgetting to save data before deletion

### 🔄 Iterative Improvement
If evals fail:
1. Identify which expectations failed
2. Modify the skill to fix the issue
3. Re-run the evals
4. Repeat until 100% success

---

## 🚀 Next Steps

Once these evaluations are in place, you can:

1. **Test the skill**: Run the evals to see how the skill performs
2. **Improve the skill**: Use results to identify weaknesses
3. **Add evals**: Create new evaluations to cover more cases
4. **Benchmark**: Compare performance with/without the skill

---

## 📚 Resources

- **Main skill**: `/mnt/skills/user/django-htmx-readable/SKILL.md`
- **Evaluations**: `evals/evals.json`
- **skill-creator documentation**: `/mnt/skills/examples/skill-creator/SKILL.md`

---

## ✨ Easy-to-Read Philosophy

These evaluations follow the **Easy-to-Read** philosophy:

- **Variable names**: Tell a complete story
- **Bilingual comments**: Explain the "why" AND the "what"
- **Linear code**: No need to jump between 5 files
- **Explicit logic**: Avoids "magic" and hidden abstractions
- **Simple for loops**: Rather than complex comprehensions

This approach makes code accessible even to beginner developers. 🎓
