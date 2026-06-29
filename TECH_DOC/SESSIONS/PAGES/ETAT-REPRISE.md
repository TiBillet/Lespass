# App `pages` — ÉTAT & REPRISE (à lire en premier pour reprendre)

> Mis à jour : 2026-06-28 (session longue, contexte ~900k). Ce fichier permet de
> reprendre proprement dans une nouvelle session. Lire aussi `SPEC.md`,
> `CHANTIER-01-*.md`, `CHANTIER-02-*.md`.

## 1. Ce qu'est l'app `pages`
Constructeur de pages publiques par **blocs** préfabriqués, édités dans l'admin
Unfold. App Django **`pages`** en **dual-list** (`SHARED_APPS` + `TENANT_APPS` dans
`TiBillet/settings.py`) → table isolée par schéma (public inclus).

## 2. Modèles (`pages/models.py`)
- **`Page`** : `uuid` PK, `titre`, `slug` (unique, validateur anti-slugs réservés),
  `position` (ordre navbar), `publie`, `est_accueil` (servie sur `/`), `meta_description`.
  `save()` garantit une seule `est_accueil` par tenant.
- **`Bloc`** : FK `page` (`related_name="blocs"`), `position`, `type_bloc` (pivot),
  + champs PLATS : `titre`, `sous_titre`, `surtitre`, `texte` (WYSIWYG, `clean_html`),
  `badge`, `image` + `image_secondaire` (StdImageField, variations), `video` (FileField),
  `points_gps`/`contenu` (JSONField), `image_position` (GAUCHE/DROITE),
  `bouton_label/url`, `bouton2_label/url`, `auteur_nom/role/photo`.
  **Tous les champs fichier sont `null=False`** (vide = `""`, jamais NULL — idiomatique
  Django + évite un crash django-stdimage `delete_orphans`). Plus de chemins static :
  vrai upload (la commande de démo uploade les assets du skin). Leaflet est **vendu**
  dans `pages/static/pages/vendor/leaflet/` (zéro CDN ; tuiles CartoDB exceptées).
  Propriété `nom_template` → `pages/classic/partials/bloc_<type>.html` (fallback).
- **`ConfigurationSite`** (django-solo singleton, app pages) : porte `skin`
  (reunion/faire_festival), **déplacé** depuis `BaseBillet.Configuration.skin`.
- **Types de blocs** : HERO, PARAGRAPHE, IMAGE_TEXTE, CTA, TEMOIGNAGE, VIDEO_TEXTE,
  CARTE, IMAGE.
- **Migrations** : `pages/0001`..`0004` ; `BaseBillet/0220` (module_pages), `0221`
  (déplacement skin → ConfigurationSite + RemoveField), `0222` (home auto par tenant).

## 3. Architecture des skins (templates)
- `pages/templates/pages/<skin>/page.html` + `…/<skin>/partials/bloc_<type>.html`.
- Skins existants : **`classic`** (défaut) et **`faire_festival`**.
- Résolution : skin lu via `BaseBillet.views.get_skin_courant()` (=
  `pages.ConfigurationSite.get_solo().skin`, fallback "reunion"/"classic").
  `rendre_page` (pages/views.py) : `render(request, ["pages/<skin>/page.html",
  "pages/classic/page.html"], …)`. Tag `{% templates_bloc bloc %}`
  (pages/templatetags/pages_tags.py) → `[skin, classic]` (select_template).
- **Regroupement** (`pages.services.grouper_blocs`) → groupes typés :
  - `solo` : un bloc seul.
  - `grille` : CARTE consécutives → grille.
  - `section_video` : un VIDEO_TEXTE **absorbe** les CARTE qui suivent + un CTA →
    rendu « vidéo gauche / texte + cartes + bouton droite » (= section 2 home FF).

## 4. Rendu public + admin
- Vue `pages.views.page_publique(slug)` : 404 si non publiée (preview staff OK) et
  si `Configuration.module_pages` est OFF. `index` (BaseBillet) sert la page
  `est_accueil` si module ON.
- Route attrape-tout `path('', include('pages.urls'))` dans `urls_tenants.py`
  APRÈS BaseBillet. `/<slug>/`.
- Admin **inversé** : on édite le **Bloc** (sidebar « Site web → Blocs »), type
  d'abord → `conditional_fields` natif Unfold (Alpine, gère les selects). La `Page`
  est un select avec boutons +/✎. Inline supprimée de PageAdmin.
  Sidebar (`Administration/admin/dashboard.py`) section « Site web » : Blocs, Pages,
  Configuration du site. Carte dashboard `module_pages` (défaut True).
  L'admin pages vit dans `pages/admin.py`, importé par `admin_tenant.py`.
- Navbar : `get_context` (BaseBillet/views.py) ajoute à `main_nav` les Pages
  publiées (y compris l'accueil → `/`, icône maison). **Plus de hardcode** skin.

## 5. État par tenant
- **lespass** : skin reunion (classic), module_pages ON, a une page démo `accueil-demo`.
- **chantefrein** : skin **faire_festival**, module ON. Pages = `accueil` (home FF
  pixel-perfect), `le-faire-festival` (pixel-perfect), `infos-pratiques` (**PLACEHOLDER**).
  Reconstruites par `manage.py charger_demo_faire_festival --schema=chantefrein`.
- **le-coeur-en-or** : skin faire_festival, module **OFF** (référence legacy).
  ⚠️ CAVEATS depuis le retrait des routes/hardcode legacy :
  - sa navbar a perdu « Le Faire Festival »/« Infos pratiques » (hardcode retiré,
    boucle pages gâtée sur module OFF).
  - son bouton « En savoir plus » (home legacy) pointe `/le-faire-festival/` → 404
    (module OFF → page_publique 404).
  - **Pour le réparer** : soit le passer module ON + lancer `charger_demo_faire_festival
    --schema=le-coeur-en-or`, soit le laisser tel quel (démo). À décider.

## 6. FAIT (vérifié Chrome)
- Archi skins + fallback ; blocs classic + faire_festival (5 existants + 3 nouveaux).
- Home faire_festival **pixel-perfect** (chantefrein == ancien le-coeur-en-or),
  section 2 imbriquée (section_video).
- Fix skin FF : navbar + footer dans `.skin-faire-festival` en HTMX
  (`faire_festival/headless.html`) + `pages/.../faire_festival/page.html` définit
  `{% block footer %}`.
- Retrait routes legacy `infos-pratiques`/`le-faire-festival` (BaseBillet/urls.py),
  slugs dé-réservés (pages/models.py), hardcode navbar retiré (get_context).
- Page `le-faire-festival` reproduite en blocs (IMAGE + PARAGRAPHE + 3 IMAGE_TEXTE).

## 7. RESTE À FAIRE (prochaine session)
1. **`infos-pratiques` pixel-perfect** (actuellement PLACEHOLDER). Source LUE :
   `BaseBillet/templates/faire_festival/views/infos_pratiques.html` (452 lignes).
   Structure exacte à reproduire :
   - **Partie 1 (2 colonnes, `row g-5`)** :
     - Gauche : badge « Infos pratiques » (`badge-festival horaire-texte`) ; intro ;
       **horaires** (`<p class="horaire-texte">JEUDI & VENDREDI 09h→21h</p>` + `SAMEDI 10h→19h`) ;
       badge « Accéder au Faire Festival » ; `<address>` (depuis `config.postal_address`) ;
       note accessibilité PMR (`texte-accessibilite`) ; **VOITURE / BUS / TRAIN** =
       3 blocs `<h3 class="titre-transport">` + `<ul class="liste-transport">` (listes
       d'arrêts — voir le template pour le texte exact).
     - Droite : logo (`logo.webp`, max-height 150px) + badge dates (`datehorizon.png`,
       `.badge-dates`) ; **carte Leaflet interactive** (`#carte-faire-festival`, 400px,
       bordure bleue) ; badge adresse (`badge-adresse` : « LA CITÉ - 55 AV. LOUIS
       BRÉGUET, 31400 TOULOUSE »).
   - **Partie 2 (1 colonne)** : badge « Se repérer dans le festival » + **plan**
     (`plan-festival.webp`, `.plan-container`).
   - **Partie 3 (2 colonnes)** : badge « Foire aux questions » (`badge-faq`) + **6 FAQ**
     (`faq-item` > `faq-question` (h3, commence par « → ») + `faq-reponse` (p, ul,
     `faq-conclusion`, `faq-contact` + mail `contact@fairefestival.fr`)).
   - **Carte Leaflet** : JS dans `{% block scripts %}` (loader dynamique unpkg
     leaflet@1.9.4, tuiles CartoDB Positron, marqueur custom « F », lat/lng depuis
     `config.postal_address`). ⚠️ Le moteur pages n'a pas de mécanisme pour injecter
     ce JS par bloc → choix à faire : (a) nouveau bloc `CARTE_LEAFLET` dont le
     template faire_festival porte le JS, ou (b) un `{% block scripts %}` dans
     `pages/faire_festival/page.html` conditionné à la présence d'un tel bloc.
   **Approche recommandée** : nouveaux blocs si besoin (classic + faire_festival) :
   un `ACCORDEON`/FAQ (classes `faq-*`) et éventuellement `CARTE_LEAFLET`. Sinon,
   FAQ via PARAGRAPHE riche, transports via CARTE×3 (surtitre=VOITURE/BUS/TRAIN),
   plan via IMAGE, et carte = à part. Reproduire dans
   `pages/management/commands/charger_demo_faire_festival.py::_charger_infos_pratiques`.
   Classes FF utiles : `badge-festival`, `horaire-texte`, `titre-transport`,
   `liste-transport`, `badge-adresse`, `badge-dates`, `titre-plan`, `plan-container`,
   `badge-faq`, `faq-item/question/reponse/conclusion/contact`, `lien-contact`.
2. **le-coeur-en-or** : décider (cf. §5).
3. **Ordre navbar** : les Pages apparaissent APRÈS les items modules
   (Adhésions/Agenda). Le legacy mettait « Le Faire Festival » en premier. Si on
   veut l'ordre exact, revoir l'insertion des pages dans `main_nav` (get_context)
   pour intercaler selon `position`.
4. **i18n** : lancer makemessages/compilemessages (libellés FR ajoutés) — mainteneur.
5. (Plus tard) **Chantier tenant public** (cf. CHANTIER initial) + vague 2 blocs riches.

## 7bis. ⚠️ PRINCIPE (correction mainteneur 2026-06-28) — texte dans les blocs, HTML dans les templates
**Règle :** les champs d'un bloc contiennent du **TEXTE / données**, pas du HTML de
structure ou de skin. Tout le **HTML (balises, classes faire_festival, grilles)**
doit vivre dans les **templates** de blocs.
- OK : `texte` = vrai contenu riche WYSIWYG (`<p>`, `<strong>`, `<ul><li>`).
- PAS OK : mettre `badge-festival`, `titre-transport`, `liste-transport`, la
  structure `faq-item/faq-question/faq-reponse`, ou des `row/col` dans `texte`.

**✅ RÉSOLU pour infos-pratiques (2026-06-28)** : reconstruite avec blocs structurés
`INFOS` (`contenu` JSON = items typés texte : badge/para/horaire/adresse/
accessibilite/transport), `CARTE_LEAFLET` (carte), `PARAGRAPHE` (titre = badge de
section en skin faire_festival), `FAQ` (titre=question, texte=réponse). Regroupements
`section_carte` (INFOS+CARTE_LEAFLET côte à côte) et `faq` (2 colonnes). Plus aucun
HTML structurel en base. Reste éventuellement à nettoyer l'intro de
`_charger_le_faire_festival` (HTML léger dans `texte`).

**Modèle de référence (futures pages bespoke) — blocs structurés :**
- **Section/badge** (« Infos pratiques », « Accéder… », « Se repérer », « Foire aux
  questions ») : via le champ `titre` d'un bloc ; le template faire_festival rend
  `<span class="badge-festival horaire-texte">{{ titre }}</span>`. (créer un bloc
  `BADGE`/`SECTION_LABEL` ou réutiliser un type avec un rendu badge).
- **Horaires** : bloc dédié ou champs (jours + créneaux), template rend `horaire-texte`.
- **Transports** (VOITURE/BUS/TRAIN) : bloc `CARTE`/dédié avec `surtitre` = titre,
  et les lignes en **texte multi-lignes** (1 ligne = 1 `<li>`), le template construit
  `<h3 class="titre-transport">` + `<ul class="liste-transport">` (split par ligne).
- **FAQ** : nouveau bloc `FAQ` : `titre` = question (texte), `texte` = réponse
  (contenu riche). Template rend `faq-item/faq-question/faq-reponse`. FAQ consécutives
  → regroupées en 2 colonnes (étendre `grouper_blocs`, cf. `section_video`).
- **Carte** : `CARTE_LEAFLET` est déjà propre côté champs (texte = contenu gauche,
  points en JSONField) SAUF que le `texte` gauche contient encore du HTML structurel
  (badges/transports) → à découper en blocs structurés ci-dessus.

## 8. Pièges / décisions clés
- **django-solo + multi-tenant** : `get_solo()` cache via `django_tenants.cache.make_key`
  (scopé par schéma). Une migration de données qui écrit un singleton via
  `apps.get_model` n'utilise pas `save()` django-solo (pas de set cache) — ok.
  La migration 0221 est durcie (ne réécrit pas si le champ skin est déjà retiré).
- **CSS faire_festival scopé** sous `.skin-faire-festival` : navbar/footer DOIVENT
  être dans ce wrapper (sinon dé-stylés en HTMX). Cf. fix headless.
- **dual-list** : une migration `pages` ne peut PAS dépendre d'une migration
  `BaseBillet` (insatisfiable sur public). Les migrations data qui touchent les deux
  vivent côté `BaseBillet` (tenant-only) et dépendent de la migration `pages`.
- **`{% include liste %}`** = select_template (premier trouvé) → mécanisme du fallback.
- **`bloc` dans le contexte** : en branche "solo"/"section_video" de page.html,
  toujours `{% with bloc=… %}` avant `{% include %}` (sinon partial reçoit bloc vide).
- **slugs réservés** : `pages.models.SLUGS_RESERVES` (validateur sur `Page.slug`).
- Aucune opération **git** par l'assistant. **ruff format** seulement sur fichiers neufs.

## 9. Commandes utiles
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas
docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -q
docker exec lespass_django poetry run python /DjangoFiles/manage.py charger_demo_faire_festival --schema=chantefrein
```
Serveur dans byobu (pane `0.0` logs). Check visuel : `https://<tenant>.tibillet.localhost/`.

## 10. Fichiers clés
- `pages/` : models, admin, views, services (grouper_blocs + construire_page_accueil),
  urls, templatetags/pages_tags, templates/pages/{classic,faire_festival}/, static/pages/css/tb-blocs.css,
  management/commands/{creer_page_demo, charger_demo_faire_festival}.
- `BaseBillet/views.py` : `get_skin_courant`, `get_skin_template`, `get_context`
  (navbar pages), `index` (hook accueil).
- `BaseBillet/templates/faire_festival/{base,headless}.html` (+ partials, views legacy).
- `Administration/admin/dashboard.py` (sidebar + module card), `admin_tenant.py` (import pages.admin).
- `TiBillet/settings.py` (pages dual-list), `urls_tenants.py` (include pages.urls).
