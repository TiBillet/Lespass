# FOUC en navigation HTMX : le CSS des blocs passe dans le `<head>` / FOUC on HTMX navigation: blocks CSS moves to the `<head>`

**Date :** 2026-07-21
**Migration :** Non

## Resume / Summary

**Quoi / What :** `tb-blocs.css` etait charge par un `<link>` place dans `{% block main %}`,
donc dans le `<body>`. Il est desormais charge par le `<head>` des deux shells (`classic` et
`faire_festival`).
/ `tb-blocs.css` was loaded by a `<link>` inside `{% block main %}`, i.e. in the `<body>`.
It is now loaded by the `<head>` of both shells (`classic` and `faire_festival`).

**Pourquoi / Why :** la navigation HTMX utilise `hx-target="body" hx-swap="innerHTML"`. Un
`<link>` pose dans le corps de la page est donc **retire du DOM a chaque swap**, et les styles
qu'il portait sont desappliques d'un coup. Le nouveau `<link>` arrive avec le contenu injecte,
le navigateur revalide le fichier (~25 ms, **meme quand il est en cache** — reponse `304`), et
pendant tout ce temps la page s'affiche **sans style**. Le symptome ressemble a un blink de
rechargement alors que la navigation HTMX, elle, fonctionne : c'est le CSS qui clignote, pas
la page.
/ HTMX navigation swaps the whole `<body>`, so a `<link>` placed there is REMOVED from the DOM
on every swap and its styles drop instantly. The new `<link>` arrives with the injected
content and the browser revalidates the file (~25 ms even when cached, a `304`), leaving the
page unstyled meanwhile. It looks like a reload blink, but it is the CSS flickering.

Le `<head>`, lui, n'est jamais swappe : la feuille y reste appliquee d'une page a l'autre.

### Ce qui avait conduit au placement d'origine

Le raisonnement initial etait exact sur son constat : le squelette `headless.html` (les
reponses HTMX) **n'a pas de `<head>`**, donc un asset declare dans `{% block extra_meta %}`
n'arrive jamais lors d'une navigation HTMX. La conclusion — poser le `<link>` dans le corps —
reglait bien ce point, mais introduisait le rechargement a chaque swap.

La bonne reponse est de charger la feuille **une fois pour toutes dans le shell**, qui n'est
rendu qu'au premier affichage et survit a toutes les navigations suivantes.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/classic/shell.html` | `<link>` vers `tb-blocs.css` ajoute au `<head>`, apres `tibillet.css` |
| `pages/templates/pages/classic/page.html` | `<link>` retire de `{% block main %}` |
| `pages/templates/pages/faire_festival/shell.html` | `<link>` ajoute au `<head>`, **avant** `faire_festival.css` |
| `pages/templates/pages/faire_festival/page.html` | `<link>` retire de `{% block main %}` |

**Le skin `faire_festival` a son propre `shell.html`** : il ne beneficie pas de celui du socle
`classic`, il fallait donc l'y ajouter separement. **L'ordre y est significatif** —
`tb-blocs.css` doit rester AVANT `faire_festival.css`, qui le surcharge. L'inverse ecraserait
l'habillage du skin par le socle.

**Cout assume :** 77 Ko bruts / **24 Ko gzippes** charges une fois sur toutes les pages, y
compris celles sans bloc (agenda, adhesions). C'est le prix d'une navigation sans repeinte.

**`sommaire_actif.js` n'est pas deplace** : un script ne provoque pas de FOUC, et il doit
s'executer apres chaque swap pour reattacher ses observateurs.

**Reste a traiter (non fait ici) :** le meme placement existe pour Leaflet dans
`vues/reseau.html` et `partials/evenement_geoloc.html`. L'effet y est moins visible — ces vues
affichent une carte qui se charge de toute facon en asynchrone.

### Mesure / Measurement

Apres navigation HTMX reelle dans le navigateur (`PerformanceObserver` sur les ressources) :

| | Avant | Apres |
|---|---|---|
| Feuilles rechargees apres le swap | `tb-blocs.css` (~25 ms, `304`) | **aucune** |
| `<link rel="stylesheet">` restes dans le `<body>` | 1 | **0** |
| `tb-blocs.css` encore appliquee apres le swap | non, le temps de la revalidation | **oui, en continu** |

---

## Comment tester (a la main) / Manual test

### Test 1 — plus de repeinte sans style

1. Ouvrir un site de contenu (`https://lespass.tibillet.localhost/`).
2. Naviguer entre plusieurs pages de blocs (Accueil, Journal, A propos...).
3. Attendu : le contenu apparait **deja mis en forme**. Aucun instant ou les blocs
   s'affichent nus (textes bruts empiles, logos geants, listes sans puces).
4. Sur une connexion lente, forcer le defaut avec l'onglet Reseau > throttling « Slow 3G » :
   avant le correctif, la page nue restait visible plusieurs centaines de millisecondes.

### Test 2 — verification instrumentee (console du navigateur)

```js
// Aucune feuille de style ne doit etre (re)chargee lors d'une navigation HTMX.
new PerformanceObserver(l => l.getEntries()
    .filter(e => e.initiatorType === 'link' || e.initiatorType === 'css')
    .forEach(e => console.log('RECHARGE :', e.name.split('/').pop(), Math.round(e.duration) + 'ms'))
).observe({type: 'resource', buffered: false});
```
Puis naviguer. Attendu : **aucune ligne**. Une ligne `RECHARGE : tb-blocs.css` signifie qu'un
`<link>` est revenu dans le corps d'une page.

Verifier aussi qu'il n'en reste aucun :
```js
document.body.querySelectorAll('link[rel="stylesheet"]').length  // doit valoir 0
```

### Test 3 — le skin `faire_festival` n'a pas perdu son habillage (LE test qui compte)

L'ordre des feuilles a change dans son `<head>` : c'est ici qu'une regression se verrait.

1. Basculer un tenant sur le skin `faire_festival` (`ConfigurationSite.skin`).
2. Ouvrir une page de contenu et comparer avec l'apparence attendue : le theme brutaliste
   jaune/bleu doit primer sur le socle.
3. Attendu : identique a avant. Si des blocs reviennent a l'apparence `classic`, c'est que
   `tb-blocs.css` est passe APRES `faire_festival.css` dans le `<head>`.
4. Verifier egalement les blocs que le skin ne surcharge pas : ils doivent rester habilles par
   le socle, jamais nus.

### Tests automatiques / Automated tests

Aucun test pytest ne couvre ce comportement : il est **entierement navigateur** (ordre de
chargement des feuilles, swap HTMX). Un test Playwright reprenant le `PerformanceObserver` du
test 2 serait le bon emplacement — non ecrit a ce jour.
