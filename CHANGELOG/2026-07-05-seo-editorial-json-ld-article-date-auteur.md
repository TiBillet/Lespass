# SEO éditorial : JSON-LD Article + date/auteur visibles sur les pages de blog / Editorial SEO: Article JSON-LD + visible date/author on blog pages

**Date :** 2026-07-05
**Migration :** Non — `Page.created_at`/`updated_at` existaient déjà, l'auteur est l'Organization / No — the date fields already existed, the author is the Organization

Critère « article » : une page dont le PARENT porte un bloc LISTE_SOUS_PAGES
(l'index d'un blog). Pour ces pages :
- **JSON-LD `Article`** (au lieu de WebPage) dans `jsonld_page` : headline,
  datePublished/dateModified (champs du modèle), author + publisher =
  Organization du lieu, image de partage en URL absolue.
- **Signature visible** (E-E-A-T — Google veut VOIR qui publie et quand) :
  « Publié le … par … (· mis à jour le …) » sous le titre, dans les 2 skins
  (`data-testid="page-signature"`), et date de publication en surtitre des
  cartes du bloc LISTE_SOUS_PAGES.
- Les autres sous-pages (ex. « Notre histoire ») restent des WebPage sans
  signature — critère vérifié dans les deux sens en live et par pytest.
