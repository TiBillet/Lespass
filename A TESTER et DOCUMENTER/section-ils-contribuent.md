# Section « Ils contribuent » (home publique) + mention France 2030 footer

## Ce qui a été fait

Sur la landing page du tenant public (app `seo`), à la suite des bandeaux
« Nos lieux vivants » et « Prochains événements » :

- **Section « Ils contribuent »** : panneau gris doux sur toute la section,
  grille de **tuiles blanches** (chaque logo + son **nom dessous**), logos
  cliquables. Liste explicite (nom + logo + URL) dans `seo/views.py`. Section
  **masquée** tant que la liste est vide. Le fond gris détache la section ;
  les tuiles blanches conviennent aux logos colorés/sombres et aux JPG à fond
  blanc. Pour un logo **blanc sur transparent** (invisible sur tuile blanche),
  on pointe vers une version inversée (cf. ci-dessous, ex. CoopCircuit).
- **Footer** : ajout de la mention obligatoire de financement France 2030,
  identique à celle des footers tenants (skin `reunion`), qui manquait sur
  le footer ROOT. Disposition : séparateur + texte à gauche, logo aligné à
  droite, centré verticalement.

### Modifications
| Fichier | Changement |
|---|---|
| `seo/views.py` | Constante `CONTRIBUTEURS` (nom + logo + URL) + `"contributeurs"` dans le contexte de `landing` |
| `seo/templates/seo/landing.html` | Section `contributeurs-section` : tuile logo + nom, guard `{% if contributeurs %}`, lien si URL renseignée sinon logo seul |
| `seo/static/seo/seo.css` | Styles `.contributeurs-*` (panneau gris `--bs-secondary-bg`, tuiles blanches, nom sous le logo, responsive) |
| `seo/templates/seo/base.html` | Mention France 2030 (séparateur + texte gauche / logo droite) dans le footer |
| `seo/static/contributeurs/coopcircuit-noir.png` | Version inversée du logo CoopCircuit (blanc → noir), générée via Pillow |

## Comment ajouter un contributeur

1. Déposer le logo dans `seo/static/contributeurs/` (SVG de préférence, sinon
   PNG transparent). Hauteur d'affichage plafonnée à 64px, donc un visuel
   net suffit.
2. Ajouter une ligne dans la liste `CONTRIBUTEURS` de `seo/views.py` :
   ```python
   {"nom": "Nom du contributeur", "logo": "contributeurs/mon-logo.svg", "url": "https://site-du-contributeur.org/"},
   ```
   - `nom` : affiché sous le logo + utilisé en `title` (infobulle). L'`alt` de
     l'image est volontairement vide (le nom est déjà en texte → pas de doublon
     pour les lecteurs d'écran).
   - `logo` : chemin **relatif au dossier static** (commence par `contributeurs/`).
   - `url` : si renseignée, la tuile devient un lien (`target="_blank"`,
     `rel="noopener"`). **Si `url` est vide (`""`)**, le logo s'affiche sans lien
     (pas de lien cassé) — pratique en attendant l'URL.
3. En production, lancer `collectstatic` pour que les nouveaux logos soient servis.

Pour retirer un contributeur : supprimer sa ligne dans `CONTRIBUTEURS`.

### Cas d'un logo blanc sur transparent (invisible sur tuile blanche)

Les tuiles sont blanches. Un logo livré en **blanc sur fond transparent**
(ex. CoopCircuit) disparaît. Générer une version inversée (RGB négatif,
transparence conservée) avec Pillow, puis pointer `logo` vers ce fichier :

```bash
docker exec lespass_django poetry run python -c "
from PIL import Image, ImageOps
src='/DjangoFiles/seo/static/contributeurs/mon-logo.png'
dst='/DjangoFiles/seo/static/contributeurs/mon-logo-noir.png'
im=Image.open(src).convert('RGBA'); r,g,b,a=im.split()
inv=ImageOps.invert(Image.merge('RGB',(r,g,b))); ri,gi,bi=inv.split()
Image.merge('RGBA',(ri,gi,bi,a)).save(dst)
"
```

⚠️ N'inverser **que** les logos monochromes blancs transparents. Un logo
**opaque** (fond blanc baked, ex. JPG ou PNG sans alpha) deviendrait un
rectangle noir — le laisser tel quel ou fournir une autre version.

## Tests à réaliser

### Test 1 : section masquée par défaut
1. Liste `CONTRIBUTEURS` vide → ouvrir la home publique (`/`).
2. Attendu : aucune section « Ils contribuent » ne s'affiche (pas de bloc vide,
   pas d'image cassée).

### Test 2 : affichage des logos
1. Déposer 2-3 logos dans `seo/static/contributeurs/` et renseigner `CONTRIBUTEURS`.
2. Recharger `/`.
3. Attendu : grille centrée sous « Prochains événements », logos en couleur,
   léger relief au survol, clic ouvre le site du contributeur dans un nouvel onglet.
4. Vérifier le responsive (mobile : logos plus petits, grille qui se réorganise).

### Test 3 : footer France 2030
1. Sur n'importe quelle page publique, dérouler jusqu'au footer.
2. Attendu : mention « Opération soutenue par l'État dans le cadre du dispositif
   « Solutions de billetteries innovantes » de France 2030, opéré par la Caisse
   des Dépôts. » + logo France 2030 à droite.

## i18n

Nouvelles chaînes ajoutées (`Ils contribuent`, le sous-titre, `Contributeurs de
TiBillet`, `Logo France 2030`, la mention France 2030). Lancer côté mainteneur :
```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
docker exec lespass_django poetry run django-admin compilemessages
```

## Compatibilité

- Le logo France 2030 (`BaseBillet/static/reunion/img/france_2030.png`) est déjà
  servi sur le schéma public (la home `seo` charge déjà les statiques `reunion/`).
- Aucun changement de modèle, aucune migration.
