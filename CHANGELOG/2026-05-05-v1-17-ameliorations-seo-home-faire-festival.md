# v1.7.17 — Améliorations SEO home Faire Festival + humans.txt / SEO improvements on Faire Festival home + humans.txt

**Date :** 2026-05-05
**Migration :** Non

---

### Améliorations SEO sur la home du skin Faire Festival / SEO improvements on Faire Festival skin home

**FR :**
Suite à l'audit RoastMyUrl sur `fairefestival.fr` (score 69/100), correction des points SEO
sur la home du skin Faire Festival :

- **Title trop court (24 char)** : enrichi en `Festival du Faire — Toulouse, 28-30 mai 2026 | <organisation>` (61 char). Inclut désormais les mots-clés métier (`Festival`, `Faire`), géo (`Toulouse`) et la date.
- **Meta description courte (113 char)** : étendue à 158 char avec `fablabs`, `22 thématiques`, et la date.
- **og:title / twitter:title** : alignés sur le nouveau title.
- **og:description / twitter:description** : alignées sur la meta description longue.
- **Bug HTML** : 3 balises `<h3>` étaient fermées par `</h4>` (typo lors du merge `template-faire-festival`). Corrigées en `</h3>`.
- **Hiérarchie H2** : la baseline `Le grand rendez-vous toulousain...` était dans un `<p>`. Passée en `<h2>` (classes Bootstrap conservées, rendu visuel identique). On passe de 1 H2 à 2 H2.
- **Alts d'images génériques** (`Billets`, `Programmation`, `Faire Festival`) : enrichis pour le SEO et l'accessibilité (`Prendre vos billets pour le Faire Festival`, `Programmation du Faire Festival : 22 thématiques`, `Infos pratiques du Faire Festival, 28-30 mai`).

**EN :**
Following the RoastMyUrl audit on `fairefestival.fr` (score 69/100), SEO fixes on the Faire
Festival skin home:

- Title extended from 24 to 61 char with geo + date keywords.
- Meta description extended to 158 char with metier keywords.
- og/twitter title and description aligned.
- Fixed 3 `<h3>` tags closed with `</h4>` (typo from the merge).
- Tagline `<p>` upgraded to `<h2>` for proper heading hierarchy.
- Generic image alts replaced with descriptive ones.

### Ajout de humans.txt dynamique / Dynamic humans.txt added

**FR :**
Ajout d'un endpoint `/humans.txt` dynamique au standard [humanstxt.org](https://humanstxt.org/Standard.html).
Crédite la Coopérative Code Commun comme équipe de développement. Le contenu est identique
pour tous les tenants (même réponse quel que soit le `Host`). La version et la date du
dernier bump sont lues depuis le fichier `VERSION` à la racine.

**EN :**
Added a dynamic `/humans.txt` endpoint following the [humanstxt.org standard](https://humanstxt.org/Standard.html).
Credits Coopérative Code Commun as the dev team. Same content for all tenants. Version
and last update date read from the root `VERSION` file.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/templates/faire_festival/views/home.html` | Title / og / twitter enrichis ; meta description étendue ; fix `<h3>...</h4>` ×3 ; baseline `<p>` → `<h2>` ; alts d'images enrichis |
| `BaseBillet/views_humans.py` | **Nouveau** — vue `humans_txt`, parse le fichier `VERSION` (version + mtime) au chargement du module |
| `BaseBillet/urls.py` | Import `humans_txt` + route `path('humans.txt', humans_txt, name='humans_txt')` |

### Migration
- **Migration necessaire / Migration required:** Non

### À faire en config admin / Admin config TODO (no code)
Pour activer pleinement le SEO en prod sur `fairefestival.fr` :
- Uploader la social card sur `Configuration > img` (1200×630 → génère `og:image`)
- Renseigner `Configuration > facebook` / `instagram` / `twitter` (alimente `JSON-LD sameAs`)
- Compléter `Configuration > postal_address` (alimente `JSON-LD address`)

### À faire i18n / i18n TODO
Les nouvelles chaînes (`Festival du Faire — Toulouse, 28-30 mai 2026`, meta description longue,
3 alts enrichis) sont en `{% translate %}` mais pas encore dans les `.po`. À traiter dans
une session de traduction dédiée (`makemessages` + `compilemessages`).

---
