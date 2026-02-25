from laboutik.utils import mockData

def selection_moyens_paiement(pv, uuids, postData):
	# moyens de paiement retournés par la fonction
	moyens_paiement = []
	articles = pv['articles']
	for uuid in uuids:
		# moyens de paiment de l'article
		moyens_paiement_article = mockData.get_article_from_uuid(uuid, articles)['bt_groupement']['moyens_paiement'].split('|')
		for paiement in moyens_paiement_article:
			# compose la liste de moyens de paiement et la filtre par moyens de paiement accepté
			if paiement not in moyens_paiement:
				paiement_accepte = False

				if paiement == 'espece' and pv['accepte_especes'] == True:
					paiement_accepte = True

				if paiement == 'carte_bancaire' and pv['accepte_carte_bancaire'] == True:
					paiement_accepte = True

				if paiement == 'CH' and pv['accepte_cheque'] == True:
					paiement_accepte = True

				moyens_paiement.append(paiement)

	return moyens_paiement


def calcul_total_addition(pv, uuids, postData):
	articles = pv['articles']
	total = 0
	for uuid in uuids:
		# prix d'un article
		prix = mockData.get_article_from_uuid(uuid, articles)['prix']
		# quantité
		qty = int(postData.get('repid-' + uuid))
		total = total + (qty * prix)

	return total / 100


def post_filter(postData):
	retour = []
	for name in postData:
		index = name.find("repid")
		if index != -1:
			retour.append(name[6:])
	return retour
