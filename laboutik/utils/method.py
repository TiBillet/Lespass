import mockData

def selection_moyens_paiement(pv, inputs, postData):
	# print('-> Sélection des moyens de paiement')
	# moyens de paiement retournés par la fonction
	moyens_paiement = []
	for input in inputs:
		# moyens de paiment de l'article
		moyens_paiement_article = mockData.get_article_from_uuid(input, pv)['bt_groupement']['moyens_paiement'].split('|')
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
		# print(f"uuid = {input}  --  qty = {postData.get(input)}")
	
	return moyens_paiement

def calcul_total_addition(pv, inputs, postData):
	total = 0
	for input in inputs:
		# moyens de paiment de l'article
		prix = mockData.get_article_from_uuid(input, pv)['prix']
		total = total + (int(postData.get(input)) * prix)
		# print(f"uuid = {input}  --  qty = {postData.get(input)}  --  prix = {prix}  --  total = {total}")

	return total / 100



def post_filter(data):
	print('-> post filter')
	retour = []
	for input in data:
		if input != 'id_table' and input != 'uuid_pv' and input !='tag_id_cm':
			retour.append(input)
	return retour
