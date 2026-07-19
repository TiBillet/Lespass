# Redesign de la landing publique + audit SEO / Public landing redesign + SEO audit

**Date :** 2026-07-17
**Migration :** Non

## Resume / Summary

**Quoi / What :** Redesign du site public TiBillet (schéma `public` : landing `/`,
hub `/features/`, pages détail `/features/<slug>/`) pour l'ancrer sur le **bleu de
marque Loséyan** et sortir de l'esthétique « IA slop ». Ajout d'une section **FAQ**,
de JSON-LD **SoftwareApplication** + **FAQPage**, et de plusieurs correctifs SEO
techniques. Un **audit SEO** complet accompagne le chantier.
/ Redesign of the TiBillet public site to anchor it on the brand blue and drop the
"AI slop" look. Adds a FAQ section, SoftwareApplication + FAQPage JSON-LD, and
several technical SEO fixes. A full SEO audit ships alongside.

**Pourquoi / Why :** La landing était la seule surface qui n'avait jamais reçu le
bleu de marque (`marque.css`) : elle codait le **vert `#259d49`** et des dégradés en
dur, plus les tells IA classiques (titre à dégradé text-clip, pastilles dégradé,
initiales arc-en-ciel). Le mainteneur voulait un rendu classe et moderne, tout
TiBillet bien expliqué, et un gros audit SEO.
/ The landing was the only surface that never got the brand blue: it hardcoded green
and gradients plus the classic AI tells. The maintainer wanted a classy, modern
result, everything TiBillet does well explained, and a big SEO audit.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/static/seo/seo.css` | Réécriture de la couche visuelle : **zéro couleur en dur**, on consomme les jetons de marque (`--tb-marque` geste, `--tb-marque-encre` texte/liens, contrastes). Style éditorial (Staatliches, filets hairline), marquees **dé-arc-en-cielisés** (deux tons de bleu), nouveaux styles FAQ. Couvre aussi les pages `.fd-*`. |
| `seo/templates/seo/landing.html` | Hero : mots-clés Staatliches + filet bleu (fin du dégradé text-clip) ; logo `fetchpriority="high"` + `width/height`. Nouvelle **section FAQ** (`<details>` natifs). JSON-LD `SoftwareApplication` + `FAQPage` injectés dans `extra_head`. |
| `seo/views.py` | Constante `FAQ_ITEMS` (5 Q/R, source unique) ; construction JSON-LD `SoftwareApplication` + `FAQPage` ; contexte enrichi. `/explorer/` retiré du sitemap ROOT (page noindex). |
| `seo/templates/seo/feature_hub.html` | H1 descriptif riche en mots-clés (au lieu de « Fonctionnalités »). |
| `seo/templates/seo/base.html` | `defer` sur `bootstrap.bundle.min.js` (parse non bloqué). |
| `BaseBillet/static/commun/css/tibillet.css` | `font-display: swap` sur `luciole` (2 blocs) + `staatliches` (levier LCP). |
| `TECH_DOC/SESSIONS/LANDING_PUBLIQUE/AUDIT-SEO.md` | Audit SEO complet (10 points, plan d'action priorisé). |

**Non modifié volontairement :** `marque.css` (couvert par `test_marque.py`), les
`data-testid` existants (tests E2E), `www/static/` (collectstatic = mainteneur).

**i18n :** ce chantier ajoute des chaînes traduisibles (FAQ, H1 hub, hero). Le
workflow `makemessages`/`compilemessages` est à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

### Test 1 — le bleu a remplacé le vert (nominal)
1. Ouvrir la landing publique (schéma public — racine du site, pas un tenant).
2. Vérifier qu'il n'y a **plus aucun vert** : boutons, icônes de fonctionnalités,
   panneau « Contribuer », affordances « En savoir plus », pages détail.
3. Tout l'accent est en **bleu Loséyan** : filet sous les mots-clés du hero, bordures
   au survol des cartes, icônes, CTA pleines.

### Test 2 — hero et typographie
1. Les mots-clés du hero (« Adhésion », « caisse enregistreuse », « outils ») sont en
   **Staatliches** (display condensé) avec un **filet bleu dessiné dessous** — pas de
   dégradé qui remplit le texte.
2. Le logo hero s'affiche sans saut de mise en page (CLS) au chargement.

### Test 3 — section FAQ + JSON-LD
1. En bas de la landing, la section **« Questions fréquentes »** : chaque question se
   déplie/replie au clic (le « + » pivote). Fonctionne **sans JavaScript**.
2. Voir le source de la page : présence de `"@type": "FAQPage"` et
   `"@type": "SoftwareApplication"` dans le `<head>`.
3. Valider avec le Rich Results Test de Google (FAQPage + SoftwareApplication).

### Test 4 — marquees dé-arc-en-cielisés
1. Bandeaux « Nos lieux vivants » et « Prochains événements » : les initiales et
   placeholders sans image sont en **deux tons de bleu** (plus d'arc-en-ciel
   indigo/orange/rouge/violet).

### Test 5 — thème sombre + mobile
1. Basculer en thème sombre (bouton navbar) : liens et textes bleus s'éclaircissent,
   les aplats bleus (boutons) restent lisibles (blanc dessus).
2. Réduire à 320 / 375 / 768 px : pas de scroll horizontal, grille features en 1 puis
   2 colonnes, hero empilé, logo masqué.

### Test 6 — pages détail et hub (couverture du seo.css partagé)
1. `/features/` : H1 descriptif, grille en bleu.
2. `/features/billetterie/` (ou autre) : icône bleue, tagline bleue, CTA bleues,
   placeholders de capture en cadre bleu pointillé, maillage interne en bleu.

### Test 7 — correctifs SEO techniques
1. `GET /sitemap-root.xml` : **ne contient plus `/explorer/`** (page noindex).
2. `<head>` de la landing : `bootstrap.bundle` a l'attribut `defer`.
3. Les `@font-face` luciole/staatliches ont `font-display: swap`.

### Verifs / Tests auto
- `docker exec lespass_django python -m py_compile /DjangoFiles/seo/views.py` (OK).
- Suite du domaine `seo` + `test_marque` (garantir que `marque.css` reste intact) via
  le skill `tibillet-test`, **après** la vérif visuelle.
