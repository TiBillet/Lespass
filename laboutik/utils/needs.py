categoriy_angry = {
	"id": 998,
  "name": "angry",
  "poid_liste": 998,
  "icon": "fa-angry",
  "couleur_backgr": "#FFFFFF",
  "couleur_texte": "#000000",
  "groupements": [],
  "tva": None
}

# id catégorie unique et triage par poid
def filter_categories(pv):
	testIdem = []	
	categories = []
	for article in pv['articles']:
		# print(f"article['categorie'] = {article['categorie']}")
		if article['categorie'] == None:
			cat = categoriy_angry
		else:
			cat = article['categorie']

		if cat['id'] not in testIdem:
			testIdem.append(cat['id'])
			categories.append(cat)

	retour = sorted(categories, key=lambda x: x['poid_liste'])
	testIdem = None
	categories = None
	return retour 

def fixe_pv(pv):
	print(f"-> fixe_pv, pv = {pv}")
	for article in pv['articles']:
		# pas de categorie
		if article['categorie'] == None:
			article['categorie'] = categoriy_angry
		
		# pas de fond
		if article['categorie']['couleur_backgr'] == None:
			article['categorie']['couleur_backgr'] = '#17a2b8'
		
		# pas de couleur texte
		if article['categorie']['couleur_texte'] == None:
			article['categorie']['couleur_texte'] = '#ffffff'
