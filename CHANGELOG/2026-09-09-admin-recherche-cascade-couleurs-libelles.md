# Recherche explicite, cascade, couleurs et libellés
/ Explicit search, cascade, colours and labels

**Date :** 2026-09-09
**Migration :** **Oui** — 9 migrations `AlterField` (libellés uniquement)

## Resume / Summary

Quatre lots de la feuille de route admin, appliques ensemble.

| Lot | Quoi |
|---|---|
| **Recherche** | le champ dit desormais SUR QUOI il cherche |
| **Cascade** | les cartes eteintes entrent l'une apres l'autre |
| **Couleurs** | 509 → 159 attributs `style` avec un hexadecimal en dur |
| **Libelles** | 62 → 9 champs d'admin sans `verbose_name` |

---

## 1. Le champ de recherche dit sur quoi il cherche

Avant : « Type to search ». Apres : **« Rechercher : e-mail, prénom, nom… »**,
derive de `search_fields`. **55 classes sur 82** en ont un : l'information
existait partout, elle n'etait jamais montree.

**Zero gabarit surcharge.** Unfold rend `search_help_text` **comme placeholder**
du champ (`unfold/templates/admin/search_form.html`), la ou l'admin Django natif
l'affiche en petit dessous. Cote Django l'attribut est lu tel quel, sans
`get_search_help_text()` ni system check : une simple `@property` suffit.

### Une classe de base pour le projet

`Administration/admin/base.py` interpose un `ModelAdmin` a nous entre Unfold et
les ~57 classes d'admin, qui n'avaient jusqu'ici **aucun point commun** ou poser
un comportement transverse. Les 14 modules d'admin importent desormais
`ModelAdmin` d'ici. Verifie : **82 classes sur 82** en heritent.

> **Ce qu'on n'a pas fait.** On pouvait surcharger `StaffAdminSite.register()`
> pour injecter la property : **une** edition au lieu de quatorze. Rejete —
> muter des classes tierces a l'enregistrement est exactement la magie que la
> regle du projet demande d'eviter, et le jour ou le placeholder se comporterait
> bizarrement, personne ne saurait ou regarder.

La fabrication du libelle gere les vraies formes de `search_fields` du projet :
prefixes `^ = @` retires, **lookups lies resolus** (`user__email` → « e-mail »,
y compris a trois niveaux), **doublons fusionnes** (`first_name` et
`memberships__first_name` donnent tous deux « prénom »), et **plafond a trois**
suivis de « … » — au-dela, le CSS d'Unfold tronque de toute facon.

## 2. La cascade d'apparition des cartes

Ouvrir « Decouvrir plus de modules » faisait surgir les cartes d'un coup.
Elles entrent desormais l'une apres l'autre, **40 ms** d'ecart, comme la
maquette.

**Le delai est calcule en Python**, pas en JavaScript : nos cartes sont rendues
cote serveur et leur ordre est deja connu — la maquette avait besoin de JS
parce qu'elle construit son DOM a l'execution. Le compteur **repart de zero a
chaque domaine**, sinon la derniere carte attendrait pres d'une seconde.

Deux points qui ne sont pas des details :

- **une animation CSS se declenche bien** quand un element passe de
  `display: none` a affiche. On garde donc le masquage existant — la grille ne
  saute pas — et on n'ajoute que l'animation ;
- **aucune animation au chargement, gratuitement** : au chargement les cartes
  sont masquees, donc rien ne part. C'est le piege de la revision 10, regle ici
  par construction plutot que par une condition.

La **sortie n'est pas animee**, et c'est un choix : il faudrait un etat
intermediaire et une temporisation dans Alpine pour retarder le retrait du flux.

## 3. Dé-durcir les couleurs

**509 → 159** attributs `style` contenant un hexadecimal (−69 %).

### D'abord : un gabarit MORT supprime

`Administration/templates/admin/cloture_detail.html` (552 lignes) n'etait
reference par **aucun Python et aucun gabarit**. Seul
`admin/cloture/rapport_before.html` est branche.

**Consequence, et c'est le vrai sujet : la colonne « Poids/Vol » n'existait que
la.** Les filtres `has_poids` / `afficher_poids` avaient des tests unitaires **au
vert**, mais la colonne qu'ils alimentent n'etait jamais rendue — alors que le
poids **est calcule a chaque rapport** (`laboutik/reports.py`, cles
`poids_total` / `unite_poids`). La donnee etait produite puis jetee.

La colonne a donc ete **portee dans le gabarit vivant AVANT** la suppression,
avec des tests qui verifient qu'elle est **rendue**. Puis le fichier mort a ete
supprime : il emportait **193 des 509** attributs colores et **152 des 302**
`#ddd`.

> Signe confirmant qu'il etait mort : le dernier commit a l'avoir touche
> (`548501c2`) s'intitule « feat(pages): add afficher_sommaire field » — un
> changement sans rapport, qui a derive dans un fichier que personne ne rend.

### Ensuite : quatre codes gris remplaces

`#ddd` (150), `#333` (13), `#666` (11), `#f0f0f0` (11) → des **jetons**
`--tb-*`.

**La regle du projet est respectee, et il faut le dire clairement** :
`.claude/skills/djc/SKILL.md` impose les styles inline dans l'admin (les classes
Tailwind personnalisees ne sont pas dans le bundle d'Unfold et rendraient du
blanc sur blanc) — mais la meme regle **autorise explicitement les variables
CSS**. On garde `style="..."`, on ne remplace que le litteral.

**Et les jetons sont redefinis sous `html.dark`.** C'est tout l'interet : un
`var(--color-base-200)` ecrit directement serait reste clair sur fond sombre,
car cette variable-la n'est pas sensible au theme. Passer par un jeton est la
seule facon d'obtenir le mode sombre depuis un attribut `style`.

Les couleurs **semantiques** (`#16a34a` succes, `#dc2626` danger) sont laissees
en dur : les faire suivre la peau les rendrait muettes.

## 4. Les `verbose_name` manquants

**62 → 9** champs affiches dans l'admin sans libelle explicite, sur 9 apps.

Le releve de `ADMIN-HANDOFF.md` (« 59 champs ») etait a reprendre : 3 etaient
deja corriges, **39 sur 59 n'etaient pas des champs de modele** (methodes
`@display`), et il ignorait entierement `crowds`, `kiosk` et `laboutik`.

Les **5 champs de `Configuration`** ont ete traites en priorite : ils
s'affichaient en anglais dans les onglets refondus au meme moment.

**9 restent, deliberement** : `uuid` et `id`, identifiants techniques en lecture
seule. Ils sont **nommes** dans `TOLERES` — une decision, pas un oubli, et un
second test echoue si l'un d'eux recoit un libelle sans etre retire de la liste.

> **9 migrations `AlterField`**, uniquement des changements de libelle — aucune
> modification de schema (verifie : l'operation `AlterField` est la seule
> presente dans les neuf fichiers). Sur ce projet multi-tenant, elles
> s'appliquent **schema par schema**.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/base.py` | **neuf** — `ModelAdmin` projet + `search_help_text` |
| 14 modules d'admin | l'import de `ModelAdmin` pointe vers la base projet |
| `Administration/admin/dashboard.py` | `+ PAS_DE_LA_CASCADE_MS`, `delai_ms` par carte |
| `admin/partials/dashboard_module_card.html` | `style="--tb-delai: …"` |
| `static/css/tibillet-admin.css` | `+ @keyframes tb-carte-entre` ; 4 jetons clair **et** sombre |
| `admin/cloture/rapport_before.html` | `+` colonne Poids/Vol, `colspan` adaptatif |
| `admin/cloture_detail.html` | **supprime** (mort) |
| 24 gabarits d'admin | 185 hexadecimaux → jetons `--tb-*` |
| 9 modules `models.py` | `+ verbose_name` sur 53 champs |
| 9 migrations `*_verbose_name_fr.py` | **neuves** — `AlterField` uniquement |
| 5 fichiers de tests | **neufs** — 24 tests |

## Verification

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_*.py \
    tests/pytest/test_cloture_colonne_poids.py tests/pytest/test_afficher_poids.py -v
```

**126 tests passent, aucun saute.**

Trois garde-fous meritent d'etre signales, parce qu'ils protegent contre le
retour de la dette plutot que contre une regression ponctuelle :

- `test_aucun_champ_affiche_n_est_sans_libelle` : un champ ajoute demain a une
  `list_display` sans `verbose_name` fera echouer les tests, au lieu de
  s'afficher en anglais pendant des mois ;
- `test_les_jetons_sont_definis_en_clair_ET_en_sombre` : un jeton defini
  seulement en clair ne vaut pas mieux qu'un hexadecimal ;
- `test_le_gabarit_mort_n_existe_plus` : si `cloture_detail.html` revenait, la
  meme erreur pourrait se reproduire.

**Non couvert :** les tests E2E (Chromium/Playwright indisponible dans
l'environnement) et le controle visuel clair/sombre.
