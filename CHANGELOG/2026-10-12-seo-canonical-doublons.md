# SEO : canonical sans paramètres, copies en noindex, fiches fédérées / SEO: query-free canonical, noindex copies, federated event pages

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Le `canonical` et `og:url` des trois skins (V2, classic, faire_festival) valent le chemin demandé **sans** les paramètres d'URL (`?utm_source=`, `?tag=`…).
- Les copies d'une page sont en `noindex, nofollow` : agenda ou adhésions en iframe (`/event/embed/`, `/memberships/embed/`) et aperçu d'un skin (`?skin_preview=`).
- Un événement d'un lieu fédéré, affiché sur un autre lieu, pointe (`canonical`, `og:url`) vers son adresse sur le lieu d'origine (`event.full_url`), passe en `noindex, follow` et n'a plus de JSON-LD Event (l'organisateur et le lieu y étaient ceux du lieu qui affiche la page).
- Le commentaire du canonical passe en `{# #}` : il n'est plus envoyé au navigateur.

/ Canonical and og:url drop query parameters in all three skins; embed and skin-preview copies are noindex; a federated event shown on another venue points to its origin, is noindex and has no Event JSON-LD.

**Pourquoi / Why :** Audit SEO du 2026-10-12 (`TECH_DOC/SESSIONS/SEO/AUDIT-ACCUEIL-V2/`) : chaque lien tracké créait une page « canonique » de plus, et chaque événement fédéré existait en plusieurs copies indexables, avec un organisateur faux. Spec : `TECH_DOC/SESSIONS/SEO/CHANTIER-09-canonical-doublons.md`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/{V2,classic,faire_festival}/shell.html` | canonical / og:url (nouveau bloc `og_url`) / twitter:url sans paramètres ; robots `noindex` si `embed` ou `skin_preview` |
| `pages/templates/pages/{V2,classic,faire_festival}/page.html` | `og_url` = adresse officielle de la page (comme le canonical) |
| `pages/templates/pages/{V2,classic,faire_festival}/vues/evenement.html` | copie fédérée : canonical et og:url = `event.full_url`, robots `noindex, follow` |
| `pages/templatetags/pages_tags.py` | `jsonld_event` : rien sur une copie fédérée ; `url` sans paramètres |
| `tests/pytest/test_seo_canonical_doublons.py` | 10 tests (vérifiés par mutation) |

---

## Comment tester (a la main) / Manual test
En dev, toutes les pages sont en `noindex` (DEBUG) : vérifier le robots en prod.

1. `curl -s "https://<lieu>/?utm_source=test" | grep -E 'canonical|og:url'` → l'adresse sans `?utm_source`.
2. `curl -s "https://<lieu>/event/?tag=concert" | grep canonical` → `https://<lieu>/event/`.
3. `curl -s "https://<lieu>/event/embed/" | grep robots` → `noindex, nofollow`. Pareil pour `/?skin_preview=reunion`.
4. Sur un lieu fédéré, ouvrir un événement d'un voisin (`/event/<slug>/` sur le domaine du lieu) :
   canonical et og:url = adresse sur le lieu d'origine, robots `noindex, follow`, pas de `"@type": "Event"` dans la page.
   Exemple en prod : `https://la-filature.tibillet.coop/event/12h12-la-democratie-est-elle-extensible-aux-enfants-251112-1212-39901a9a/`.
5. Un événement du lieu lui-même : canonical sur lui-même, `index, follow`, JSON-LD Event présent.

`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_seo_canonical_doublons.py -q`
