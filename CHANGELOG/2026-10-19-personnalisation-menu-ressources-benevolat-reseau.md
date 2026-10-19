# Personnalisation des pages Ressources, Bénévolat et Réseau / Customizable Resources, Volunteering and Network pages

**Date :** 2026-10-19
**Migration :** Oui — `BaseBillet/migrations/0236_configuration_personnalisation_ressources_benevolat_reseau.py` (5 champs sur `Configuration`).
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas BaseBillet`

## Resume / Summary
**Quoi / What :**
- Admin Configuration, onglet « Personnalisation » : nom de menu pour Ressources, Bénévolat et Réseau (vide = libellé par défaut), comme Agenda et Adhésions.
  / Menu name for Resources, Volunteering and Network (empty = default label).
- Texte d'introduction (WYSIWYG, nettoyé à l'enregistrement) pour les pages Ressources et Bénévolat.
  / Intro text (WYSIWYG, sanitized on save) for the Resources and Volunteering pages.
- Réseau : le texte d'introduction existant reste dans Fédération › Options, section « Présentation ». Le texte d'aide du champ « Nom de la page Réseau » y renvoie.
  / Network intro text stays in Federation › Options; the menu name field points to it.
- Le nom choisi s'applique au menu, au titre de l'onglet, aux balises Open Graph/Twitter, au h1 (Bénévolat, Réseau) et (Réseau) au fil d'Ariane JSON-LD.
- Page Ressources (`/booking/`) : le h1 est masqué à l'écran (`visually-hidden`), toujours lu par les lecteurs d'écran et les moteurs de recherche.
  / Resources page: the h1 is visually hidden, still read by screen readers and search engines.
  / The name applies to menu, title, OG/Twitter tags, h1 and breadcrumb.

**Pourquoi / Why :** chaque lieu nomme ses pages à sa façon, comme il le fait déjà pour l'agenda et les adhésions. / Each venue names its pages its own way.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `booking_menu_name`, `benevolat_menu_name`, `federation_menu_name`, `description_booking_page`, `description_benevolat_page` |
| `BaseBillet/migrations/0236_…` | AddField × 5 |
| `Administration/admin_tenant.py` | Champs ajoutés à l'onglet « Personnalisation » |
| `BaseBillet/views.py` | Libellés du menu (`get_context`) ; `FederationViewset.list` : `nom_de_la_page_reseau` (titre + fil d'Ariane) |
| `booking/templates/booking/views/resources_list.html` | Titre de l'onglet, h1 masqué (`visually-hidden`), texte d'intro |
| `booking/templates/booking/benevolat/liste.html` | Titre, h1, texte d'intro (remplace le chapô par défaut) |
| `pages/templates/pages/V2/vues/reseau.html` | Titre, OG/Twitter, h1 |
| `pages/templates/pages/classic/vues/reseau.html` | Titre, OG/Twitter, h1 masqué |
| `tests/pytest/test_admin_configuration_onglets.py` | Liste des champs attendus mise à jour |

---

## Comment tester (a la main) / Manual test

### Test 1 — noms de menu
1. Admin → Configuration → onglet « Personnalisation ».
2. Remplir « Nom de la page Ressources », « Nom de la page Bénévolat », « Nom de la page Réseau ». Enregistrer.
3. Sur le site : le menu affiche les nouveaux noms. Sur chaque page, le titre de l'onglet aussi, et le h1 (masqué à l'écran sur `/booking/`, visible dans le code source).
4. Vider les trois champs : retour à « Ressources », « Bénévolat », « Autour de nous ».

### Test 2 — textes d'introduction
1. Remplir « Description de la page Ressources » (gras, liste) → affichée au-dessus des cartes de `/booking/`.
2. Remplir « Description de la page Bénévolat » → remplace le chapô par défaut de `/booking/benevolat/`.
3. Vide → `/booking/` sans intro, `/booking/benevolat/` avec le chapô par défaut.

### Test 3 — Réseau
1. Fédération › Options, section « Présentation » : le texte d'introduction s'affiche en haut de `/federation/` (skins V2 et classic).

### Test 4 — XSS
1. Mettre `<script>alert(1)</script>` dans une description : retiré à l'enregistrement (`sanitize_textfields` de `ConfigurationAdmin`).

### Verifs DB / Playwright
- Pytest : `test_admin_configuration_onglets.py`, `test_pages.py`, `test_federation_view_integration.py`, `test_benevolat_*.py`, `test_booking_calendrier_semaine.py`, `booking/tests/` (330 verts).
- Rendu vérifié par curl sur le tenant `lespass` (valeurs posées puis remises à vide).
