# Depliage anime des groupes du rail / Animated sidebar group expansion

**Date :** 2026-09-08
**Migration :** Non

## Resume / Summary

**Quoi / What :** cliquer un domaine dans le rail deplie ses modules **en
douceur** au lieu de les faire surgir d'un coup.
/ Expanding a domain in the sidebar now animates instead of popping.

**Pourquoi / Why :** le chevron, lui, s'animait **deja** — Unfold lui met
`transition-transform` et bascule `rotate-90`. On avait donc une fleche qui
pivotait en douceur au-dessus d'une liste qui surgissait. C'est ce decalage
qu'on ressentait.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/templates/unfold/helpers/app_list.html` | le sous-menu est enveloppe dans un conteneur qui anime sa hauteur ; `x-show` retire |
| `static/css/tibillet-admin.css` | `+ .tb-sousmenu`, `+ .tb-sousmenu-ouvert` ; les deux rejoignent le bloc `prefers-reduced-motion` |
| `tests/pytest/test_admin_tableau_de_bord.py` | `+ 4` tests de structure (43 au total) |

## Pourquoi en CSS et pas en JavaScript

`x-show` bascule `display`, et **`display` ne s'anime pas** : c'est la cause
directe du surgissement.

Alpine propose `x-collapse` pour exactement ce cas — mais **Unfold ne charge
pas ce plugin**. Il charge `anchor`, `persist`, `sort` et `resize` ; le
fichier `alpine.collapse.js` n'est meme pas sur le disque. Le vendorer pour
une animation ne se justifiait pas.

On anime donc `grid-template-rows` de `0fr` a `1fr` — la seule facon d'animer
une hauteur inconnue sans JavaScript, et c'est exactement la technique de la
maquette (`.submod-slot` dans son `style.css`).

**Aucun fichier forke en plus** : `app_list.html` etait deja surcharge, pour
le titre de domaine cliquable. La surcharge a donc maintenant trois
differences avec l'original, toutes documentees en tete du fichier.

## Trois details qui ne sont pas des details

### 1. Pas d'animation au chargement de page

Le groupe du module courant s'ouvre tout seul. Si la classe etait posee par
Alpine **apres** le premier rendu, le rail s'animerait **a chaque
navigation** — insupportable.

La classe est donc posee **cote serveur**, avec la meme condition que celle
qui alimente `navigationOpen` (`has_active or group.ouvert`). Alpine ne fait
que prendre la suite au premier clic.

Verifie sur les quatre types de page : sur une page de module et sur une page
de domaine, le groupe concerne est deja deplie dans le HTML rendu ; sur le
tableau de bord, tout est replie.

### 2. Les groupes non repliables n'ont pas de variable Alpine

`Tableau de bord`, `Configuration generale`, `Ventes & comptabilite` et
`Configuration racine` ont `collapsible: False` : Unfold ne leur met **pas**
de `x-data`, donc **pas** de `navigationOpen`. Y poser une liaison leverait
une erreur Alpine dans la console a chaque page. Ils recoivent la classe
ouverte en dur et aucune liaison.

### 3. Les liens d'un groupe replie ne doivent pas etre atteignables au clavier

Un conteneur de hauteur nulle laisse ses liens focusables : un utilisateur au
clavier tabulerait dans des liens invisibles. Le sous-menu passe donc aussi
en `visibility: hidden`.

`visibility` se transitionne de facon **discrete** — il passe a `visible` des
le debut de l'ouverture, et a `hidden` seulement a la fin de la fermeture.
C'est exactement le comportement voulu, et c'est pour cela qu'il figure dans
la transition plutot que d'etre bascule brutalement.

## A tester / To test

Il n'y a **rien a tester automatiquement** sur l'animation elle-meme : aucun
test Python ne constate une transition CSS. Les tests ajoutes gardent la
**structure** — `x-show` absent, liens toujours rendus, groupes non
repliables sans liaison Alpine, et etat initial pose cote serveur.

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_tableau_de_bord.py -v
```

**Visuel**, en clair et en sombre :

| Verification | Attendu |
|---|---|
| Clic sur un domaine | les modules se deplient en douceur, en meme temps que le chevron |
| Re-clic | ils se replient de la meme facon |
| **Chargement d'une page** | le rail est deja dans son etat final, **aucune animation** |
| Groupes non repliables | toujours ouverts, **aucune erreur Alpine** en console |
| Tabulation au clavier | Tab ne descend **pas** dans un groupe replie |
| Reglage systeme « moins d'animations » | depliage instantane |

## Releve au passage — pas corrige

Sur une **changelist** (`/admin/BaseBillet/event/`), le rail n'indique pas ou
l'on se trouve : aucun lien surligne, aucun groupe deplie.

C'est une consequence de l'architecture Domaines -> Modules : les entrees du
rail sont des **pages de module**, et l'URL d'une changelist ne correspond a
aucune d'elles. Unfold ne deplie un groupe que si l'un de ses liens est actif.

Ce n'est pas lie a cette animation, et la corriger est un choix de conception
(faut-il surligner le module quand on est sur l'une de ses pages ?). Rien
n'est fait.
