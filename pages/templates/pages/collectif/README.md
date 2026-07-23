# Skin « collectif » — exploration

**Statut : maquette. Rien n'est branché.**

Ce dossier ne contient aucun gabarit Django. Le skin n'est **pas** déclaré dans
`SiteConfiguration.skin` (`pages/models.py`) : il est impossible de le
sélectionner, et rien dans le code ne le charge. Il est là pour donner envie de
continuer, pas pour tourner.

## `maquette/`

Bibliothèque de blocs en **HTML/CSS pur** — zéro build, zéro framework, zéro
JavaScript obligatoire. Trois fichiers autonomes.

| Fichier | Rôle |
|---|---|
| `index.html` | 19 blocs rendus et étiquetés, plus le chrome (nav, pied, ruban) |
| `tokens.css` | Couleurs, thèmes, typographie, espacement, rayons, mouvement |
| `blocks.css` | Le chrome et les blocs |

**Pour regarder :**

```bash
cd pages/templates/pages/collectif/maquette && python3 -m http.server 8899
# puis http://localhost:8899/index.html
```

Un double-clic sur `index.html` marche aussi (le seul appel réseau est
l'import Google Fonts ; sans réseau, la page retombe sur les polices système).

Vérifié au rendu à **360 / 768 / 1440 px** : zéro débordement horizontal, zéro
commande sous 44 × 44 px, la nav se replie en bouton sous 1024 px.

## D'où ça vient

Étude de `projetcollectif.ca` (Craft CMS headless + Vue — pas WordPress), dont
le mainteneur détient les droits. L'ADN complet, les mesures, les écarts
assumés et la comparaison avec `pages/blocs_catalogue.py` sont dans :

- [`TECH_DOC/DESIGN/design-collectif.md`](../../../../TECH_DOC/DESIGN/design-collectif.md)
- [`TECH_DOC/DESIGN/collectif-blocks/README.md`](../../../../TECH_DOC/DESIGN/collectif-blocks/README.md)

## L'idée à retenir, si on reprend un jour

Le site étudié n'a pas *un* thème, il en a douze — et **le thème se pose bloc
par bloc**, via un attribut `data-theme`. Chaque thème ne redéfinit que deux ou
trois variables ; tout le CSS est écrit contre `--theme-*`, jamais contre une
couleur.

```html
<section class="b-highlight" data-theme="sun">   <!-- aplat jaune -->
<a       class="c-tile"      data-theme="ink">   <!-- carte noire  -->
```

C'est ce qui permet à une même carte d'être crème sur l'accueil, noire dans une
grille d'actualités et jaune sur une fiche rubrique, sans une ligne de CSS
supplémentaire.

Lespass a **un skin par site** (global). Ce serait **un thème par bloc** en
plus — les deux se composent : le skin choisit le vocabulaire graphique, le
thème choisit la couleur d'un aplat.

## Si on décide de vraiment le faire

Ne pas partir de ce dossier à la main : `python manage.py demarrer_skin
collectif` copie `classic/` et affiche la marche à suivre. Le contrat de skin
est dans `TECH_DOC/SESSIONS/SKINS/CONTRAT-DE-SKIN.md`. La maquette sert alors
de référence visuelle, pas de point de départ technique.
