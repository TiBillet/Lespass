# Appel à l'action à plus de deux boutons, bloc Texte centré, position d'un bloc par l'API / Multi-button call to action, centered Text block, block position via the API

**Date :** 2026-10-19
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- FR : l'appel à l'action (SECTION / APPEL_ACTION) accepte des boutons au-delà des deux premiers, saisis dans « Éléments de la section » (un libellé et un lien par ligne), stockés dans `contenu`. Skin V2 : l'appel à l'action est centré, ses boutons ont une largeur minimale commune. Skin V2 : la colonne de lecture du bloc Texte (72 caractères) est centrée avec son titre, les paragraphes sont justifiés avec césure (texte d'un seul paragraphe : dernière ligne centrée ; pas de justification sur écran étroit). API v2 : `PATCH /api/v2/blocs/{uuid}/` prend en compte `position` (elle était ignorée sans erreur, avec un 200).
- EN: the call to action renders extra buttons from `contenu`. V2 skin: centered call to action with equal-width buttons; Text block reading column centered, justified and hyphenated. API v2: block PATCH now applies `position` (it was silently ignored).

**Pourquoi / Why :**
- FR : la landing tibillet.coop a quatre boutons dans son hero, impossible à reproduire avec deux boutons. Le bloc Texte restait collé à gauche, avec le tiers droit de la page vide. Sans `position`, un bloc ne pouvait pas être déplacé par l'API : il fallait reconstruire la page.
- EN: reproduce multi-button heroes; the Text block left the right third of the page empty; blocks could not be reordered through the API.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/views.py` | `BlocViewSet.partial_update` : `position` (entier ≥ 0, sinon 400) |
| `pages/blocs_catalogue.py` | APPEL_ACTION lit `contenu` ; clés d'élément `titre`, `url` |
| `pages/templates/pages/{classic,V2,faire_festival}/partials/bloc_section_appel_action.html` | Boutons supplémentaires (lien http(s) ou / seulement) |
| `pages/static/V2/css/V2.css` | Appel à l'action centré ; bloc Texte centré, justifié, césure |
| `tests/pytest/test_pages_appel_action.py` | Nouveau : rendu des boutons dans les 3 skins, lien dangereux, lien absent |
| `tests/pytest/test_pages_api.py` | PATCH position : déplacement, valeurs invalides |
| `tests/pytest/test_pages_admin_apercu.py` | Le lien d'élément vaut pour RESSOURCES et APPEL_ACTION |
| `pages/README.md`, `api_v2/openapi-schema.yaml` | Documentation |

---

## Comment tester (a la main) / Manual test

### Test 1 : appel à l'action à quatre boutons (admin)
1. Site web personnalisé → une page → ajouter un bloc « Section mise en avant › Appel à l'action ».
2. Remplir les deux boutons, puis deux lignes dans « Éléments de la section » (libellé + lien `https://…`).
3. L'aperçu en direct montre les quatre boutons, centrés (skin V2), les deux derniers en contour.
4. Une ligne avec le lien `javascript:alert(1)` : le lien est vidé à l'enregistrement, le bouton n'apparaît pas.

### Test 2 : bloc Texte (skin V2)
1. Ouvrir une page avec un bloc Texte de plusieurs paragraphes : colonne centrée, titre centré, texte justifié avec césure.
2. Un bloc Texte d'une seule phrase sous un titre : la phrase est centrée.
3. Réduire la fenêtre sous 576 px : le texte n'est plus justifié.
4. Vérifier une page de documentation (menu latéral, sommaire) : le texte reste lisible dans sa colonne.

### Test 3 : position par l'API
```bash
curl -k -X PATCH -H "Authorization: Api-Key <clé>" -H "Content-Type: application/json" \
  -d '{"position": 0}' https://lespass.tibillet.localhost/api/v2/blocs/<uuid>/
```
Le bloc remonte en tête de page. `{"position": -1}` ou `{"position": "abc"}` → 400.
