# `<c-addition>` composant cotton

## Infos
- écoute des évènements:
  . additionInsertArticle
	. additionReset
	. additionDisplayPaymentTypes
	. additionUpdateForm

- émet des évènements:
  . additionRemoveArticle
	. additionTotalChange

- Tous les évènements sont envoyés à l'eventsOrganizer par l'évènement "organizerMsg"
- la gestion des demandes extérieures est gérée par l'écoute de l'évènement "organizerMsg"