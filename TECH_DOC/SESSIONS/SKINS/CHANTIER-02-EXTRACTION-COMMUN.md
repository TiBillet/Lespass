# CHANTIER-02 — Extraction du `commun/` (templates + statics + offcanvas)

**Statut :** SPEC à valider (2026-07-03). Aucun code.
**Objectif :** matérialiser les décisions P1-P4 — tout ce qui est partagé entre les
skins déménage vers `commun/` (templates) et `static/commun/` (statics), le pattern
offcanvas est unifié. **Zéro changement visible.** C'est le point dur du plan
(60-70 % du risque) : on avance par lots, chaque lot est vérifié avant le suivant.

## Principe de sécurité (hérité du CHANTIER-01)

- Snapshots curl normalisés avant/après CHAQUE lot, sur les 2 skins
  (lespass=reunion, chantefrein=faire_festival — dispo d'office depuis le fix seed).
- Lots A, B, C1 : le HTML de sortie doit être **identique au bit près** (modulo la
  substitution de chemins statics au lot A, filtrée dans le diff).
- Lot C2 (déplacement DOM) : critère = **iso-visuel** (vérif Chrome sur
  `https://lespass.tibillet.localhost/` et chantefrein) + E2E complets.
- Les **ids** des offcanvas et de leurs corps HTMX ne changent JAMAIS (contrat).
- Après chaque lot : `manage.py check`, pytest pages + gabarit_skin. E2E complets
  en fin de chantier.

---

## Lot A — Statics communs → `BaseBillet/static/commun/`

### A.1 Fichiers à déplacer (structure préservée : les CSS référencent
`../font/…` et `motif/*.svg` en relatif — css/ et font/ déménagent ensemble)

```
static/reunion/css/bootstrap.min.5.3.3.css      → static/commun/css/
static/reunion/css/bootstrap-icons.min.css      → static/commun/css/
static/reunion/css/vars.css                     → static/commun/css/
static/reunion/css/tibillet.css                 → static/commun/css/
static/reunion/css/swal.css                     → static/commun/css/
static/reunion/css/motif/                       → static/commun/css/motif/
static/reunion/font/                            → static/commun/font/   (4 familles)
static/reunion/js/bootstrap.bundle.min.5.3.3.js → static/commun/js/
static/reunion/js/sweetalert2@11.js             → static/commun/js/
static/reunion/js/theme-switcher.mjs            → static/commun/js/
static/reunion/js/language-switcher.mjs         → static/commun/js/
static/reunion/js/membership-form.mjs           → static/commun/js/
static/reunion/js/bs-counter.mjs                → static/commun/js/
static/reunion/img/favicon.png                  → static/commun/img/
static/reunion/img/france_2030.png              → static/commun/img/
```

**Restent dans `static/reunion/`** (spécifiques) : `js/qr-scanner*`, `js/qrcode.min.js`,
`js/booking-calculator.mjs`, `js/form-spinner.mjs`, `js/htmx.min.1.9.12.js`
(⚠ vérifier s'il est encore référencé — les shells chargent `mvt_htmx/js/htmx…` ;
si orphelin, le signaler, ne pas supprimer), `leaflet/`, `media/`.

### A.2 Références à mettre à jour
Ré-inventorier À L'EXÉCUTION (la liste bouge) : `rg "static 'reunion/" -t html` et
`rg 'static "reunion/' -t html`. Sites connus : `pages/classic/shell.html` (~12 réfs),
`pages/faire_festival/shell.html` (~15 réfs), navbars/footers des 2 skins,
`pages/classic/headless.html`, vues diverses. ⚠ Chercher AUSSI dans les `.mjs`/`.js`
(imports croisés) et les templates emails (aucun attendu, vérifier).

### A.3 Vérification
`collectstatic`, snapshots (diff filtré : seules les substitutions
`static/reunion/ → static/commun/` sont tolérées), vérif visuelle Chrome des 2 skins
(règle CSS-extraction du skill : toujours vérifier visuellement après un move CSS),
onglet Réseau sans 404.

---

## Lot B — Templates partagés → `BaseBillet/templates/commun/`

### B.1 Fichiers à déplacer (extraction pure, contenu inchangé)
```
reunion/forms/contact.html                    → commun/formulaires/contact.html
reunion/forms/login.html                      → commun/formulaires/login.html
reunion/partials/toasts.html                  → commun/toasts.html
reunion/loading.html                          → commun/loading.html
reunion/views/event/partial/booking_form.html → commun/formulaires/reservation.html
```
Anciens fichiers **supprimés** après bascule de toutes les références (pas de
redirection : ces chemins ne sont jamais étendus, seulement inclus).

### B.2 Références à mettre à jour (ré-inventorier : `rg "reunion/forms|reunion/partials/toasts|reunion/loading|booking_form" -t html`)
- `pages/classic/shell.html` + `pages/classic/headless.html` (toasts, loading)
- `pages/faire_festival/shell.html` + `headless.html` (toasts, loading, contact, login)
- `reunion/partials/navbar.html` (contact, login — corps des offcanvas)
- `reunion/views/event/partial/booking.html` (booking_form)
- `faire_festival/views/event/retrieve.html` (booking_form)
- `reunion/partials/picture.html` est référencé par ff (vérifier : s'il est bien
  partagé → `commun/partials/picture.html`, sinon le laisser)

### B.3 Vérification
Snapshots strictement identiques (aucune tolérance), check, pytest.
**Contrôle d'autonomie** : `rg "reunion/" BaseBillet/templates/faire_festival/
pages/templates/pages/faire_festival/` doit tendre vers 0 (il restera les
statics si lot A pas encore fait — d'où l'ordre A puis B).

---

## Lot C1 — Extraction des offcanvas → `commun/offcanvas/` (sans bouger le DOM)

Chaque définition d'offcanvas sort de son template hôte vers un include, **inséré
au même endroit** → sortie HTML identique au bit près.

| Include cible | id (INCHANGÉ) | Extrait de |
|---|---|---|
| `commun/offcanvas/contact.html` | `#contactPanel` | `reunion/partials/navbar.html:104-122` ET `pages/faire_festival/shell.html:201-224` |
| `commun/offcanvas/connexion.html` | `#loginPanel` | `reunion/partials/navbar.html:124-135` ET `pages/faire_festival/shell.html:226-234` |
| `commun/offcanvas/adhesion_tunnel.html` | `#subscribePanel` (+corps `#offcanvas-membership`) | `reunion/views/membership/list.html:34-…` ET `faire_festival/views/membership/list.html:14-…` |
| `commun/offcanvas/reservation.html` | `#bookingPanel` | `reunion/views/event/partial/booking.html:75-…` ET `faire_festival/views/event/retrieve.html:111-…` |
| `commun/offcanvas/filtres_agenda.html` | `#filterPanel` | `reunion/views/event/partial/search.html:59-…` (reunion seul) |

⚠ **Les définitions doublées (reunion vs ff) ne sont pas toujours identiques**
(commentaires, classes, JS d'auto-ouverture). À l'exécution : diff des deux
versions, unifier sur UNE (a priori la reunion, look par défaut), puis vérif
visuelle du skin qui a « perdu » sa variante. Si une différence est réellement
porteuse (ex : bloc `{% block offcanvas %}` ff), la conserver dans l'hôte, pas
dans l'include.

`#ticketPanel` et `#refundPanel` (pages compte, reunion seul, non skinnables) :
**hors périmètre** — ils suivront les pages fonctionnelles au CHANTIER-06.

### C1 bonus — CSS largeur factorisé
Classe `.offcanvas-tunnel` dans `tibillet.css`
(`--bs-offcanvas-width: 100vw` + media query `800px`), posée sur
`#subscribePanel` et `#bookingPanel` ; suppression des 4 blocs `<style>` inline
dupliqués. (Diff HTML attendu : attribut class + disparition des `<style>` —
vérif visuelle des 2 tunnels ouverts, largeur desktop 800px / mobile 100vw.)

---

## Lot C2 — Blocs offcanvas dans les shells (déplacement DOM, iso-visuel)

1. `pages/classic/shell.html` : ajouter en fin de `<body>` (avant scripts) :
   ```django
   {% block offcanvas_globaux %}
     {% include "commun/offcanvas/contact.html" %}
     {% include "commun/offcanvas/connexion.html" %}
   {% endblock %}
   {% block offcanvas %}{% endblock %}
   ```
   et RETIRER les includes contact/login du partial navbar reunion (qui ne garde
   que les boutons déclencheurs — alignement sur le pattern ff).
2. `pages/classic/headless.html` : ajouter `{% block offcanvas %}{% endblock %}`
   (parité avec ff/headless).
3. `pages/faire_festival/shell.html` : remplacer ses définitions inline par les
   mêmes includes dans `offcanvas_globaux` (son `{% block offcanvas %}` existe déjà).
4. Garder le JS d'auto-ouverture du loginPanel (navbar reunion:137-161) fonctionnel —
   il cible `#loginPanel` par id, le déplacement DOM ne le casse pas (à retester).

**Critère :** iso-visuel (pas iso-bytes). Vérifs : ouverture contact/login depuis
navbar ET footer des 2 skins, auto-ouverture login (`?openloginPanel` / flux
volunteers), E2E complets, axe accessibilité (aria-controls intacts).

---

## Ordre, périmètre, livrables

- Ordre : **A → B → C1 → C2**, un lot = un commit mainteneur possible.
- Chaque lot laisse le dépôt 100 % fonctionnel (pas d'état intermédiaire cassé).
- Hors périmètre : vues `views/*` (CHANTIERS 03-05), pages fonctionnelles et
  `#ticketPanel`/`#refundPanel` (06), emails (06), suppression arbo reunion (08),
  correction du « HTMX = page complète » en ff.
- Livrables : CHANGELOG (1 entrée), fiche A TESTER (parcours offcanvas des 2 skins),
  mise à jour ETAT-REPRISE, test pytest complémentaire si pertinent
  (ex : `test_offcanvas_includes_presents_dans_les_shells`).

## Risques identifiés
1. Les deux variantes d'un même offcanvas divergent subtilement (cf. C1 ⚠) —
   mitigation : diff + choix explicite + vérif visuelle.
2. Une référence static oubliée hors templates (JS import, CSS url(), email) —
   mitigation : rg multi-extensions + onglet Réseau sans 404 sur les 2 skins.
3. Le déplacement DOM (C2) change l'ordre de tabulation clavier autour des panels —
   mitigation : test clavier rapide (tab jusqu'au bouton login, ouverture, focus).
4. `collectstatic` garde les anciens fichiers dans `www/static` (copie obsolète) —
   mitigation : `collectstatic --clear` en fin de lot A (dev uniquement).
