# LE CONTRAT DE SKIN — version 1.0 (2026-07-04)

> Ce document est le CONTRAT entre TiBillet/Lespass et les créateur·ices de
> skins. Tout ce qui est nommé ici est **FIGÉ** : les noms de blocs, de
> partials, d'ids et de variables ne changeront plus (décision 2 du plan).
> Créer un skin = copier `pages/classic/`, restyler, supprimer ce qu'on ne
> change pas (le fallback fait le reste). **Zéro code Python.**

## 1. Démarrer

```bash
python manage.py demarrer_skin mon-skin
```
La commande copie `pages/templates/pages/classic/` → `pages/templates/pages/mon-skin/`
et affiche la marche à suivre. Ensuite : supprimer tous les fichiers qu'on ne
veut PAS personnaliser (ils retomberont sur classic), et restyler le reste.

## 2. Le principe

**Un skin décrit À QUOI ÇA RESSEMBLE, jamais CE QUE ÇA FAIT.**
- Résolution : `pages/<skin>/<gabarit>` → sinon `pages/classic/<gabarit>`
  (resolver `pages.services.gabarit_skin`, fallback automatique = filet de
  sécurité permanent).
- **Règle d'autonomie** : un skin ne référence QUE (a) ses propres fichiers,
  (b) `pages/classic/…`, (c) le partagé `commun/…`. Jamais un autre skin.
- Le **chrome** (offcanvas, tunnels, formulaires, filtres — tout ce qui agit)
  est partagé et NON skinnable par template : `BaseBillet/templates/commun/`.
  Retouche visuelle du chrome = CSS global depuis le skin uniquement.
- Les **pages fonctionnelles** (compte, connexion, caisse QR, wizard, statuts
  de paiement — `BaseBillet/templates/fonctionnel/`) héritent du squelette du
  skin : elles prennent son look sans copie.

## 3. Arborescence d'un skin

```
pages/templates/pages/<skin>/
├── shell.html            squelette page complète (head, CSS, navbar, footer, offcanvas)
├── headless.html         squelette des réponses HTMX (hx-target="body")
├── page.html             rendu des pages CMS (moteur de blocs)
├── vues/
│   ├── accueil.html      home historique (si pas de page CMS d'accueil)
│   ├── agenda.html       liste des événements
│   ├── agenda_liste.html         partiel HTMX (résultats de recherche, p.1)
│   ├── agenda_liste_suite.html   partiel HTMX (« voir plus »)
│   ├── evenement.html    détail d'un événement
│   ├── adhesions.html    liste des adhésions
│   └── reseau.html       explorateur de la fédération
└── partials/
    ├── navbar.html       barre de navigation (déclencheurs contact/connexion)
    ├── footer.html       pied de page
    ├── carte_evenement.html      une ligne/carte de l'agenda
    └── bloc_*.html       les blocs du moteur de pages CMS
```
Tout fichier absent → version classic. Conseil : pour ne changer que quelques
blocs d'une vue, faire `{% extends "pages/classic/vues/agenda.html" %}` et ne
surcharger que les blocs voulus (jamais de copie intégrale : on hériterait des
corrections futures, et on ne perd pas les blocs invisibles type SEO).

## 4. Les blocs (FIGÉS)

### shell.html / headless.html
| Bloc | Rôle |
|---|---|
| `title`, `meta_description`, `meta_robots`, `og_*`, `twitter_*`, `extra_meta` | SEO/head |
| `main` | LE bloc que chaque vue remplit |
| `offcanvas_globaux` | panneaux contact + connexion (includes commun, position déplaçable, contenu non) |
| `offcanvas` | offcanvas spécifiques posés par les vues (tunnels) |
| `scripts` | scripts additionnels de la vue |

> ⚠️ **`extra_meta` = SEO uniquement (meta, JSON-LD).** Ce bloc ne vit que dans
> le `<head>` de shell.html : en réponse HTMX (headless, pas de `<head>`), son
> contenu est PERDU. Un asset CSS/JS nécessaire au rendu d'une vue se charge
> dans le bloc `main` (un `<link>` dans le body est valide en HTML5, le
> navigateur déduplique) ou dans `scripts`. Bug historique : `tb-blocs.css`
> des pages CMS, invisible en navigation HTMX (corrigé le 2026-07-05).

### vues/agenda.html
`agenda_carrousel` / `agenda_description` / `agenda_filtres` (inclut la LOGIQUE
commune `commun/agenda/filtres.html`) / `agenda_liste`.

### vues/evenement.html
`evenement_entete` (média+titre) / `evenement_tags` / `evenement_description` /
`evenement_reservation` (déclencheur du tunnel) / `evenement_complements`.

### vues/adhesions.html
`adhesions_entete` / `adhesions_tunnel` (include chrome) / `adhesions_grille` /
`adhesions_federees`.

## 5. Les ids du chrome (FIGÉS — Bootstrap et HTMX y réfèrent en dur)
`#contactPanel`, `#loginPanel`, `#subscribePanel` + corps `#offcanvas-membership`,
`#bookingPanel`, `#filterPanel`, `#event_list`, `#paginator`, `#search_form`.
Classe utilitaire : `.offcanvas-tunnel` (largeur responsive des tunnels).

## 6. Le contexte fourni (variables garanties par vue)
- **Partout** : `config` (Configuration du tenant), `base_template` (squelette
  résolu), `embed` (rendu iframe : masquer navbar/footer), `main_nav`/navbar,
  `loading_delay`, `user`.
- **Agenda** : `dated_events` (dict date → events), `paginated_info`,
  `all_tags`, `tags`, `active_tag`, `search`, `carrousel_event_list`,
  `querystring_filtres`.
- **Événement** : `event`, `event_max_per_user_reached`, `action_total_jauge`,
  `inscrits`.
- **Adhésions** : `products`, `federated_tenants`.
- **Pages CMS** : `page_courante`, `groupes_de_blocs`, `skin_courant`.

## 7. Statics
Partagé : `static/commun/…` (bootstrap, icônes, vars.css, tibillet.css, swal,
modules JS, polices). Un skin ajoute les siens sous `static/<skin>/…` et les
charge depuis SON shell. Ne jamais référencer les statics d'un autre skin.

## 8. Activer un skin
Admin du tenant → *Configuration du site → Thème graphique*. (Les choices du
champ `pages.ConfigurationSite.skin` sont déclarées dans `pages/models.py` —
l'ajout d'une nouvelle choice est une décision mainteneur.)
