# Session 35 — Audit front HTMX et fuite NfcReader

> Date : 2026-04-27
> Branche : `V2`
> Auteur : audit assisté Claude Code (lecture du code + reproduction directe via Chrome instrumenté)
> Statut : audit terminé, correctif **non implémenté**

---

## 1. Contexte et objectif

Le mainteneur a observé un comportement répété sur la caisse LaBoutik :

> « Souvent un appel fonctionne, mais le second non. »

Symptôme typique : 1er paiement cashless OK, 2ème paiement cashless KO ou aléatoire.
Crainte d'un problème de **re-hydratation HTMX** lié à l'archi modulaire (Cotton + partials inclus + scripts qui « sautent »).

Ce document :
- résume l'archi front actuelle (ce qui est sain)
- liste les bugs réels détectés et reproduits
- explique **pourquoi** le 2ème appel cashless échoue
- propose un correctif minimal (~15 lignes) sans refactor

**Aucun code n'a été modifié.** Le but est de dégager le diagnostic avant d'attaquer le fix.

---

## 2. Architecture front — vue d'ensemble

### 2.1 Stack

- Django 4.2 + django-cotton + Vanilla JS (pas de bundler)
- HTMX 2.0.6 + extension `loading-states` + extension `ws` (Daphne / WebSocket)
- Event bus custom dans `tibilletUtils.js` (table `switches` + `eventsOrganizer`)
- 3 fichiers JS centraux : `articles.js`, `addition.js`, `tarif.js`
- 1 fichier NFC : `nfc.js` (classe `NfcReader`)

### 2.2 Layers HTMX

```
Layer 0 : interface principale (#products, #addition)
Layer 1 : #messages   (paiement, sélection tarif, identification)
Layer 2 : #confirm    (confirmation, lecture NFC)
```

Les partials sont injectés en **innerHTML** sur ces conteneurs permanents.
Un listener global `htmx:afterSwap` (base.html:156-164) retire `.hide` quand un partial est injecté.

### 2.3 Ce qui est sain

- `#event-organizer` est permanent → l'event bus s'attache une seule fois au `DOMContentLoaded`.
- `#addition` et `#products` sont permanents → leurs listeners (`additionInsertArticle`, `articlesAdd`, `tarifSelection`...) survivent à tous les swaps. Pas de re-binding nécessaire.
- La table `switches` est statique → pas de risque d'empilement de routes.
- Les Cotton components (sauf `read_nfc.html`) **ne contiennent pas** de `<script>` inline. Ils sont structurels.
- Les scripts inline dans certains partials (`hx_lire_nfc_client.html`) sont auto-exécutants `(function(){...})()` mais idempotents (ils peuplent juste des inputs cachés).

**Conclusion : l'archi front n'est pas globalement cassée.** Le bug est concentré sur un endroit précis : la lecture NFC.

---

## 3. Bugs détectés

### 3.1 [CRITIQUE] Fuite d'instances `NfcReader` — pas de `stop()` au RETOUR

**Fichiers** :
- `laboutik/static/js/nfc.js`
- `laboutik/templates/cotton/read_nfc.html`

**Symptôme** : à chaque ouverture de l'overlay cashless, une nouvelle instance `NfcReader` est créée. Aucune instance précédente n'est nettoyée. Le bouton RETOUR ferme juste l'overlay (`hideAndEmptyElement('#confirm')`) mais n'appelle **pas** `nfc.stop()`.

**Code coupable** :

`templates/cotton/read_nfc.html:13-24` :
```html
<script>
  function initNfc() {
    try {
      const nfc = new NfcReader()
      nfc.start({eventManageForm: '{{ event_manage_form }}', submitUrl: '{{ submit_url }}'})
    } catch (error) {
      console.log('-> Cotton - read_nfc.html - initNfc,', error)
    }
  }
  initNfc()
</script>
```

- `const nfc = ...` est une variable locale perdue dès la fin du script.
- Aucune référence globale → impossible d'appeler `stop()` depuis l'extérieur.
- À chaque rendu du Cotton, **une nouvelle instance est créée** sans toucher l'ancienne.

`static/js/nfc.js:199-219` (méthode `stop()`) :
```javascript
async stop() {
    if (modeNfc === "NFCLO") {
        this.socket.emit('AnnuleDemandeTagId', { uuidConnexion: this.uuidConnexion })
        // PAS de this.socket.disconnect() → la socket reste ouverte
    }
    if (modeNfc === 'NFCSIMU') {
        document.querySelector('#nfc-simu-tag')
            .removeEventListener('click', this.sendSimuNfcTagId)
        // this.sendSimuNfcTagId N'EXISTE PAS — le listener réel
        // est une arrow function anonyme à la ligne 145.
        // removeEventListener est un no-op.
    }
    this.uuidConnexion = null
}
```

**Pourquoi en mode NFCSIMU (dev) ça ne casse pas le paiement** : le DOM `#nfc-simu-tag` est entièrement remplacé via le swap `#confirm`. Le listener click de l'ancienne instance meurt avec son élément. Le scan touche bien la nouvelle instance. Pas de panne fonctionnelle visible — juste une fuite mémoire.

**Pourquoi en mode NFCLO (production, socket.io serveur sur le Pi) ça casse** :
- L'ancienne instance a `socket = io('http://localhost:3000')` → connexion ouverte.
- La nouvelle instance ouvre une **2ème** connexion sur le même port.
- Au scan, le serveur émet `envoieTagId` aux **2 sockets**.
- Les 2 instances reçoivent. L'ancienne a un `uuidConnexion` qui ne correspond plus → `verificationTagId` log "Erreur uuidConnexion différent" (nfc.js:58-60) et **silencieusement ignore**.
- Selon le timing (ordre des callbacks socket.io), si l'ancienne répond la première, le formulaire est soumis avec son uuid périmé → erreur côté serveur.

**Pourquoi en mode NFCMC (Cordova) ça casse aussi** : `nfcPlugin.startListening()` de l'ancienne instance est probablement encore en attente. La nouvelle instance appelle `startListening()` à son tour → le plugin natif renvoie peut-être une erreur ou bloque.

### 3.2 [CRITIQUE] `eventsOrganizer` plante silencieusement sur message inconnu

**Fichier** : `laboutik/static/js/tibilletUtils.js:204-225`

```javascript
function eventsOrganizer(event) {
    try {
        const data = event.detail.data
        const msg = event.detail.msg
        const eventSwitch = switches[msg]      // undefined si msg inconnu
        for (let i = 0; i < eventSwitch.length; i++) {  // TypeError
            const eventData = eventSwitch[i]
            sendEvent(eventData.name, eventData.selector, data)
        }
    } catch (error) {
        // Silencieux en production  ← commentaire dans le code
    }
}
```

Toute faute de frappe dans un nom de message côté template ou JS produit un échec **totalement invisible**. Pas de log, pas d'erreur. Cache potentiellement d'autres bugs en debug.

### 3.3 [MOYEN] `_tarifVariableCounter` jamais reset

**Fichier** : `laboutik/static/js/tarif.js`

- ligne 360 : `let _tarifVariableCounter = 0` au module-level
- ligne 394 : `_tarifVariableCounter++`
- aucun reset dans `additionReset()` ni ailleurs (vérifié au grep)

Sans gravité fonctionnelle (les `lineId` restent uniques), mais les suffixes `--N` dérivent au fil de la session (`--7`, `--8`, `--9`...). Mauvais pour le debug de cassure.

### 3.4 [BAS] `stop()` no-op en mode NFCSIMU

Voir 3.1 — `removeEventListener('click', this.sendSimuNfcTagId)` est un no-op car la référence n'existe pas. Sans gravité car le DOM est replacé.

---

## 4. Reproduction Chrome — preuves directes

Scénario joué dans le navigateur en mode démo (`state.demo.active === true`, `modeNfc === 'NFCSIMU'`) :

1. PV "Bar" → clic Bière (5€) → VALIDER → CASHLESS
2. RETOUR (sans scanner)
3. CASHLESS (2ème ouverture)
4. Scan "Carte client 1" → succès → RETOUR
5. Bière → VALIDER → CASHLESS (3ème ouverture)

`NfcReader`, `start()` et `stop()` instrumentés via wrap de classe.

| Étape | Instances vivantes | start() cumulés | stop() cumulés |
|---|---|---|---|
| Avant 1er CASHLESS | 0 | 0 | 0 |
| Après 1er CASHLESS | 1 (uuid `41078642...`) | 1 | 0 |
| Après RETOUR | **1 zombie, uuid intact** | 1 | **0** |
| Après 2e CASHLESS | **2** (les 2 vivantes) | 2 | 0 |
| Après scan + succès | 2 (zombie + stoppée) | 2 | 1 |
| Après 2e vente CASHLESS | **3** | 3 | **1** |

Conclusion : **chaque cycle CASHLESS+RETOUR ajoute +1 zombie**.

### Bug 3.2 reproduit en direct

```javascript
sendEvent('organizerMsg', '#event-organizer', {
    src: { file: 'test', method: 'test' },
    msg: 'MESSAGE_INEXISTANT_XYZ',
    data: {}
})
// Résultat : 0 log, 0 warning, 0 error.
// Bug avalé silencieusement par le try/catch.
```

---

## 5. Correctif minimal recommandé (~15 lignes)

Pas de refactor de l'archi. Trois actions chirurgicales.

### 5.1 Singleton global pour `NfcReader`

`nfc.js` à la fin :
```javascript
// Singleton global — une seule instance vivante à la fois.
// / Global singleton — only one live instance at a time.
window.tibilletNfc = null
```

`templates/cotton/read_nfc.html` (remplace le bloc `initNfc`) :
```html
<script>
  (async function () {
    try {
      // Détruit l'instance précédente si elle existe (zombie zombie zombie).
      // / Destroys the previous instance if it exists.
      if (window.tibilletNfc) {
        await window.tibilletNfc.stop()
      }
      window.tibilletNfc = new NfcReader()
      window.tibilletNfc.start({
        eventManageForm: '{{ event_manage_form }}',
        submitUrl: '{{ submit_url }}'
      })
    } catch (error) {
      console.log('-> read_nfc.html - init,', error)
    }
  })()
</script>
```

Bonus : ajouter un appel `await window.tibilletNfc?.stop()` dans le bouton RETOUR du composant `c-bt.return` quand le selector pointe sur `#confirm`. Ou plus simplement : écouter `htmx:afterSwap` quand `#confirm` est vidé et déclencher le stop.

### 5.2 Réparer `nfc.js:199-219` (`stop()`)

```javascript
async stop() {
    if (this.modeNfc === "NFCLO" && this.socket) {
        this.socket.emit('AnnuleDemandeTagId', { uuidConnexion: this.uuidConnexion })
        this.socket.disconnect()    // AJOUTÉ — ferme la socket pour de bon
        this.socket = null
    }
    if (this.modeNfc === 'NFCMC') {
        await nfcPlugin.stopListening()
    }
    // Plus besoin de removeEventListener pour NFCSIMU :
    // les éléments DOM sont remplacés au prochain swap.
    this.uuidConnexion = null
    this.modeNfc = ''
}
```

### 5.3 Logger les messages inconnus de l'event bus

`tibilletUtils.js:204-225` :
```javascript
function eventsOrganizer(event) {
    const msg = event.detail.msg
    const eventSwitch = switches[msg]
    if (!eventSwitch) {
        console.warn('[event-bus] msg inconnu :', msg, event.detail)
        return
    }
    const data = event.detail.data
    eventSwitch.forEach(({ name, selector }) => {
        sendEvent(name, selector, data)
    })
}
```

Plus de try/catch silencieux. Plus de `for` C-style.

### 5.4 (Optionnel) Reset `_tarifVariableCounter`

`tarif.js` : exposer une fonction `tarifResetCounter()` et l'appeler depuis `additionReset()` dans `addition.js`. Ou simpler : déplacer le compteur dans `addition.js` et le reset dans `additionReset()`.

---

## 6. Ce qu'il NE faut PAS refactorer

- L'event bus `tibilletUtils.js` : statique, lisible, FALC. Pas de raison de le changer (juste corriger le silent fail).
- Les Cotton components (sauf `read_nfc.html`) : structurels uniquement, propres.
- Les partials HTMX : leur contenu est idempotent et l'archi des layers (`#messages`, `#confirm`) tient la route.
- Les listeners attachés au `DOMContentLoaded` sur `#addition`, `#products`, `#event-organizer` : ces éléments sont permanents, leurs listeners survivent à tous les swaps. Pas besoin de migrer vers `htmx:load`.

---

## 7. Tests à ajouter

À écrire dans `tests/e2e/test_pos_cashless_singleton.py` (Playwright Python) :

1. **test_one_cashless_one_instance** : 1 vente cashless complète → vérifier qu'à la fin il n'y a qu'1 instance `NfcReader` ou 0 (instance courante, pas de zombie). Hook : `window.__nfcAuditCount` exposé en debug.
2. **test_cashless_back_no_leak** : ouvrir CASHLESS, RETOUR, ouvrir CASHLESS → 1 instance vivante max.
3. **test_unknown_event_logs_warning** : `sendEvent('organizerMsg', ..., { msg: 'XYZ' })` → vérifier que `console.warn` a bien été émis.
4. **test_two_consecutive_cashless_payments** : 2 ventes cashless de suite → les 2 réussissent.

---

## 8. Référence rapide pour le fix

| Fichier | Ligne(s) | Action |
|---|---|---|
| `laboutik/static/js/nfc.js` | 199-219 | Réparer `stop()` (disconnect socket, retirer no-op simu) |
| `laboutik/static/js/nfc.js` | (fin) | Ajouter `window.tibilletNfc = null` |
| `laboutik/templates/cotton/read_nfc.html` | 13-24 | Remplacer `initNfc()` par version singleton |
| `laboutik/static/js/tibilletUtils.js` | 204-225 | Réécrire `eventsOrganizer` avec `console.warn` au lieu de catch silencieux |
| `laboutik/static/js/tarif.js` | 360 | (optionnel) reset `_tarifVariableCounter` dans `additionReset` |

Total : 4-5 fichiers, ~30 lignes modifiées.

---

## 9. Suite

- [ ] Valider ce diagnostic avec le mainteneur
- [ ] Décider si on attaque le fix dans cette session ou plus tard
- [ ] Si fix : TDD via `superpowers:test-driven-development` (tests E2E d'abord)
- [ ] Mettre à jour `CHANGELOG.md` après le fix
- [ ] Ajouter une entrée dans `A TESTER et DOCUMENTER/` pour le scénario manuel
