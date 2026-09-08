# Navigation de l'admin par domaines / Domain-based admin navigation

**Date :** 2026-09-08
**Migration :** Non

## Resume / Summary

**Quoi / What :** la sidebar de l'admin passe d'une liste de ~16 sections a plat
(environ 60 liens) a une arborescence **Domaine -> Module** : 5 domaines
(Lespass, Laboutik, Lerezo, Lekontrib, Lemachines) contenant 14 modules, soit
14 liens. Les pages d'un module deviennent ses **onglets**.
/ The admin sidebar moves from ~16 flat sections (about 60 links) to a
Domain -> Module tree: 5 domains, 14 modules, 14 links. A module's pages
become its tabs.

**Pourquoi / Why :** c'est l'arborescence proposee par la maquette
`TEMP-tibillet-admin-main/`. Le point de depart etait favorable : le code
regroupait **deja** les sections en 6 « familles » via un champ `_order`.
Il n'y avait donc pas de structure a inventer, seulement a recaler sur les
5 domaines.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | `+ DOMAINES` ; `_domaine`/`_order`/`_icone` sur les 16 sections ; `get_sidebar_navigation` renommee en `_construire_sections_modules` ; `+ get_sidebar_navigation` (repli par domaine) ; `+ _regrouper_sections_par_domaine`, `+ _module_en_lien` ; `+ get_tabs`, `+ _carte_des_liens_vers_modeles`, `+ _onglets_hors_modules` |
| `Administration/admin_tenant.py` | re-export de `get_tabs` |
| `TiBillet/settings.py` | `TABS` : liste statique -> `"Administration.admin_tenant.get_tabs"` |
| `tests/pytest/test_module_newsletter_activation.py` | 2 tests de sidebar adaptes au nouveau contrat, `+ 1` test de rangement |

Aucun template, aucun `ModelAdmin`, aucun modele n'a ete touche.

## La contrainte, et le choix qui en decoule

La maquette veut **trois** niveaux : Domaine -> Module -> pages. La sidebar
d'Unfold n'en a que **deux** : un groupe, et ses liens. Un groupe sans liens
est meme purement masque (`has-[ol]:has-[li]:block` dans `app_list.html`), donc
on ne peut pas se contenter d'ajouter un sur-titre de domaine.

**Choix retenu : groupe = DOMAINE, lien = MODULE.** C'est la forme la plus
fidele au rail de la maquette.

Sa consequence directe : **les pages d'un module quittent la sidebar.** Elles
doivent donc reapparaitre ailleurs, sinon 46 pages deviendraient inatteignables.
D'ou les onglets.

> **Ce choix est a l'essai.** Il change la navigation en profondeur : on passe
> d'un clic a deux (choisir le module, puis l'onglet). Si cela s'avere penible
> a l'usage, deux replis existent, et **seule `_regrouper_sections_par_domaine()`
> serait a reecrire** — la construction des sections, elle, n'a pas bouge :
>
> - **repli partiel** : garder les domaines mais y remettre toutes les pages a
>   plat (le groupe Lespass contiendrait une vingtaine de liens) ;
> - **repli complet** : revenir aux modules comme groupes, en recalant
>   simplement les familles sur les 5 domaines.

## Comment ca marche / How it works

### Une seule source pour la sidebar ET les onglets

`_construire_sections_modules(request)` est l'ancienne `get_sidebar_navigation`,
simplement renommee. Elle produit les sections brutes — une par module — et
**n'a pas ete modifiee** : toute la logique de permissions, de modules
desactives et de `_safe_rev` est intacte.

Deux fonctions la consomment :

- `get_sidebar_navigation()` replie ces sections en groupes-domaines ;
- `get_tabs()` en derive la barre d'onglets de chaque module.

C'est ce partage qui garantit qu'une page ajoutee a un module apparait aux deux
endroits **sans double saisie**.

### Les onglets ne sont pas un confort

Ils sont la seconde moitie de la navigation. `UNFOLD["TABS"]` est donc passe
d'une liste statique a un chemin pointe. Verifie dans `unfold/sites.py` :
`_get_config` fait passer la valeur par `_get_value`, qui importe et appelle
un chemin pointe — exactement comme `SIDEBAR.navigation`.

Les deux barres historiques (Formbricks, et Parametres/Cles API/Webhooks) sont
conservees telles quelles dans `_onglets_hors_modules()`.

### Detail : retrouver le modele derriere une URL

Les sections stockent une URL deja calculee (`/admin/BaseBillet/event/`), alors
qu'Unfold attend un nom de modele (`BaseBillet.event`) pour savoir sur quelles
pages afficher une barre d'onglets. `_carte_des_liens_vers_modeles()`
reconstruit la correspondance a partir des modeles reellement enregistres dans
l'admin, plutot que de decouper la chaine d'URL — un nom d'application peut
contenir un souligne (`fedow_core`, `root_billet`), le decoupage serait faux.

## Verification de non-regression

Le risque numero un de ce chantier, c'est qu'une page devienne inatteignable.
Le controle a ete fait, tous modules actives :

| | |
|---|---|
| Pages avant regroupement | 62 |
| Pages atteignables apres (sidebar + onglets) | 66 |
| **Pages perdues** | **0** |
| Barres d'onglets generees | 14 |

66 > 62 parce que les deux barres historiques ajoutent des pages qui n'etaient
pas dans la sidebar (cles API, webhooks, Formbricks).

Deux cas ne produisent pas de barre d'onglets, volontairement :

- un module d'**une seule page** (Kiosk) : son unique page est le lien de
  sidebar, elle reste atteignable ;
- une page qui **n'est pas une changelist** (tableau de bord maison, rapport) :
  elle figure bien dans la liste des onglets, mais ne declenche pas la barre
  quand on est dessus, car Unfold associe une barre a des modeles.

## Rangements qui relevent d'un choix

- **Ressources** (`module_booking`) est absent de la maquette. Range dans
  **Lespass** : c'est une reservation faite par le public, comme l'agenda.
- **Blog** et **Reseaux sociaux**, presents dans la maquette sous Lespass,
  **n'existent pas encore** dans le projet.
- **Configuration generale** (en tete), **Ventes & comptabilite** et
  **Configuration racine** (en pied) restent des entrees autonomes avec tous
  leurs liens, conformement au rail de la maquette.

## A tester / To test

### 1. La sidebar

Ouvrir `/admin/` sur un lieu ou **tous** les modules sont actifs. Attendu :

```
    Configuration generale     (Tableau de bord, Parametres, Comptes)
--- Lespass                    (Site web, Agenda, Adhesion, Ressources, Newsletter)
--- Laboutik                   (Caisse & Restaurant, Inventaire)
--- Lerezo                     (Federation, Monnaies & cashless)
--- Lekontrib                  (Financement participatif)
--- Lemachines                 (Kiosk, Tireuses, Terminaux)
--- Ventes et comptabilite     (Rapports, Lignes comptables)
--- Configuration racine       (En attente, Tenants, Domaines iframe)
```

Puis sur un lieu ou peu de modules sont actifs : les domaines sans aucun
module actif doivent **disparaitre entierement** (et non apparaitre vides).

### 2. Les onglets — le point critique

Cliquer sur chaque module et verifier que la barre d'onglets apparait et
donne acces a toutes ses pages. Les modules les plus fournis :

| Module | Onglets attendus |
|---|---|
| Agenda et Billetterie | 9 |
| Caisse & Restaurant | 7 |
| Tireuses connectees | 11 |
| Ressources | 6 |

Verifier en particulier qu'aucune page n'est devenue orpheline : le badge
d'adhesions recentes doit aussi avoir remonte sur le lien « Adhesion ».

### 3. Permissions

Se connecter avec un gestionnaire **non-root** : le groupe « Configuration
racine » doit disparaitre, et aucun onglet ne doit pointer vers une page
interdite.

### 4. Tests automatiques

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_module_newsletter_activation.py -v
docker exec lespass_django poetry run pytest tests/e2e/test_admin_*.py -v -s
```

Les tests E2E naviguent dans l'admin : ce sont eux qui diront si un parcours
s'appuyait sur un lien de sidebar qui n'existe plus.

**Deja verifie :** `manage.py check` propre ; 0 page perdue sur 62 ;
6 tests de `test_module_newsletter_activation.py` au vert.

## Suites / Next steps

1. **Les 3 onglets de la maquette** (Gerer / Configurer / Analyser) ne sont pas
   repris : les onglets actuels listent les pages du module a plat. Les
   regrouper demanderait une page de module dediee, donc une vraie vue.
2. **Le sous-titre des domaines** (« La vitrine du lieu et tout ce qui parle a
   votre public. ») est present dans `DOMAINES` mais pas affiche : la sidebar
   d'Unfold n'a pas d'emplacement pour lui.
3. **Blog et Reseaux sociaux** restent a creer, cote Lespass.
