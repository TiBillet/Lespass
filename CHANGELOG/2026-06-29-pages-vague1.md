# App `pages` — Constructeur de pages par blocs (vague 1)

## Ce qui a été fait

Nouvelle app Django `pages` (en `SHARED_APPS` + `TENANT_APPS`, isolation par
schéma) permettant de composer des pages publiques en empilant des **blocs
préfabriqués** édités dans l'admin Unfold. Vague 1 = 5 blocs à champs plats :
**Hero, Paragraphe riche, Image + texte, CTA, Témoignage**.

Une `Page` peut être marquée **page d'accueil** (`est_accueil`) : elle est alors
servie sur la **racine `/`** du tenant. Sinon, chaque page est servie sur
`/<slug>/` et les pages publiées apparaissent dans la navbar.

L'édition d'un bloc se fait sur sa propre fiche : les champs s'affichent/se
masquent selon le **type de bloc** grâce au `conditional_fields` **natif**
d'Unfold (aucun JavaScript maison).

### Modifications
| Fichier | Changement |
|---|---|
| `pages/models.py` | Modèles `Page` + `Bloc` (champs plats), validateur slugs réservés, `nom_template` |
| `pages/admin.py` | `PageAdmin` + `BlocInline` (drag-drop) + `BlocAdmin` (conditional_fields natif) |
| `pages/views.py` | `page_publique(slug)` + `rendre_page` (réutilise `get_context` + skin) |
| `pages/urls.py` | Route attrape-tout `/<slug>/` |
| `pages/templates/pages/` | `page.html` + 5 partials `bloc_*.html` (markup neutre `.tb-bloc*`) |
| `pages/static/pages/css/tb-blocs.css` | CSS commun conforme Hallmark |
| `pages/management/commands/creer_page_demo.py` | Crée une page d'accueil démo (5 blocs) |
| `TiBillet/settings.py` | `'pages'` dans SHARED_APPS + TENANT_APPS |
| `TiBillet/urls_tenants.py` | `include('pages.urls')` après BaseBillet |
| `Administration/admin_tenant.py` | `import pages.admin` |
| `Administration/admin/dashboard.py` | Sidebar « Website » → Pages |
| `BaseBillet/views.py` | navbar (`main_nav`) + hook page d'accueil dans `index` |

## Tests à réaliser

### Prérequis : appliquer les migrations
```bash
docker exec lespass_django poetry run python manage.py migrate_schemas
```

### Test 1 : page de démonstration sur la racine (déjà créée)
La commande a déjà été lancée sur `lespass`. Vérifier visuellement :
1. Ouvrir `https://lespass.tibillet.localhost/`
2. La racine affiche la page démo « Accueil (démo) » avec les 5 blocs empilés :
   Hero (2 boutons), Paragraphe (gras/italique/liste), Image+texte, CTA (bordure
   d'accent), Témoignage (Camille D. / adhérente).
3. L'en-tête et le pied de page du skin sont conservés.

Pour (re)créer la démo sur un autre tenant :
```bash
docker exec lespass_django poetry run python manage.py creer_page_demo --schema=<tenant>
```

### Test 2 : admin — créer une page et ses blocs
1. `https://lespass.tibillet.localhost/admin/` → sidebar **Website → Pages**.
2. Ajouter une page (titre → slug auto-rempli), cocher « Publiée », enregistrer.
3. Dans l'inline « Blocs », ajouter une ligne (type + titre), enregistrer.
4. Cliquer « modifier » sur le bloc → sa fiche s'ouvre.
5. **Changer le « Type de bloc »** : les champs affichés doivent changer
   instantanément (ex : Témoignage → Texte + Nom/Rôle/Photo de l'auteur ;
   Hero → Titre/Sous-titre/Image/Boutons).
6. Réordonner les blocs par glisser-déposer dans l'inline de la page.

### Test 3 : rendu public d'une page secondaire
1. Créer une page publiée avec slug ex. `notre-histoire` (sans `est_accueil`).
2. Ouvrir `https://lespass.tibillet.localhost/notre-histoire/` → la page s'affiche.
3. Le lien apparaît dans la navbar du site.

### Test 4 : slug réservé refusé
Dans l'admin, tenter de créer une page avec le slug `event` (ou `my_account`) →
le formulaire doit refuser avec un message « Ce slug est réservé… ».

### Test 5 : non-régression des routes existantes
`https://lespass.tibillet.localhost/event/`, `/memberships/`, `/my_account/`
doivent fonctionner normalement (non masquées par la route `/<slug>/`).

### Test 6 : responsive (Hallmark)
Vérifier à 320 / 375 / 414 / 768 px : pas de scroll horizontal, image+texte qui
passe en une colonne, boutons jamais coupés sur deux lignes.

### Revenir à l'accueil par défaut
Pour que la racine `/` réaffiche la home d'origine : dans l'admin, décocher
« Page d'accueil » sur la page démo (ou la supprimer).

## Tests automatiques
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pages.py -v
```
11 tests : modèles (slug réservé, ordre des blocs, page d'accueil unique,
`nom_template`), vue publique (rendu, 404 brouillon, route `/event/` non masquée),
admin (conditional_fields, changelist, sanitisation du texte).

## Compatibilité
- **Tenant public / landing `www.tibillet.localhost`** : la table existe déjà
  dans le schéma public (dual-list), mais l'admin et le rendu public ne sont
  **pas encore branchés** sur l'URLconf public — c'est le **chantier 02**
  (cf. `TECH_DOC/SESSIONS/PAGES/`). En vague 1, l'app est validée sur les tenants.
- **Vagues suivantes** : vague 2 (galerie M2M, carte/FAQ/horaires JSON),
  vague 3 (programme événements + bouton billetterie liés à l'API).
- i18n : textes source en FR ; lancer `makemessages`/`compilemessages` (mainteneur).
