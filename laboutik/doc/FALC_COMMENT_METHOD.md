# Méthode de commentaires FALC pour JavaScript
# FALC Commenting Method for JavaScript

## Principe / Principle

Les commentaires dans les fichiers JavaScript doivent suivre la méthode **FALC** (Facile À Lire et Comprendre) avec une structure spécifique :

**FR : Explications détaillées en français**
**EN : Une seule ligne succincte en anglais**

---

## Structure d'un commentaire de fonction

```javascript
/**
 * NOM DE LA FONCTION - DESCRIPTION EN FRANÇAIS
 * / Short description in English
 *
 * LOCALISATION : Chemin du fichier où est définie la fonction
 * / Location: File path where function is defined
 *
 * DESCRIPTION DÉTAILLÉE EN FRANÇAIS :
 * - Ce que fait la fonction
 * - Comment elle interagit avec d'autres fichiers
 * - Le flux d'exécution (si applicable)
 * - Les événements émis ou reçus
 * - Les dépendances
 *
 * SHORT ENGLISH SUMMARY :
 * Brief description of what the function does
 *
 * @param {Type} nom - Description du paramètre (si applicable)
 * @returns {Type} Description de la valeur retournée (si applicable)
 */
```

---

## Règles / Rules

### 1. Toujours en FRANÇAIS d'abord
- Explications détaillées
- Logique métier
- Flux d'événements
- Configuration
- Pointeurs vers autres fichiers

### 2. Une ligne EN ANGLAIS suffit
- Juste une traduction courte du titre/description
- Pas besoin de détailler en anglais
- Format : `/ Brief description`

### 3. Section LOCALISATION obligatoire
- Indique où est définie la fonction
- Permet de naviguer facilement dans le code
- Format : `LOCALISATION : chemin/fichier.js`

### 4. Documenter les communications inter-fichiers
Si la fonction émet ou reçoit des événements :
```javascript
/**
 * ÉVÉNEMENTS ÉMIS :
 * - 'nomEvent' → eventsOrganizer → handler sur #selecteur
 *
 * ÉVÉNEMENTS REÇUS :
 * - 'nomEvent' depuis fichier.js via tibilletUtils.js
 */
```

### 5. Flux d'appel (Call Flow)
Pour les fonctions complexes, documenter le flux :
```javascript
/**
 * FLUX D'APPEL :
 * 1. Événement déclenché dans fichierA.js
 * 2. Routage via tibilletUtils.js:eventsOrganizer()
 * 3. switches['nomEvent'] route vers cette fonction
 * 4. CETTE FONCTION est exécutée
 */
```

---

## Exemple complet

```javascript
/**
 * Ajoute un article au panier
 * / Adds item to cart
 *
 * LOCALISATION : laboutik/static/js/addition.js
 *
 * Handler de l'événement 'additionInsertArticle'. Appelé via le flux :
 * clic article → articles.js:addArticle → 'articlesAdd' → 
 * tibilletUtils.js:eventsOrganizer() → CETTE FONCTION
 *
 * Actions effectuées :
 * - Crée un input caché 'repid-{uuid}' dans le formulaire
 * - Crée une ligne d'affichage dans #addition-list
 * - Recalcule le total et émet 'additionTotalChange'
 *
 * COMMUNICATION :
 * Reçoit : Événement 'additionInsertArticle' depuis tibilletUtils.js
 * Émet : 'additionTotalChange' → eventsOrganizer → updateBtValider sur #bt-valider
 *
 * @param {Object} param0 - event.detail contenant uuid, price, quantity, name, currency
 */
function additionInsertArticle({ detail }) {
    // ... code ...
}
```

---

## Commentaires inline

Pour les commentaires à l'intérieur des fonctions :

```javascript
function example() {
    // Récupère l'élément DOM du panier
    // / Gets cart DOM element
    const cart = document.querySelector('#cart');
    
    // Calcule le total en centimes (prix × quantité)
    // / Calculates total in cents
    const total = price * quantity;
}
```

---

## Avantages de cette méthode

1. **Lisibilité** : Le français est plus accessible pour l'équipe
2. **Concision** : Pas de duplication inutile (une ligne EN suffit)
3. **Navigation** : LOCALISATION permet de retrouver facilement les définitions
4. **Compréhension** : Les flux documentés aident à suivre la logique
5. **Maintenance** : Les TODO peuvent être ajoutés pour marquer les problèmes

---

## Cas particulier : TODO

Pour marquer un problème sans le corriger :

```javascript
// TODO : Explication du problème en FR
// / Brief description of issue
```

Exemple :
```javascript
// TODO : Cette variable n'est pas déclarée avec 'let' ou 'const',
// ce qui crée une variable globale implicite. Risque de conflit.
// / Global variable created implicitly
total = 0;
```

---

## Résumé / Summary

| Élément | FR | EN |
|---------|-----|-----|
| Titre fonction | ✅ Détaillé | ✅ 1 ligne |
| Description | ✅ Complète | ❌ Non |
| Localisation | ✅ Chemin fichier | ✅ File path |
| Flux/Logique | ✅ Détaillé | ❌ Non |
| Paramètres | ✅ Description | ✅ Type + desc |
| Commentaires inline | ✅ Explication | ✅ 1 phrase |
| TODO | ✅ Problème détaillé | ✅ Brief issue |
