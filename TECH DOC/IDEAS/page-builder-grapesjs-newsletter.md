# Page builder & newsletter : GrapesJS intégré dans Lespass

## Sources

- SimplePageBuilder (exemple d'UX basé sur GrapesJS) : https://simplepagebuilder.app/tutorial/
- GrapesJS — framework open source : https://github.com/GrapesJS/grapesjs
- Plugin MJML newsletter officiel : https://github.com/GrapesJS/mjml
- Demo MJML live : https://grapesjs.com/demo-mjml.html
- GrapesJS Storage Manager (save/load API) : https://grapesjs.com/docs/modules/Storage.html
- Runtime Revolution — article + projet complet : https://revs.runtime-revolution.com/integrating-grapesjs-with-django-a1a514d1b9f2
- djangonian-grapes — code source complet : https://github.com/runtime-revolution/djangonian-grapes

## Exemples réels analysés

### djangonian-grapes (Runtime Revolution) — LE projet de référence

C'est le seul projet Django + GrapesJS open source complet et maintenu trouvé en 2026.
Le code source est lisible et bien structuré. On l'a analysé en entier pour en tirer
les bonnes pratiques et les pièges à éviter.

**Modèle utilisé dans djangonian-grapes :**

```python
# Modèle simple (projet sans multi-tenant)
class Page(models.Model):
    title = models.CharField(max_length=50)
    slug  = models.SlugField(max_length=50, default="", null=False)
    data  = models.JSONField(default=dict, blank=True)  # état éditeur
    html  = models.TextField(default="", blank=True)    # HTML rendu
    css   = models.TextField(default="", blank=True)    # CSS rendu
```

Notre modèle `PageBuilderContent` est directement inspiré de ce pattern.
La différence : on ajoute `publie` (brouillon/publié) et `updated_at`,
et on n'a pas besoin de `slug` car l'isolation multi-tenant est assurée
automatiquement par le `search_path` PostgreSQL de django-tenants.

**Ce qu'ils font dans le template JS (pattern `onStore` explicite) :**

```javascript
// Extrait du template djangonian-grapes
// Ce pattern est plus sûr que de laisser GrapesJS gérer seul le POST

const editeur = grapesjs.init({
    container: '#gjs',
    storageManager: {
        type: 'remote',
        urlLoad  : `/builder/load/${pageId}/`,
        urlStore : `/builder/save/${pageId}/`,
        // GrapesJS n'envoie PAS automatiquement l'id de la page —
        // il faut l'ajouter manuellement dans onStore
        onStore: function(donnees_editeur) {
            return {
                id  : pageId,          // ID de la page Django
                data: donnees_editeur, // État complet de l'éditeur
                html: editeur.getHtml(),
                css : editeur.getCss(),
            };
        },
    },
    // Preset tout-en-un : blocs + styles + responsive prêts à l'emploi
    plugins: ['gjs-preset-webpage'],
});
```

**Pourquoi `onStore` explicite plutôt que `storeHtml: true` ?**

Avec `storeHtml: true` dans `storageManager`, GrapesJS injecte `html` et `css`
directement dans le JSON qu'il envoie, mais le format exact peut varier entre
les versions. Le pattern `onStore` est plus lisible et plus stable : on sait
exactement ce qu'on envoie, et on peut ajouter des données supplémentaires
(comme l'id de la page) sans bricoler.

**Preset `gjs-preset-webpage` : pourquoi ne pas définir les blocs à la main ?**

djangonian-grapes utilise `gjs-preset-webpage` qui fournit d'emblée :
- Blocs standards : texte, image, vidéo, colonnes, map, slider, countdown
- Style manager visuel complet (typographie, couleurs, espacements)
- Responsive automatique (mobile/tablette/desktop)
- Toolbar de sélection d'éléments

Sans ce preset, il faudrait définir manuellement chaque bloc (comme dans
notre template actuel avec `section-hero`) et reconstruire tout le style manager.
**C'est le piège numéro un dans lequel on ne veut pas tomber.**

Pour le mode "Page principale", on partira du preset et on AJOUTERA nos blocs
TiBillet-spécifiques par-dessus, plutôt que de partir de zéro.

**Installation :**
```bash
# CDN (dans le template)
<script src="https://unpkg.com/grapesjs-preset-webpage"></script>
```

### Autres projets observés (moins aboutis)

- `django-grapesjs` sur PyPI : **abandonné depuis 2022, dernier commit 2022**.
  Ne pas utiliser — confirme notre choix d'intégration manuelle.
- Plusieurs threads GitHub Issues montrent que les gens réinventent la roue
  (blocs manuels, Storage Manager bricolé) car ils ne connaissent pas le preset.
  C'est la source de 80% des questions "why isn't GrapesJS saving my content".

## Contexte et besoin

Les gestionnaires de lieux culturels sur TiBillet veulent pouvoir personnaliser
la page principale de leur espace (présentation du lieu, programme mis en avant,
liens, visuels) sans dépendre d'un développeur.

Besoin identifié en parallèle : un éditeur de newsletters événementielles
(annonces de concerts, récaps de saison) avec un output HTML email compatible
tous clients mail.

GrapesJS couvre les deux usages avec la même interface et la même intégration Django.

## Qu'est-ce que GrapesJS ?

Framework open source (licence BSD, ~20K étoiles GitHub en 2025) pour embarquer
un éditeur visuel drag-and-drop dans une application web. Ce n'est pas un SaaS
— c'est une brique JavaScript à intégrer. Extensible via plugins.

**Composants de base disponibles :**
- Texte, titres, paragraphes
- Images, vidéos
- Boutons, liens
- Colonnes, sections, grilles
- Formulaires

**Style Manager :** contrôles CSS visuels (typographie, couleurs, marges, etc.)
sans écrire une ligne de CSS.

**⚠️ `django-grapesjs` sur PyPI est inactif depuis 12+ mois. Ne pas utiliser.**
L'intégration manuelle via le Storage Manager REST est la voie recommandée.

## Architecture d'intégration Django

### Modèle — un contenu par tenant

```python
# BaseBillet/models.py (ou un app dédiée)
from django.db import models

class PageBuilderContent(models.Model):
    """
    Stocke le contenu de la page principale d'un tenant,
    éditée via GrapesJS.

    grapesjs_json : état complet de l'éditeur (composants + styles)
    html_rendu    : HTML final généré, prêt à afficher sur la page publique
    css_rendu     : CSS généré par GrapesJS, injecté dans la page publique
    """

    # Chaque tenant a exactement un PageBuilderContent
    # (OneToOne via django-tenants : le tenant est implicite via search_path)
    nom_page = models.CharField(
        max_length=100,
        default='page_principale',
        help_text="Identifiant de la page (page_principale, newsletter_1, etc.)"
    )

    # JSON complet de l'éditeur GrapesJS — rechargé quand le gestionnaire
    # rouvre l'éditeur pour continuer ses modifications
    grapesjs_json = models.JSONField(
        default=dict,
        help_text="État complet de l'éditeur GrapesJS (ne pas modifier manuellement)"
    )

    # HTML final généré par GrapesJS — utilisé pour afficher la page publique
    html_rendu = models.TextField(
        blank=True,
        help_text="HTML final généré par GrapesJS, affiché sur la page publique"
    )

    # CSS généré par GrapesJS
    css_rendu = models.TextField(
        blank=True,
        help_text="CSS généré par GrapesJS, injecté dans la page publique"
    )

    publie = models.BooleanField(
        default=False,
        help_text="Si False, la page publique affiche le contenu par défaut"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('nom_page',)]   # Une seule page par nom par tenant
        verbose_name = "Contenu page builder"
        verbose_name_plural = "Contenus page builder"

    def __str__(self):
        statut = "publié" if self.publie else "brouillon"
        return f"Page '{self.nom_page}' ({statut}, modifié {self.updated_at:%d/%m/%Y})"
```

### Vues API — save et load

GrapesJS appelle ces deux endpoints automatiquement via son Storage Manager.

```python
# BaseBillet/views_pagebuilder.py

import json
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .models import PageBuilderContent


class PageBuilderAPIView(LoginRequiredMixin, View):
    """
    API REST pour GrapesJS Storage Manager.

    GET  → charge le JSON de l'éditeur pour ce tenant + cette page
    POST → sauvegarde le JSON + le HTML/CSS rendu

    GrapesJS envoie : { "components": [...], "styles": [...], "html": "...", "css": "..." }
    """

    def get(self, request, nom_page='page_principale'):
        """
        Charge le contenu existant dans l'éditeur GrapesJS.
        Retourne un JSON vide si la page n'existe pas encore.
        """
        contenu_existant = PageBuilderContent.objects.filter(
            nom_page=nom_page
        ).first()

        if contenu_existant:
            # GrapesJS s'attend à recevoir directement le JSON de l'éditeur
            return JsonResponse(contenu_existant.grapesjs_json)
        else:
            # Première ouverture : éditeur vide
            return JsonResponse({})

    def post(self, request, nom_page='page_principale'):
        """
        Sauvegarde le contenu depuis l'éditeur GrapesJS.
        GrapesJS envoie le JSON complet en body de la requête POST.
        """
        try:
            donnees_editeur = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(
                {'erreur': 'JSON invalide'},
                status=400
            )

        contenu, cree = PageBuilderContent.objects.get_or_create(
            nom_page=nom_page
        )

        # Stocker l'état complet de l'éditeur (pour rechargement futur)
        contenu.grapesjs_json = donnees_editeur

        # Extraire le HTML et CSS générés (pour la page publique)
        contenu.html_rendu = donnees_editeur.get('html', '')
        contenu.css_rendu  = donnees_editeur.get('css', '')

        contenu.save()

        # GrapesJS n'attend qu'un status 200, pas de contenu particulier
        return JsonResponse({'status': 'sauvegardé'})
```

### Template de l'éditeur

**Version révisée après analyse de djangonian-grapes.**
Les différences clés par rapport à une intégration naïve :
- On utilise `gjs-preset-webpage` (mode page) ou `grapesjs-mjml` (mode newsletter)
  plutôt que de définir les blocs à la main
- On utilise `onStore` explicite pour contrôler exactement ce qu'on envoie à Django
- On utilise `autoload: true` pour que GrapesJS charge automatiquement au démarrage

```html
<!-- templates/pagebuilder/editeur.html -->
{% load static %}
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Éditeur de page — {{ request.tenant.name }}</title>

    <!-- GrapesJS CSS -->
    <link rel="stylesheet"
          href="https://unpkg.com/grapesjs/dist/css/grapes.min.css">

    <style>
        /* L'éditeur prend tout l'écran */
        body { margin: 0; }
        #gjs  { height: 100vh; }
    </style>
</head>
<body>
    <div id="gjs"></div>

    <!-- GrapesJS JS -->
    <script src="https://unpkg.com/grapesjs"></script>

    {% if not mode_newsletter %}
    <!--
        Preset "Page web" : blocs standards + style manager + responsive
        Charge : texte, image, vidéo, colonnes, slider, countdown, map
        C'est le preset qui évite de tout reconstruire à la main.
        ⚠️ Ne PAS réimplémenter les blocs déjà fournis par ce preset.
    -->
    <script src="https://unpkg.com/grapesjs-preset-webpage"></script>
    {% else %}
    <!--
        Preset MJML : éditeur newsletters compatible tous clients mail
        Charge : mj-section, mj-column, mj-text, mj-image, mj-button, etc.
    -->
    <script src="https://unpkg.com/grapesjs-mjml"></script>
    {% endif %}

    <script>
        // ── Utilitaires ──────────────────────────────────────────────────────

        /**
         * Récupère le token CSRF Django depuis les cookies.
         * Indispensable : sans ce token, tous les POST seront rejetés (403).
         */
        function getCsrfToken() {
            const cookie_csrf = document.cookie
                .split('; ')
                .find(ligne => ligne.startsWith('csrftoken='));
            return cookie_csrf ? cookie_csrf.split('=')[1] : '';
        }

        // ── Configuration ────────────────────────────────────────────────────

        // Injecté par Django via le contexte de la vue
        const nom_de_la_page = "{{ nom_page|default:'page_principale' }}";

        // URL de base pour les deux endpoints (load et store utilisent la même URL,
        // GET pour charger, POST pour sauvegarder)
        const url_api_pagebuilder = `/api/pagebuilder/${nom_de_la_page}/`;

        // ── Initialisation de GrapesJS ────────────────────────────────────────

        const configuration_editeur = {
            container: '#gjs',

            // Storage Manager : save/load vers notre API Django
            storageManager: {
                type    : 'remote',
                urlLoad : url_api_pagebuilder,
                urlStore: url_api_pagebuilder,

                // ⚠️ CSRF obligatoire — sans ça, Django rejette tous les POST
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'Content-Type': 'application/json',
                },

                // Sauvegarde automatique après 3 modifications
                autosave       : true,
                stepsBeforeSave: 3,

                // Chargement automatique au démarrage de l'éditeur
                autoload: true,

                /**
                 * onStore : contrôle EXPLICITEMENT ce qu'on envoie à Django.
                 *
                 * Pattern appris de djangonian-grapes :
                 * GrapesJS avec storeHtml:true peut changer de format entre
                 * les versions. onStore explicite est plus stable et plus lisible.
                 *
                 * On envoie :
                 * - grapesjs_json : état complet de l'éditeur (rechargement futur)
                 * - html          : HTML final pour la page publique
                 * - css           : CSS final pour la page publique
                 */
                onStore: function(donnees_editeur, editeur_instance) {
                    return {
                        grapesjs_json: donnees_editeur,
                        html         : editeur_instance.getHtml(),
                        css          : editeur_instance.getCss(),
                    };
                },

                /**
                 * onLoad : extrait le JSON de l'éditeur depuis la réponse Django.
                 *
                 * Notre API Django retourne { grapesjs_json: {...} }
                 * GrapesJS a besoin que onLoad retourne directement le JSON éditeur.
                 */
                onLoad: function(reponse_django) {
                    // Si la page n'existe pas encore, retourner un objet vide
                    return reponse_django.grapesjs_json || {};
                },
            },

            {% if not mode_newsletter %}
            // ── Mode "Page principale" ─────────────────────────────────────────
            plugins: ['gjs-preset-webpage'],
            pluginsOpts: {
                'gjs-preset-webpage': {
                    // Désactiver les blocs qu'on ne veut pas proposer aux gestionnaires
                    // (ex: countdown inutile pour un lieu culturel)
                    blocks: [
                        'link-block', 'quote', 'text-basic',
                        'image', 'video', 'map',
                        // NE PAS lister 'countdown' si non pertinent
                    ],
                },
            },
            {% else %}
            // ── Mode "Newsletter MJML" ─────────────────────────────────────────
            plugins: ['grapesjs-mjml'],
            pluginsOpts: {
                'grapesjs-mjml': {
                    columnsPadding: '0',
                },
            },
            {% endif %}
        };

        // Lancer l'éditeur avec la configuration définie ci-dessus
        const editeur = grapesjs.init(configuration_editeur);

        // ── Blocs TiBillet-spécifiques (mode page uniquement) ─────────────────
        // Ces blocs s'AJOUTENT au preset — on ne remplace pas le preset,
        // on l'étend avec nos composants métier.
        {% if not mode_newsletter %}
        editeur.BlockManager.add('bloc-programme-evenements', {
            label   : '🎵 Programme événements',
            category: 'TiBillet',
            content : `
                <section class="tibillet-programme" style="padding: 40px; background: #0d0d0d;">
                    <h2 style="color: #e0b000; font-family: sans-serif;">Prochains événements</h2>
                    <p style="color: #ccc; font-family: sans-serif;">
                        Remplacez ce bloc par votre programme (intégration API TiBillet à venir)
                    </p>
                </section>
            `,
        });

        editeur.BlockManager.add('bloc-billetterie-lien', {
            label   : '🎟️ Bouton billetterie',
            category: 'TiBillet',
            content : `
                <a href="#billetterie"
                   style="display: inline-block; padding: 16px 32px;
                          background: #e0b000; color: #000;
                          font-family: sans-serif; font-weight: bold;
                          text-decoration: none; border-radius: 4px;">
                    Réserver ma place
                </a>
            `,
        });
        {% endif %}
    </script>
</body>
</html>
```

**⚠️ Changement important dans la vue Django (`views_pagebuilder.py`) :**

Avec `onStore` explicite, la vue `post()` doit maintenant lire
`donnees_editeur['grapesjs_json']` et non plus `donnees_editeur` directement :

```python
def post(self, request, nom_page='page_principale'):
    try:
        corps_requete = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'erreur': 'JSON invalide'}, status=400)

    contenu, cree = PageBuilderContent.objects.get_or_create(nom_page=nom_page)

    # Avec onStore explicite, GrapesJS envoie un objet structuré
    # (pas le JSON éditeur brut directement)
    contenu.grapesjs_json = corps_requete.get('grapesjs_json', {})
    contenu.html_rendu    = corps_requete.get('html', '')
    contenu.css_rendu     = corps_requete.get('css', '')
    contenu.save()

    return JsonResponse({'status': 'sauvegardé'})
```

Et la vue `get()` doit retourner l'objet complet (pas juste le JSON éditeur),
pour que `onLoad` puisse extraire `grapesjs_json` :

```python
def get(self, request, nom_page='page_principale'):
    contenu_existant = PageBuilderContent.objects.filter(nom_page=nom_page).first()

    if contenu_existant:
        # On retourne un objet avec grapesjs_json comme clé explicite
        # (onLoad dans le template extrait cette clé)
        return JsonResponse({'grapesjs_json': contenu_existant.grapesjs_json})
    else:
        # Première ouverture — éditeur vide
        return JsonResponse({'grapesjs_json': {}})
```

### URLs

```python
# BaseBillet/urls.py
from django.urls import path
from . import views_pagebuilder

urlpatterns = [
    # API GrapesJS (save/load)
    path(
        'api/pagebuilder/<str:nom_page>/',
        views_pagebuilder.PageBuilderAPIView.as_view(),
        name='pagebuilder_api'
    ),
    # Interface éditeur
    path(
        'admin/pagebuilder/<str:nom_page>/',
        views_pagebuilder.PageBuilderEditeurView.as_view(),
        name='pagebuilder_editeur'
    ),
    # Page publique (affiche le HTML rendu)
    path(
        '',
        views_pagebuilder.PagePubliqueView.as_view(),
        name='page_principale'
    ),
]
```

## Plugin MJML — éditeur newsletter

Le plugin officiel `grapesjs-mjml` transforme GrapesJS en éditeur de newsletters
compatibles tous clients mail (Gmail, Outlook, Apple Mail).

**Composants MJML disponibles :**
`mj-section`, `mj-column`, `mj-text`, `mj-image`, `mj-button`, `mj-social`,
`mj-divider`, `mj-hero`, `mj-navbar`, `mj-spacer`

**Workflow newsletter TiBillet :**
1. Gestionnaire ouvre l'éditeur en mode `mode_newsletter=True`
2. Drag-and-drop des composants MJML (sections, images d'événements, boutons billetterie)
3. Sauvegarde → JSON stocké en DB + HTML MJML rendu
4. HTML MJML compilé → envoyé via l'outil d'envoi mail existant

**Avantage clé :** même interface pour la page publique ET la newsletter.
Formation utilisateur × 1 au lieu de × 2.

## Pièges spécifiques à l'intégration Django

Ces pièges sont documentés à partir de l'analyse de djangonian-grapes
et des dizaines de questions StackOverflow/GitHub Issues sur le sujet.

| Piège | Symptôme | Solution |
|-------|----------|----------|
| **CSRF Django** | Tous les POST GrapesJS → 403 Forbidden | Passer `X-CSRFToken: getCsrfToken()` dans les headers du Storage Manager |
| **Reconstruire les blocs à la main** | Des heures passées sur du code déjà fait | Utiliser `gjs-preset-webpage` comme base, n'ajouter que les blocs métier TiBillet |
| **`storeHtml: true` instable** | Format du POST change entre versions GrapesJS | Utiliser `onStore` explicite : on contrôle exactement ce qu'on envoie |
| **`onLoad` absent** | L'éditeur charge mais reste vide | Implémenter `onLoad` pour extraire `grapesjs_json` de la réponse Django |
| **Classes `gjs-*` dans le HTML public** | La page publique contient des classes internes GrapesJS (`gjs-row`, `gjs-cell`, etc.) | Ces classes sont inoffensives mais inutiles. Option : `editeur.getCss()` + `editeur.getHtml()` les nettoient partiellement. Pour un nettoyage complet → `bleach` ou regex côté Django avant de stocker |
| **Permission trop permissive** | N'importe quel user connecté peut modifier la page | Ne pas se contenter de `LoginRequiredMixin`. Vérifier que le user est bien gestionnaire du tenant courant (ex: `request.user.is_staff` ou groupe `gestionnaire`) |
| **Multi-tenant : mauvaise isolation** | Un tenant voit le contenu d'un autre | `PageBuilderContent` doit vivre dans le schéma tenant (app normale, pas `SHARED_APPS`). Si l'app est dans `SHARED_APPS` → les données sont partagées entre tous les tenants |
| **GrapesJS depuis CDN** | Éditeur ne charge pas avec CSP strict | Héberger les assets GrapesJS en local (npm + webpack/vite) ou configurer CSP pour autoriser `unpkg.com` |
| **`autoload` absent** | Il faut recharger la page pour que l'éditeur charge le contenu existant | Ajouter `autoload: true` dans `storageManager` |
| **`django-grapesjs` PyPI** | Package installé mais buggé / rien ne se passe | Package abandonné depuis 2022. Désinstaller, intégration manuelle uniquement |
| **Autosave + formulaires Django imbriqués** | Les POST autosave interfèrent avec d'autres formulaires sur la page | Mettre l'éditeur sur une page dédiée, pas en inline dans une page d'admin Django existante |

### Le piège multi-tenant le plus subtil

Avec django-tenants, une app peut être dans `TENANT_APPS` (schéma isolé par tenant)
ou dans `SHARED_APPS` (schéma `public`, partagé entre tous).

```python
# settings.py — s'assurer que l'app pagebuilder est dans TENANT_APPS

TENANT_APPS = [
    # ...
    'BaseBillet',   # ← PageBuilderContent est ici → isolation automatique ✅
]

SHARED_APPS = [
    # 'BaseBillet',  ← NE PAS mettre ici, sinon tous les tenants partagent
    #                   le même contenu de page builder ❌
]
```

Si le modèle est dans `SHARED_APPS`, les requêtes `PageBuilderContent.objects.filter()`
vont chercher dans le schéma `public` → tous les tenants partagent les mêmes pages.
Ce bug est silencieux et difficile à détecter en dev (on n'a souvent qu'un tenant local).

## Deux modes d'utilisation

### Mode "Page principale"
- GrapesJS standard sans plugin MJML
- Blocs TiBillet-spécifiques (hero, programme, carte lieu, liens réseaux)
- Output : HTML + CSS stockés, rendus sur la page publique du tenant

### Mode "Newsletter"
- GrapesJS + plugin `grapesjs-mjml`
- Blocs MJML (sections responsives, boutons, images d'événements)
- Output : HTML MJML inliné, prêt à envoyer via l'outil mail

## Ordre d'implémentation suggéré

1. Créer le modèle `PageBuilderContent` + migration
2. Créer les 2 vues API (GET/POST) + les URLs
3. Intégrer GrapesJS dans un template basique (mode page)
4. Tester save/load avec un vrai tenant
5. Ajouter le plugin MJML en mode newsletter
6. Créer des blocs TiBillet-spécifiques (programme, billetterie)
7. Relier la page publique au `html_rendu` stocké

## Priorité

Basse pour l'instant — fonctionnalité de confort, pas bloquante.
À envisager après stabilisation de l'infra (Redis, observabilité, PgBouncer).
Le plugin MJML en particulier mérite un prototype rapide pour valider
l'intérêt des gestionnaires avant de s'engager sur l'intégration complète.
