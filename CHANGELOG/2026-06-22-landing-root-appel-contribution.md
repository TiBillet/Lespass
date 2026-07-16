# Landing ROOT — Appel à contribution dans « Fonctionnalités »

## Ce qui a été fait

Sur la page d'accueil du tenant public **ROOT** (`https://tibillet.localhost/`, vue
`seo.views.landing`) :

- **Retrait** de l'ancien accordéon `<details>` « Futur de TiBillet » (roadmap : newsletter,
  réseaux sociaux, Fédiverse, économie cascade) qui se trouvait entre « Fonctionnalités » et
  « Nos lieux vivants ».
- **Ajout** d'un panneau d'appel à contribution **intégré dans la section « Fonctionnalités »**
  (en bas, après la grille des cartes). Il résume les chantiers ouverts et redirige, via un lien
  **codé en dur** (espace de la coopérative), vers `https://codecommun.tibillet.coop/contrib/`.
- **Ajout** d'un bouton **« Contribuer à TiBillet »** dans le **hero** (haut de page), aux côtés des
  boutons « Explorateur du réseau », « Documentation », « Créer son espace », vers la **même**
  destination contrib.
- **Ajout** d'un lien **« Contribuer »** (icône fusée) dans le **menu de navigation** ROOT
  (`seo/templates/seo/base.html`, navbar partagée par toutes les pages ROOT : landing, lieux,
  événements, explorer, recherche), entre « Documentation » et « Contact ».

### Modifications
| Fichier | Changement |
|---|---|
| `seo/templates/seo/landing.html` | Suppression de la section accordéon roadmap ; ajout du bloc `.contribute-panel` dans `.features-section` ; bouton « Contribuer à TiBillet » dans le hero |
| `seo/templates/seo/base.html` | Lien « Contribuer » dans la navbar ROOT |
| `seo/static/seo/seo.css` | Bloc CSS `.roadmap-*` (devenu mort) remplacé par les styles `.contribute-*` |

### Contenu du panneau
- Icône fusée (`bi-rocket-takeoff`) dans un cercle gradient vert→bleu.
- Titre `h3` : « Venez participer à l'élaboration de TiBillet ! »
- Résumé : commun en construction, feuille de route ouverte (newsletter, réseaux sociaux, site web
  complet, interopérabilité ERP…), tout se construit en coopérative.
- Pastilles des chantiers : Newsletter intégrée · Réseaux sociaux & Fédiverse · Site web complet ·
  Interopérabilité ERP · Économie en cascade.
- Bouton vert « Participer au projet → » (`target="_blank" rel="noopener"`) +
  rappel du domaine « Espace coopératif · codecommun.tibillet.coop ».

## Tests à réaliser

### Test 1 : Affichage desktop
1. Ouvrir `https://tibillet.localhost/`.
2. Scroller jusqu'à la section « Fonctionnalités ».
3. **Attendu** : sous la grille des 10 cartes, un panneau gradient doux avec icône fusée, titre,
   résumé, 5 pastilles à anneau vert, et le bouton vert « Participer au projet → ».
4. **Attendu** : l'accordéon « Futur de TiBillet » n'existe plus (le panneau le remplace, juste
   au-dessus de « Nos lieux vivants »).

### Test 2 : Liens de contribution (hero + panneau)
1. En haut de page, cliquer sur **« Contribuer à TiBillet »** (bouton hero).
2. **Attendu** : ouverture dans un nouvel onglet de `https://codecommun.tibillet.coop/contrib/`.
3. Plus bas, cliquer sur **« Participer au projet »** (panneau Fonctionnalités).
4. **Attendu** : même destination, nouvel onglet.

### Test 3 : Responsive mobile (≤ 375 px)
1. Réduire la fenêtre à 375 px (ou DevTools mobile).
2. **Attendu** : la grille « Fonctionnalités » passe en 1 colonne ; les pastilles wrappent
   proprement ; le bouton reste sur **une seule ligne** ; **aucun défilement horizontal**.

### Test 4 : Accessibilité
1. Navigation clavier (Tab) jusqu'au bouton.
2. **Attendu** : anneau de focus vert visible et **instantané** (non animé).
3. Lecteur d'écran : la liste des chantiers est annoncée (`aria-label="Chantiers ouverts"`),
   les icônes décoratives sont ignorées (`aria-hidden="true"`).

### Test 5 : SEO / hiérarchie des titres
1. Inspecter le DOM.
2. **Attendu** : `h1` (hero) → `h2` « Fonctionnalités » → `h3` cartes + `h3` panneau contribution.
   Plus de `h2` orphelin lié à l'ancienne roadmap.

## i18n (à faire par le mainteneur)

Nouvelles chaînes `{% translate %}` (texte source **FR**) ajoutées dans `landing.html` :
« Venez participer à l'élaboration de TiBillet ! », le résumé, « Chantiers ouverts »,
« Newsletter intégrée », « Réseaux sociaux & Fédiverse », « Site web complet »,
« Interopérabilité ERP », « Économie en cascade », « Participer au projet »,
« Espace coopératif · codecommun.tibillet.coop », « Contribuer à TiBillet » (bouton hero),
« Contribuer » (lien navbar, dans `base.html`).
Le résumé a été reformulé (« se construit en commun ») → nouveau msgid.

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
# éditer locale/en/LC_MESSAGES/django.po (traduire les msgstr), retirer les #, fuzzy
docker exec lespass_django poetry run django-admin compilemessages
```

Les anciennes chaînes roadmap (« Futur de TiBillet », « Fédiverse et Mobilizon »,
« Réseaux sociaux unifiés », etc.) deviennent obsolètes : `makemessages` les marquera
`#~` (obsolète) — à nettoyer.

## Compatibilité

- **Aucune migration**, aucun changement de vue Python (seuls template + CSS touchés).
- Aucun test pytest/E2E n'assertait sur l'ancienne section roadmap (`roadmap-section`,
  `roadmap-toggle`) — vérifié par recherche dans `tests/`.
- Le lien est **codé en dur** par choix explicite (espace de la coopérative, pas de config tenant).
