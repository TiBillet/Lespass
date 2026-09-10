# Tableau de bord par domaines et page de domaine / Domain dashboard and domain pages

**Date :** 2026-09-08
**Migration :** Non

## Resume / Summary

**Quoi / What :** le tableau de bord de l'admin passe d'une grille plate de 11
cartes a **cinq blocs, un par domaine**, chacun avec son compteur
« actifs / total ». Les modules eteints sont **replies** derriere un
interrupteur « Decouvrir plus de modules ». Et cliquer le nom d'un domaine —
dans le rail ou sur le tableau de bord — ouvre desormais **la page de ce
domaine**, qui liste ses modules.
/ The dashboard moves from a flat grid to five domain blocks with counters;
off modules fold away; clicking a domain opens its own page.

**Pourquoi / Why :** c'etaient les deux derniers ecrans de la maquette
`TEMP-tibillet-admin-main/` a porter. Le tableau de bord etait aussi le dernier
ilot de l'ancien style : styles inline partout, replis violets `#7c3aed` qui
contredisaient le vert de marque, et **aucun test**.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | `domaine`, `icone`, `slug` sur chaque entree de `MODULE_FIELDS` ; `+ page_de_domaine`, `+ _grouper_les_cartes_par_domaine`, `+ _compter_les_cartes_reelles`, `+ _compter_les_cartes_actives`, `+ _compter_les_cartes_eteintes`, `+ _build_cartes_a_venir`, `+ _poser_les_liens_des_modules` ; `_build_modules_context` reecrit ; `link` sur les groupes de domaine |
| `Administration/admin/site.py` | route `domaine/<cle>/` |
| `Administration/templates/admin/dashboard.html` | reecrit : blocs par domaine, repli Alpine, appel a idees |
| `Administration/templates/admin/partials/dashboard_module_card.html` | reecrit : icone, etats, plus aucun style inline ni logique |
| `Administration/templates/admin/domaine_page.html` | **neuf** |
| `Administration/templates/unfold/helpers/app_list.html` | **neuf** — surcharge : le titre d'un domaine devient un lien |
| `Administration/templates/admin/index.html` | nettoyage du decor mort |
| `static/css/tibillet-admin.css` | `+` section 11 : cartes, blocs de domaine, interrupteur, repli |
| `Administration/templates/admin/dashboard_module_modal.html` | retrait de `hx-target`/`hx-swap`, qui cassaient la modale hors du tableau de bord |
| `Administration/templates/admin/partials/dashboard_beta_notice.html` | reecrit en classes : plus de style inline, plus de violet |
| `tests/pytest/test_admin_tableau_de_bord.py` | **neuf** — 21 tests |

Reutilises **sans y toucher** : `ConfigurationAdmin.module_toggle_modal` et
`module_toggle`, et `dashboard_module_modal.html`.

## Comment ca marche / How it works

### Une seule carte pour deux ecrans

`dashboard_module_card.html` sert au tableau de bord (en grille) ET a la page
de domaine (en liste). C'est la classe du conteneur qui change la taille, pas
le gabarit. Un module ajoute apparait donc aux deux endroits, sans double
saisie.

### L'interrupteur n'a pas bouge

Le POST de bascule repond `HX-Refresh: true` : il ne renvoie aucun fragment,
il recharge la page. Il est donc **page-agnostique** — il fonctionne
a l'identique depuis la page de domaine, sans une ligne de code en plus.

Les interverrouillages serveur sont evidemment conserves : desactiver la
monnaie locale pendant que la caisse tourne reste refuse, et activer la caisse
allume automatiquement la monnaie locale.

### Le repli des modules eteints

Deux details repris de la maquette, qui ont l'air anodins mais font tout :

- **toutes les cartes restent dans le DOM**, seule une classe change. C'est ce
  qui empeche la grille de sauter quand on ouvre le repli — le nombre de
  colonnes et la largeur des cartes ne bougent pas ;
- `scrollbar-gutter: stable` sur `html`, pour la meme raison a l'echelle de la
  page.

L'etat vit dans **Alpine**, deja charge par Unfold : aucun JS maison, aucun
aller-retour serveur. C'est une preference d'affichage, pas une donnee.

### Aucune decision dans les gabarits

Tout ce dont la carte a besoin est calcule dans `dashboard.py` :
`montre_interrupteur`, `allume`, `url_modale`, `testid_interrupteur`,
`lien_du_module`. Le gabarit se contente d'afficher. C'est la regle du projet,
et cela evite les conditions de template illisibles.

`lien_du_module` n'est pose que si le module a **vraiment** une entree dans la
sidebar : un module eteint n'en a pas, et une caisse en V1 non plus. Poser un
lien mort ferait une carte cliquable qui tombe sur une 404.

### La surcharge d'`app_list.html` — la seule concession

Unfold rend un titre de groupe en `<h2>` et **ne connait aucune cle `link`**.
Rendre « Lespass » cliquable dans le rail imposait donc de surcharger
`unfold/helpers/app_list.html`.

La copie est fidele : **une seule difference**, le `<h2>` du titre, qui devient
un `<a>` quand le groupe porte un `link`. Le chevron reste dedie au repli, et
un `x-on:click.stop` empeche le clic sur le mot de replier le groupe au
passage. Un groupe sans `link` s'affiche exactement comme avant.

> **A relire a chaque montee de version d'Unfold.** Si ce fichier devient
> penible a maintenir, le repli est simple : ajouter une entree
> « Vue d'ensemble » en tete de chaque groupe de domaine et supprimer la
> surcharge. Seul `_regrouper_sections_par_domaine()` serait a changer ; les
> deux vues, les gabarits et le CSS resteraient identiques.

## Ce qu'on repare au passage

- **`v1_online` est enfin affiche.** La carte de la caisse calculait deja, a
  chaque chargement, si le serveur LaBoutik V1 repond (health-check HTTP, cache
  60 s par lieu) — et ne le montrait nulle part. C'est maintenant une pastille
  en ligne / hors ligne. Un health-check en echec s'affiche « hors ligne », pas
  en erreur.
- **La section « Outils externes » disparait.** La newsletter et les reseaux
  sociaux sont de la communication publique : ils rejoignent le domaine
  Lespass, comme le reste. La maquette range tout par domaine.
- **Le decor mort d'`index.html`** est retire : `navigation`, `filters` et
  `kpi` n'etaient alimentes par personne (`dashboard_callback` n'en pose
  aucun), les composants rendaient donc du vide, et un long bloc commente
  laissait derriere lui trois `</div>` orphelins.
- **Plus aucun style inline** sur ces ecrans, ni les replis violets `#7c3aed`
  qui contredisaient le vert de marque.

## Deux subtilites de comptage

- Le total **ne compte que les modules reels**. Une carte « bientot
  disponible » (Postiz) n'a pas d'interrupteur : l'inclure afficherait
  « 4/6 » alors que seuls 5 modules existent, et laisserait croire qu'il reste
  deux choses a activer.
- La carte de la caisse ne porte pas de booleen mais un **etat a trois
  valeurs**. Elle compte comme allumee des que la V1 **ou** la V2 tourne.

## A tester / To test

### 1. Le tableau de bord

| Verification | Attendu |
|---|---|
| `/admin/` | 5 blocs de domaine, chacun avec icone, sous-titre et compteur |
| Modules eteints | masques par defaut |
| Clic sur « Découvrir plus de modules » | ils apparaissent, et **la grille ne saute pas** |
| Clic sur une carte allumee | ouvre la page du module |
| Clic sur une carte eteinte | ne fait rien |
| Carte « Réseaux sociaux » | grisee, **sans** interrupteur |
| Domaine sans aucun module actif | affiche « Aucun module activé ici » |

### 2. La page d'un domaine

| Verification | Attendu |
|---|---|
| Clic sur « Lespass » dans le rail | ouvre `/admin/domaine/lespass/` |
| Clic sur l'en-tete d'un domaine du tableau de bord | meme page |
| La page | en-tete, compteur, modules en **liste** (cartes plus larges) |
| `/admin/domaine/inconnu/` | **404**, sans casser l'admin |
| Replier un domaine avec le chevron | le clic sur le chevron ne doit **pas** naviguer |

### 3. La bascule d'un module

Depuis le tableau de bord **et** depuis une page de domaine : la modale
s'ouvre, la confirmation recharge la page, la sidebar se met a jour.

Cas particuliers a verifier :
- desactiver la monnaie locale pendant que la caisse tourne -> refuse, message ;
- activer la caisse -> la monnaie locale s'allume aussi, message.

### 4. Un lieu en LaBoutik V1

La carte de la caisse doit montrer « V1 active », **sans interrupteur**, avec
la pastille en ligne / hors ligne. Couper le serveur V1 : la pastille passe a
« hors ligne » et la page continue de s'afficher.

### 5. Tests automatiques

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_tableau_de_bord.py -v
docker exec lespass_django poetry run pytest tests/pytest/test_module_newsletter_activation.py tests/pytest/test_admin_page_de_module.py -v
```

**Deja verifie :** `manage.py check` propre ; 21 tests neufs au vert ; les deux
ecrans repondent en 200 et un domaine inconnu en 404 ; les cartes allumees
pointent vers la page de leur module et les eteintes vers rien ; la modale de
bascule repond toujours.

## Corrections apres le premier retour d'usage

### 1. L'interrupteur ne faisait rien sur la page d'un domaine

**Symptome :** activer ou desactiver un module depuis `/admin/domaine/lespass/`
ne produisait rien, avec un `htmx:targetError` dans la console.

**Cause :** le bouton de confirmation de la modale declarait
`hx-target="#dashboard-modules"`. Cet element n'existe QUE sur le tableau de
bord. htmx verifie la cible **avant** d'envoyer la requete : il levait donc
l'erreur et n'envoyait jamais le POST.

**Correctif :** retrait pur et simple de `hx-target` et `hx-swap`. Ils ne
servaient a rien — la vue repond `HX-Refresh: true` avec un corps vide, donc
rien n'est jamais echange. Ils ne faisaient que casser la modale partout
ailleurs que sur le tableau de bord.

La modale est desormais page-agnostique, comme le POST qu'elle declenche.

### 2. L'encart BETA se rangeait a cote du texte

**Symptome :** sur la page d'un domaine, au-dela de ~1440 px, le bandeau
« acces anticipe » de la carte Newsletter s'affichait a droite au lieu de
passer dessous.

**Cause :** la carte est un conteneur flex. L'encart en etait un enfant
direct : des que la carte etait assez large, il se rangeait sur la meme
ligne. Le tableau de bord ne le montrait pas, ses cartes y sont etroites.

**Correctif :** l'encart est enveloppe dans un `.tb-carte-beta` en
`flex-basis: 100%` avec un `order` qui le place en dernier — il passe donc
toujours a la ligne, quelle que soit la largeur.

**Au passage :** l'encart etait ecrit en **styles inline**, ce qui rendait sa
marge basse incorrigeable depuis la feuille du projet, et il portait le
**violet d'Unfold** (`rgba(124,58,237,…)`) qui contredisait le vert de marque.
Il est reecrit en classes. C'etait le dernier style inline de ces ecrans.

### 3. Le sous-menu d'un domaine restait ferme sur sa propre page

**Symptome :** en arrivant sur `/admin/domaine/lespass/`, le groupe « Lespass »
du rail etait replie — on ne voyait pas ou l'on se trouvait.

**Cause :** Unfold n'ouvre un groupe que si l'un de ses **liens** est actif.
Le lien du domaine est sur le titre, pas dans la liste : aucun item n'etait
donc actif.

**Correctif :** `_regrouper_sections_par_domaine` pose une cle `ouvert` en
comparant `request.path` au lien du domaine, et la surcharge d'`app_list.html`
la lit. La surcharge a donc maintenant **deux** differences avec l'original
d'Unfold, toutes deux documentees en tete du fichier.

Ces trois corrections sont couvertes par des tests. Le premier a ete verifie
contre le code bugue : il echoue bien dessus.

## Suites / Next steps

1. **La cascade d'apparition** des cartes eteintes (la maquette les fait
   entrer l'une apres l'autre, 40 ms d'ecart) n'est pas reprise : le repli
   est instantane. A ajouter si le geste parait sec a l'usage.
2. **Blog et Reseaux sociaux** restent a construire, cote Lespass.
