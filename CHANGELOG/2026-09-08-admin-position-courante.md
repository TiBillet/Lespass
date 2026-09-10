# Savoir ou l'on est sur une changelist / Knowing where you are on a changelist

**Date :** 2026-09-08
**Migration :** Non

## Resume / Summary

**Quoi / What :** sur une changelist, le rail surligne desormais le module
courant et deplie son domaine, et le fil d'Ariane nomme **le module** au lieu
de l'application Django.
/ A changelist now highlights its module in the sidebar, expands its domain,
  and the breadcrumb names the module instead of the Django app.

**Pourquoi / Why :** depuis le passage a la navigation Domaines -> Modules
(revision 3), les pages d'un module ont quitte le rail : seul le module y
figure. Deux consequences etaient restees non corrigees, et toutes deux
echouaient **en silence** — aucune erreur, juste une interface qui ne disait
plus ou l'on se trouvait.

| | Avant / Before | Apres / After |
|---|---|---|
| Rail sur `/admin/BaseBillet/event/` | rien de surligne, aucun domaine deplie | **Agenda et Billetterie** surligne, **Lespass** deplie |
| Fil d'Ariane | `Billetterie > Evenements`, vers `/admin/BaseBillet/` | `Agenda et Billetterie > Evenements`, vers `/admin/module/agenda/` |

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | `+ _chemin_correspond()`, `+ _module_du_chemin()` ; `_module_en_lien(section, est_courant)` pose la cle `active` ; `_regrouper_sections_par_domaine` calcule le module courant une fois |
| `Administration/templatetags/__init__.py` | **neuf** |
| `Administration/templatetags/tb_admin.py` | **neuf** — la balise `fil_ariane_par_module` |
| `Administration/templates/unfold/helpers/header_title.html` | **neuf** — surcharge, 2 lignes ajoutees au fichier d'Unfold |
| `tests/pytest/test_admin_fil_ariane_et_rail.py` | **neuf** — 16 tests |

Aucun CSS : le style du lien actif existait deja depuis la revision 3.

## Volet 1 — le rail, sans toucher un gabarit

`unfold/sites.py:377` :

```python
if "active" in item:
    item["active"] = self._get_value(item["active"], request)
else:
    item["active"] = self._get_is_active(...)
```

**Une cle `active` deja posee est respectee** — Unfold ne calcule que si elle
est absente. Il suffisait donc que `_module_en_lien()` la pose.

Le depliage du domaine suit tout seul : notre surcharge d'`app_list.html`
ouvre un groupe des qu'un de ses liens est actif
(`{% has_nav_item_active %}`), et la classe est posee cote serveur — donc
**aucune animation au chargement** (revision 10).

### Le piege, et le test qui le couvre

Poser la cle `active` **desactive** le calcul d'Unfold pour ce lien. Notre
valeur devait donc aussi couvrir le cas qui marchait **deja** : etre **sur**
`/admin/module/agenda/`. L'oublier aurait repare un ecran en cassant l'autre.
C'est l'objet de `test_la_page_du_module_reste_surlignee`.

### Portee exacte, mesuree

| | |
|---|---|
| Changelists enregistrees | 82 |
| rattachees a un module (corrigees ici) | **51** |
| sans module | 31 |

Les 31 restantes sont soit des pages de **section autonome** (`Parametres`,
`Ventes et comptabilite`, `Configuration racine`) — **deja surlignees**
correctement par Unfold, puisqu'elles sont de vrais liens de rail — soit des
admins qui ne figurent nulle part dans le rail. **Le lot ne les touche pas**,
et deux tests le verifient.

## Volet 2 — le fil d'Ariane

`header_title` (`unfold/templatetags/unfold.py`) ouvre toujours par
l'application Django. « Billetterie » est le `verbose_name` de `BaseBillet` :
il **ressemble** a un nom de module sans en etre un, et son lien mene a
`/admin/BaseBillet/`, 29 modeles a plat — une page qui n'a aucun sens dans une
navigation Domaines -> Modules.

### Pourquoi une deuxieme surcharge de gabarit

`header_title` construit sa liste **en Python** ; `header_title.html` ne fait
que l'afficher. Il n'existe **ni reglage `UNFOLD`, ni bloc de gabarit** pour
l'inflechir — verifie. **Retirer** l'entree et **la remplacer** passaient donc
par le meme point d'accroche : ce fichier.

Une troisieme voie **sans surcharge** — reecrire `/admin/<app>/` rangee par
module via `StaffAdminSite.app_index()` — a ete etudiee puis **ecartee** :
elle laissait « Billetterie » dans le fil d'Ariane, et surtout **rien d'autre
ne mene a cette page** (le panneau « Toutes les applications » du rail pointe
vers les changelists ; les gabarits d'Unfold qui affichent `app_url` ne
servent que quand `SIDEBAR.navigation` n'est pas configure — or nous le
configurons). On aurait meuble un troisieme axe de navigation au lieu de le
supprimer.

C'est donc le **deuxieme** gabarit d'Unfold surcharge, apres `app_list.html`.
Pour que la surcharge reste triviale et **sans logique**, tout le calcul est
dans `Administration/templatetags/tb_admin.py` ; le fichier ne gagne que deux
lignes, et son corps est **mot pour mot** celui d'Unfold.

### Les deux garde-fous de la balise

1. **Elle ne retire ni n'ajoute jamais une entree** : elle en remplace au plus
   une. Un fil d'Ariane casse serait plus genant que le defaut corrige.
2. **Elle exige au moins deux entrees.** `header_title.html` est rendu par
   `render_to_string(..., context={"parts": parts})` : `opts` n'est **pas**
   dans le contexte, on ne peut donc pas savoir autrement qu'on est sur une
   page de modele. Or une page de modele produit toujours 2 entrees
   (application + modele) ou 3 (+ l'objet), tandis qu'une page sans modele —
   tableau de bord, domaine, module — en produit **une seule** :
   « Bienvenue <untel> ». Sans ce test, on ecraserait ce message d'accueil.

## Un cache abandonne en cours de route

`_construire_sections_modules()` etait deja appelee deux fois par page ; le
fil d'Ariane en ajoutait une troisieme. Un cache pose sur l'objet `request`
a d'abord ete ecrit — puis **retire** : il faisait dependre
`get_sidebar_navigation()` de l'**ordre** des appels, et cassait
`test_newsletter_est_rangee_dans_le_domaine_lespass`, qui active le module
**apres** un premier rendu et re-interroge la meme requete.

Mesure avant de trancher : `_construire_sections_modules()` coute **0,99 ms et
1 requete SQL**. Le cache economisait cela au prix d'un piege de peremption.
Il a ete supprime.
/ A per-request cache was written then removed: it made the sidebar depend on
  call order for a measured saving of 0.99 ms and one SQL query.

## Verification

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_fil_ariane_et_rail.py -v
```

**16 tests, aucun saute.** Les **5** qui visent le defaut ont ete rejoues
contre le code **d'avant** et **echouent** — un test qui passe des deux cotes
ne prouve rien. Les 11 autres sont des garde-fous : ils doivent passer des
deux cotes, c'est leur role.

Suites d'admin completes : **71 tests passent**
(`test_admin_fil_ariane_et_rail`, `test_admin_tableau_de_bord`,
`test_admin_page_de_module`, `test_module_newsletter_activation`).

**Non couvert ici :** les tests E2E n'ont pas pu etre joues (Chromium /
Playwright indisponible dans l'environnement courant).

**Visuel**, en clair et en sombre : `/admin/BaseBillet/event/` — module
surligne, domaine deja deplie **sans animation** au chargement, barre haute
« Agenda et Billetterie > Evenements » dont le premier mot ouvre la page du
module.

## Retour arriere / Rollback

Les deux volets sont independants :

- rail : retirer la cle `"active": est_courant` de `_module_en_lien()` ;
- fil d'Ariane : supprimer
  `Administration/templates/unfold/helpers/header_title.html` — Django reprend
  alors celui d'Unfold.

Aucune migration, aucune donnee touchee.
