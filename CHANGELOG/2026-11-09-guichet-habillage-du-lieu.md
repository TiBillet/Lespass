# Guichet de connexion : habillé aux couleurs du lieu / Login desk: dressed in the venue's look

**Date :** 2026-11-09
**Migration :** Non

## Resume / Summary
**Quoi / What :** le guichet de connexion commun (`/sso/`, sur le domaine du schéma `public`) prend l'habillage du skin du lieu qui envoie la personne : V2 (fond sable, en-tête du lieu, carte papier, Unbounded / Luciole), « reunion » (Bootstrap + `marque.css`), ou « faire_festival » (bandeau jaune, bordures bleues, ombre dure). L'en-tête montre le logo et le nom du lieu, avec un lien « Retour sur <lieu> ». Un lieu inconnu prend l'habillage V2. Avant, la page reprenait l'habillage du site vitrine tibillet.coop (`seo/base.html`).
/ The shared login desk takes the sending venue's skin (V2, reunion, faire_festival), with the venue's logo, name and a back link. Unknown venue: V2 look. It used to wear the tibillet.coop showcase look.

**Pourquoi / Why :** la personne quitte le site du lieu pour se connecter. Si la page change complètement d'allure, elle peut croire à une erreur, ou à un site piège.
/ The person leaves the venue site to log in: a page that looks completely different is confusing, or feels like a trap.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `AuthBillet/views_sso.py` | `lire_l_habillage_du_lieu()` (skin, nom, URL du lieu, URL absolue du logo, lus dans `tenant_context`), `choisir_le_gabarit_du_guichet()`, `rendre_la_page_d_erreur()`, dictionnaire `GABARIT_DU_GUICHET_PAR_SKIN` ; `lire_le_nom_du_lieu()` retirée |
| `AuthBillet/templates/sso/guichet.html` | Devient le socle : document HTML autonome (plus `seo/base.html`), blocs `feuilles_de_style`, `classes_du_body`, `page` |
| `AuthBillet/templates/sso/guichet_V2.html` | Nouveau : habillage V2 (et habillage par défaut) |
| `AuthBillet/templates/sso/guichet_reunion.html` | Nouveau : habillage « reunion » |
| `AuthBillet/templates/sso/guichet_faire_festival.html` | Nouveau : habillage « faire_festival » |
| `AuthBillet/templates/sso/partials/etape_email.html`, `erreur.html` | Marges explicites (V2 remet les `<p>` à 0) |
| `tests/pytest/test_sso_guichet.py` | 4 tests : un gabarit par skin, lien absolu vers le lieu ; lieu inconnu → V2 |

Le titre de la carte est « Vérification », et l'étape email commence par « Pour continuer, nous avons besoin de vérifier que vous êtes un vrai humain. » : la personne arrive en cliquant « Réserver » ou « Adhérer », on lui parle de vérification, pas de compte.

Chaînes traduisibles ajoutées (msgid FR) : « Vérification », « Vérification — %(nom_du_lieu)s », « Pour continuer, nous avons besoin de vérifier que vous êtes un vrai humain. », « Une seule connexion pour tous les lieux TiBillet. », « Retour sur %(nom_du_lieu)s », « Logo %(nom_du_lieu)s ». Le workflow i18n est à lancer.

---

## Comment tester (a la main) / Manual test
### Test 1 — lieu en skin V2
1. Déconnecté, sur `https://lespass.tibillet.localhost/`, cliquer sur « Connexion ».
2. Attendu sur `tibillet.localhost/sso/` : fond sable, carte « Lespass » avec son logo, carte « Vérification » avec la phrase « vrai humain », bouton V2.
3. Demander un code : le message s'affiche en encre et papier (pas de cyan ni de jaune Bootstrap).
4. « Retour sur Lespass » ramène sur le lieu.

### Test 2 — lieu en skin faire_festival
1. Ouvrir `https://tibillet.localhost/sso/?lieu=festival.tibillet.localhost&state=un-state-quelconque-assez-long`.
2. Attendu : bandeau jaune avec le logo du festival, carte à bordure bleue épaisse et ombre dure, bouton jaune en majuscules.

### Test 3 — lieu en skin « reunion »
1. Admin d'un lieu → Configuration du site → Thème « Réunion ».
2. Se déconnecter, cliquer sur « Connexion ». Attendu : barre blanche avec le logo et le nom du lieu, carte Bootstrap, couleur primaire du site (`marque.css`).
3. Remettre le thème d'origine.

### Test 4 — lien invalide
1. Ouvrir `https://tibillet.localhost/sso/?lieu=inconnu.tibillet.localhost&state=un-state-quelconque-assez-long`.
2. Attendu : habillage V2 sans en-tête de lieu, message « Lien de connexion invalide. ».

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_sso_guichet.py"`.
- E2E du guichet (`tests/e2e/test_connexion_par_code.py`) : `data-testid` et id des formulaires inchangés.
