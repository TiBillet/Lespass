# HTMX Patterns — Interactions Courantes

Collection de patterns HTMX pour les interactions dynamiques.

---

## Pattern 1: Recherche en Temps Reel

```html
<!-- Template: articles/list.html -->

<!-- Champ de recherche avec debounce -->
<!-- Search field with debounce -->
<input 
    type="search"
    name="q"
    placeholder="Rechercher un article... / Search articles..."
    hx-get="{% url 'article-search' %}"
    hx-trigger="keyup changed delay:300ms, search"
    hx-target="#search-results"
    hx-indicator="#search-loading"
    autocomplete="off"
>

<!-- Indicateur de chargement -->
<!-- Loading indicator -->
<div id="search-loading" class="htmx-indicator">
    <span>Chargement... / Loading...</span>
</div>

<!-- Resultats injectes ici -->
<!-- Results injected here -->
<div id="search-results">
    {% include "articles/partials/search_results.html" %}
</div>
```

**Partiel: `articles/partials/search_results.html`**
```html
{% if articles %}
    <ul class="article-list">
        {% for article in articles %}
            <li>
                <a href="{% url 'article-detail' pk=article.uuid %}">
                    {{ article.title }}
                </a>
            </li>
        {% endfor %}
    </ul>
    <p>{{ count }} resultat(s) pour "{{ query }}"</p>
{% else %}
    <p class="text-muted">
        {% if query %}
            Aucun resultat pour "{{ query }}" / No results for "{{ query }}"
        {% else %}
            Commencez a taper pour rechercher / Start typing to search
        {% endif %}
    </p>
{% endif %}
```

---

## Pattern 2: Bouton avec Confirmation

```html
<!-- Suppression avec confirmation SweetAlert2 -->
<!-- Delete with SweetAlert2 confirmation -->

<button 
    class="btn btn-danger"
    hx-delete="{% url 'article-delete' pk=article.uuid %}"
    hx-confirm="Supprimer '{{ article.title }}' ? / Delete '{{ article.title }}'?"
    hx-target="body"
    hx-swap="innerHTML"
>
    Supprimer / Delete
</button>

<!-- 
    hx-confirm utilise la boite de dialogue native.
    Pour SweetAlert2 personnalise, utiliser l'evenement htmx:confirm
-->
```

**JavaScript pour SweetAlert2 personnalise:**
```javascript
// Dans le template de base / In base template
document.body.addEventListener('htmx:confirm', function(evt) {
    // Ne pas afficher la confirmation native
    // Don't show native confirmation
    evt.preventDefault();
    
    const message = evt.detail.question;
    const element = evt.detail.elt;
    
    Swal.fire({
        title: 'Confirmer ? / Confirm?',
        text: message,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Oui / Yes',
        cancelButtonText: 'Non / No'
    }).then((result) => {
        if (result.isConfirmed) {
            // Proceder avec la requete HTMX
            // Proceed with HTMX request
            evt.detail.issueRequest(true);
        }
    });
});
```

---

## Pattern 3: Infinite Scroll (Chargement au Defilement)

```html
<!-- Template: articles/list.html -->

<div id="articles-container">
    {% include "articles/partials/article_list_items.html" %}
</div>

<!-- Declencheur de chargement automatique -->
<!-- Auto-load trigger -->
{% if articles_page.has_next %}
    <div 
        id="load-more-trigger"
        hx-get="{% url 'article-list' %}?page={{ articles_page.next_page_number }}"
        hx-trigger="revealed"
        hx-target="#articles-container"
        hx-swap="beforeend"
        hx-select="#articles-container > *"
    >
        <span class="htmx-indicator">Chargement... / Loading...</span>
    </div>
{% endif %}
```

**Partiel: `articles/partials/article_list_items.html`**
```html
{% for article in articles_page %}
    <article class="article-card">
        <h3>{{ article.title }}</h3>
        <p>{{ article.excerpt }}</p>
        <a href="{% url 'article-detail' pk=article.uuid %}">Lire / Read</a>
    </article>
{% endfor %}
```

---

## Pattern 4: Formulaire avec Validation en Ligne

```html
<!-- Formulaire qui remplace lui-meme en cas d'erreur -->
<!-- Form that replaces itself on error -->

<form 
    id="comment-form"
    hx-post="{% url 'comment-create' %}"
    hx-target="#comment-form"
    hx-swap="outerHTML"
>
    {% csrf_token %}
    
    <div class="mb-3">
        <label for="author_name">Nom / Name</label>
        <input 
            type="text" 
            id="author_name" 
            name="author_name" 
            value="{{ form_data.author_name }}"
            class="{% if form_errors.author_name %}is-invalid{% endif %}"
        >
        {% if form_errors.author_name %}
            <div class="invalid-feedback">
                {{ form_errors.author_name.0 }}
            </div>
        {% endif %}
    </div>
    
    <div class="mb-3">
        <label for="content">Commentaire / Comment</label>
        <textarea 
            id="content" 
            name="content"
            class="{% if form_errors.content %}is-invalid{% endif %}"
        >{{ form_data.content }}</textarea>
        {% if form_errors.content %}
            <div class="invalid-feedback">
                {{ form_errors.content.0 }}
            </div>
        {% endif %}
    </div>
    
    <button type="submit">Envoyer / Send</button>
</form>
```

**Controller pour retourner le formulaire ou le succes:**
```python
def create(self, request):
    serializer = CommentSerializer(data=request.POST)
    
    if serializer.is_valid():
        comment = serializer.save()
        # Retourne un nouveau formulaire vide
        # Return empty form
        return render(request, "comments/partials/form.html", {
            'success_message': 'Commentaire ajoute / Comment added'
        })
    
    # Retourne le formulaire avec erreurs
    # Return form with errors
    return render(request, "comments/partials/form.html", {
        'form_errors': serializer.errors,
        'form_data': request.POST
    }, status=400)
```

---

## Pattern 5: Navigation Liste-Detail sans Blink

```html
<!-- Template: articles/list.html -->

<div class="layout-two-columns">
    <!-- Liste a gauche -->
    <!-- List on left -->
    <aside class="article-list">
        {% for article in articles %}
            <a 
                href="{% url 'article-detail' pk=article.uuid %}"
                hx-get="{% url 'article-detail' pk=article.uuid %}"
                hx-target="body"
                hx-swap="innerHTML"
                hx-push-url="true"
                class="article-item {% if current_article.uuid == article.uuid %}active{% endif %}"
            >
                {{ article.title }}
            </a>
        {% endfor %}
    </aside>
    
    <!-- Detail a droite -->
    <!-- Detail on right -->
    <main class="article-detail">
        <h1>{{ current_article.title }}</h1>
        <div class="content">
            {{ current_article.content|linebreaks }}
        </div>
    </main>
</div>
```

---

## Pattern 6: Tabs Dynamiques

```html
<!-- Onglets -->
<!-- Tabs -->
<div class="tabs">
    <button 
        class="tab-btn active"
        hx-get="{% url 'product-tab' tab='info' %}"
        hx-target="#tab-content"
        hx-swap="innerHTML"
    >
        Informations
    </button>
    <button 
        class="tab-btn"
        hx-get="{% url 'product-tab' tab='reviews' %}"
        hx-target="#tab-content"
        hx-swap="innerHTML"
    >
        Avis ({{ review_count }})
    </button>
    <button 
        class="tab-btn"
        hx-get="{% url 'product-tab' tab='specs' %}"
        hx-target="#tab-content"
        hx-swap="innerHTML"
    >
        Specifications
    </button>
</div>

<!-- Contenu de l'onglet -->
<!-- Tab content -->
<div id="tab-content">
    {% include "products/partials/tab_info.html" %}
</div>

<!-- JavaScript pour gerer l'etat actif -->
<script>
    document.body.addEventListener('htmx:afterSwap', function(evt) {
        if (evt.detail.target.id === 'tab-content') {
            // Met a jour les classes actives des boutons
            // Update active button classes
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // Trouve le bouton qui a declenche la requete
            // Find button that triggered request
            const triggeredBy = evt.detail.requestConfig.elt;
            triggeredBy.classList.add('active');
        }
    });
</script>
```

---

## Pattern 7: Toasts/Messages Globaux

**Dans le template de base:**
```html
<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
    
    <!-- Contenu principal -->
    <!-- Main content -->
    {% block content %}{% endblock %}
    
    <!-- SweetAlert2 pour les toasts -->
    <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
    <script>
        // Ecouteur pour les toasts declenches par le serveur
        // Listener for server-triggered toasts
        document.body.addEventListener('toast', function(evt) {
            const items = evt.detail.items || [];
            
            items.forEach(function(item) {
                const iconMap = {
                    'success': 'success',
                    'info': 'info',
                    'warning': 'warning',
                    'error': 'error',
                    'debug': 'info'
                };
                
                Swal.fire({
                    toast: true,
                    position: 'top-end',
                    icon: iconMap[item.level] || 'info',
                    title: item.text,
                    showConfirmButton: false,
                    timer: 3000,
                    timerProgressBar: true
                });
            });
        });
        
        // Ecouteur pour les redirections declenchees par le serveur
        // Listener for server-triggered redirects
        document.body.addEventListener('redirect', function(evt) {
            window.location.href = evt.detail.url;
        });
    </script>
</body>
```

**Controller pour envoyer un toast:**
```python
def update(self, request, pk=None):
    article = get_object_or_404(Article, uuid=pk)
    
    # ... logique de mise a jour ...
    # ... update logic ...
    
    messages.add_message(request, messages.SUCCESS, 'Mis a jour! / Updated!')
    
    # Si requete HTMX, envoie le toast
    # If HTMX request, send toast
    if request.headers.get('HX-Request'):
        messages_list = get_messages(request)
        toast_payload = [
            {"level": m.level_tag, "text": str(m)} 
            for m in messages_list
        ]
        
        response = render(request, "articles/partials/detail_content.html", {
            'article': article
        })
        response["HX-Trigger"] = json.dumps({"toast": {"items": toast_payload}})
        return response
    
    return redirect('article-detail', pk=article.uuid)
```

---

## Pattern 8: Indicateurs de Chargement

```html
<!-- Bouton avec spinner lors du chargement -->
<!-- Button with spinner during loading -->
<button 
    hx-post="{% url 'like-article' pk=article.uuid %}"
    hx-target="#like-count"
    hx-swap="innerHTML"
    hx-disabled-elt="this"
>
    <span class="default-text">❤ J'aime</span>
    <span class="loading-text htmx-indicator">
        <span class="spinner"></span> Envoi...
    </span>
</button>

<span id="like-count">{{ article.like_count }}</span>
```

```css
/* Masque l'indicateur par defaut */
/* Hide indicator by default */
.htmx-indicator {
    display: none;
}

/* Affiche quand HTMX est en cours */
/* Show when HTMX is processing */
.htmx-request .htmx-indicator,
.htmx-request.htmx-indicator {
    display: inline;
}

/* Cache le texte par defaut pendant le chargement */
/* Hide default text during loading */
.htmx-request .default-text {
    display: none;
}
```

---

## Pattern 9: Polling (Mises a Jour en Temps Reel)

```html
<!-- Notifications qui se rafraichissent automatiquement -->
<!-- Auto-refreshing notifications -->

<div 
    id="notifications"
    hx-get="{% url 'notifications-partial' %}"
    hx-trigger="every 30s"
    hx-swap="innerHTML"
>
    {% include "notifications/partials/list.html" %}
</div>
```

---

## Pattern 10: Upload de Fichier avec Progression

```html
<!-- Formulaire d'upload avec barre de progression -->
<!-- Upload form with progress bar -->

<form 
    id="upload-form"
    hx-post="{% url 'file-upload' %}"
    hx-encoding="multipart/form-data"
    hx-target="#upload-result"
    hx-swap="innerHTML"
>
    {% csrf_token %}
    <input type="file" name="file" required>
    <button type="submit">Uploader / Upload</button>
    
    <!-- Barre de progression -->
    <!-- Progress bar -->
    <div class="progress-wrapper htmx-indicator">
        <progress id="upload-progress" value="0" max="100"></progress>
        <span id="upload-percent">0%</span>
    </div>
</form>

<div id="upload-result"></div>

<script>
    // Mise a jour de la barre de progression
    // Update progress bar
    htmx.on('#upload-form', 'htmx:xhr:progress', function(evt) {
        const percent = (evt.detail.loaded / evt.detail.total) * 100;
        document.getElementById('upload-progress').value = percent;
        document.getElementById('upload-percent').innerText = Math.round(percent) + '%';
    });
</script>
```
