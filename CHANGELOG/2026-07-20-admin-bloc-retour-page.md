# Admin des blocs : retour vers la page parente / Block admin: return to the parent page

**Date :** 2026-07-20
**Migration :** Non

## Resume / Summary

**Quoi / What :** dans l'admin Unfold de l'app `pages`, la fiche d'un Bloc ne renvoie
plus jamais vers la liste brute de TOUS les blocs. Apres « Enregistrer », on revient sur
la fiche de la page parente, onglet « Blocs » deja ouvert. Le fil d'Ariane affiche
« Pages / \<nom de la page\> » au lieu de « Pages / Blocs / \<titre du bloc\> ».
/ In the `pages` Unfold admin, a Bloc form never leads back to the raw list of ALL
blocks. After "Save", the user returns to the parent page form with the "Blocs" tab
already open. The breadcrumb reads "Pages / \<page name\>" instead of
"Pages / Blocs / \<block title\>".

**Pourquoi / Why :** la liste brute des blocs ne dit pas a quelle page chaque bloc
appartient — on y perd le contexte d'edition. Le point d'entree de l'app `pages` est la
PAGE, pas le bloc. Meme logique parent/enfant que `PriceAdmin`, qui renvoie deja un tarif
vers son produit parent.
/ The raw block list does not say which page each block belongs to — the editing context
is lost. The entry point of the `pages` app is the PAGE, not the block. Same parent/child
logic as `PriceAdmin`, which already sends a price back to its parent product.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `pages/admin.py` | Import `HttpResponseRedirect` |
| `pages/admin.py` | Helper module-level `_url_onglet_blocs_de_la_page()` + constante `_ANCRE_ONGLET_BLOCS` |
| `pages/admin.py` | `BlocAdmin.changeform_view()` — pose `opts`/`original` sur la Page pour reecrire le fil d'Ariane |
| `pages/admin.py` | `BlocAdmin.response_post_save_change()` et `response_post_save_add()` — redirection vers la page parente |

### Notes techniques / Technical notes

- **`response_post_save_change` et non `response_change`.** Django n'appelle ce hook que
  pour le bouton « Enregistrer » simple. « Enregistrer et continuer les modifications »
  garde donc son comportement normal (on reste sur la fiche du bloc). `PriceAdmin`
  surcharge `response_change`, ce qui redirige aussi dans ce cas — on n'a pas repris ce
  defaut.
- **Ancre `#blocs`.** Unfold nomme ses onglets d'inline avec le prefixe du formset passe
  par `slugify` (cf. son gabarit `unfold/helpers/tab_items.html`). Ce prefixe est
  l'accesseur inverse de la cle etrangere, soit `related_name="blocs"` sur `Bloc.page`.
  Verifie en shell : `inlineformset_factory(Page, Bloc, fk_name='page').get_default_prefix()`
  renvoie bien `blocs`.
- **Helper hors de la classe.** `_url_onglet_blocs_de_la_page()` est defini au niveau du
  module : Unfold wrappe les methodes d'un `ModelAdmin` avec son systeme d'actions et
  casserait l'appel (piege documente dans le skill `unfold`).
- **Contrepartie assumee :** le titre du bloc n'apparait plus dans le `<h1>` (le tag
  `header_title` d'Unfold se construit a partir de `opts` + `original`, desormais la
  Page). Il reste visible dans le formulaire.

---

## Comment tester (a la main) / Manual test

### Test 1 — retour apres enregistrement (scenario nominal)

1. Aller sur `/admin/pages/page/` et ouvrir une page qui porte des blocs.
2. Onglet « Blocs » → cliquer sur « ✎ modifier » d'une ligne.
3. Modifier le titre du bloc, cliquer sur **« Enregistrer »**.
4. **Attendu :** on revient sur `/admin/pages/page/<pk>/change/#blocs`, l'onglet
   « Blocs » est deja ouvert, la modification est visible dans le sommaire.
   On ne passe PAS par `/admin/pages/bloc/`.

### Test 2 — fil d'Ariane

1. Ouvrir la fiche d'un bloc (meme chemin qu'au test 1).
2. Regarder le `<h1>` en haut de page.
3. **Attendu :** « Pages › \<nom de la page\> ». Plus de maillon « Blocs ».
4. Cliquer sur le nom de la page → on arrive sur la fiche de la page.

### Test 3 — « Enregistrer et continuer les modifications » (non-regression)

1. Ouvrir la fiche d'un bloc.
2. Cliquer sur **« Enregistrer et continuer les modifications »**.
3. **Attendu :** on reste sur la fiche du bloc (comportement Django standard,
   PAS de redirection vers la page).

### Test 4 — creation d'un bloc

1. Depuis l'onglet « Blocs » d'une page, ajouter une ligne, choisir un type et un titre,
   enregistrer la page.
2. Cliquer sur « ✎ modifier » de la nouvelle ligne, saisir du contenu, « Enregistrer ».
3. **Attendu :** meme retour vers l'onglet « Blocs » de la page.

### Test 5 — bloc sans page (cas limite)

1. Si un bloc orphelin existe (`page` vide), ouvrir sa fiche et enregistrer.
2. **Attendu :** pas de 500 — on retombe sur le comportement Django par defaut
   (redirection vers la liste des blocs). Le code teste `obj.page_id` avant de rediriger.

### Verifs automatiques

```bash
docker exec lespass_django bash -c "cd /DjangoFiles && poetry run python manage.py check"
docker exec lespass_django bash -c "cd /DjangoFiles && poetry run pytest tests/pytest/test_pages.py -q"
```

Etat au moment du chantier : `check` sans erreur, `test_pages.py` = **50 passed**.
