# Correctif : la caisse n'etait plus accessible depuis l'admin / Fix: no way into the POS from the admin

**Date :** 2026-09-08
**Migration :** Non

## Resume / Summary

**Quoi / What :** la carte « Caisse & Restaurant » du tableau de bord a perdu
ses liens d'ouverture. On ne pouvait plus atteindre l'interface LaBoutik
depuis l'admin.
/ The POS card lost its opening links: no way into the LaBoutik interface
from the admin any more.

**Pourquoi / Why :** **regression introduite au commit `35b34a23`**, en
reecrivant `dashboard_module_card.html`. L'ancienne carte de la caisse etait
rendue en ligne dans `dashboard.html` et portait trois elements que la carte
generique a perdus :

| Element perdu | Etat concerne | `data-testid` |
|---|---|---|
| Lien **« Open POS »** vers `/laboutik/caisse/` | `v2_active` | `dashboard-card-pos-open-link` |
| Lien **« Ouvrir LaBoutik V1 »** + la note de migration | `v1_active` | `dashboard-card-pos-v1-link` |
| Badge « Enable LaBoutik V2 — BETA » | `inactive` | `dashboard-card-pos-beta-badge` |

Le premier est celui qui a ete signale. **Le second etait la meme
regression** : un lieu reste en V1 n'avait plus aucun acces a son interface.
Les deux sont restaures.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | `+ _poser_le_lien_d_ouverture()` ; la carte POS porte `lien_externe`, `libelle_externe`, `testid_externe`, `externe_nouvel_onglet` |
| `Administration/templates/admin/partials/dashboard_module_card.html` | `+` le lien d'ouverture et la note de migration V1 |
| `static/css/tibillet-admin.css` | `+ .tb-carte-ouvrir`, `+ .tb-carte-note` |
| `tests/pytest/test_admin_tableau_de_bord.py` | `+ 4` tests, `+` fixture `lieu_avec_admin` (39 au total) |

## Ce qui a ete fait

### Rien a recalculer

Le contexte fournissait deja tout — seul l'affichage manquait :
`v2_open_url` (`/laboutik/caisse/`, depuis `MODULE_FIELDS`), `v1_url` (le
`server_cashless` du lieu) et `link_label`.

La decision se prend **en Python**, comme le reste de la carte :

| Etat | Lien | Libelle | Onglet |
|---|---|---|---|
| `v2_active` | `/laboutik/caisse/` | « Open POS » | le meme |
| `v1_active` | le `server_cashless` du lieu | « Ouvrir LaBoutik V1 » | **nouveau** (le serveur est ailleurs) |
| `inactive` | aucun | — | — |

**Aucun lien quand la caisse est eteinte** : `HasLaBoutikTerminalAccess`
refuse toute route POS dans ce cas, meme a un admin. Un lien menerait droit
a un 403.

### Ou le lien est place, et pourquoi

Dans `.tb-carte-etat`, a cote de l'interrupteur. **C'est le seul endroit
possible** : le corps de la carte est deja un `<a>` vers la page du module,
et deux liens ne s'imbriquent pas. Verifie sur la page rendue : aucun `<a>`
imbrique.

### Les libelles n'ont pas change

Repris de `MODULE_FIELDS` et des `msgid` existants : **aucune chaine
nouvelle, donc pas de `makemessages` a lancer**.

À signaler : le `msgid "Open POS"` a un **`msgstr` vide** dans `locale/fr`.
Le bouton s'affichait donc deja en anglais avant la regression. Le restaurer
a l'identique le laisse en anglais — le traduire est un point i18n distinct,
de la meme famille que les 59 `verbose_name` manquants deja recenses.

## Qui peut ouvrir la caisse

`HasLaBoutikTerminalAccess` accepte deux chemins : un **terminal appaire**
(TermUser au role LaBoutik lie a ce lieu), ou une **session d'admin du lieu**.
Un superadmin qui n'administre pas ce lieu recoit un 403 — c'est voulu.

Verifie : `/laboutik/caisse/` repond **200** pour un admin du lieu.

## Le test qui manquait

C'est lui qui aurait attrape la regression. Quatre tests ajoutes :

- un lieu en **V2** affiche le lien, et **la page repond** — un lien mort
  passerait un simple test de presence ;
- le lien est aussi sur la **page du domaine** (la carte est partagee) ;
- les **trois etats** produisent le bon lien, ou aucun ;
- un lieu en **V1** garde son acces.

**Verifie contre le code bugue** : les deux tests de rendu echouent bien
dessus.

### Un piege de fixture, corrige

Le premier essai reutilisait la fixture du superadmin, qui rend le **premier
lieu ayant un superadmin** — pas forcement un lieu ayant un **admin de lieu**.
Les deux tests passaient alors en « skip » sans rien verifier. La fixture
`lieu_avec_admin` cherche desormais un lieu qui a vraiment un admin.

## A tester / To test

| Verification | Attendu |
|---|---|
| `/admin/`, carte « Caisse & Restaurant » | le lien d'ouverture a cote de l'interrupteur |
| `/admin/domaine/laboutik/` | le meme lien |
| Clic sur le lien | ouvre l'interface de caisse |
| Clic sur le **corps** de la carte | ouvre la page du module — les deux cibles ne doivent pas se marcher dessus |
| Lieu en V1 | lien « Ouvrir LaBoutik V1 », dans un **nouvel onglet**, + la note de migration |
| Caisse eteinte | **aucun** lien |

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_tableau_de_bord.py -v
```

## Releve au passage — pas fait

`MODULE_FIELDS["module_tireuse"]` declare `link_url = /controlvanne/kiosk/` et
`link_label = "Open kiosk"` depuis toujours — **et ils n'ont jamais ete
rendus**, meme avant la reecriture. L'URL repond 200.

Ce n'est pas une regression, et ce n'etait pas la demande : rien n'est fait.
Le mecanisme mis en place ici permettrait de l'afficher en une ligne.
