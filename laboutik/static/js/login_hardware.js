window.glob = {
	"appConfig": {
		"hostname": "appareilDemo",
		"password": "passwordDemo",
		"front_type": "FOR",
		"locale": "fr",
		"mode_nfc": "modeNfcDemo",
		"ip_lan": "127.0.0.1",
		"pin_code": 123456
	},
	"csrf_token": "Dk4FcujmHzzGnAC4j1XchJ81eiJpTPlcHDd27w0LLMJKgKDaYIpwSIypVsibcWHN",
	"uuidArticlePaiementFractionne": "42ffe511-d880-4964-9b96-0981a9fe4071",
	"tagIdCm": "EE144CE8",
	"data": [



	],
	"responsable": {
		"nom": [
			"TEST"
		],
		"uuid": "17896c22-7a60-45f4-a959-175bfc8a5369",
		"edit_mode": true
	},
	"monnaie_principale_name": "TestCoin",
	"passageModeGerant": true,
	"modeGerant": false,
	"currencyData": {
		"cc": "EUR",
		"symbol": "€",
		"name": "European Euro"
	},
	"bt_groupement": {
		"VenteArticle": {
			"moyens_paiement": "espece|carte_bancaire|nfc|CH",
			"besoin_tag_id": "nfc",
			"groupe": "groupe1",
			"nb_commande_max": 1000
		},
		"RetourConsigne": {
			"moyens_paiement": "espece|nfc",
			"besoin_tag_id": "nfc",
			"groupe": "groupe2",
			"nb_commande_max": 1000
		},
		"Adhesion": {
			"moyens_paiement": "espece|carte_bancaire|CH",
			"besoin_tag_id": "tout",
			"groupe": "groupe3",
			"nb_commande_max": 1000
		},
		"AjoutMonnaieVirtuelle": {
			"moyens_paiement": "espece|carte_bancaire|CH",
			"besoin_tag_id": "tout",
			"groupe": "groupe4",
			"nb_commande_max": 1000
		},
		"AjoutMonnaieVirtuelleCadeau": {
			"moyens_paiement": "",
			"besoin_tag_id": "tout",
			"groupe": "groupe5",
			"nb_commande_max": 1000
		},
		"BG": {
			"moyens_paiement": "",
			"besoin_tag_id": "tout",
			"groupe": "groupe6",
			"nb_commande_max": 1000
		},
		"ViderCarte": {
			"moyens_paiement": "",
			"besoin_tag_id": "tout",
			"groupe": "groupe7",
			"nb_commande_max": 1
		},
		"Inconnue": {
			"moyens_paiement": "",
			"besoin_tag_id": "",
			"groupe": "groupe888",
			"nb_commande_max": 0
		}
	},
	"tabMethodesATester": [
		"VenteArticle",
		"RetourConsigne",
		"Adhesion",
		"AjoutMonnaieVirtuelle",
		"AjoutMonnaieVirtuelleCadeau",
		"BG",
		"ViderCarte",
		"Inconnue"
	],
	"tableEnCours": null
}
