# Fixes HTMX (session débug 2026-07-05) + middleware cache prod

## Ce qui a été fait

### Modifications
| Fichier | Changement |
|---|---|
| `pages/classic/page.html` | `tb-blocs.css` chargé dans `main` (plus dans `extra_meta`, perdu en HTMX) |
| `BaseBillet/views.py` | ordre navbar (pages → réseau/crowd → agenda → adhésions), `slugs_pages_publiees` dans `index()`, `MyAccount.dispatch` → `HX-Redirect /?login=1` si session expirée sous HTMX, suppression des vues mortes `infos_pratiques`/`le_faire_festival` |
| `crowds/views.py` | pk invalide sous HTMX → `HX-Redirect /contrib` |
| `pages/faire_festival/headless.html` | bloc `offcanvas_globaux` (panneaux contact + connexion, absents avant → boutons morts après swap) |
| `fonctionnel/event_wizard/_base.html` | `wizard.css` déplacé d'`extra_meta` vers `main` |
| `BaseBillet/middleware.py` (nouveau) + `settings.py` | `Vary: HX-Request` partout + `Cache-Control` (`no-cache` public, `private, no-store` connecté) |
| `pages/classic/shell.html` + `ff/shell.html` | meta `htmx-config` : `historyCacheSize: 0`, `refreshOnHistoryMiss: true` |
| `pages/faire_festival/vues/accueil.html` | boutons Infos pratiques / Le Faire Festival conditionnés aux pages CMS publiées |
| `tests/pytest/test_pages.py` | `nombre_max=32000` (test déterministe face à la base dev vivante) |

## Tests à réaliser (mainteneur)

### Test 1 : le bug d'origine (la-fourmiliere)
1. Ouvrir `/event/` (chargement complet), puis clic navbar « La Fourmilière ».
2. Attendu : page CMS entièrement stylée (blocs hero/carte avec CSS), panneaux
   contact/connexion fonctionnels. Vérifié en session via Chrome.

### Test 2 : ordre navbar
Sur chaque tenant : pages CMS d'abord, puis Réseau/Contribuez, puis
**Agenda, Adhésions, Aide et contact** en fin de menu (2 skins).

### Test 3 : en-têtes cache (curl)
```bash
curl -skI https://lespass.tibillet.localhost/event/ | grep -iE "vary|cache-control"
# → vary contient HX-Request ; cache-control: no-cache
# connecté (navigateur, DevTools onglet Network sur /my_account/) :
# → cache-control: private, no-store
```

### Test 4 : session expirée pendant navigation HTMX
Connecté sur /my_account/, supprimer le cookie de session, cliquer un onglet
du compte → vraie navigation vers `/` avec panneau de connexion ouvert
(avant : la home se swappait DANS l'onglet).

### Test 5 : bouton retour après déploiement
Naviguer 2-3 pages en HTMX, puis « retour » → chaque retour refait une vraie
requête (historyCacheSize 0) ; pas de restauration d'un vieux DOM.

### Test 6 : skin ff — panneaux après swap
Sur chantefrein : naviguer via navbar (swap HTMX), puis ouvrir Contact et
Connexion → les 2 panneaux s'ouvrent (avant : ids absents du fragment).

## Compatibilité
- Le middleware ne touche que le HTML sans `Cache-Control` déjà posé ; les
  API JSON ne sont pas affectées.
- `no-cache` = comportement navigateur identique à avant, mais contractuel.
- Restent documentés non corrigés : 404/500 muets sous HTMX, vues ff qui
  étendent shell.html en dur, `#paginator` dupliqué en scroll infini.
