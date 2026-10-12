# Audit SEO — vue plateforme et code : accueil V2 à l'échelle de 500 lieux

Date : 2026-10-12. Périmètre : ce que les audits page par page ne voient pas — duplication inter-lieux, pages minces en masse, maillage racine ↔ lieux, sitemaps, et la cause dans le code.

Méthode :
- Code lu (lecture seule) : `pages/templates/pages/V2/{shell,headless,tenant_header}.html`, `vues/{accueil,evenement,agenda,reseau}.html`, `partials/footer.html`, `cotton/V2/event_card.html`, `BaseBillet/views.py` (`index`, `get_context`, `EventMVT.retrieve/federated_events_*`), `BaseBillet/sitemap.py`, `pages/sitemap.py`, `seo/{views,views_common,services,tasks}.py`, `seo/templates/seo/*`, `Customers/middleware.py`, `TiBillet/seo_indexing.py`.
- Prod, lecture seule : 27 requêtes GET/HEAD à ≤ 1/s. Sitemap index racine (481 lieux), 14 accueils de lieux (13 + 1 tenant de test), 2 fiches événement croisées, 3 sitemaps de lieux, 3 variantes d'URL. Fichiers bruts dans `../raw/`, liste des lieux dans `../tenants_list.txt`, sortie de l'analyseur dans `../analyse_accueils.txt`.
- Chaque constat est marqué **[vérifié]** (observé en prod ou lu dans le code) ou **[supposé]** (déduit, non mesuré).

---

## 0. L'échantillon en un tableau

Sitemap index racine `https://tibillet.coop/sitemap.xml` : 481 lieux « vivants » (425 `.tibillet.coop`, 54 `.tibillet.re`, 2 domaines propres). Échantillon : les 7 premiers du sitemap index, 4 pris aux rangs 120/240/360/470, plus la-filature, raffinerie et claf (captures des autres agents), plus `test.tibillet.coop`.

| Lieu | `<title>` | meta description | og:image | Événements affichés | Texte par défaut « Bienvenue… » | Mots du contenu propre* | Mots du footer TiBillet | JSON-LD Organization |
|---|---|---|---|---|---|---|---|---|
| la-filature.tibillet.coop | Accueil \| La Filature | OK (161 c.) | oui | 3 (21 à venir) | non | 263 | 92 | valide, entités HTML `&#x27;` |
| raffinerie.tibillet.re | Accueil \| La Raffinerie | « Le Tiers-Lieu Sous les Filaos » | oui | 3 (10) | non | 76 | 93 | valide, entités HTML |
| claf.tibillet.coop | Accueil \| CLAF | OK | oui | 2 (2) | non | 52 | 92 | valide, entités HTML |
| yauternet.tibillet.coop | Accueil \| Yauternet | OK | **vide** | 0 | non | 17 | 95 | valide |
| la-hune-scopie.tibillet.coop | Accueil \| La Hune - Scopie | **« gdfvxc »** | **vide** | 0 | **oui** | 67 (dont ~50 de texte par défaut) | 95 | valide |
| sauvegarde-du-nord.tibillet.coop | Accueil \| CHSF de La Sauvegarde du Nord | **« None »** (littéral) | oui | 0 | non | 16 | 97 | valide, entités HTML |
| association-nationale-des-tiers-lieux.tibillet.re | Accueil \| Association Nationale des Tiers-Lieux | « Association loi du 1er juillet 1901 » | oui | 3 (9) | non | 49 | 100 | valide |
| cuisine-commune-de-chaud-bouillon.tibillet.coop | Accueil \| Cuisine Commune de Chaud Bouillon | OK | oui | 3 (9) | non | 16 | 96 | valide, entités HTML |
| la-fabrique.tibillet.coop | Accueil \| La Fabrique | OK | oui | 3 (17) | non | 49 | 92 | valide, entités HTML |
| la-ferme-du-lac.tibillet.coop | Accueil \| La ferme du Lac | OK | **vide** | 0 | **oui** | 68 (texte par défaut) | 95 | valide |
| zamm.tibillet.coop | Accueil \| ZAMM | OK | **vide** | 0 | **oui** | 54 (texte par défaut) | 92 | valide |
| club-des-elus-a-l-eco-transition.tibillet.coop | Accueil \| CLUB DES ELUS A L ECO TRANSITION | OK | **vide** | 0 | **oui** | 54 (texte par défaut) | 98 | valide |
| lapasrel.tibillet.coop | Accueil \| LAPASREL | OK (contient un saut de ligne) | **vide** | 0 | non | 172 | 92 | **INVALIDE** (`Invalid control character`) |
| test.tibillet.coop | Accueil \| test | « test » | **vide** | 0 | non | 18 | 92 | valide |

\* « contenu propre » = mots de la section `venue-brief` (description longue + adresse + contact), hors en-tête, hors cartes d'événements, hors footer.

Lecture [vérifié sur 13 lieux réels] :
- **7/13 accueils sans aucun événement et sans image** (og:image vide) ; **4/13 affichent encore le texte d'onboarding « Bienvenue dans votre nouvel espace ! »** ; 2/13 ont une meta description cassée (« gdfvxc », « None »).
- Sur **8/13 lieux, le footer TiBillet (92-100 mots, identique partout) pèse plus que le contenu propre du lieu.**
- 13/13 : `<title>` = « Accueil | {organisation} », `<h1>` = nom seul, `robots: index, follow`, aucun `hreflang`.
- JSON-LD Organization : 6/13 contiennent des entités HTML dans le JSON (`L&#x27;Université`), 1/13 est invalide.

Le sitemap index racine liste aussi **16 tenants au nom explicite de test/démo** [vérifié] : `test.tibillet.coop`, `test-22`, `testttt`, `test-cath`, `cerobytetest`, `demo-gorgon`, `collectif-test-de-paul`, `test-formation-ul-36`, etc. Ils sont « vivants » au sens du code (un produit publié suffit) et donc déclarés à Google avec `index, follow`.

---

## 1. CRITIQUE

### C1 — Chaque fiche événement fédérée existe en N copies auto-canoniques, avec un JSON-LD `organizer` faux [vérifié]

**Preuve.** La Filature et l'Université Populaire de Villeurbanne (UPV) sont fédérées. Un événement de l'UPV est servi en page complète, indexable, sur le domaine de La Filature :

- `https://la-filature.tibillet.coop/event/12h12-la-democratie-est-elle-extensible-aux-enfants-251112-1212-39901a9a/` → HTTP 200, `<title>12h12 - La démocratie… | La Filature</title>`, `robots: index, follow`, `<link rel="canonical" href="https://la-filature.tibillet.coop/event/12h12-…/">` (auto-canonique), JSON-LD `"organizer": {"name": "La Filature", "url": "https://la-filature.tibillet.coop/"}` alors que l'organisateur est l'UPV.
- Sens inverse identique : `https://universite-populaire-villeurbanne.tibillet.coop/event/radio-social-club-261014-0930-dcb5aed3/` (événement de La Filature) → 200, canonical auto, `organizer = Université Populaire Villeurbanne`.
- L'original (`event1.html`) a lui aussi un canonical sur lui-même : Google voit deux pages distinctes qui se déclarent chacune originale, avec deux organisateurs différents pour le même événement.

**Impact à l'échelle.** Tout lieu avec `module_federation` et au moins un `FederatedPlace` reçoit une copie indexable de chaque événement de ses voisins, sous son propre domaine, avec un JSON-LD Event qui ment sur l'organisateur. Avec les fédérations thématiques par tags (`FederationConfiguration.tags_federation`, `BaseBillet/views.py:3330-3355`), le nombre de copies d'un même événement peut atteindre le nombre de lieux partageant le tag. Les signaux (liens, partages) se dispersent entre copies ; les rich results Event risquent d'afficher le mauvais organisateur ; cannibalisation au sein de `*.tibillet.coop`.

**Cause dans le code.**
- `BaseBillet/views.py:3814-3820` (`EventMVT.retrieve`) : `except Event.DoesNotExist` → `self.federated_events_get(slug)` cherche l'événement dans **tous** les `FederatedPlace` et le rend avec le gabarit local.
- `pages/templates/pages/V2/vues/evenement.html` : aucun `{% block canonical %}` → le canonical par défaut de `shell.html:65` (`request.build_absolute_uri`) s'applique.
- `pages/templatetags/pages_tags.py:409-495` (`jsonld_event`) : `url = request.build_absolute_uri()` et `organizer.name = config.organisation` (config du lieu **visiteur**, pas du lieu d'origine).

**Correction (petite, dans l'architecture existante).** `Event.full_url` est déjà stocké à la sauvegarde avec le domaine d'origine (`BaseBillet/models.py:2792-2793`) et déjà utilisé par `event_card.html` pour le lien « via ». Il suffit de :
1. `evenement.html` : ajouter `{% block canonical %}{{ event.full_url }}{% endblock %}` (et pareil pour `og:url` si on le passe en bloc, cf. C3). La copie fédérée pointe alors vers l'original ; l'original pointe vers lui-même.
2. `jsonld_event` : `"url": event.full_url`, et `organizer` lu depuis le lieu d'origine. Le plus simple sans requête cross-schema : quand `event_in_this_tenant` est `False` (déjà calculé dans `retrieve`, ligne 3733/3812 et passé au contexte ligne 3836), **ne pas émettre le JSON-LD Event** (ou n'émettre que `url` + `sameAs`), la copie n'étant pas canonique. Variante plus propre : poser `organizer` depuis le nom de domaine d'origine extrait de `full_url`.
3. Optionnel mais recommandé : `{% block meta_robots %}{% if not event_in_this_tenant %}noindex, follow{% else %}{{ block.super }}{% endif %}{% endblock %}` dans `evenement.html`. Le canonical seul est un indice, le `noindex` est un ordre.

### C2 — Des centaines d'accueils minces, tous `index, follow`, tous déclarés dans les sitemaps [vérifié sur l'échantillon, extrapolé sur 481]

**Preuve.** Voir tableau : 7/13 accueils réels n'ont ni événement ni image, 4/13 gardent le texte d'onboarding, `test.tibillet.coop` (« Accueil | test », description « test ») est indexable et dans le sitemap index racine. `https://zamm.tibillet.coop/sitemap.xml` déclare `/` et `/federation/` pour un lieu dont la page d'accueil se réduit au texte par défaut.

**Impact à l'échelle.** Si l'échantillon est représentatif (c'est un échantillon aléatoire du sitemap index, pas des « meilleurs » lieux), de l'ordre de **la moitié des 481 lieux** expose à Google une page d'accueil quasi vide, au gabarit identique (même `<title>` « Accueil | … », même h1 seul, même footer de ~95 mots). Google évalue la qualité par hôte, mais `*.tibillet.coop` partage un nom de domaine racine : à cette échelle le motif est celui du « scaled content » que le guide Google cité dans `TECH_DOC/SESSIONS/SEO/SPEC.md` demande d'éviter. Les lieux riches (La Filature) en paient la note.

**Cause dans le code.**
- `TiBillet/seo_indexing.py` : `noindex` est **global à l'instance** (flags d'env DEBUG/TEST/DEMO), jamais par tenant ni par page.
- `pages/templates/pages/V2/shell.html:24` : `meta_robots` ne connaît que `noindex_seo`.
- `BaseBillet/views.py:2780-2860` (`index`) : aucun calcul de « contenu suffisant ».
- `BaseBillet/sitemap.py:96-139` (`StaticViewSitemap.items`) : `'index'` est **toujours** déclaré (les autres sections sont conditionnelles, pas la racine).
- `seo/tasks.py:306-310` et `seo/services.py:127` : un lieu est « vivant » si `event_count > 0 OU product_count > 0` — un seul produit publié (même sur un tenant « test ») suffit à entrer dans le sitemap index racine et le bandeau de la landing.
- `BaseBillet/validators.py:1417` : le texte « Bienvenue dans votre nouvel espace ! » est écrit dans `long_description` à la création du tenant et jamais retiré.

**Correction.**
1. Dans `index()` (après le calcul de `events_a_afficher`), poser `template_context["accueil_est_mince"] = (not events_a_afficher) and (not config.img) and (not config.long_description or "Bienvenue dans votre nouvel espace" in config.long_description)`. Trois lignes, lisibles, pas de nouvelle table.
2. `accueil.html` : `{% block meta_robots %}{% if accueil_est_mince %}noindex, follow{% else %}{{ block.super }}{% endif %}{% endblock %}`. `follow` pour conserver le maillage vers l'agenda/adhésions si elles existent.
3. `StaticViewSitemap.items()` : n'ajouter `'index'` que si la même condition est fausse (même logique que les autres sections, « une page vide au sitemap est un signal négatif », déjà écrit dans le commentaire ligne 97-100).
4. `seo/tasks.py` (filtre « vivant ») : exiger `event_count > 0` **ou** (`product_count > 0` **et** `short_description` non vide **et** pas de texte par défaut) ; exclure les schémas dont le nom commence par `test`/`demo` (ou mieux : un champ `Client.exclure_du_referencement` renseigné à la main par l'équipe pour les 16 tenants listés — [supposé] que c'est l'équipe qui les a créés).
5. Produit : un bandeau admin « votre accueil n'est pas référencé tant que… » rendrait la règle visible aux lieux (hors périmètre code SEO, mais c'est ce qui fera remonter le taux de pages pleines).

### C3 — Canonical et og:url recopient la query string ; `/event/embed/` et `?skin_preview=` sont indexables [vérifié]

**Preuve.**
- `https://la-filature.tibillet.coop/?utm_source=audit` → 200, `<link rel="canonical" href="https://la-filature.tibillet.coop/?utm_source=audit">`, `og:url` idem, `index, follow`.
- `https://la-filature.tibillet.coop/?skin_preview=classic` → 200, autre skin rendu (sans authentification), canonical `…/?skin_preview=classic`, `index, follow`.
- `https://la-filature.tibillet.coop/event/embed/` → 200, `<title>Agenda | La Filature</title>`, canonical `…/event/embed/`, `index, follow` : copie intégrale de `/event/` sans navbar/footer.
- Par le code : `/event/?tag=…`, `/event/?search=…`, `/event/?page=N` (`agenda.html` ne surcharge pas `canonical`) → espace d'URL infini, chacune auto-canonique.

**Impact à l'échelle.** × 481 lieux : chaque lien tracké partagé par un lieu (newsletter, réseaux sociaux avec utm) crée un doublon indexable de l'accueil ; chaque iframe `embed` posée sur le site d'un lieu crée une copie indexable de l'agenda ; l'aperçu admin des skins est indexable par quiconque devine le paramètre.

**Cause dans le code.** `shell.html:29` (`og:url`) et `shell.html:65` (`canonical`) utilisent `request.build_absolute_uri` (chemin **et** query). `EventMVT.embed` (`views.py:3695-3697`) et `MembershipMVT.embed` (`:4258-4261`) posent `embed=True` sans `noindex`. `skin_preview_de_la_requete` (`views.py:267-284`) n'exige aucun droit.

**Correction.**
1. `shell.html` : remplacer les deux `{{ request.build_absolute_uri }}` par `https://{{ request.get_host }}{{ request.path }}` (chemin sans query). Pour l'agenda, les filtres `?tag=` restent accessibles aux robots via les liens, mais consolidés sur `/event/`. Un gabarit qui veut une canonique différente surcharge déjà le bloc (`page.html` le fait).
2. `shell.html:24` : `{% if noindex_seo or embed or skin_preview %}noindex, nofollow{% else %}…` — trois variables déjà présentes dans le contexte, zéro vue à toucher.
3. `og:url` : le faire passer par le même `{% block canonical %}` (un seul bloc, deux usages) pour que fiche partagée = fiche canonique.

---

## 2. HAUT

### H1 — JSON-LD Organization/WebSite écrit à la main dans `shell.html` : invalide ou pollué sur ~la moitié des lieux [vérifié]

**Preuve.** `lapasrel.tibillet.coop` : `json.loads` échoue (`Invalid control character`, saut de ligne dans `short_description`). 6/13 lieux ont `L&#x27;Université`, `d&#x27;atelier`… dans la chaîne JSON : à l'intérieur d'un `<script>`, le navigateur et Google **ne décodent pas** les entités HTML, la valeur lue est littéralement `L&#x27;Université`. Le fichier `pages_tags.py:420-432` documente exactement ce piège (« audit SEO 2026-07-05 : JSON écrit à la main INVALIDE ») et l'a corrigé pour Event… mais pas pour Organization.

**Impact.** Sur tout lieu dont le nom ou la description contient une apostrophe (très fréquent en français) ou un saut de ligne, le Knowledge Panel/Organization est faux ou ignoré en silence. Cela touche aussi `"name": "{{ config.organisation }}"` (`shell.html:85,102`) et `address` (virgule finale si `address_country` est vide — [supposé], le champ n'a pas de défaut, `models.py:331`).

**Cause.** `shell.html:79-110` : JSON en gabarit Django avec autoescape HTML.

**Correction.** Un templatetag `{% jsonld_organisation config %}` dans `pages_tags.py`, construit avec `json.dumps` comme `jsonld_event` (même échappement `<`). Une trentaine de lignes, le gabarit garde une ligne.

### H2 — Titre, description et h1 génériques sur 500 sites ; meta description « None » [vérifié]

**Preuve.** 14/14 `<title>` = « Accueil | {org} ». `sauvegarde-du-nord` : `<meta name="description" content="None">`. `la-hune-scopie` : « gdfvxc ». Le h1 est le nom seul.

**Impact.** « Accueil » n'apporte rien au classement et occupe le début du `<title>` (le plus pesé). Un lieu qui cherche « tiers-lieu Villeurbanne » doit le trouver dans le `<title>`. La description « None » est affichée telle quelle dans les SERP.

**Cause.**
- `accueil.html:4` : `{% block title %}{% translate 'Accueil' %}{% endblock %}` + `shell.html:25` ajoute ` | {{ config.organisation }}`.
- `accueil.html:5,7,10` et `reseau.html:16` : `{{ config.short_description|striptags|default:config.organisation }}` — `striptags(None)` renvoie la chaîne `"None"`, qui est vraie, donc `default` ne s'applique jamais. `agenda.html:30,32,35` : `- {{ config.short_description }}` → « - None » quand vide.

**Correction.**
- `accueil.html:4` : `{% block title %}{{ config.organisation }}{% if config.postal_address.address_locality %} — {{ config.postal_address.address_locality }}{% endif %}{% endblock %}` et dans `shell.html:25` ne suffixer ` | {{ config.organisation }}` que si le bloc ne commence pas déjà par le nom (ou, plus simple : `accueil.html` surcharge un bloc `title_complet` ; on peut aussi laisser le suffixe et accepter « La Filature — Villeurbanne | La Filature », moins bien).
- Inverser l'ordre des filtres : `{{ config.short_description|default:config.organisation|striptags }}` (4 occurrences). `agenda.html` : entourer de `{% if config.short_description %}`.
- La description par défaut d'un lieu sans `short_description` devrait être une phrase construite : « {org} : agenda, billetterie et adhésions à {ville} sur TiBillet » plutôt que le nom seul (identique au `<title>`).

### H3 — Maillage racine ↔ lieux ↔ voisins quasi inexistant pour les robots [vérifié]

**Preuve.**
- `https://la-filature.tibillet.coop/federation/` (« Autour de nous ») : les voisins (UPV, Relief) ne sont présents que dans `<script id="explorer-data" type="application/json">` ; **aucun `<a href>` vers un lieu voisin**. Le seul lien sortant est `https://tibillet.coop/explorer/`.
- `https://tibillet.coop/explorer/` est `noindex, nofollow` (`seo/templates/seo/explorer.html:15`) : les liens qu'il contient ne transmettent rien, et il est rendu en JS.
- `https://tibillet.coop/` : 100 liens `<a href="https://{lieu}/">` tirés **au hasard** parmi 481 à chaque chargement (`seo/views.py:166-186`). Un lieu donné a ~20 % de chances d'être lié au moment du crawl ; il n'existe **aucune page annuaire indexable** (`/lieux/` évoqué dans les commentaires de `landing.html:233-236` et `PIEGES.md:43`, mais absent de `seo/urls.py`).
- Les 6 liens événements de la landing sont sans slash final (`href="https://la-filature.tibillet.coop/event/radio-social-club-261014-0930-dcb5aed3"`) → `HEAD` : **301** vers la version avec slash. Chaque lien passe par une redirection.
- Le footer de chaque lieu renvoie vers `tibillet.coop` (3 liens), mais rien ne revient de façon stable.

**Impact.** Les 481 sous-domaines ne reçoivent de la racine qu'un lien instable ; les voisins fédérés, qui sont la seule « preuve » thématique/locale entre lieux, ne sont pas liés en HTML. Le réseau existe en base, pas pour Google.

**Cause.** `reseau.html:169-198` (rendu par `explorer.js`), `explorer.html:15` (`nofollow`), `seo/views.py:166-186` (shuffle + plafond 100), `seo/tasks.py:118` (`canonical_url` construit sans `/` final).

**Correction.**
1. `reseau.html` : sous la carte, une liste HTML `{% for lieu in explorer_data.tenants %}<li><a href="https://{{ lieu.domain }}/">{{ lieu.name }}</a> — {{ lieu.locality }}</li>{% endfor %}` (données déjà dans le contexte, 5 lignes). Même chose pour les événements voisins si présents.
2. `explorer.html:15` : `noindex, follow` (garder noindex, retirer nofollow) **et** rendre la liste des lieux en HTML serveur (le JSON `explorer-data` est déjà là) ; ou créer la page `/lieux/` indexable, triée par ville, paginée (une vue `seo/views.py` lisant `AGGREGATE_LIEUX`, un gabarit ; la déclarer dans `sitemap_root_view`).
3. `seo/tasks.py:118` : `f"https://{tenant_domain}/event/{slug}/"`.

### H4 — Sitemaps : événements privés, archivés, actions bénévoles et passés sans limite ; `lastmod` sans valeur [vérifié dans le code ; passés vérifiés en prod]

**Preuve.**
- `BaseBillet/sitemap.py:57` : `Event.objects.filter(published=True)` — pas de filtre `archived=False`, `private=False`, ni `.exclude(categorie=Event.ACTION)`, alors que l'agenda (`views.py:3380-3395`) applique les trois.
- `universite-populaire-villeurbanne…/sitemap.xml` liste des événements de novembre 2025 (11 mois) ; la-filature : 12 des 33 URL d'événements sont passées. Rien ne borne.
- `BaseBillet/sitemap.py:61` : `lastmod = obj.created` (l'événement n'a pas de champ de modification).
- `seo/views.py:667` : `tenant.get("updated_at", timezone.now())` — la clé n'existe pas dans `sitemap_tenants` (`seo/tasks.py:333-337`) → **481 `<lastmod>` = date du jour**, à chaque rebuild. Google ignore les `lastmod` qu'il juge non fiables, pour tout l'index.

**Impact.** Événements « non fédérables » (`private=True`) et archivés déclarés à Google ; budget de crawl dépensé sur des pages passées à `eventStatus: EventScheduled` ; signal `lastmod` discrédité pour les 481 sitemaps.

**Correction.** `EventSitemap.items()` : `Event.objects.filter(published=True, archived=False, private=False).exclude(categorie=Event.ACTION)` ; borner les passés à `datetime__gte=now - 6 mois` (les anciens restent accessibles, juste plus « poussés »). `sitemap_index_view` : retirer `<lastmod>` ou stocker la vraie date dans `sitemap_tenants` (max `created` des événements du lieu, disponible dans `TENANT_SUMMARY`).

---

## 3. MOYEN

### M1 — Sitemap index racine inter-hôtes [supposé]
`https://tibillet.coop/sitemap.xml` référence 481 sitemaps sur d'autres hôtes. Google n'accepte les sitemaps inter-hôtes que si la propriété est vérifiée en Search Console (une propriété de **domaine** `tibillet.coop` couvre les 425 sous-domaines, pas `tibillet.re` ni `latendresse.fr`/`fairefestival.fr`). À vérifier côté GSC ; sinon ces entrées sont ignorées sans erreur visible. Pour les 54 `.tibillet.re` : soit une 2ᵉ propriété de domaine, soit migrer en `.coop` (le `CanonicalDomainRedirectMiddleware`, `Customers/middleware.py`, est prêt mais en 302 : passer `REDIRECTION_PERMANENTE = True` une fois la config figée).

### M2 — FR/EN par cookie : pas d'URL par langue [vérifié]
`language-switcher.mjs` POST `/i18n/setlang/` puis recharge ; la même URL sert `lang="fr"` ou `lang="en"` selon cookie/`Accept-Language` (`Vary` correct). Conséquence : pas de `hreflang` possible, la version EN n'est jamais indexée, et un robot en `Accept-Language: en` peut indexer un `<title>Home | La Filature</title>` pour la page FR. Acceptable tant que le public est francophone ; ne pas ajouter de `hreflang` sans URL distincte (`i18n_patterns`), ce serait faux.

### M3 — Footer boilerplate identique sur 481 sites [vérifié]
92-100 mots + 3 liens sortants (`tibillet.coop`, `/onboard/`, `codecommun.tibillet.coop/crowd/`) sur chaque page de chaque lieu. En soi c'est le motif « powered by » toléré par Google. Le problème est le **ratio** : sur 8/13 lieux de l'échantillon, le footer est plus long que le contenu propre. Pas d'action sur le footer lui-même (c'est la marque) ; c'est C2 qui règle le ratio. Petit plus : `rel="noopener"` sur la marque est bien, `target="_blank"` sur un lien texte est discutable mais sans effet SEO.

### M4 — Événement inconnu → 302 vers `/event/` (soft 404) [vérifié dans le code]
`views.py:3826-3828` : slug introuvable → `redirect("/event/")`. Un événement supprimé reste une URL « vivante » pour Google (soft 404), et l'agenda hérite d'URL fantômes. Rendre un vrai 404 (ou 410) via `handler404`, déjà skin-aware. Au passage, `views.py:3753-3755` : `Event.objects.get(slug__startswith=slug)` ne filtre pas `published=True` — un événement non publié est servi à qui connaît son slug (hors SEO, à remonter).

### M5 — `?skin_preview=` sans contrôle d'accès [vérifié]
`skin_preview_de_la_requete` (`views.py:267-284`) accepte le paramètre pour tout visiteur ; `hx-vals` le propage. Couvert par le `noindex` de C3 ; idéalement restreindre aux admins du tenant (`profile.admin_this_tenant`).

---

## 4. BAS

- **B1** `tibrss/views.py:48` : `Event.objects.order_by('-created')[:20]` — le flux RSS (déclaré dans `shell.html:72-74`) inclut les événements non publiés/privés. [vérifié dans le code]
- **B2** `shell.html:34` : `<meta property="og:image" content="">` quand le lieu n'a pas d'image (7/13). Facebook/LinkedIn tombent sur le premier `<img>` (logo France 2030 du footer, probablement). Prévoir une image de repli TiBillet par défaut. [vérifié]
- **B3** `/federation/` est déclaré dans le sitemap de lieux sans voisin (zamm) parce que `afficher_lieux_entrants` vaut `True` par défaut (`models.py:5394-5395`) et que le test `StaticViewSitemap.items()` l'accepte. Tester `explorer_data["tenants"]` > 1 serait plus juste. [vérifié]
- **B4** Événements passés gardent `eventStatus: EventScheduled` dans le JSON-LD (`pages_tags.py:445`). Un `if event.datetime < now` → omettre le statut ou poser `endDate` suffit. [vérifié : copie UPV de nov. 2025]

---

## 5. Ce qui est correct et à conserver [vérifié]

- **HTMX et robots** : chaque lien porte `href` + `hx-get` ; `get_context` (`views.py:300-304`) sert `shell.html` quand `request.htmx` est faux. Un robot sans JS reçoit le HTML complet (vérifié : toutes les captures `curl` contiennent `<html>`, `<head>`, meta, JSON-LD, footer). Le piège « `extra_meta` perdu en HTMX » est documenté dans `page.html` et sans effet pour les robots.
- `robots.txt` par tenant avec `Sitemap:` ; `noindex` global DEBUG/TEST/DEMO ; canonical sur les pages CMS (`page.html`) ; `ProductSitemap` déjà retiré ; sections de sitemap conditionnelles ; `/explorer/` hors sitemap ; JSON-LD Event construit en Python.
- `<html lang>` correct, `og:locale` correct, `twitter:card` présent.

---

## 6. Les 3 actions prioritaires (meilleur rapport effort / impact, 481 lieux d'un coup)

### Action 1 — Canoniques et `noindex` justes dans `shell.html` + `evenement.html` (≈ 15 lignes, 2 fichiers)
Règle C1 + C3 + M5 et une partie de H1.
- `shell.html:29,65` : canonical et `og:url` = `https://{{ request.get_host }}{{ request.path }}` via un seul bloc `canonical`.
- `shell.html:24` : `noindex, nofollow` si `noindex_seo or embed or skin_preview`.
- `evenement.html` : `{% block canonical %}{{ event.full_url }}{% endblock %}` et `{% block meta_robots %}` → `noindex, follow` quand `not event_in_this_tenant`.
- `pages_tags.py:jsonld_event` : `url = event.full_url` ; pas de `organizer` local sur une copie fédérée.
Effet : fin des doublons fédérés et des doublons par paramètre sur 481 lieux, JSON-LD Event véridique.

### Action 2 — Règle « accueil mince » : `noindex, follow` + hors sitemap + titre/description réparés (≈ 25 lignes, 4 fichiers)
Règle C2 + H2.
- `views.py:index()` : `accueil_est_mince` (pas d'événement à venir, pas d'image, description absente ou texte d'onboarding).
- `accueil.html` : `meta_robots` conditionnel ; `title` = « {org} — {ville} » ; `default` **avant** `striptags` (4 occurrences, + `reseau.html:16`, `agenda.html:30-35`).
- `BaseBillet/sitemap.py:StaticViewSitemap.items()` : `'index'` conditionnel comme les autres sections.
- `seo/tasks.py:306-310` : durcir « vivant » (ou champ d'exclusion manuel pour les 16 tenants test/démo).
Effet : la moitié vide du parc cesse de diluer la moitié pleine ; le `<title>` porte enfin le nom et la ville.

### Action 3 — Rendre le réseau crawlable (≈ 20 lignes, 3 fichiers) + réparer les sitemaps (≈ 6 lignes, 2 fichiers)
Règle H3 + H4.
- `reseau.html` : liste HTML des voisins depuis `explorer_data.tenants` (déjà dans le contexte).
- `explorer.html:15` : `noindex, follow` + liste HTML serveur des lieux ; ou page `/lieux/` indexable alimentée par `AGGREGATE_LIEUX`, déclarée dans `sitemap_root_view`.
- `seo/tasks.py:118` : slash final sur `canonical_url`.
- `BaseBillet/sitemap.py:57` : `archived=False, private=False`, exclure `ACTION`, borner les passés ; `seo/views.py:667` : retirer `<lastmod>` tant qu'il n'est pas vrai.
Effet : chaque lieu reçoit un lien stable de la racine et de ses voisins ; Google cesse de crawler des copies privées/archivées et de voir 481 `lastmod` identiques.

---

## 7. Hypothèses et limites

- L'échantillon (13 lieux réels + 1 test) est tiré du sitemap index ; la proportion « ~50 % d'accueils minces » est une **extrapolation** [supposé] — un comptage exact est possible côté serveur en une requête sur `SEOCache(TENANT_SUMMARY)` (`event_count`, `social_card_url`, `long_description`).
- Je n'ai pas vérifié l'état Search Console (propriétés de domaine, erreurs de sitemap, pages « dupliquées, Google a choisi une autre canonique ») : c'est la mesure qui confirmerait C1/C3 en volume.
- Les événements `private=True` dans les sitemaps sont établis par lecture du code, pas observés (impossible de l'extérieur).
- Les deux autres agents couvrent le détail technique et on-page de La Filature ; je n'ai pas re-mesuré performance, images, accessibilité.
