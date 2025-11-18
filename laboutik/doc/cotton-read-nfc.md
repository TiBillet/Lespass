# `<c-read-nfc>` composant cotton

## Example
```html
<c-read-nfc id="confirm" selector="#confirm" set="partial" nfc-send='{"eventName":"manageFormHtmx", "selectorForm": "#form-nfc", "actions": ["input,#addition-moyen-paiement,nfc", "inputTagId,#nfc-tag-id","hx-trigger,nfcResult", "url,hx_payment", "submit"]}'>
<form id="form-nfc" class="hide" hx-post="ask_primary_card" hx-trigger="nfcResult" hx-target=".message-nfc"
		hx-swap="innerHTML">
		{% csrf_token %}
		<input id="nfc-tag-id" name="tag_id" />
		<input id="addition-moyen-paiement,nfc" name="addition-moyen-paiement,nfc">
	</form>
</c-read-nfc>
```
```html
<c-read-nfc>
	{{ slot }}
</c-read-nfc>
```
## Doc
- id = "confirm" mais peut être changé 

- selector permet d'ajouter un bouton retour qui éfface la vue contenant <-read-nfc>
  et sa valeur est égale a "#<valeur de id>", exemple "#confirm"; il n'est pas obligatoire.

- eventName est le nom de l'évènement à écouter et aussi le nom de la fonction à lancer pour gérer le formulaire; obligatoire.

- selectorForm permet de cibler le formulaire à modifier et à écouter; obligatoire.

- set: 
  . partial = c-read-nfc est un contenu "partial" requêté par htmx
  . page    = c-read-nfc fait partie du contenu d'une page

- send permet au lecteur nfc(nfc.js) de modifier les inputs et d'envoyer un formulaire, c'est une queu([])
  de demandes d'actions/informations pour un formulaire:
  . input = permet de modifier la valeur d'un input; le 2ème élément est l'id de celui-ci et le 3ème élément est sa valeur à modifier

  . inputTagId = permet d'insérer la valeur du tag id; il ne nécéssite qu'un 2ème élément qui correspond à l'id de celui-ci.
    Attention, il est obligatoire.

  . hx-trigger = permet de modifier et informer l'évènement qui permet d'envoyer(submit) le formulaire;
    le 2ème élément est l'évènement à envoyer pour submit le formulaire.
    Attention, il est obligatoire si vous utilisez 'submit' dans send.

  . url = permet de changer l'url du hx-post, le 2ème élément est l'url du POST.

  . submit = permet d'envoyer le formulaire; vous avez besoin de hx-trigger et du eventName pour cette action.


## Infos
### NFC
- .../laboutik/static/js/nfc.js lecture et simulation du nfc (envoie les actions de `<c-read-nfc>`)
- .../laboutik/static/js/tibilletUtils.js, function manageFormHtmx(applique les actions de `<c-read-nfc>`)
