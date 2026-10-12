# Audit SEO de l'accueil par défaut V2 — synthèse

Date : 2026-10-12
Page auditée : https://la-filature.tibillet.coop/ (accueil par défaut du skin V2,
`pages/templates/pages/V2/vues/accueil.html`), avec un échantillon de 14 autres lieux.
Méthode : trois agents en parallèle, lecture seule sur la prod (GET/HEAD, ~90
requêtes au total) + lecture du code. Rapports détaillés, avec preuves et
`fichier:ligne` :

| Rapport | Angle | Agent |
|---|---|---|
| [technique.md](./technique.md) | Indexation, JSON-LD, performance | Opus |
| [contenu.md](./contenu.md) | On-page, contenu, images, recherche IA, SXO | Opus |
| [plateforme.md](./plateforme.md) | 500 lieux, doublons fédérés, maillage, cause dans le code | Fable |

## Notes

**Note globale : 53/100** (pondération du skill claude-seo).

| Catégorie | Note |
|---|---|
| Technique | 66 |
| Contenu | 55 |
| On-page | 52 |
| Recherche IA | 50 |
| Données structurées | 45 |
| Images | 42 |
| Performance | 40 |

Ce qui est sain : redirections https et slash final, robots.txt, sitemap par lieu
et index racine, `lang`, temps de réponse serveur (0,19 s), un événement fédéré
lié vers son lieu d'origine dans les cartes (`event_card.html`).

## Constats retenus, par gravité

### Critique
1. **Aucune compression HTTP** (vérifié 2026-10-12 : pas de `Content-Encoding`
   même avec `Accept-Encoding: gzip, br`, pas de CDN devant). HTML, CSS et JS
   bruts : `V2.css` seul pèse 140 Ko, le CSS bloquant total 468 Ko (~100 Ko en
   gzip). `nginx_prod/lespass_prod.conf` n'a aucune directive `gzip`.
   Déjà relevé par l'audit du moteur de pages (M10), où un CDN était supposé :
   il n'y en a pas. → chantier 12.
2. **Fiches événement fédérées dupliquées** (vérifié) : un événement d'un lieu
   voisin est servi en 200, `index`, canonique sur lui-même, sur le domaine du
   lieu qui l'affiche, avec un JSON-LD `organizer` faux. → chantier 09.
3. **Title générique** : « Accueil | <lieu> » sur tous les lieux, sans ville ni
   activité ; meta description « None » quand la description courte est vide.
   → chantier 10.

### Haut
4. **Canonical et `og:url` recopient les paramètres d'URL** (`?utm_source=`,
   `?tag=`, `?skin_preview=`) ; `/event/embed/` et `?skin_preview=` sont
   indexables. Les pages CMS étaient déjà corrigées (audit du moteur de pages,
   B7), pas le canonical par défaut des shells. → chantier 09.
5. **JSON-LD Organization écrit à la main** (`shell.html`) : entités HTML dans le
   JSON, JSON invalide sur un lieu, `logo` = photo de partage, `sameAs` vide,
   `addressCountry` = « France ». → chantier 10.
6. **Accueils minces en masse** : sur 13 lieux réels, 7 sans événement ni image,
   4 avec le texte d'onboarding ; 16 lieux de test/démo dans le sitemap racine ;
   tous `index`. → chantier 10.
7. **Images lourdes** : hero en fond CSS de 390 Ko servi en 1920 px même sur
   mobile, sans `alt` ni préchargement ; images des cartes choisies selon l'écran
   et non la carte (jusqu'à 293 Ko pour 380 px) ; pas de `loading="lazy"`.
   Rejoint B5/M8 de l'audit du moteur de pages. → chantier 10 (préchargement) et
   chantier images à planifier.
8. **Maillage invisible pour les robots** : « Autour de nous » rendu en JS sans
   `<a href>`, `/explorer/` en `noindex, nofollow`, racine qui lie 100 lieux au
   hasard sur 481. → chantier 11.

### Moyen et bas (extraits)
- Hero sans bouton d'action ; 3 événements sur 21 affichés.
- Libellés de prix fautifs sur tous les lieux : « Entré libre », « A partir de 0.00 € ».
- `Configuration.legal_documents` utilisé dans aucun gabarit (pas de mentions légales).
- FR/EN sur la même URL sans hreflang (déjà B8 de l'audit du moteur de pages :
  décision d'architecture d'URLs, non tranchée).
- Sitemap : événements privés/archivés/passés sans limite, `/event/` absent,
  `lastmod` faux. → chantier 11.
- 404 en `index`, `/media` sans cache, Leaflet toujours chargé, pas de WebP.
- Footer TiBillet = 28 à 50 % des mots de la page.
- Côté admins de lieu : email personnel en contact, descriptions courtes trop
  courtes, liens en URL brute.

### Écarté
- **`llms.txt`** (recommandé par l'agent contenu) : refusé par décision du
  chantier SEO (SPEC.md §5, atom `491b2fe3`).

## Plan

| Chantier | Contenu | Statut |
|---|---|---|
| 09 | Canonical sans paramètres, `noindex` embed/aperçu, fiches fédérées canoniques vers l'original | Implémenté, à déployer |
| 10 | Accueil : title « lieu — ville », bug « None », `noindex` des accueils vides, JSON-LD Organization en Python, préchargement du hero | Implémenté, à déployer |
| 11 | Maillage et sitemaps : voisins en HTML, sitemap des événements filtré, `lastmod` retirés, lieux à accueil vide hors du sitemap racine | Implémenté, à déployer |
| 12 | Compression gzip et cache dans nginx (infra) | gzip écrit et testé en local, à déployer ; cache `/media` à faire |
