# Overlay de chargement : le délai était court-circuité par 4 formulaires / Loading overlay: the delay was bypassed by 4 forms

**Date :** 2026-07-21
**Migration :** Non

## Resume / Summary

**Quoi / What :** l'overlay de chargement (`#tibillet-spinner`) s'affichait ~3 ms apres le
debut de **toute** requete htmx, au lieu d'attendre le delai prevu. Quatre formulaires le
declenchaient sans temporisation ; leurs attributs sont retires. Le seuil reste a **400 ms**.
/ The loading overlay showed ~3 ms after the start of **any** htmx request instead of
waiting for the delay. Four forms triggered it with no debounce; their attributes are
removed. The threshold stays at **400 ms**.

**Pourquoi / Why :** `loading-states.js` cherche le delai avec
`htmx.closest(sourceElt, '[data-loading-delay]')` et, **quand il n'en trouve pas, appelle le
callback immediatement** (aucune temporisation). Les formulaires de connexion, contact,
reservation et adhesion portaient `data-loading-class="active"` +
`data-loading-target="#tibillet-spinner"` **sans `data-loading-delay`** : ils allumaient donc
l'overlay global instantanement.

Aggravant : l'extension n'a aucun scope cote site public (aucun `data-loading-states`), elle
balaie tout `document.body` a **chaque** requete htmx. Comme le shell embarque les panneaux
connexion et contact sur toutes les pages, n'importe quelle navigation allumait l'overlay via
des formulaires qui n'avaient rien a voir avec elle.
/ `loading-states.js` calls the callback immediately when no `data-loading-delay` is found.
Four forms declared `data-loading-class` without a delay, and the extension has no scope on
the public site (it scans all of `document.body` on every htmx request) — while the shell
embeds the login and contact panels on every page.

### Mesure / Measurement

Instrumentation d'un `MutationObserver` sur la classe de `#tibillet-spinner`, navigation
reelle dans le navigateur :

| | Requete | Overlay |
|---|---|---|
| Avant | 71 ms | **VISIBLE a +3 ms** |
| Apres | 79 ms | jamais affiche |
| Apres, seuil force a 10 ms | 96 ms | VISIBLE a +12 ms, cache a +125 ms |

La troisieme ligne verifie que le mecanisme n'a pas ete desactive : c'est bien le SEUIL qui
decide desormais, pas un declencheur parasite.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/templates/commun/formulaires/login.html` | retrait de `data-loading-target` + `data-loading-class` |
| `BaseBillet/templates/commun/formulaires/contact.html` | idem |
| `BaseBillet/templates/commun/formulaires/reservation.html` | idem |
| `BaseBillet/templates/commun/adhesion/form.html` | idem |
| `BaseBillet/templates/commun/loading.html` | delai par defaut aligne sur 400, + commentaire de garde sur le declencheur unique |
| `BaseBillet/views.py` | commentaire sur `loading_delay` (valeur inchangee : 400) |
| `TECH_DOC/SKILLS/djc/SKILL.md` | section « HTMX Loading Overlay » reecrite |

**Pourquoi le seuil RESTE a 400 ms :** c'est un seuil de **visibilite**, pas de confort. Une
page publique doit repondre sous 400 ms ; un overlay qui apparait signale donc une lenteur
reelle, a corriger. Le monter pour « moins voir le spinner » masquerait le symptome sans
traiter la cause. En production, la home de codecommun.coop repond aujourd'hui en 541 ms
(`urt=0.542`) : l'overlay y apparait, et c'est le comportement voulu tant que ce temps n'a
pas baisse.

**Non touche :** `#token-table-loader` dans `fonctionnel/compte/balance.html`. C'est un
spinner LOCAL correct — il se cible lui-meme et porte son propre delai.

**Correction du skill `djc` :** il portait la regle « ne jamais mettre `data-loading-target`
sur un conteneur qui contient des formulaires, l'overlay se declencherait aussi sur les
soumissions ». Elle est fausse a deux titres : l'overlay se declenche de toute facon sur
toutes les requetes (scope = `document.body`), et `data-loading-target` seul ne declenche
rien — c'est un redirecteur, il n'agit que sur un element portant deja un attribut actif.

---

## Comment tester (a la main) / Manual test

### Test 1 — la navigation n'affiche plus de spinner parasite

1. Ouvrir `https://lespass.tibillet.localhost/`.
2. Naviguer entre Accueil, Journal, Agenda, une page de contenu.
3. Attendu : **aucun voile gris / flou** entre deux pages. Le contenu change, c'est tout.
4. Avant le correctif : un flash de flou a chaque clic, meme sur une page rapide.

### Test 2 — l'overlay sort toujours quand c'est lent (LE test qui compte)

C'est ici que le correctif pourrait avoir trop enleve. Chaque formulaire touche doit encore
voiler l'ecran quand son traitement depasse 400 ms :

1. **Connexion** — panneau de connexion, saisir un email, valider. L'envoi du mail de
   connexion prend plus de 400 ms : l'overlay doit apparaitre.
2. **Contact** — panneau contact, envoyer un message (envoi d'email).
3. **Reservation** — reserver une place sur un evenement payant (aller-retour Stripe).
4. **Adhesion** — souscrire une adhesion payante.

Attendu dans les 4 cas : le voile + le spinner apparaissent pendant l'attente, puis
disparaissent. Si l'un d'eux ne montre plus rien alors que l'attente est longue, c'est une
regression de ce chantier.

Le bouton de soumission, lui, doit se desactiver **immediatement** au clic (anti double-clic) :
c'est `data-loading-disable`, volontairement sans delai, et il n'a pas ete touche.

### Test 3 — verification instrumentee (console du navigateur)

Un overlay qui flashe 50 ms se voit mal a l'oeil. Coller dans la console :

```js
const sp = document.querySelector('#tibillet-spinner');
const t0 = performance.now();
new MutationObserver(() => console.log(
    Math.round(performance.now() - t0) + 'ms',
    sp.classList.contains('active') ? 'VISIBLE' : 'cache'
)).observe(sp, {attributes: true, attributeFilter: ['class']});
```

Puis naviguer. Attendu : **aucune ligne** sur une navigation rapide. Si une ligne `VISIBLE`
apparait quelques millisecondes apres le clic, c'est qu'un element porte a nouveau
`data-loading-class` sans `data-loading-delay`.

Pour retrouver le coupable le cas echeant :

```js
Array.from(document.querySelectorAll('[data-loading-class],[data-loading]'))
  .filter(el => !el.closest('[data-loading-delay]'))
  .map(el => el.tagName + (el.id ? '#' + el.id : ''));
```
Tout ce qui sort de cette liste, hormis les boutons en `data-loading-disable`, declenche sans
delai.

### Tests automatiques / Automated tests

Aucun test pytest ne couvre ce comportement : il est **entierement navigateur** (extension
htmx + CSS). Les tests pytest n'executent pas de JavaScript. Un test Playwright reprenant le
`MutationObserver` du test 3 serait le bon emplacement — non ecrit a ce jour.
