# Audit SEO : on-page, contenu, images, recherche IA et SXO
## Accueil par défaut du skin V2 (TiBillet / Lespass)

Date : 2026-10-12. Pages étudiées (prod, en lecture seule, 22 requêtes GET/HEAD au total) :
- https://la-filature.tibillet.coop/ (cas principal)
- https://raffinerie.tibillet.re/
- https://claf.tibillet.coop/

**Correction du brief (vérifié) :** CLAF n'a **pas** de page d'accueil CMS. Elle sert l'accueil par défaut, comme les deux autres : on y trouve `data-testid="accueil-hero"`, le titre `Accueil | CLAF` et la section « Ce qui arrive ». Les trois pages sortent donc du même gabarit, et les comparer revient à comparer **ce que chaque admin a saisi**.

Code lu (lecture seule) : `pages/templates/pages/V2/shell.html`, `vues/accueil.html`, `tenant_header.html`, `partials/footer.html`, `cotton/V2/agenda_a_venir.html`, `cotton/V2/event_card.html`, `BaseBillet/templates/commun/partials/picture.html`, `BaseBillet/views.py` (index), `BaseBillet/views_robots.py`, `BaseBillet/sitemap.py`, `pages/templatetags/pages_tags.py`.

Légende : **[V]** = vérifié (sur la prod ou dans le code) · **[S]** = supposé (déduit, non mesuré) · **Code** = à corriger dans le dépôt (vaut pour les ~500 lieux) · **Admin** = à corriger par l'admin du lieu.

---

## Notes

| Catégorie | Note /100 | Justification |
|---|---|---|
| **On-page** | **52** | Un seul h1 (le nom du lieu) et une meta description propre à chaque lieu. Mais le title générique « Accueil \| Nom » ne contient ni la ville ni l'activité, la canonique reprend les paramètres d'URL, et la section de présentation n'a aucun titre. |
| **Contenu** | **55** | La Filature a un vrai texte de présentation, son adresse et son téléphone : le fond est bon. La forme pèche : un bloc de texte sans intertitre, un e-mail personnel, ni horaires ni mentions légales, et le bandeau TiBillet identique pèse 28 à 50 % des mots de la page. |
| **Images** | **42** | La photo du hero est un fond CSS : pas d'alt, découverte tardive, 390 Ko en 1920 px même sur mobile. Les cartes d'événements choisissent leur image selon la taille de l'écran, pas de la carte : jusqu'à 293 Ko pour une carte de 370 px, sans lazy-load. Seule l'og:image est correcte. |
| **Recherche IA (GEO)** | **50** | Points forts : robots ouverts, texte rendu côté serveur et servi aux robots IA, JSON-LD Event propre sur les fiches événement. Points faibles : pas de llms.txt, et un JSON-LD Organization écrit à la main avec des entités HTML (`L&#x27;Hermitage`), un « logo » qui est une photo, `sameAs` vide alors que le nom est ambigu, et ni horaires ni coordonnées GPS. |
| *SXO (indicatif)* | *50* | En 5 secondes, on lit le nom, l'adresse et une phrase de présentation (bien chez La Filature). Mais le hero n'a **aucun bouton** (agenda, adhésion), et les événements, raison n°1 de la visite, sont repoussés sous un long texte et une carte. |

---

## Ce qui marche

- **[V] Un seul `<h1>`** sur les trois pages, qui contient le nom du lieu (`accueil.html:34`). Les titres d'événements sont en `<h3>` sous un `<h2>` « Ce qui arrive · N événements à venir ».
- **[V] `<html lang="fr">`**, `og:locale` valide (`fr_FR` / `en_US`) et `meta robots index, follow`.
- **[V] La meta description et l'og:description viennent de `config.short_description`**, donc chaque lieu a la sienne. Chez La Filature, elle est riche : « tiers-lieu villeurbannais installé dans une ancienne friche industrielle… ».
- **[V] Open Graph et Twitter complets** : `og:image` absolue en 1200×630 (`social_card`, 279 Ko), `og:site_name`, `twitter:card=summary_large_image`.
- **[V] Les robots IA sont acceptés** : GPTBot, ClaudeBot et PerplexityBot reçoivent un 200 avec le HTML complet (61 976 octets, identique au navigateur). Tout le texte est rendu côté serveur. Seules la carte Leaflet et la photo du hero dépendent du JS ou du CSS.
- **[V] Le nom, l'adresse et la ville sont visibles au-dessus de la ligne de flottaison**, dans l'en-tête du lieu : « La Filature, 10 Rue du Pérou, Villeurbanne · lafilature-villeurbanne.fr ↗ » (`tenant_header.html:42-53`).
- **[V] Les liens « En savoir plus » des cartes sont explicites pour les lecteurs d'écran** : le nom de l'événement y figure en `visually-hidden` (`event_card.html:104-107`). Le lien sortant vers le site du lieu est annoncé « (nouvel onglet) ».
- **[V] Les fiches événement ont un JSON-LD `Event` construit en Python avec `json.dumps`** (`pages_tags.py:408` `jsonld_event`, appelé dans `V2/vues/evenement.html:96`). L'échappement y est sûr, contrairement au bloc Organization du shell.
- **[V] Un flux RSS est déclaré** (`shell.html:72-74`), le sitemap est référencé dans robots.txt, et le footer reprend le menu en liens HTML crawlables.

---

## Constats

### CRITIQUE

#### C1. Title générique « Accueil | Nom du lieu » sans ville ni activité, sur ~500 accueils [V] (Code)
- **Preuve :** `<title>Accueil | La Filature</title>` (21 caractères), `Accueil | La Raffinerie`, `Accueil | CLAF` (14 caractères). Avec `Accept-Language: en` : `Home | La Filature`.
- **Impact :** le title est le signal on-page le plus fort et le texte du lien bleu dans Google. « Accueil » ne sert à rien, et le mot de tête est perdu. Surtout, **« La Filature » est une entité ambiguë** : un projet immobilier de 700 logements à Villeurbanne (BNP Paribas Immobilier / Gingko), une scène nationale à Mulhouse… Une recherche web sur « La Filature Villeurbanne tiers-lieu agenda » ne remonte **aucune** page TiBillet, seulement le projet immobilier (lebonbon.fr, lyondemain.fr). Recherche lancée depuis les États-Unis : résultat indicatif. Sans « Villeurbanne » ni « tiers-lieu » dans le title, Google n'a pas de quoi trancher. C'est vrai pour tous les lieux qui portent un nom courant.
- **Fichiers :** `pages/templates/pages/V2/vues/accueil.html:4` (`{% block title %}{% translate 'Accueil' %}{% endblock %}`) et `pages/templates/pages/V2/shell.html:25`, qui colle de force ` | {{ config.organisation }}` : l'accueil ne peut donc pas produire un title qui commence par le nom.
- **Correction :**
  1. Dans le shell, rendre surchargeable tout le contenu de `<title>` : `<title>{% block title_complet %}{% block title %}…{% endblock %} | {{ config.organisation }}{% endblock %}</title>`.
  2. Dans `accueil.html`, surcharger avec : `{{ config.organisation }}{% if config.postal_address.address_locality %} – {{ config.postal_address.address_locality }}{% endif %} : {% translate 'agenda, billetterie et adhésions' %}`. Résultat : « La Filature – Villeurbanne : agenda, billetterie et adhésions » (61 caractères).
  3. Faire de même pour `og_title` / `twitter_title` (`accueil.html:6,9`), qui valent aujourd'hui le nom seul.
- **Qui :** Code. L'admin n'y peut rien : il ne contrôle que le nom.

#### C2. JSON-LD Organization écrit à la main : entités HTML dans les données, « logo » qui est une photo, `sameAs` vide [V] (Code)
- **Preuve (JSON extrait de la prod, puis parsé) :**
  - Raffinerie : `"addressLocality": "L&#x27;Hermitage Les Bains"`. La ville elle-même est corrompue dans les données structurées.
  - La Filature : `"description": "… L&#x27;Université Populaire de Villeurbanne …"`. CLAF : `"Caisse Locale de l&#x27;Alimentation…"`.
  - La Filature : `"logo": ".../a-la-filature-un-tiers-lieu-occupe-et-anime.social_card.jpg"` (une photo 1200×630), alors que le vrai logo `cropped-Filature-logo-final-tricolore` est affiché dans l'en-tête.
  - `"sameAs": []` sur les trois sites, alors que `config.site_web` est renseigné (`lafilature-villeurbanne.fr`, `www.laraffinerie.re`).
  - `"addressCountry": "France"` (La Filature, Raffinerie) au lieu du code ISO `FR` (CLAF a `FR`).
- **Impact :** les moteurs et les LLM lisent ces champs **tels quels** : un `<script>` ne décode pas les entités HTML. La ville de la Raffinerie devient « L&#x27;Hermitage » pour Google. Le logo n'est pas un logo, ce qui disqualifie le Knowledge Panel. Le `sameAs` vide empêche de relier l'entité TiBillet au site officiel du lieu, alors que c'est **le** levier de désambiguïsation de C1. Risque supposé [S] : un `\` ou un retour à la ligne dans un champ rendrait tout le bloc invalide. C'est exactement le défaut corrigé pour Event lors de l'audit du 2026-07-05 (`pages_tags.py:418-428`), mais il est resté dans le shell.
- **Fichiers :** `pages/templates/pages/V2/shell.html:79-107` ; `:87` (logo = `config.get_social_card`) ; `:88` (`striptags` + autoescape → `&#x27;`) ; `:89` (sameAs sans `site_web`) ; `:93-96` (adresse non échappée pour JSON).
- **Correction :** remplacer le bloc par une balise `{% jsonld_lieu %}` construite avec `json.dumps`, sur le modèle de `jsonld_event`. Contenu :
  - `@type: ["Organization", "Place"]` (ou `EventVenue` / `LocalBusiness` selon le cas) ;
  - `logo` = `config.logo` (absolu) et `image` = `config.img.social_card` ;
  - `sameAs` = `site_web` + facebook + instagram + twitter ;
  - `telephone`, `email` ;
  - `geo` (`GeoCoordinates`, latitude et longitude en float) ;
  - `address` avec `addressCountry` en code ISO.
  - La même dette existe dans `classic/shell.html:73` et `faire_festival/shell.html:226`.
- **Qui :** Code.

### HAUT

#### H1. Le hero ne propose aucune action et les événements arrivent loin sous la ligne de flottaison [V code, S rendu] (Code + Admin)
- **Preuve :** le hero ne contient qu'un `h1` et un sous-titre (`accueil.html:33-38`). Il a un padding vertical allant jusqu'à 8rem (`tb-blocs.css:451`). Viennent ensuite la description longue (environ 350 mots chez La Filature, sans intertitre), le bloc adresse/contact et la carte. Les cartes d'événements n'arrivent qu'après (`accueil.html:208`). Rendu non mesuré : position estimée d'après le CSS et la quantité de texte.
- **Impact SXO :** les requêtes visées sont « La Filature », « La Filature agenda », « La Filature concert », « tiers-lieu Villeurbanne », et l'intention dominante est **« que se passe-t-il, quand, comment réserver »**. En 5 secondes, le visiteur sait ce qu'est le lieu (chez La Filature, pas chez la Raffinerie : « Le Tiers-Lieu Sous les Filaos » ne dit ni où ni quoi). En revanche, il ne voit ni le prochain événement ni bouton « Voir l'agenda » ou « Adhérer ». Le seul accès est le menu en petits caractères. Taux de rebond attendu élevé sur mobile [S].
- **Correction (Code) :**
  1. Ajouter dans le hero 1 ou 2 boutons conditionnels : « Voir l'agenda » (si événements) et « Adhérer » (si `module_adhesion`).
  2. Remonter « Ce qui arrive » **au-dessus** de la présentation, ou insérer le prochain événement dans le hero.
  3. Afficher la description longue repliée après environ 80 mots (`<details>` ou classe CSS) : le texte reste dans le HTML, donc indexé.
- **Correction (Admin) :** écrire une description courte qui dise *quoi + où* (cf. M3).

#### H2. La photo du hero est un fond CSS : pas d'alt, 390 Ko en 1920 px pour tous les écrans, découverte tardive [V] (Code)
- **Preuve :** `style="--tb-hero-image: url('/media/images/a-la-filature-un-tiers-lieu-occupe-et-anime.fhd.jpg');"`. HEAD : 390 671 octets, JPEG. Aucun WebP ou AVIF, aucun `image-set`, aucun preload.
- **Impact :** c'est très probablement l'élément LCP [S]. Le scanner de préchargement ne voit pas les fonds CSS, donc le téléchargement ne démarre qu'après le CSS et la mise en page. Un mobile en 390 px télécharge l'image prévue pour la HD. L'image n'a pas de texte alternatif et n'est pas indexable dans Google Images : la seule photo du lieu sur la page reste invisible pour les moteurs.
- **Fichier :** `pages/templates/pages/V2/vues/accueil.html:30-32` (`config.img.fhd.url` en dur).
- **Correction :** passer à un vrai `<img>` en position absolue sous le contenu du hero :
  - `srcset` sur les variantes `med` / `hdr` / `fhd` et `sizes="100vw"` ;
  - `fetchpriority="high"`, sans `loading="lazy"` ;
  - `alt="{{ config.organisation }}{% if config.postal_address.address_locality %}, {{ config.postal_address.address_locality }}{% endif %}"`, ou un champ « texte alternatif de l'image » dans Configuration.
- **Qui :** Code.

#### H3. Aucune mention légale, CGV ni politique de confidentialité sur le site du lieu [V] (Code)
- **Preuve :** le footer ne contient que les liens du lieu, TiBillet et France 2030 (`footer.html:18-106`). Le champ `Configuration.legal_documents` (« Terms and conditions document », `BaseBillet/models.py:441`) n'est utilisé dans **aucun** gabarit (grep sur tout le dépôt : 0 résultat dans les `.html`).
- **Impact :** le critère « Trust » de l'E-E-A-T est faible. C'est surtout une obligation pour un site qui vend des billets : identité de l'éditeur (LCEN), CGV et RGPD. Les Quality Raters et les LLM regardent qui édite le site. Ici, rien n'indique qui est responsable : TiBillet ou l'association du lieu.
- **Correction :** dans la colonne « lieu » du footer, ajouter « Mentions légales » (une page générée depuis Configuration : nom, adresse, SIREN `config.siren`, e-mail, hébergeur TiBillet) et « CGV » (`config.legal_documents` si renseigné).
- **Qui :** Code (gabarit et page générée). L'admin renseigne SIREN et CGV.

#### H4. Canonique et og:url reprennent les paramètres d'URL [V] (Code)
- **Preuve :** `https://la-filature.tibillet.coop/?utm_source=audit` déclare `<link rel="canonical" href="https://la-filature.tibillet.coop/?utm_source=audit">`. `/event/?tag=atelier` est auto-canonique et `index, follow`.
- **Impact :** chaque lien partagé avec `fbclid`, `utm_*` ou `?tag=` devient une URL « officielle » distincte. Le signal de l'accueil se dilue. Les pages filtres `?tag=` (une par tag, liées depuis chaque carte d'événement) sont des quasi-doublons minces et indexables.
- **Fichiers :** `shell.html:65` (`request.build_absolute_uri`), `:29` (og:url), `:48` (twitter:url).
- **Correction :**
  - Dans `accueil.html` : `{% block canonical %}https://{{ request.get_host }}/{% endblock %}`.
  - Dans le shell, utiliser par défaut `request.build_absolute_uri(request.path)`, sans query string.
  - Pour l'agenda filtré, canonique vers `/event/` ou `noindex, follow` dès qu'un filtre est actif.
- **Qui :** Code.

### MOYEN

#### M1. La présentation du lieu n'a aucun intertitre et les faits clés sont des `<div>` anonymes [V] (Code + Admin)
- **Preuve :** la structure des titres est h1 « La Filature » → h2 « Ce qui arrive » → h3 (événements). Le bloc « ce qu'est le lieu » n'a aucun titre (`accueil.html:45-58`). « Adresse », « Contact » et « Où l'on est » sont des `<div>` ou `<span>` (`:62`, `:82`, `:96`). L'adresse n'est pas dans un `<address>`. Le contenu admin de La Filature est un seul bloc `<p><strong>…</strong></p>` suivi de texte coupé par des `<br>`, avec un collage « …de la Filature.900 m² ».
- **Impact :** la page ne contient aucune section du type « À propos de La Filature » ou « Infos pratiques » que moteurs et LLM pourraient extraire comme passage citable. La lisibilité est faible sur mobile.
- **Correction (Code) :**
  - un `<h2>` « {{ config.organisation }} en bref » (ou « Le lieu »), visible ou `visually-hidden` ;
  - un `<h2>` « Infos pratiques » au-dessus de `venue-facts` ;
  - `<address>` autour de l'adresse et du contact ;
  - « Où l'on est » en `h3`.
- **Correction (Admin) :** découper la description longue en paragraphes et intertitres, corriger les espaces manquantes.

#### M2. Faits locaux incomplets : pas de code postal visible, pas d'horaires, téléphone non cliquable, « Voir sur la carte » trompeur [V] (Code)
- **Preuve :**
  - Le bloc affiche « 10 Rue du Pérou, Villeurbanne », sans le 69100 (`accueil.html:64-65`).
  - La fiche « Horaires » est commentée faute de champ (`accueil.html:72-80`).
  - Le téléphone s'affiche en texte brut `0698895330` / `+262693453393`, sans `tel:` ni formatage (`:85-87`).
  - « Voir sur la carte » mène à `/federation/`, la page réseau « Autour de nous », et non à la carte ou à un itinéraire (`:66-68`).
- **Impact :** l'adresse visible est incomplète, ce qui nuit à la cohérence NAP (nom, adresse, téléphone) attendue en SEO local. Les horaires sont **le** fait que demandent les requêtes « … ouvert aujourd'hui » et les assistants IA. Le libellé de lien ne correspond pas à sa cible.
- **Correction :**
  - afficher `{{ postal_code }} {{ address_locality }}` ;
  - `<a href="tel:{{ config.phone }}">` et formatage via `phonenumbers` ;
  - « Itinéraire » vers `https://www.openstreetmap.org/?mlat=…&mlon=…` ;
  - ajouter un champ `horaires_ouverture` (texte libre, ou `openingHoursSpecification` dans le JSON-LD).
- **Qui :** Code. L'admin remplit ensuite les horaires.

#### M3. La meta description dépend entièrement de l'admin, sans garde-fou ni aide à la saisie [V] (Code + Admin)
- **Preuve :**
  - La Filature : 196 caractères, tronqués vers 155-160 dans les résultats de recherche.
  - Raffinerie : « Le Tiers-Lieu Sous les Filaos » (29 caractères, ni ville ni activité).
  - CLAF : « Caisse Locale de l'Alimentation de Flers Agglo » (46 caractères).
  - Sans description courte, le repli est **le nom seul** (`accueil.html:5`, `shell.html:23`).
  - Le champ n'a pas de `help_text` (`BaseBillet/models.py:426`).
- **Impact :** Google réécrit les descriptions trop courtes avec du texte pris dans la page, souvent le footer TiBillet. Le CTR baisse.
- **Correction (Code) :**
  - `help_text` sur `short_description` : « 120 à 155 caractères : ce qu'est le lieu, la ville, ce qu'on y fait. Ex. : Tiers-lieu à Villeurbanne : café associatif, cantine, concerts et ateliers. » ;
  - repli automatique quand la description fait moins de 70 caractères : `{{ short_description }} – {{ ville }}. {% translate 'Agenda des prochains événements, billetterie et adhésions.' %}`.
- **Correction (Admin) :** Raffinerie et CLAF doivent réécrire leur description courte. La Filature doit raccourcir la sienne.

#### M4. Le footer et les panneaux TiBillet identiques pèsent 28 à 50 % du texte de la page [V] (Code)
- **Preuve :** 173 mots identiques sur les 3 sites (footer TiBillet, mention France 2030, panneaux contact et connexion), sur un total de 626 (La Filature, 28 %), 428 (Raffinerie, 40 %) et 342 mots (CLAF, 50 %). Il faut y ajouter environ 30 mots d'interface (menu en double desktop/mobile, « Connexion Français Anglais »…). Le paragraphe « TiBillet est un commun numérique : billetterie en ligne, caisse enregistreuse… » (`footer.html:53-54`) est répété sur ~500 sous-domaines.
- **Impact :** sur les lieux à texte court (la majorité, supposé [S]), le thème le plus présent sur la page devient « billetterie / caisse enregistreuse / coopérative » et non le lieu. La page ressemble à une page mince générée en masse, et l'extrait est parfois tiré du footer [S].
- **Correction :** réduire le bloc marque à une ligne (« Billetterie propulsée par TiBillet, coopérative du numérique libre »), supprimer le paragraphe descriptif (sa place est sur tibillet.coop) et garder les liens communautaires.
- **Qui :** Code.

#### M5. Le contenu change de langue selon `Accept-Language` sur la même URL, sans hreflang [V] (Code)
- **Preuve :** avec `Accept-Language: en-US`, la même URL `/` renvoie `<html lang="en">`, `Home | La Filature`, « What's coming up · 21 upcoming events », « Free entry », `og:locale en_US`, `Vary: … Accept-Language`, et la même canonique.
- **Impact :** Googlebot crawle en général sans `Accept-Language`, donc la version FR est indexée [S]. Les autres robots (Bing, robots IA, agrégateurs) peuvent recevoir une page hybride, avec l'interface en anglais et le contenu du lieu en français, sous la même URL. Il n'existe aucune URL anglaise distincte vers laquelle pointer un hreflang.
- **Correction :** pour les visiteurs anonymes, ne négocier la langue **que** par le cookie du sélecteur, la langue par défaut du lieu étant le français. Ou bien créer des URL préfixées (`/en/`) avec hreflang réciproque.
- **Qui :** Code.

#### M6. Libellés de prix fautifs sur toutes les cartes de tous les lieux [V] (Code)
- **Preuve :** « Entré libre » (sans e) sur La Filature et CLAF ; « A partir de 0.00 € » (sans accent, point décimal à l'anglaise, 0 € annoncé comme prix d'appel) sur la Raffinerie.
- **Fichiers :** `BaseBillet/views.py:2839` (`_("A partir de %(price)s €")` avec un Decimal brut), `:2843` et `:3253` (`_("Entré libre")`).
- **Impact :** la faute d'orthographe est répétée sur ~500 sites, ce qui nuit au sérieux (E-E-A-T). Un prix « 0.00 € » n'est ni lisible ni cohérent avec `offers.price` du JSON-LD Event.
- **Correction :** `_("Entrée libre")`, `_("À partir de %(price)s €")` avec `floatformat:"-2"` ou `localize`, et « Gratuit » quand le minimum est 0. Mettre à jour les `.po` (le mainteneur lance makemessages).
- **Qui :** Code.

#### M7. Les images des cartes sont choisies selon la fenêtre, pas selon la carte : trop lourdes et sans lazy-load [V] (Code)
- **Preuve :** les `<source media="(min-width: 1920px)…">` et `(min-width: 1280px)` (`picture.html:15-19`) font charger la variante `fhd` (293 Ko, mesurée sur `atelier.fhd.jpg`) ou `hdr` (169 Ko) pour une carte d'environ 370 px de large sur un écran de bureau. Les variantes `med`/`crop` pèsent 22 à 45 Ko. Les `<img>` n'ont ni `loading="lazy"` ni `decoding="async"` (`picture.html:32-37`), alors que les cartes sont sous la ligne de flottaison. Le logo, affiché en 52 px, charge aussi sa variante `fhd` (39 Ko) sur les grands écrans.
- **Impact :** environ 1,3 Mo d'images sur un écran 1920 px [S, d'après la logique de sélection de `<picture>`]. Le LCP et l'INP se dégradent, ce qui pèse sur l'expérience de page.
- **Correction :** remplacer les `<source media>` par un `<img srcset="… 480w, … 960w, … 1280w, … 1920w" sizes="(min-width: 960px) 33vw, 100vw" loading="lazy" decoding="async">`. Ajouter un paramètre `sizes` au partial : `33vw` pour les cartes, `52px` pour le logo.
- **Qui :** Code.

#### M8. L'accueil ne lie que 3 événements sur 21, et le sitemap omet l'agenda tout en listant des événements passés [V] (Code)
- **Preuve :**
  - L'accueil annonce « Ce qui arrive · 21 événements à venir » mais `events|slice:":3"` n'en affiche que 3 (`agenda_a_venir.html:24`). La vue calcule pourtant les prix des 21 (`views.py:2828-2846`).
  - Le sitemap de La Filature (36 URL) ne contient ni `/event/` ni `/memberships/`, seulement `/`, `/federation/` et des fiches événement, dont des événements **passés** (brocante du 2026-09-04, etc.).
  - Raison : `StaticViewSitemap` n'ajoute `event-list` que si `module_billetterie` (`sitemap.py:105`), alors que l'agenda est dans le menu. Explication supposée [S] : le module est probablement désactivé chez La Filature. `EventSitemap.items()` prend tous les `published=True` sans filtre de date (`sitemap.py:57`).
- **Impact :** l'agenda, page cible naturelle de « La Filature agenda », n'est déclaré nulle part. Le budget de crawl part dans des événements terminés.
- **Correction :**
  - afficher 6 cartes ;
  - libellé d'ancre « Tout l'agenda de {{ config.organisation }} » (`agenda_a_venir.html:20`) ;
  - ajouter `event-list` dès qu'il existe des événements publiés à venir, quel que soit le module ;
  - dans `EventSitemap`, ne garder que les événements à venir (ou passés depuis moins de N jours) ;
  - `lastmod` = date de modification et non `created` (`sitemap.py:61`).
- **Qui :** Code.

#### M9. Contact affiché : e-mail personnel et texte d'ancre en URL brute [V] (Admin)
- **Preuve :**
  - La Filature affiche `jturbeaux@pm.me` (adresse nominative) comme contact du lieu ; CLAF affiche `nicolas.vivier@coopcircuits.fr`.
  - Dans la description longue de La Filature : « Déposez votre dossier ici : https://la-filature.tibillet.coop/event ». C'est un lien dont l'ancre est l'URL, et qui mène à l'agenda plutôt qu'à un formulaire de dépôt de dossier. Même chose pour « …c'est ici : https://lafilature-villeurbanne.fr/#newsletter » (inscription bénévole → ancre newsletter).
  - Tag mal orthographié : « Université populaire de villeurbnane » (`/event/?tag=universite-populaire-de-villeurbnane`).
- **Impact :** confiance (E-E-A-T), vie privée de la personne, ancres sans valeur, faute répétée dans une URL indexable.
- **Correction :** utiliser un e-mail générique (contact@…), écrire des ancres descriptives (« déposer un projet », « devenir bénévole ») et corriger le tag et son slug.
- **Qui :** Admin. Côté code, une piste : `help_text` sur `email` (« adresse publique du lieu, affichée sur l'accueil »).

### BAS

#### B1. Pas de llms.txt [V] (Code)
- **Preuve :** `/llms.txt` renvoie 404 (page d'erreur HTML de 42 Ko). `robots.txt` est générique (`views_robots.py:40-46`).
- **Impact :** faible aujourd'hui (aucun moteur majeur ne lit llms.txt de façon confirmée). Le coût est quasi nul, et ce serait un résumé « citable » propre à chaque lieu.
- **Correction :** une vue `llms_txt` qui génère en Markdown, depuis Configuration : `# {{ organisation }}` > description courte ; adresse, ville, contact, site officiel ; liens vers `/event/`, `/memberships/` et le flux RSS. Profiter de l'occasion pour ajouter `Disallow: /my_account/` et `Disallow: /panier/` dans robots.txt.
- **Qui :** Code.

#### B2. Le titre de la carte d'événement n'est pas un lien [V] (Code)
- **Preuve :** `<h3 class="event-card__title">{{ event.name }}</h3>` sans lien (`event_card.html:59`). Le seul lien interne vers la fiche est « En savoir plus » (+ nom en `visually-hidden`, `:104-107`).
- **Impact :** l'ancre visible reste générique, la zone cliquable est petite sur mobile, et le signal d'ancre est moins net que si le lien portait le nom de l'événement.
- **Correction :** mettre le lien sur le `h3` (lien étiré `stretched-link` sur la carte) et garder « En savoir plus » en `aria-hidden` ou le retirer.
- **Qui :** Code.

#### B3. `alt=""` sur les images d'événements [V] (Code), défendable
- **Preuve :** `event_card.html:35` (`alt=""`). Sur la prod, les 3 images de cartes ont `alt=''`.
- **Impact :** c'est correct pour l'accessibilité (l'image est décorative, le titre suit). En contrepartie, les affiches d'événements sont absentes de Google Images.
- **Correction (facultative) :** `alt="{{ event.name }}"` **uniquement si** le titre n'est pas lu juste après, sinon c'est redondant. À ne pas faire tant que B2 n'est pas traité.

#### B4. Landmarks et navigation au clavier [V] (Code)
- **Preuve :**
  - L'en-tête du lieu (identité + menu) est **dans** `<main>` (`shell.html:238-246`), pas dans un `<header>`.
  - Il n'y a pas de lien d'évitement « Aller au contenu ».
  - Les titres des panneaux hors écran apparaissent après le footer, dans le désordre : `h5` « Aide et contact », `h5` « Connexion », puis `h4`.
  - Le libellé « Documentation » est doublé dans le footer et dans le panneau contact.
- **Impact :** faible en SEO, réel pour les lecteurs d'écran et pour la lecture de la structure de la page.
- **Correction :** envelopper `tenant_header.html` dans `<header>` avant `<main>`, ajouter un lien d'évitement `visually-hidden-focusable`, passer les titres des panneaux en `h2`.

#### B5. og:image:alt peu descriptif et choix d'image laissé à l'admin [V] (Code + Admin)
- **Preuve :** `og:image:alt` vaut « La Filature - Page d'accueil » (`accueil.html:8`). La Raffinerie utilise comme image principale un logo en cartouche (`logocartouche_La_Raffinerie_bleu…social_card.jpg`), recadré en 1200×630 pour l'aperçu social et en fond de hero.
- **Correction :** alt = « {{ organisation }}, {{ ville }} » (Code). Pour l'image principale, une photo du lieu, pas un logo, avec une consigne dans le `help_text` de `config.img` (Admin).

---

## Requêtes cibles et réponse de la page (SXO)

| Requête | La page y répond-elle ? | Manque |
|---|---|---|
| « La Filature » / « La Filature Villeurbanne » | Partiellement : nom en h1, ville dans l'en-tête et la description. | Ville absente du title (C1) ; `sameAs` vide alors que l'entité est ambiguë (C2). Concurrence directe du site officiel `lafilature-villeurbanne.fr` : le sous-domaine TiBillet doit se positionner « agenda / billetterie ». |
| « La Filature agenda » / « concert La Filature » | Mal : 3 événements seulement, sous la ligne de flottaison. | Bouton agenda dans le hero, plus d'événements remontés (H1, M8) ; `/event/` absent du sitemap. |
| « tiers-lieu Villeurbanne » | Uniquement grâce au texte saisi par l'admin. | Aucun champ « type de lieu » ; `Client.categorie` (S/F/A…) est trop grossier pour alimenter le title. |
| « La Filature horaires » / « adresse » | Adresse oui (sans code postal), horaires non. | M2. |
| « adhérer La Filature » | Non visible sur l'accueil (sections commentées `accueil.html:210-332`). | Bouton « Adhérer » si le module est actif. |

**Ce qui relève de l'admin du lieu (à communiquer, par exemple dans un guide « bien remplir sa fiche ») :** description courte de 120 à 155 caractères avec *quoi + où* ; description longue structurée en paragraphes et intertitres ; e-mail public générique ; photo du lieu (pas un logo) en image principale ; logo séparé ; site web et réseaux sociaux renseignés (ils alimenteront `sameAs` une fois C2 corrigé) ; orthographe des tags.

**Ce qui relève du code (vaut pour ~500 lieux) :** C1, C2, H1 à H4, M1 à M8, B1 à B5. Par ordre de rentabilité : **C1 (title) → C2 (JSON-LD) → H4 (canonique) → M6 (libellés) → H1/H2 (hero)**. Les quatre premiers se règlent en quelques lignes de gabarit ou de balise de gabarit.

---
Sources de la recherche web (SXO) : [lebonbon.fr — La Filature, quartier de 5 ha à Villeurbanne](https://en.lebonbon.fr/lyon/news/new-spinning-mill-xx-large-neighborhood-5-hectares-villeurbanne/), [lyondemain.fr](https://www.lyondemain.fr/actu/artistes).
