# Section "Administration" multi-tenant — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher sur "Mon compte" la liste des tenants administrables avec nom + domaine, en remplacement du bouton unique "Panneau d'administration".

**Architecture:** Ajouter `tenants_admin` dans le contexte de `MyAccount.list()`, itérer dessus dans les templates reunion et HTMX. Aucune migration, aucun nouveau modèle.

**Tech Stack:** Django, HTMX, Bootstrap 5, django-tenants

**Spec:** `docs/superpowers/specs/2026-04-01-admin-tenants-mon-compte-design.md`

---

### Task 1 : Ajouter `tenants_admin` dans le contexte de la vue

**Files:**
- Modify: `BaseBillet/views.py:722-733` (méthode `MyAccount.list()`)

- [ ] **Step 1 : Lire le code actuel**

Vérifier que `MyAccount.list()` ressemble bien à :

```python
def list(self, request: HttpRequest):
    template_context = get_context(request)
    template_context['header'] = False
    template_context['account_tab'] = 'index'

    if not request.user.email_valid:
        logger.warning("User email not active")
        messages.add_message(request, messages.WARNING,
                             _("Please validate your email to access all the features of your profile area."))

    return render(request, "reunion/views/account/index.html", context=template_context)
```

- [ ] **Step 2 : Ajouter la logique `tenants_admin`**

Modifier `MyAccount.list()` dans `BaseBillet/views.py`. Ajouter le bloc suivant **entre** `template_context['account_tab'] = 'index'` et le `if not request.user.email_valid` :

```python
        # Liste des tenants que l'utilisateur peut administrer
        # / List of tenants the user can administer
        user = request.user
        if user.is_superuser:
            # Superuser : un seul bouton pour le tenant courant
            # / Superuser: single button for current tenant only
            current_tenant = connection.tenant
            tenants_admin = Client.objects.filter(
                pk=current_tenant.pk
            ).prefetch_related('domains')
        else:
            tenants_admin = user.client_admin.prefetch_related('domains').all()

        template_context['tenants_admin'] = tenants_admin
```

Vérifier que les imports nécessaires sont présents en haut du fichier :
- `from django.db import connection` — déjà importé (utilisé dans `get_context`)
- `from Customers.models import Client` — déjà importé (utilisé dans `get_context` ligne 157)

- [ ] **Step 3 : Vérifier que le serveur démarre sans erreur**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`
Expected: `System check identified no issues.`

- [ ] **Step 4 : Commit**

```bash
git add BaseBillet/views.py
git commit -m "feat(account): add tenants_admin to MyAccount context"
```

---

### Task 2 : Modifier le template reunion (grille de boutons)

**Files:**
- Modify: `BaseBillet/templates/reunion/views/account/index.html:50-57`

- [ ] **Step 1 : Lire le template actuel**

Le bloc admin actuel (lignes 50-57) est :

```html
{% if user|can_admin %}
<div class="col">
    <a class="w-100 btn btn-lg btn-outline-danger" href="/admin/" target="_blank">
        <i class="bi bi-key-fill fs-1"></i>
        <span class="d-block">{% trans 'Admin panel' %}</span>
    </a>
{% endif %}
</div>
```

- [ ] **Step 2 : Remplacer par la section "Administration"**

Remplacer le bloc ci-dessus (lignes 50-57, du `{% if user|can_admin %}` jusqu'au `</div>` qui ferme le col) par :

```html
</div>

{% if tenants_admin %}
<div class="row row-cols-1 row-cols-md-2 g-3 text-center mb-3">
    <div class="col-12">
        <hr class="text-danger">
        <h5 class="text-danger mb-0">
            <i class="bi bi-key-fill me-1" aria-hidden="true"></i>{% trans 'Administration' %}
        </h5>
    </div>
    {% for tenant in tenants_admin %}
    <div class="col">
        <a class="w-100 btn btn-lg btn-outline-danger"
           href="https://{{ tenant.get_primary_domain.domain }}/admin/"
           target="_blank">
            <i class="bi bi-key-fill fs-1" aria-hidden="true"></i>
            <span class="d-block">{{ tenant.name }}</span>
            <small class="d-block text-muted">{{ tenant.get_primary_domain.domain }}</small>
        </a>
    </div>
    {% endfor %}
</div>
{% endif %}

<div class="row row-cols-1 row-cols-md-2 g-3 text-center mb-3">
```

**Attention :** cette modification ferme la grille existante (`</div>`), insère la section admin, puis rouvre une nouvelle grille pour le bouton "Se déconnecter". Le template complet après modification doit être :

```html
{% extends 'reunion/account_base.html' %}
{% load static i18n tibitags %}

{% block title %}{% translate 'My account' %}{% endblock %}

{% block account_page %}
<div class="row row-cols-1 row-cols-md-2 g-3 text-center mb-3">
    <div class="col">
        <a class="w-100 btn btn-lg btn-outline-primary{% if account_tab == 'balance' %} active" aria-current="page{% endif %}"
            href="/my_account/balance/">
            <i class="bi bi-piggy-bank-fill fs-1"></i>
            <span class="d-block">{% trans 'My wallet' %}</span>
        </a>
    </div>
    <div class="col">
        <a class="w-100 btn btn-lg btn-outline-secondary{% if account_tab == 'memberships' %} active" aria-current="page{% endif %}"
            href="/my_account/membership/">
            <i class="bi bi-person-badge-fill fs-1"></i>
            <span class="d-block">{% trans 'My subscriptions' %}</span>
        </a>
    </div>
    <div class="col">
        <a class="w-100 btn btn-lg btn-outline-secondary{% if account_tab == 'reservations' %} active" aria-current="page{% endif %}"
            href="/my_account/my_reservations/">
            <i class="bi bi-ticket-perforated-fill fs-1"></i>
            <span class="d-block">{% trans 'My bookings' %}</span>
        </a>
    </div>
    <div class="col">
        <a class="w-100 btn btn-lg btn-outline-secondary{% if account_tab == 'card' %} active" aria-current="page{% endif %}"
            href="/my_account/card/">
            <i class="bi bi-postcard-fill fs-1"></i>
            <span class="d-block">{% trans 'My Pass card' %}</span>
        </a>
    </div>
    <div class="col">
        <a class="w-100 btn btn-lg btn-outline-secondary{% if account_tab == 'profile' %} active" aria-current="page{% endif %}"
            href="/my_account/profile/">
            <i class="bi bi-gear-fill fs-1"></i>
            <span class="d-block">{% trans 'My settings' %}</span>
        </a>
    </div>
</div>

{% if tenants_admin %}
<div class="row row-cols-1 row-cols-md-2 g-3 text-center mb-3">
    <div class="col-12">
        <hr class="text-danger">
        <h5 class="text-danger mb-0">
            <i class="bi bi-key-fill me-1" aria-hidden="true"></i>{% trans 'Administration' %}
        </h5>
    </div>
    {% for tenant in tenants_admin %}
    <div class="col">
        <a class="w-100 btn btn-lg btn-outline-danger"
           href="https://{{ tenant.get_primary_domain.domain }}/admin/"
           target="_blank">
            <i class="bi bi-key-fill fs-1" aria-hidden="true"></i>
            <span class="d-block">{{ tenant.name }}</span>
            <small class="d-block text-muted">{{ tenant.get_primary_domain.domain }}</small>
        </a>
    </div>
    {% endfor %}
</div>
{% endif %}

<div class="row row-cols-1 g-3 text-center mb-3">
    <div class="col">
        <a class="w-100 btn btn-lg btn-outline-secondary" href="/deconnexion/">
            <i class="bi bi-box-arrow-right fs-1"></i>
            <span class="d-block">{% trans 'Log out' %}</span>
        </a>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 3 : Vérifier visuellement dans le navigateur**

Ouvrir `/my_account/` dans le navigateur et vérifier :
1. Les boutons perso sont inchangés (icônes, libellés)
2. La section "Administration" apparaît entre les boutons perso et "Se déconnecter"
3. Chaque tenant a un bouton rouge avec nom + domaine
4. Cliquer un bouton admin ouvre `/admin/` du bon domaine dans un nouvel onglet

- [ ] **Step 4 : Commit**

```bash
git add BaseBillet/templates/reunion/views/account/index.html
git commit -m "feat(account): replace single admin button with per-tenant admin section"
```

---

### Task 3 : Modifier le template HTMX (header du wizard)

**Files:**
- Modify: `BaseBillet/templates/htmx/views/my_account/my_account.html:22-24`

- [ ] **Step 1 : Lire le code actuel**

Le bloc admin actuel (lignes 22-24) est :

```html
{% elif profile.admin_this_tenant %}
    <p><a href="/admin">{% translate "Administration" %}</a></p>
{% endif %}
```

- [ ] **Step 2 : Remplacer par la liste des tenants**

Remplacer les lignes 22-24 par :

```html
{% endif %}
{% if tenants_admin %}
    <p><strong>{% translate "Administration" %}</strong></p>
    {% for tenant in tenants_admin %}
    <p>
        <a href="https://{{ tenant.get_primary_domain.domain }}/admin/"
           target="_blank">
            {{ tenant.name }}
            <small class="text-muted">({{ tenant.get_primary_domain.domain }})</small>
        </a>
    </p>
    {% endfor %}
{% endif %}
```

**Attention :** le `{% endif %}` de la ligne 24 d'origine (qui fermait le `{% if not user.email_valid %}...{% elif %}`) est remplacé. Le premier `{% endif %}` ferme le bloc email validation, puis un nouveau `{% if tenants_admin %}` ouvre la section admin.

Le header complet après modification (lignes 13-26) :

```html
<h3 class="creation-title">{{ user.email }}</h3>

{% if not user.email_valid %}
    <p>{% translate "Please validate your email for activate your account." %}</p>
    <a aria-label="{% translate "Resend validation email" %}"
       href=""
       hx-get="/my_account/resend_activation_email/">
        {% translate "Resend validation email" %}
    </a>
{% endif %}
{% if tenants_admin %}
    <p><strong>{% translate "Administration" %}</strong></p>
    {% for tenant in tenants_admin %}
    <p>
        <a href="https://{{ tenant.get_primary_domain.domain }}/admin/"
           target="_blank">
            {{ tenant.name }}
            <small class="text-muted">({{ tenant.get_primary_domain.domain }})</small>
        </a>
    </p>
    {% endfor %}
{% endif %}
<p class="mt-2"><a href="/deconnexion">{% translate "Se deconnecter" %}</a></p>
```

- [ ] **Step 3 : Ajouter `tenants_admin` au contexte du template HTMX**

Vérifier quelle vue sert ce template. Chercher dans `BaseBillet/views.py` la vue qui rend `htmx/views/my_account/my_account.html`. Si elle utilise `get_context()` (qui ne contient pas `tenants_admin`), il faut aussi y ajouter la variable.

Si c'est `MyAccount.list()` qui sert ce template (via détection `request.htmx`), la variable est déjà présente (Task 1). Sinon, ajouter la même logique dans la vue concernée.

- [ ] **Step 4 : Vérifier visuellement**

Tester le template HTMX en accédant à `/my_account/` dans un contexte HTMX (navigation interne de l'app).

- [ ] **Step 5 : Commit**

```bash
git add BaseBillet/templates/htmx/views/my_account/my_account.html
git commit -m "feat(account): show tenant admin links in HTMX account header"
```

---

### Task 4 : Adapter `account_base.html` (indication "Administrateur")

**Files:**
- Modify: `BaseBillet/templates/reunion/account_base.html:9-11`

- [ ] **Step 1 : Lire le code actuel**

Ligne 9-11 de `account_base.html` :

```html
{% if profile.admin_this_tenant %}
    <span class="text-danger">{% trans 'Administrator' %}</span>
{% endif %}
```

Ce bloc ne montre "Administrateur" que si l'utilisateur est admin du tenant **courant**. Avec la nouvelle section, cette indication reste utile (elle dit "tu es admin **ici**"). On la garde telle quelle — pas de changement.

- [ ] **Step 2 : Vérifier la cohérence**

Confirmer que :
1. Un user admin du tenant courant voit "Administrateur" sous son email ET la section admin avec ses tenants
2. Un user admin d'autres tenants (pas le courant) voit la section admin MAIS PAS "Administrateur"
3. Un user non-admin ne voit ni l'un ni l'autre

Aucun code à modifier. Cette task est une vérification.

---

### Task 5 : Traductions i18n

**Files:**
- Modify: `locale/fr/LC_MESSAGES/django.po`
- Modify: `locale/en/LC_MESSAGES/django.po`

- [ ] **Step 1 : Extraire les nouvelles chaînes**

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
```

- [ ] **Step 2 : Vérifier les chaînes**

La seule nouvelle chaîne est `"Administration"` (déjà utilisée dans le template HTMX actuel). Vérifier dans les `.po` qu'elle a une traduction correcte. Si c'est une nouvelle entrée :

Dans `locale/fr/LC_MESSAGES/django.po` :
```
msgid "Administration"
msgstr "Administration"
```

Dans `locale/en/LC_MESSAGES/django.po` :
```
msgid "Administration"
msgstr "Administration"
```

- [ ] **Step 3 : Compiler**

```bash
docker exec lespass_django poetry run django-admin compilemessages
```

- [ ] **Step 4 : Commit**

```bash
git add locale/
git commit -m "chore(i18n): update translations for admin section"
```
