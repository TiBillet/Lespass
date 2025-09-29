# id catégorie unique et triage par poid
def filter_categories(pv):
	testIdem = []	
	categories = []
	for article in pv['articles']:
		cat = article['categorie']
		if cat['id'] not in testIdem:
			testIdem.append(cat['id'])
			categories.append(cat)

	retour = sorted(categories, key=lambda x: x['poid_liste'])
	testIdem = None
	categories = None
	return retour 
