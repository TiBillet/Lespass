# `<c-read-nfc>` composant cotton

## Exemple
```html
<c-read-nfc id="nfc-container" event-manage-form="primaryCardManageForm" submit-url="ask_primary_card">
	<form id="form-nfc" class="hide" hx-post="ask_primary_card" hx-trigger="nfcResult" hx-target=".message-nfc"
		hx-swap="innerHTML">
		{% csrf_token %}
		<input id="nfc-tag-id" name="tag_id" />
	</form>
	<h1>{% translate "Attente carte primaire" %}</h1>
	<h3 class="message-nfc">{{msg}}</h3>
</c-read-nfc>

<script>
	// gestionnaire de formulaire
	function primaryCardManageForm(event) {
		try {
			const data = event.detail
			const form = document.querySelector('#form-nfc')

			// update input
			if (data.actionType === 'updateInput') {
				form.querySelector(data.selector).value = data.value
			}

			// change post url
			if (data.actionType === 'postUrl') {
				form.setAttribute('hx-post', data.value)
				htmx.process(form)
			}

			// submit form
			if (data.actionType === 'submit') {
				form.setAttribute('hx-trigger', 'click')
				htmx.process(form)
				// submit
				form.click()
			}

		} catch (error) {
			console.log('-> addition.js - additionManageForm,', error)
		}
	}
	// écoute des commandes sur le formulaire "#form-nfc"
	document.querySelector('#form-nfc').addEventListener('primaryCardManageForm', primaryCardManageForm)
</script>
```
## Infos
- nfc.js receptionne un tagId et l'envoie dans un formulaire par l'intermédiaire d'un évènement.
- Le formulaire qui post le tagId de la carte primaire est géré par l'évènement "primaryCardManageForm".
- Le formulaire d'achats est géré par l'évènement "additionManageForm".

## Doc
- id = sert à référencer le conteneur(html) principal qui contient tout le visuel lors de la lecture des cartes nfc.

- selector permet d'ajouter un bouton retour qui efface le conteneur contenant tout le visuel
  lors de la lecture des cartes nfc.
  Sa valeur est égale au id.

- event-manage-form est le nom de l'évènement qui gère l'insertion du tagId et l'envoi du formulaire.

- submit-url permet de fixer l'url du formulaire à poster (suivant les  étapes du fonctionnnement de l'application,
  l'url du formulaire peux être dynamique)

## Exemples
- ask_primary_card.html
- common_user_interface.html + addirtion.js

## NFC
- .../laboutik/static/js/nfc.js - lecture et simulation du nfc (`<c-read-nfc>`)