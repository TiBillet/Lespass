/**
* Réinitialise complètement l'interface de vente
* / Resets the entire sales interface
* 
* LOCALISATION : Cette fonction est définie DANS CE FICHIER (lignes ci-dessous)
* / Location: This function is defined IN THIS FILE (lines below)
* 
* Cette fonction est appelée lors du clic sur le bouton RESET (#bt-reset).
* Elle envoie un événement 'resetArticles' qui sera routé par eventsOrganizer
* vers deux handlers dans d'autres fichiers JS (déjà commentés) :
* 
* HANDLERS DE L'ÉVÉNEMENT (déjà commentés, voir fichiers sources) :
* - additionReset() dans laboutik/static/js/addition.js : 
*   Voir la documentation complète dans le fichier addition.js
*   Action : Vide l'addition, supprime les inputs, réinitialise le formulaire
* 
* - articlesReset() dans laboutik/static/js/articles.js :
*   Voir la documentation complète dans le fichier articles.js  
*   Action : Remet les quantités à zéro et déverrouille les groupes d'articles
* 
* TABLE DE ROUTAGE / ROUTING TABLE :
* Voir tibilletUtils.js : switches['resetArticles'] définit ces routes
*/
function manageReset() {
  sendEvent('organizerMsg', '#event-organizer', {
    src: { file: 'common_user_interface.html', method: 'manageReset' },
    msg: 'resetArticles',
    data: {}
  })
}

/**
  * Affiche les types de paiement disponibles
  * / Displays available payment types
  *
  * LOCALISATION : Cette fonction est définie DANS CE FICHIER (lignes ci-dessous)
  * / Location: This function is defined IN THIS FILE (lines below)
  *
  * Cette fonction est appelée lors du clic sur le bouton VALIDER (#bt-valider).
  * Elle envoie l'événement 'additionDisplayPaymentTypes' qui est géré par
  * le handler dans le fichier JS suivant (déjà commenté) :
  *
  * HANDLER DE L'ÉVÉNEMENT (déjà commenté, voir fichier source) :
  * - additionDisplayPaymentTypes() dans laboutik/static/js/addition.js
  *   Voir la documentation complète dans le fichier addition.js
  *   Action : Affiche l'écran de sélection des moyens de paiement (CASHLESS, ESPÈCE, CB, etc.)
  *   ou le message d'erreur si aucun article n'est sélectionné
  *   Configure HTMX pour charger partial/hx_display_type_payment.html
  *
  * TABLE DE ROUTAGE / ROUTING TABLE :
  * Voir tibilletUtils.js : switches['additionDisplayPaymentTypes'] définit cette route
  */
function displayPaymentTypes() {
  console.log('-> displayPaymentTypes');

  sendEvent('organizerMsg', '#event-organizer', {
    src: { file: 'common_user_interface.html', method: 'displayPaymentTypes' },
    msg: 'footerAskAdditionDisplayPaymentTypes',
    data: {}
  })
}


/**
* Met à jour l'affichage du total sur le bouton VALIDER
* / Updates the total display on the VALIDER button
*
* LOCALISATION : Cette fonction est définie DANS CE FICHIER (lignes ci-dessous)
* / Location: This function is defined IN THIS FILE (lines below)
*
* Cette fonction est un HANDLER d'événement. Elle est appelée automatiquement
* lorsque l'événement 'updateBtValider' est déclenché sur #bt-valider.
*
* ÉMETTEUR DE L'ÉVÉNEMENT (déjà commenté, voir fichier source) :
* - addition.js envoie 'additionTotalChange' → eventsOrganizer
* - Voir laboutik/static/js/addition.js pour la documentation complète :
*   * additionInsertArticle() émet 'additionTotalChange' après ajout
*   * additionRemoveArticle() émet 'additionTotalChange' après retrait
*   * additionReset() émet 'additionTotalChange' avec total=0
* - switches['additionTotalChange'] dans tibilletUtils.js route vers #bt-valider
*
* Cette fonction reçoit le total en centimes et l'affiche en euros (divisé par 100).
*
* @param {Event} event - Événement contenant event.detail.totalAddition (total en centimes)
*/
function updateSumOfValidateButton(event) {
  document.querySelector('#bt-valider-total').innerText = (event.detail.totalAddition / 100).toFixed(2)
}

/**
 * Change method to launch by #bt-valider
 * @param {Event} event - Événement contenant event.detail.method
 */
function changeMethodOfValidateButton(event) {
  console.log('changeMethodOfValidateButton - event.detail =', event.detail)
  document.querySelector('#bt-valider').setAttribute('method-launch', event.detail.method)
}

/**
* Initialisation des écouteurs d'événements au chargement de la page
* / Event listeners initialization on page load
*
* LOCALISATION : Cette fonction est définie DANS CE FICHIER
* / Location: This function is defined IN THIS FILE
*
* Attache trois types d'écouteurs différents :
*
* 1. ÉCOUTEUR DE CLIC (click event listener) :
*    - #bt-reset → manageReset() : réinitialise la commande
*    - #bt-valider → displayPaymentTypes() : affiche les options de paiement
*
* 2. ÉCOUTEUR D'ÉVÉNEMENT PERSONNALISÉ (custom event listener) :
*    - #bt-valider → updateBtValider() : met à jour le total affiché
*      Cet événement 'updateBtValider' est émis par addition.js (voir ci-dessus)
*
* Three types of listeners are attached:
* 1. Click event listeners on #bt-reset and #bt-valider
* 2. Custom event listener 'updateBtValider' on #bt-valider
*/
document.addEventListener('DOMContentLoaded', () => {
  document.querySelector('#bt-reset').addEventListener('click', manageReset)
  document.querySelector('#bt-valider').addEventListener('updateSumOfValidateButton', updateSumOfValidateButton)
  // manage bt validate
  document.querySelector('#bt-valider').addEventListener('changeMethodOfValidateButton', changeMethodOfValidateButton)
  document.querySelector('#bt-valider').addEventListener('click', displayPaymentTypes)
})
