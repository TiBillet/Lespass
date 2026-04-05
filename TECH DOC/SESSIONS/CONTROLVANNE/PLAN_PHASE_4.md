# Phase 4 — Templates + conformité djc controlvanne

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Le kiosk et la calibration sont conformes aux standards Lespass : nom du tenant (pas "Mike's Bar"), Bootstrap local (Pi hors-ligne), `data-testid`, `aria-*`, `{% translate %}`, JS externalisé, calibration dans l'admin Unfold. Le consumer ne référence plus `tb.monnaie` (champ supprimé en Phase 1).

**Architecture:** On corrige les templates existants sans les réécrire entièrement. Le JS du kiosk est externalisé dans un fichier statique. La calibration hérite du base admin Unfold. Le consumer et ws_payloads sont nettoyés des références à `monnaie`. Bootstrap 5.3 est copié dans les statics controlvanne pour fonctionner hors-ligne.

**Tech Stack:** Django templates, Bootstrap 5.3, HTMX 1.9, Django Channels (WebSocket), Unfold admin

**Spec de référence :** `TECH DOC/SESSIONS/CONTROLVANNE/SPEC_CONTROLVANNE.md` sections 2.14–2.17

**IMPORTANT :** Ne pas faire d'opérations git. Le mainteneur gère git.

---

## Vue d'ensemble des fichiers

| Fichier | Action | Rôle |
|---------|--------|------|
| `controlvanne/consumers.py` | Modifier | Supprimer `tb.monnaie`, remplacer par `"€"` |
| `controlvanne/ws_payloads.py` | Modifier | Supprimer champ `monnaie` |
| `controlvanne/signals.py` | Vérifier | S'assurer que `monnaie` n'est pas référencé |
| `controlvanne/templates/base.html` | Réécrire | Nom tenant, Bootstrap local, `{% load i18n static %}`, `data-testid` |
| `controlvanne/templates/controlvanne/panel_bootstrap.html` | Modifier | Supprimer `monnaie`, `data-testid`, `{% translate %}`, JS externalisé |
| `controlvanne/templates/controlvanne/index.html` | Supprimer | Doublon de panel_bootstrap (ancienne version légère) |
| `controlvanne/templates/calibration/page.html` | Modifier | Hériter `admin/base_site.html`, `data-testid`, `{% translate %}` |
| `controlvanne/templates/calibration/partial_*.html` | Modifier | `data-testid` |
| `controlvanne/templates/admin/date_range_filter.html` | Modifier | `data-testid` |
| `controlvanne/static/controlvanne/js/panel_kiosk.js` | Créer | JS externalisé depuis panel_bootstrap.html |
| `controlvanne/static/controlvanne/css/bootstrap.min.css` | Créer | Bootstrap 5.3 CSS (copie locale) |
| `controlvanne/static/controlvanne/js/bootstrap.bundle.min.js` | Créer | Bootstrap 5.3 JS (copie locale) |

---

## Ordre des tâches

1. Consumer + ws_payloads : supprimer `monnaie`
2. Bootstrap local : copier les fichiers statiques
3. base.html : nom tenant, Bootstrap local, i18n
4. panel_bootstrap.html : supprimer `monnaie`, `data-testid`, externaliser JS
5. Supprimer index.html (doublon)
6. Calibration : hériter admin Unfold, `data-testid`
7. Partials calibration + filtre date : `data-testid`
8. Vérification finale

---

### Tâche 1 : Consumer + ws_payloads — supprimer monnaie

**Fichiers :**
- Modifier : `controlvanne/consumers.py` (ligne 85)
- Modifier : `controlvanne/ws_payloads.py` (ligne 24)

- [ ] **Step 1 : Modifier consumers.py**

Ligne 85, remplacer :
```python
            "monnaie": tb.monnaie,
```
par :
```python
            "currency": "€",
```

- [ ] **Step 2 : Modifier ws_payloads.py**

Ligne 24, remplacer :
```python
    monnaie: str               # Unité monétaire (ex: "patate", "€")
```
par :
```python
    currency: str              # Symbole monétaire, toujours "€" (ex-champ monnaie, supprimé en Phase 1)
```

- [ ] **Step 3 : Vérifier qu'il n'y a plus de référence à tb.monnaie**

```bash
docker exec lespass_django grep -rn "tb\.monnaie\|\.monnaie" /DjangoFiles/controlvanne/ --include="*.py" | grep -v "Pi/" | grep -v "__pycache__"
```

Attendu : aucun résultat (les templates seront corrigés dans les tâches suivantes).

- [ ] **Step 4 : Vérifier l'import du consumer**

```bash
docker exec lespass_django poetry run python -c "from controlvanne.consumers import PanelConsumer; print('OK')"
```

---

### Tâche 2 : Bootstrap local — copier les fichiers statiques

**Fichiers :**
- Créer : `controlvanne/static/controlvanne/css/bootstrap.min.css`
- Créer : `controlvanne/static/controlvanne/js/bootstrap.bundle.min.js`

Le kiosk Pi peut être hors-ligne. On copie Bootstrap 5.3.3 depuis le CDN vers les statics locaux.

- [ ] **Step 1 : Créer les répertoires**

```bash
mkdir -p /home/jonas/TiBillet/dev/Lespass/controlvanne/static/controlvanne/css
mkdir -p /home/jonas/TiBillet/dev/Lespass/controlvanne/static/controlvanne/js
```

- [ ] **Step 2 : Télécharger Bootstrap CSS**

```bash
curl -sL "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" \
  -o /home/jonas/TiBillet/dev/Lespass/controlvanne/static/controlvanne/css/bootstrap.min.css
```

- [ ] **Step 3 : Télécharger Bootstrap JS**

```bash
curl -sL "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" \
  -o /home/jonas/TiBillet/dev/Lespass/controlvanne/static/controlvanne/js/bootstrap.bundle.min.js
```

- [ ] **Step 4 : Vérifier les fichiers**

```bash
ls -la /home/jonas/TiBillet/dev/Lespass/controlvanne/static/controlvanne/css/bootstrap.min.css
ls -la /home/jonas/TiBillet/dev/Lespass/controlvanne/static/controlvanne/js/bootstrap.bundle.min.js
```

Les deux fichiers doivent exister et ne pas être vides.

---

### Tâche 3 : base.html — nom tenant, Bootstrap local, i18n

**Fichiers :**
- Réécrire : `controlvanne/templates/base.html`

- [ ] **Step 1 : Réécrire base.html**

```html
{% load i18n static %}
<!doctype html>
<html lang="{{ LANGUAGE_CODE|default:'fr' }}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{% block title %}{% translate "Tap panel" %}{% endblock %}</title>
  <link rel="stylesheet"
        href="{% static 'controlvanne/css/bootstrap.min.css' %}" />
  <style>
    body { background: #0b1116; color: #e6edf3; }
    .card { background: #fcfcfd; border: 1px solid #213040; }
    .stat { font-variant-numeric: tabular-nums; }
  </style>
  {% block head %}{% endblock %}
</head>
<body>
  <nav class="navbar navbar-dark bg-dark mb-3" data-testid="kiosk-navbar">
    <div class="container-fluid">
      <span class="navbar-brand" data-testid="kiosk-venue-name">
        {{ config.organisation|default:"TiBillet" }}
      </span>
      {% block nav_right %}{% endblock %}
    </div>
  </nav>
  <main class="container" role="main" data-testid="kiosk-main">
    {% block content %}{% endblock %}
  </main>

  <script src="{% static 'controlvanne/js/bootstrap.bundle.min.js' %}"></script>
  {% block scripts %}{% endblock %}
</body>
</html>
```

Note : `config` est l'objet `BaseBillet.Configuration.get_solo()` — il doit être injecté dans le contexte du template par la vue qui rend le kiosk. Si la vue n'injecte pas encore `config`, il faudra l'ajouter dans la vue kiosk (tâche 4).

- [ ] **Step 2 : Vérifier la syntaxe du template**

```bash
docker exec lespass_django poetry run python -c "
from django.template.loader import get_template
t = get_template('base.html')
print('OK:', t.origin)
"
```

---

### Tâche 4 : panel_bootstrap.html — supprimer monnaie, data-testid, externaliser JS

**Fichiers :**
- Modifier : `controlvanne/templates/controlvanne/panel_bootstrap.html`
- Créer : `controlvanne/static/controlvanne/js/panel_kiosk.js`

C'est la tâche la plus grosse. Le template kiosk actuel a :
- `b.monnaie` → remplacer par `"€"`
- Pas de `data-testid` → ajouter
- Pas de `{% translate %}` → ajouter sur les textes statiques
- ~270 lignes de JS inline → externaliser dans `panel_kiosk.js`
- Pas de `{% load i18n static %}` → ajouter
- `data-monnaie="{{ b.monnaie }}"` → supprimer (plus de champ monnaie)

- [ ] **Step 1 : Externaliser le JS dans panel_kiosk.js**

Créer `/home/jonas/TiBillet/dev/Lespass/controlvanne/static/controlvanne/js/panel_kiosk.js` avec le contenu du bloc `<script>` actuel de panel_bootstrap.html (lignes 148-418), mais en remplaçant :

1. `{{ slug_focus }}` par une lecture depuis `document.body.dataset.slugFocus` (on ajoutera `data-slug-focus` sur le body du template)
2. Toutes les occurrences de `monnaie` par `currency` (`"€"`)
3. Le `data-monnaie` n'est plus lu (supprimé du HTML)

Le JS reste identique dans sa logique — on le déplace sans le réécrire.

Modifications dans le JS :
- Ligne 279 : `const slugFocus = "{{ slug_focus }}";` → `const slugFocus = document.body.dataset.slugFocus || "all";`
- Ligne 184 `function updatePrix(c, prixLitre, monnaie)` → `function updatePrix(c, prixLitre)`
  - Lignes 186-191 : supprimer les `monnaie` et `mon`, remplacer par `"€"` en dur
  - `c.p25.textContent = (pL * 0.25).toFixed(2) + ' €';` etc.
- Supprimer `monnaieL` de l'objet cards
- Ligne 223 `updatePrix(cards[uuid], prixBlock.dataset.prixlitre, prixBlock.dataset.monnaie)` → `updatePrix(cards[uuid], prixBlock.dataset.prixlitre)`
- Ligne 356-358 : bloc `monnaie` → supprimer la condition `payload.monnaie`, simplifier

- [ ] **Step 2 : Modifier panel_bootstrap.html**

Le template modifié :
1. Ajouter `{% load i18n static %}` en haut
2. Remplacer `{% block title %}Chez Mike's Bar{% endblock %}` par `{% block title %}{{ config.organisation|default:"TiBillet" }}{% endblock %}`
3. Ajouter `data-slug-focus="{{ slug_focus }}"` sur le `<body>` ou un `<div>` racine — en fait, on étend `base.html` qui a déjà le `<body>`. Ajouter un attribut sur le `<div>` racine `cards-grid` : `data-slug-focus="{{ slug_focus }}"`
4. Supprimer `data-monnaie="{{ b.monnaie }}"` (ligne 75)
5. Supprimer `{{ b.monnaie }}` dans le HTML (lignes 83)
6. Remplacer `Aucune tireuse définie.` par `{% translate "No tap configured." %}`
7. Ajouter `data-testid` sur les éléments clés : `cards-grid`, chaque carte, chaque badge état/auth
8. Ajouter `aria-label` sur les badges et jauges
9. Remplacer le bloc `{% block scripts %}<script>...</script>{% endblock %}` par :
   ```html
   {% block scripts %}
   <script src="{% static 'controlvanne/js/panel_kiosk.js' %}"></script>
   {% endblock %}
   ```

- [ ] **Step 3 : Ajouter `config` au contexte de la vue kiosk**

La vue qui rend `panel_bootstrap.html` doit injecter `config` (le singleton `BaseBillet.Configuration`). Chercher la vue existante et ajouter `config` au contexte.

Si la vue n'existe pas encore (le kiosk était servi par l'ancien système), il faudra la créer comme action sur `TireuseViewSet` ou comme vue séparée. C'est un point à vérifier à l'implémentation.

- [ ] **Step 4 : Vérifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

---

### Tâche 5 : Supprimer index.html (doublon)

**Fichiers :**
- Supprimer : `controlvanne/templates/controlvanne/index.html`

L'ancien `index.html` est la version légère/brute du kiosk (pas de Bootstrap card, pas de jauge SVG). `panel_bootstrap.html` le remplace entièrement.

- [ ] **Step 1 : Supprimer le fichier**

```bash
rm /home/jonas/TiBillet/dev/Lespass/controlvanne/templates/controlvanne/index.html
```

- [ ] **Step 2 : Vérifier qu'aucune vue ne le référence**

```bash
docker exec lespass_django grep -rn "index.html" /DjangoFiles/controlvanne/ --include="*.py" | grep -v "Pi/" | grep -v "__pycache__"
```

Si une vue le référence, la pointer vers `panel_bootstrap.html`.

---

### Tâche 6 : Calibration — hériter admin Unfold

**Fichiers :**
- Modifier : `controlvanne/templates/calibration/page.html`

- [ ] **Step 1 : Modifier page.html pour hériter de admin/base_site.html**

Remplacer `{% extends "base.html" %}` par `{% extends "admin/base_site.html" %}`.

Ajouter `{% load i18n %}` en haut.

Remplacer les textes en dur par `{% translate %}` :
- `"Calibration — {{ tireuse.nom_tireuse }}"` → `{% translate "Calibration" %} — {{ tireuse.nom_tireuse }}`
- `"Mode opératoire"` → `{% translate "Operating procedure" %}`
- `"Mesures en attente de saisie"` → `{% translate "Measurements awaiting input" %}`
- etc.

Ajouter `data-testid` sur les éléments clés :
- `data-testid="calibration-page"` sur le container
- `data-testid="calibration-sessions"` sur le tableau des sessions
- `data-testid="calibration-recap"` sur le récap

Supprimer le lien `← Admin` codé en dur (`/admin/controlvanne/tireusebec/`) — dans le base_site Unfold, la sidebar est déjà disponible.

Remplacer le lien vers l'admin dans l'alerte "Désactiver dans l'admin" par un lien construit avec `{% url %}` :
```html
<a href="{% url 'staff_admin:controlvanne_tireusebec_change' tireuse.uuid %}" class="alert-link ms-1">
```

Charger HTMX depuis les statics au lieu du CDN :
Le projet utilise déjà `htmx` dans l'admin Unfold — quand on hérite de `admin/base_site.html`, HTMX est déjà chargé. Supprimer la ligne `<script src="https://unpkg.com/htmx.org@1.9.12">`.

- [ ] **Step 2 : Vérifier la syntaxe**

```bash
docker exec lespass_django poetry run python -c "
from django.template.loader import get_template
t = get_template('calibration/page.html')
print('OK:', t.origin)
"
```

---

### Tâche 7 : Partials calibration + filtre date — data-testid

**Fichiers :**
- Modifier : `controlvanne/templates/calibration/partial_mesure.html`
- Modifier : `controlvanne/templates/calibration/partial_confirmation.html`
- Modifier : `controlvanne/templates/calibration/partial_recap.html`
- Modifier : `controlvanne/templates/admin/date_range_filter.html`

- [ ] **Step 1 : partial_mesure.html — ajouter data-testid**

Ajouter `{% load i18n %}` en haut.

Sur le `<tr>` : `data-testid="calibration-mesure-{{ session.pk }}"`.
Sur le `<input>` volume réel : `data-testid="input-volume-reel"`.
Sur le bouton Calculer : `data-testid="btn-calculer"`.
Sur le bouton Supprimer : `data-testid="btn-supprimer"`.

- [ ] **Step 2 : partial_confirmation.html — ajouter data-testid**

Ajouter `{% load i18n %}` en haut.

Sur l'alerte succès : `data-testid="calibration-confirmation-success"`.
Sur le lien nouvelle série : `data-testid="btn-nouvelle-serie"`.

- [ ] **Step 3 : partial_recap.html — ajouter data-testid**

Sur le `<div class="card">` : `data-testid="calibration-recap"`.
Sur le bouton Appliquer : `data-testid="btn-appliquer-facteur"`.

- [ ] **Step 4 : date_range_filter.html — ajouter data-testid**

Sur l'input `date_from` : `data-testid="filter-date-from"`.
Sur l'input `date_to` : `data-testid="filter-date-to"`.
Sur le bouton Filtrer : `data-testid="btn-filtrer-dates"`.

- [ ] **Step 5 : Vérifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

---

### Tâche 8 : Vérification finale

- [ ] **Step 1 : System check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Step 2 : Collectstatic (vérifier que les fichiers statiques sont trouvés)**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py findstatic controlvanne/css/bootstrap.min.css
docker exec lespass_django poetry run python /DjangoFiles/manage.py findstatic controlvanne/js/panel_kiosk.js
docker exec lespass_django poetry run python /DjangoFiles/manage.py findstatic controlvanne/js/bootstrap.bundle.min.js
```

- [ ] **Step 3 : Vérifier qu'il n'y a plus de référence à monnaie (sauf Pi/)**

```bash
docker exec lespass_django grep -rn "monnaie\|Mike" /DjangoFiles/controlvanne/ --include="*.py" --include="*.html" | grep -v "Pi/" | grep -v "__pycache__" | grep -v "static/"
```

Attendu : aucun résultat (ou uniquement des commentaires).

- [ ] **Step 4 : Tests non-régression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

---

## Résumé des fichiers

| Fichier | Changement |
|---------|------------|
| `controlvanne/consumers.py` | `tb.monnaie` → `"€"` |
| `controlvanne/ws_payloads.py` | `monnaie` → `currency` |
| `controlvanne/templates/base.html` | RÉÉCRIT — tenant name, Bootstrap local, i18n |
| `controlvanne/templates/controlvanne/panel_bootstrap.html` | MODIFIÉ — sans monnaie, data-testid, JS externalisé |
| `controlvanne/templates/controlvanne/index.html` | SUPPRIMÉ (doublon) |
| `controlvanne/templates/calibration/page.html` | MODIFIÉ — admin/base_site.html, data-testid |
| `controlvanne/templates/calibration/partial_*.html` | MODIFIÉ — data-testid |
| `controlvanne/templates/admin/date_range_filter.html` | MODIFIÉ — data-testid |
| `controlvanne/static/controlvanne/js/panel_kiosk.js` | CRÉÉ — JS externalisé |
| `controlvanne/static/controlvanne/css/bootstrap.min.css` | CRÉÉ — Bootstrap 5.3 local |
| `controlvanne/static/controlvanne/js/bootstrap.bundle.min.js` | CRÉÉ — Bootstrap 5.3 local |
