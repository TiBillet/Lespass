# Pages de détail des fonctionnalités (ROOT) — prototype SEO

> **Mise à jour (itération 2)** : les **10 fonctionnalités** ont maintenant leur page + breadcrumb.
> Ajout d'une **page hub `/features/`** (même grille que la landing via un include partagé),
> d'un **sitemap ROOT** (`/sitemap-root.xml`) référencé dans l'index, de **liens doc profonds** et de
> **`<title>` SEO** enrichis. Les pages **`/lieux/` et `/evenements/` ont été supprimées**.
> Voir les tests 6 à 9 ci-dessous.
>
> **Mise à jour (itération 3)** : l'URL est passée en **anglais** : `/features/` et `/features/<slug>/`
> (au lieu de `/fonctionnalites/`) — meilleur pour le SEO et neutre vis-à-vis des futures traductions
> FR/EN. Un **bouton « Fonctionnalités »** (icône grille) a été ajouté dans le **menu de navigation**
> ROOT, en premier, vers `/features/`. Le libellé d'affichage reste « Fonctionnalités » (français,
> traduisible) ; seul le chemin d'URL est en anglais.

## Ce qui a été fait

Au clic sur une carte de la section **« Fonctionnalités »** de la landing ROOT
(`https://tibillet.localhost/`), on ouvre une **vraie page de détail indexable**
`/features/<slug>/` avec captures (placeholder), textes descriptifs, liens vers la
documentation et maillage interne vers les autres fonctionnalités.

**Choix d'architecture (décision UX validée : « page dédiée anti-blink ») :**
- La page de détail est rendue **entièrement côté serveur** → crawlable et indexable.
- La transition au clic est **anti-blink** (htmx `hx-select="#seo-content"`) : pas de flash, le
  `<head>`/navbar/footer ne sont pas rejoués, mais l'URL change et la page existe en standalone.
- C'est la combinaison « vraie URL + JSON-LD + maillage » qui permet les **extraits enrichis /
  sitelinks** sur Google — pas une modale JavaScript (invisible aux robots).

**Prototype : 2 fonctionnalités** ont une page de détail (Billetterie + Cashless NFC). Les 8 autres
cartes restent non cliquables tant qu'elles n'ont pas d'entrée dans `seo/features.py`.

### Modifications
| Fichier | Changement |
|---|---|
| `seo/features.py` | **Nouveau** : registre `FEATURE_DETAILS` (titre, icône, accroche, intro, sections texte+capture, lien doc, meta description) |
| `seo/views.py` | Vue `feature_detail` (rendu serveur complet + JSON-LD Breadcrumb/TechArticle, 404 si slug inconnu) ; `ItemList` JSON-LD + `feature_detail_slugs` ajoutés à la landing |
| `seo/urls.py` | Route `fonctionnalites/<slug:slug>/` → `feature_detail` |
| `seo/templates/seo/feature_detail.html` | **Nouveau** : breadcrumb, en-tête, intro, sections alternées, CTA, maillage interne |
| `seo/templates/seo/base.html` | Wrapper `#seo-content` autour du contenu (cible du swap htmx) |
| `seo/templates/seo/landing.html` | Cartes Billetterie + Cashless converties en liens (hx-get + hx-select) ; `id="features"` sur la section ; bloc `extra_head` pour l'ItemList |
| `seo/static/seo/seo.css` | Styles `.feature-card--link` / `.feature-more` + page détail `.fd-*` |

## Tests à réaliser

### Test 1 : Page de détail en accès direct (chemin robot)
1. Ouvrir `https://tibillet.localhost/features/billetterie/`.
2. **Attendu** : page complète (navbar, breadcrumb « Accueil › Fonctionnalités › Billetterie »,
   icône, titre, accroche, intro, 3 sections alternées texte/capture, CTA doc + créer espace,
   « Autres fonctionnalités »).
3. Idem `https://tibillet.localhost/features/cashless-nfc/` (le titre s'affiche
   « Monnaie locale et carte NFC » — traduction FR existante du msgid, cohérent avec la landing).

### Test 2 : Interaction anti-blink depuis la landing
1. Sur `/`, scroller jusqu'à « Fonctionnalités ».
2. **Attendu** : seules les cartes **Billetterie** et **Cashless** portent l'affordance verte
   « En savoir plus → » (les 8 autres non).
3. Cliquer Billetterie. **Attendu** : l'URL devient `/features/billetterie/`, le contenu se
   remplace **sans flash**, le titre de l'onglet change, navbar/footer inchangés.
4. Cliquer le breadcrumb « Accueil ». **Attendu** : retour à la landing sans flash, URL = `/`.
5. Bouton **Précédent** du navigateur : doit refonctionner (hx-push-url).

### Test 3 : SEO (lisible par les robots)
```bash
# JSON-LD présents sur la page de détail
curl -sk https://tibillet.localhost/features/billetterie/ | grep -o '"@type": *"[^"]*"' | sort | uniq -c
#   attendu : BreadcrumbList, ListItem (x3), TechArticle, SoftwareApplication, WebSite

# title + canonical + meta description
curl -sk https://tibillet.localhost/features/billetterie/ | grep -oE '<title>[^<]*</title>|canonical|name="description"'

# ItemList des fonctionnalités sur la landing (signal sitelinks)
curl -sk https://tibillet.localhost/ | grep -o '"@type": *"ItemList"'

# 404 sur slug inconnu
curl -sk -o /dev/null -w "%{http_code}\n" https://tibillet.localhost/features/inexistant/   # -> 404
```
Vérifier aussi avec l'outil Google « Test des résultats enrichis » (rich results test) une fois en
ligne, pour confirmer la validité du `BreadcrumbList` et du `TechArticle`.

### Test 4 : Responsive (≤ 375 px)
1. Réduire à 375 px.
2. **Attendu** : sections de la page détail en **1 colonne** (texte puis capture), aucun défilement
   horizontal, CTA sur une seule ligne, breadcrumb lisible.

### Test 5 : Accessibilité
1. Tab jusqu'aux cartes cliquables et aux liens de la page détail.
2. **Attendu** : anneau de focus vert visible et instantané.
3. Lecteur d'écran : le breadcrumb (`aria-label`), `aria-current="page"` sur l'élément courant, les
   `figcaption` décrivant les captures, et les icônes décoratives ignorées (`aria-hidden`).

### Test 6 : Hub `/features/`
1. Ouvrir `https://tibillet.localhost/features/`.
2. **Attendu** : breadcrumb « Accueil › Fonctionnalités », **H1** « Fonctionnalités », intro, puis la
   **même grille** que la landing avec les **10 cartes** cliquables (« En savoir plus → »).
3. Cliquer une carte → page de détail (anti-blink). Le breadcrumb « Fonctionnalités » revient au hub.

### Test 7 : Les 10 fonctionnalités ont leur page + breadcrumb
```bash
for s in adhesions billetterie agenda-federe caisse cashless-nfc monnaie-locale-temps \
         donnees-ouvertes logiciel-libre agenda-participatif seo; do
  printf "%s -> " "$s"
  curl -sk -o /dev/null -w "%{http_code}\n" https://tibillet.localhost/features/$s/
done   # -> 200 partout
```
Vérifier sur chaque page : breadcrumb à 3 niveaux, `<title>` enrichi, lien doc profond (HTTP 200).

### Test 8 : Sitemaps
```bash
# Le sitemap index reference le sitemap ROOT
curl -sk https://tibillet.localhost/sitemap.xml | grep sitemap-root.xml

# Le sitemap ROOT liste landing + hub + explorer + les 10 pages
curl -sk https://tibillet.localhost/sitemap-root.xml | grep -c '<loc>'   # -> 13
```

### Test 9 : Pages supprimées (/lieux, /evenements)
```bash
curl -sk -o /dev/null -w "%{http_code}\n" https://tibillet.localhost/lieux/        # -> 404
curl -sk -o /dev/null -w "%{http_code}\n" https://tibillet.localhost/evenements/   # -> 404
```
Vérifier aussi que le footer ROOT n'affiche plus « Lieux »/« Événements » mais « Fonctionnalités ».
(Le marquee « Nos lieux vivants » et l'explorateur, qui utilisent la **donnée cache** des lieux,
fonctionnent toujours — seules les **pages** `/lieux/` et `/evenements/` sont retirées.)

## Comment ajouter / modifier une fonctionnalité (extension)

**Une seule source de vérité** : `seo/features.py` → `FEATURE_DETAILS` (l'ordre des clés = l'ordre
d'affichage des cartes). Ajouter une entrée (même schéma, nouveau slug) suffit : la carte (grille de la
landing **et** du hub via l'include `_features_grid.html`), la page de détail, le breadcrumb, le
`<title>`, le JSON-LD, l'`ItemList`, le sitemap ROOT et le maillage interne se mettent à jour
**automatiquement**. Plus aucune édition de template n'est nécessaire pour une nouvelle fonctionnalité.

## i18n (à faire par le mainteneur)

Beaucoup de nouvelles chaînes : le contenu des **10 fonctionnalités** dans `seo/features.py`
(`card_desc`, `tagline`, `lead`, `page_title`, `meta_description`, sections + captures), le hub
(`feature_hub.html`), et les libellés de `feature_detail.html` / `_features_grid.html` (« En savoir
plus », « Accueil », « Fonctionnalités », « Lire la documentation », « Créer mon espace », « Autres
fonctionnalités », « Capture à venir », « Fil d'Ariane »).

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
# éditer locale/en/LC_MESSAGES/django.po, retirer #, fuzzy
docker exec lespass_django poetry run django-admin compilemessages
```

## Compatibilité

- **Aucune migration**, aucune dépendance ajoutée.
- `request.htmx` (django-htmx) est déjà actif dans le projet — mais la vue n'en dépend pas
  (rendu serveur complet dans tous les cas ; l'anti-blink est 100 % côté client via `hx-select`).
- `manage.py check` : 0 issue.
- Pistes suite : liens doc profonds, vraies captures, étendre aux 8 autres cartes, sitemap ROOT dédié.
