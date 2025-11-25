# `<c-read-nfc>` composant cotton

## Example
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

```
```html
<c-read-nfc>
	{{ slot }}
</c-read-nfc>
```
## Infos
- nfc.js donne un tagId et demande d'envoyer un formulaire par l'intermédiaire d'un évènement qui lance une méthode.
- Le formulaire qui post le tagId de la carte primaire est géré par l'évènement "primaryCardManageForm".
- Le formulaire d'achats est géré par l'évènement "additionManageForm".

## Doc
- id = sert à référencer le conteneur(html) principal qui contient tout le visuel lors de la lecture des cartes nfc.

- selector permet d'ajouter un bouton retour qui éfface le conteneur lequel contient tout le visuel lors de la lecture des cartes nfc.
  Sa valeur est égale au id.

- event-manage-form est le nom de l'évènement qui gère l'insertion du tagId et l'envoi du formulaire.

- submit-url permet de fixer l'url du formulaire à poster (suivant les  étapes du fonctionnnement de l'application,
  l'url du formulaire peux être dynamique)

## Exemples
- ask_primary_card.html
- common_user_interface.html + addirtion.js

## NFC
- .../laboutik/static/js/nfc.js - lecture et simulation du nfc (envoie les actions de `<c-read-nfc>`)