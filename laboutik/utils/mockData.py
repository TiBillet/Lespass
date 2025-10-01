from django.conf import settings

pvs = [
	{
		"id": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	"name": "Bar 1",
  	"poid_liste": 1,
  	"comportement": "A",
  	"afficher_les_prix": True,
  	"accepte_especes": True,
  	"accepte_carte_bancaire": True,
  	"accepte_cheque": False,
  	"accepte_commandes": True,
  	"service_direct": True,
  	"articles": [
			{
				"id": "8f08b90d-d3f0-49da-9dbd-8be795f689ef",
  	    "name": "Retour Consigne",
  	    "prix": -1,
  	    "poid_liste": 16,
  	    "categorie": {
					"id": 4,
  	      "name": "Consigne",
  	      "poid_liste": 5,
  	      "icon": "fa-recycle",
  	      "couleur_backgr": "#FFFFFF",
  	      "couleur_texte": "#000000",
  	      "groupements": [],
  	      "tva": None
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "RetourConsigne",
  	    "methode_choices": "CR",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|nfc",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe2",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "consigne"
  	  },
  	  {
  		  "id": "67d231cd-d1c2-4bf3-ac51-18af778b4f8c",
  		  "name": "Pression 33",
  		  "prix": 2,
  		  "poid_liste": 28,
  		  "categorie": {
  		    "id": 9,
  		    "name": "Pression",
  		    "poid_liste": 10,
  		    "icon": "fa-beer",
  		    "couleur_backgr": "#f6cd61",
  		    "couleur_texte": None,
  		    "groupements": [2],
  		    "tva": {
  		      "name": "Alcool",
  		      "taux": "20.00"
  		    }
  		  },
  		  "url_image": "https://lespass.filaos.re/static/images/biere_52x52.png",
  		  "couleur_texte": None,
  		  "methode_name": "VenteArticle",
  		  "methode_choices": "VT",
  		  "archive": False,
  		  "bt_groupement": {
  		  	"moyens_paiement": "espece|carte_bancaire|nfc|CH",
  		    "besoin_tag_id": "nfc",
  		    "groupe": "groupe1",
  		    "nb_commande_max": 1000
  		  },
  		  "afficher_les_prix": True,
  		  "nom_module": "vue_pv",
  		  "monnaie_principale_name": "TestCoin",
  		  "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  		  "class_categorie": "pression"
  	  },
  	  {
  	    "id": "855b9cc1-3ece-488a-8783-7b782d4151fb",
  	    "name": "Pression 50",
  	    "prix": 2.5,
  	    "poid_liste": 29,
  	    "categorie": {
  	      "id": 9,
  	      "name": "Pression",
  	      "poid_liste": 10,
  	      "icon": "fa-beer",
  	      "couleur_backgr": "#f6cd61",
  	      "couleur_texte": None,
  	      "groupements": [2],
  	      "tva": {
  	        "name": "Alcool",
  	        "taux": "20.00"
  	      }
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "VenteArticle",
  	    "methode_choices": "VT",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|carte_bancaire|nfc|CH",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe1",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "pression"
  	  },
  	  {
  	    "id": "8a75f2d2-9d3f-4ca7-9367-13b0afa19bca",
  	    "name": "Eau 50cL",
  	    "prix": 1,
  	    "poid_liste": 30,
  	    "categorie": {
  	      "id": 8,
  	      "name": "Soft",
  	      "poid_liste": 9,
  	      "icon": "fa-coffee",
  	      "couleur_backgr": "#337ab7",
  	      "couleur_texte": None,
  	      "groupements": [2],
  	      "tva": {
  	        "name": "Restauration",
  	        "taux": "10.00"
  	      }
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "VenteArticle",
  	    "methode_choices": "VT",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|carte_bancaire|nfc|CH",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe1",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "soft"
  	  },
  	  {
  	    "id": "7beda12d-4295-49a7-a2fd-81cce64dbeab",
  	    "name": "Eau 1L",
  	    "prix": 1.5,
  	    "poid_liste": 31,
  	    "categorie": {
  	      "id": 8,
  	      "name": "Soft",
  	      "poid_liste": 9,
  	      "icon": "fa-coffee",
  	      "couleur_backgr": "#337ab7",
  	      "couleur_texte": None,
  	      "groupements": [2],
  	      "tva": {
  	      	"name": "Restauration",
  	        "taux": "10.00"
  	      }
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "VenteArticle",
  	    "methode_choices": "VT",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|carte_bancaire|nfc|CH",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe1",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "soft"
  	  },
  	  {
  	    "id": "ffec2f43-44a1-4688-aa32-2959d5fd8c00",
  	    "name": "Café",
  	    "prix": 1,
  	    "poid_liste": 32,
  	    "categorie": {
  	      "id": 8,
  	      "name": "Soft",
  	      "poid_liste": 9,
  	      "icon": "fa-coffee",
  	      "couleur_backgr": "#337ab7",
  	      "couleur_texte": None,
  	      "groupements": [2],
  	      "tva": {
  	          "name": "Restauration",
  	          "taux": "10.00"
  	      }
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "VenteArticle",
  	    "methode_choices": "VT",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|carte_bancaire|nfc|CH",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe1",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "soft"
  	  },
  	  {
  	    "id": "f372cb3e-c487-4f46-8a89-650458d7435f",
  	    "name": "Soft P",
  	    "prix": 1,
  	    "poid_liste": 33,
  	    "categorie": {
  	      "id": 8,
  	      "name": "Soft",
  	      "poid_liste": 9,
  	      "icon": "fa-coffee",
  	      "couleur_backgr": "#337ab7",
  	      "couleur_texte": None,
  	      "groupements": [2],
  	      "tva": {
  	        "name": "Restauration",
  	        "taux": "10.00"
  	      }
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "VenteArticle",
  	    "methode_choices": "VT",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|carte_bancaire|nfc|CH",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe1",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "soft"
  	  },
  	  {
  	    "id": "a5035dc2-17d7-496e-a614-6cd503c1e800",
  	    "name": "Soft G",
  	    "prix": 1.5,
  	    "poid_liste": 34,
  	    "categorie": {
  	      "id": 8,
  	      "name": "Soft",
  	      "poid_liste": 9,
  	      "icon": "fa-coffee",
  	      "couleur_backgr": "#337ab7",
  	      "couleur_texte": None,
  	      "groupements": [2],
  	      "tva": {
  	        "name": "Restauration",
  	        "taux": "10.00"
  	      }
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "VenteArticle",
  	    "methode_choices": "VT",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|carte_bancaire|nfc|CH",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe1",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "soft"
  	  },
  	  {
				"id": "e183504e-b98d-409a-9cca-618fec771f6e",
  	    "name": "Guinness",
  	    "prix": 4.99,
  	    "poid_liste": 35,
  	    "categorie": {
  	      "id": 10,
  	      "name": "Bieres Btl",
  	      "poid_liste": 11,
  	      "icon": "fa-wine-bottle",
  	      "couleur_backgr": "#00FF00",
  	      "couleur_texte": None,
  	      "groupements": [2],
  	      "tva": {
  	        "name": "Alcool",
  	        "taux": "20.00"
  	      }
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "VenteArticle",
  	    "methode_choices": "VT",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|carte_bancaire|nfc|CH",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe1",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "bieres-btl"
  	  },
  	  {
  	    "id": "9de6ba60-d939-4658-b235-b13ea322b299",
  	    "name": "Despé",
  	    "prix": 3.2,
  	    "poid_liste": 36,
  	    "categorie": {
  	      "id": 10,
  	      "name": "Bieres Btl",
  	      "poid_liste": 11,
  	      "icon": "fa-wine-bottle",
  	      "couleur_backgr": "#00FF00",
  	      "couleur_texte": None,
  	      "groupements": [2],
  	      "tva": {
  	        "name": "Alcool",
  	        "taux": "20.00"
  	      }
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "VenteArticle",
  	    "methode_choices": "VT",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|carte_bancaire|nfc|CH",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe1",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "bieres-btl"
  	  },
			{
  	    "id": "61214857-0e75-4eee-85cb-a1d0154788cc",
  	    "name": "Chimay Bleue",
  	    "prix": 2.8,
  	    "poid_liste": 37,
  	    "categorie": {
  	      "id": 10,
  	      "name": "Bieres Btl",
  	      "poid_liste": 11,
  	      "icon": "fa-wine-bottle",
  	      "couleur_backgr": "#00FF00",
  	      "couleur_texte": None,
  	      "groupements": [2],
  	      "tva": {
  	        "name": "Alcool",
  	        "taux": "20.00"
  	      }
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "VenteArticle",
  	    "methode_choices": "VT",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|carte_bancaire|nfc|CH",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe1",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "bieres-btl"
  	  },
  	  {
  	    "id": "6afe6ea7-38bc-4278-8024-43996c51c5e4",
  	    "name": "Chimay Rouge",
  	    "prix": 2.6,
  	    "poid_liste": 38,
  	    "categorie": {
  	      "id": 10,
  	      "name": "Bieres Btl",
  	      "poid_liste": 11,
  	      "icon": "fa-wine-bottle",
  	      "couleur_backgr": "#00FF00",
  	      "couleur_texte": None,
  	      "groupements": [2],
  	      "tva": {
  	        "name": "Alcool",
  	        "taux": "20.00"
  	      }
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "VenteArticle",
  	    "methode_choices": "VT",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|carte_bancaire|nfc|CH",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe1",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "bieres-btl"
  	  },
  	  {
  	    "id": "12549d06-62b9-4742-8529-3cbf040783c0",
  	    "name": "CdBoeuf",
  	    "prix": 25,
  	    "poid_liste": 39,
  	    "categorie": {
  	      "id": 11,
  	      "name": "Menu",
  	      "poid_liste": 12,
  	      "icon": "fa-hamburger",
  	      "couleur_backgr": "#FF0000",
  	      "couleur_texte": None,
  	      "groupements": [1],
  	      "tva": {
  	        "name": "Run Alcool",
  	        "taux": "8.50"
  	      }
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "VenteArticle",
  	    "methode_choices": "VT",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|carte_bancaire|nfc|CH",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe1",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "menu"
  	  },
  	  {
  	    "id": "8f8bf701-10aa-4943-9368-6c1a0ccf253c",
  	    "name": "Gateau",
  	    "prix": 8,
  	    "poid_liste": 40,
  	    "categorie": {
  	      "id": 12,
  	      "name": "Dessert",
  	      "poid_liste": 13,
  	      "icon": "fa-birthday-cake",
  	      "couleur_backgr": "#E64A19",
  	      "couleur_texte": None,
  	      "groupements": [1],
  	      "tva": {
  	        "name": "Run Resto",
  	        "taux": "2.10"
  	      }
  	    },
  	    "url_image": None,
  	    "couleur_texte": None,
  	    "methode_name": "VenteArticle",
  	    "methode_choices": "VT",
  	    "archive": False,
  	    "bt_groupement": {
  	      "moyens_paiement": "espece|carte_bancaire|nfc|CH",
  	      "besoin_tag_id": "nfc",
  	      "groupe": "groupe1",
  	      "nb_commande_max": 1000
  	    },
  	    "afficher_les_prix": True,
  	    "nom_module": "vue_pv",
  	    "monnaie_principale_name": "TestCoin",
  	    "pv": "0e724e72-3399-4642-8cb3-3df4eff94182",
  	    "class_categorie": "dessert"
  	  }
		],
  	"icon": "fa-beer",
	},
	{
    "id": "0877636e-dae1-411f-806b-87ce0560705d",
    "name": "Resto",
    "poid_liste": 2,
    "comportement": "A",
    "afficher_les_prix": True,
    "accepte_especes": True,
    "accepte_carte_bancaire": True,
    "accepte_cheque": False,
    "accepte_commandes": True,
    "service_direct": False,
    "articles": [
      {
        "id": "8f08b90d-d3f0-49da-9dbd-8be795f689ef",
        "name": "Retour Consigne",
        "prix": -1,
        "poid_liste": 16,
        "categorie": {
          "id": 4,
          "name": "Consigne",
          "poid_liste": 5,
          "icon": "fa-recycle",
          "couleur_backgr": "#FFFFFF",
          "couleur_texte": "#000000",
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "RetourConsigne",
        "methode_choices": "CR",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|nfc",
          "besoin_tag_id": "nfc",
          "groupe": "groupe2",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "consigne"
      },
      {
        "id": "67d231cd-d1c2-4bf3-ac51-18af778b4f8c",
        "name": "Pression 33",
        "prix": 2,
        "poid_liste": 28,
        "categorie": {
          "id": 9,
          "name": "Pression",
          "poid_liste": 10,
          "icon": "fa-beer",
          "couleur_backgr": "#f6cd61",
          "couleur_texte": None,
          "groupements": [2],
          "tva": {
            "name": "Alcool",
            "taux": "20.00"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_group,ment": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "pression"
      },
      {
        "id": "855b9cc1-3ece-488a-8783-7b782d4151fb",
        "name": "Pression 50",
        "prix": 2.5,
        "poid_liste": 29,
        "categorie": {
          "id": 9,
          "name": "Pression",
          "poid_liste": 10,
          "icon": "fa-beer",
          "couleur_backgr": "#f6cd61",
          "couleur_texte": None,
          "groupements": [2],
          "tva": {
            "name": "Alcool",
            "taux": "20.00"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "pression"
      },
      {
        "id": "8a75f2d2-9d3f-4ca7-9367-13b0afa19bca",
        "name": "Eau 50cL",
        "prix": 1,
        "poid_liste": 30,
        "categorie": {
          "id": 8,
          "name": "Soft",
          "poid_liste": 9,
          "icon": "fa-coffee",
          "couleur_backgr": "#337ab7",
          "couleur_texte": None,
          "groupements": [2],
          "tva": {
            "name": "Restauration",
            "taux": "10.00"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "soft"
      },
      {
        "id": "7beda12d-4295-49a7-a2fd-81cce64dbeab",
        "name": "Eau 1L",
        "prix": 1.5,
        "poid_liste": 31,
        "categorie": {
            "id": 8,
            "name": "Soft",
            "poid_liste": 9,
            "icon": "fa-coffee",
            "couleur_backgr": "#337ab7",
            "couleur_texte": None,
            "groupements": [2],
            "tva": {
              "name": "Restauration",
              "taux": "10.00"
            }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "soft"
      },
      {
        "id": "ffec2f43-44a1-4688-aa32-2959d5fd8c00",
        "name": "Café",
        "prix": 1,
        "poid_liste": 32,
        "categorie": {
          "id": 8,
          "name": "Soft",
          "poid_liste": 9,
          "icon": "fa-coffee",
          "couleur_backgr": "#337ab7",
          "couleur_texte": None,
          "groupements": [2],
          "tva": {
            "name": "Restauration",
            "taux": "10.00"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "soft"
      },
      {
        "id": "f372cb3e-c487-4f46-8a89-650458d7435f",
        "name": "Soft P",
        "prix": 1,
        "poid_liste": 33,
        "categorie": {
          "id": 8,
          "name": "Soft",
          "poid_liste": 9,
          "icon": "fa-coffee",
          "couleur_backgr": "#337ab7",
          "couleur_texte": None,
          "groupements": [2],
          "tva": {
            "name": "Restauration",
            "taux": "10.00"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "soft"
      },
      {
        "id": "a5035dc2-17d7-496e-a614-6cd503c1e800",
        "name": "Soft G",
        "prix": 1.5,
        "poid_liste": 34,
        "categorie": {
          "id": 8,
          "name": "Soft",
          "poid_liste": 9,
          "icon": "fa-coffee",
          "couleur_backgr": "#337ab7",
          "couleur_texte": None,
          "groupements": [2],
          "tva": {
            "name": "Restauration",
            "taux": "10.00"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "soft"
      },
      {
        "id": "e183504e-b98d-409a-9cca-618fec771f6e",
        "name": "Guinness",
        "prix": 4.99,
        "poid_liste": 35,
        "categorie": {
          "id": 10,
          "name": "Bieres Btl",
          "poid_liste": 11,
          "icon": "fa-wine-bottle",
          "couleur_backgr": "#00FF00",
          "couleur_texte": None,
          "groupements": [2],
          "tva": {
            "name": "Alcool",
            "taux": "20.00"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "bieres-btl"
      },
      {
        "id": "9de6ba60-d939-4658-b235-b13ea322b299",
        "name": "Despé",
        "prix": 3.2,
        "poid_liste": 36,
        "categorie": {
          "id": 10,
          "name": "Bieres Btl",
          "poid_liste": 11,
          "icon": "fa-wine-bottle",
          "couleur_backgr": "#00FF00",
          "couleur_texte": None,
          "groupements": [2],
          "tva": {
            "name": "Alcool",
            "taux": "20.00"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "bieres-btl"
      },
			{
        "id": "61214857-0e75-4eee-85cb-a1d0154788cc",
        "name": "Chimay Bleue",
        "prix": 2.8,
        "poid_liste": 37,
        "categorie": {
          "id": 10,
          "name": "Bieres Btl",
          "poid_liste": 11,
          "icon": "fa-wine-bottle",
          "couleur_backgr": "#00FF00",
          "couleur_texte": None,
          "groupements": [2],
          "tva": {
            "name": "Alcool",
            "taux": "20.00"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "bieres-btl"
    	},
    	{
        "id": "6afe6ea7-38bc-4278-8024-43996c51c5e4",
        "name": "Chimay Rouge",
        "prix": 2.6,
        "poid_liste": 38,
        "categorie": {
          "id": 10,
          "name": "Bieres Btl",
          "poid_liste": 11,
          "icon": "fa-wine-bottle",
          "couleur_backgr": "#00FF00",
          "couleur_texte": None,
          "groupements": [2],
          "tva": {
            "name": "Alcool",
            "taux": "20.00"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "bieres-btl"
    	},
    	{
        "id": "12549d06-62b9-4742-8529-3cbf040783c0",
        "name": "CdBoeuf",
        "prix": 25,
        "poid_liste": 39,
        "categorie": {
          "id": 11,
          "name": "Menu",
          "poid_liste": 12,
          "icon": "fa-hamburger",
          "couleur_backgr": "#FF0000",
          "couleur_texte": None,
          "groupements": [1],
          "tva": {
            "name": "Run Alcool",
            "taux": "8.50"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "menu"
    	},
    	{
        "id": "8f8bf701-10aa-4943-9368-6c1a0ccf253c",
        "name": "Gateau",
        "prix": 8,
        "poid_liste": 40,
        "categorie": {
          "id": 12,
          "name": "Dessert",
          "poid_liste": 13,
          "icon": "fa-birthday-cake",
          "couleur_backgr": "#E64A19",
          "couleur_texte": None,
          "groupements": [1],
          "tva": {
            "name": "Run Resto",
            "taux": "2.10"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "0877636e-dae1-411f-806b-87ce0560705d",
        "class_categorie": "dessert"
    	}
		],
  	"icon": "fa-hamburger"
  },
	{
    "id": "7d4e787e-a238-4f3b-adb6-b14a9d7ccc73",
    "name": "Test",
    "poid_liste": 5,
    "comportement": "A",
    "afficher_les_prix": True,
    "accepte_especes": True,
    "accepte_carte_bancaire": True,
    "accepte_cheque": False,
    "accepte_commandes": True,
    "service_direct": True,
    "articles": [
      {
        "id": "c25e4191-8ac5-425d-897a-017492a13836",
        "name": "Retour Consigne bis",
        "prix": -1,
        "poid_liste": 41,
        "categorie": None,
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "RetourConsigne",
        "methode_choices": "CR",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|nfc",
          "besoin_tag_id": "nfc",
          "groupe": "groupe2",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "7d4e787e-a238-4f3b-adb6-b14a9d7ccc73"
      },
      {
        "id": "dcb08c46-9b0d-4aca-9de8-b50ebde80a0d",
        "name": "Retour Consigne Rebis",
        "prix": -1,
        "poid_liste": 42,
        "categorie": None,
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "RetourConsigne",
        "methode_choices": "CR",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|nfc",
          "besoin_tag_id": "nfc",
          "groupe": "groupe2",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "7d4e787e-a238-4f3b-adb6-b14a9d7ccc73"
      },
      {
        "id": "be5158ad-b97e-435d-9d8b-f4446f7801ae",
        "name": "Jeux ou acteurs et non-acteurs",
        "prix": 21,
        "poid_liste": 43,
        "categorie": {
          "id": 11,
          "name": "Menu",
          "poid_liste": 12,
          "icon": "fa-hamburger",
          "couleur_backgr": "#FF0000",
          "couleur_texte": None,
          "groupements": [1],
          "tva": {
            "name": "Run Alcool",
            "taux": "8.50"
          }
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "7d4e787e-a238-4f3b-adb6-b14a9d7ccc73",
        "class_categorie": "menu"
      }
    ],
    "icon": None
	},
	{
    "id": "789df895-e22b-4837-828e-0fe99fb43dcf",
    "name": "Kiosque",
    "poid_liste": 10,
    "comportement": "K",
    "afficher_les_prix": True,
    "accepte_especes": True,
    "accepte_carte_bancaire": True,
    "accepte_cheque": False,
    "accepte_commandes": True,
    "service_direct": True,
    "articles": [],
    "icon": None
	},
	{
    "id": "12083d94-cd0e-4839-bce8-6a9838efc735",
    "name": "Cashless",
    "poid_liste": 200,
    "comportement": "C",
    "afficher_les_prix": True,
    "accepte_especes": True,
    "accepte_carte_bancaire": True,
    "accepte_cheque": False,
    "accepte_commandes": False,
    "service_direct": True,
    "articles": [
      {
        "id": "90eb4507-1c55-4d87-ad6c-bf6ccd35b532",
        "name": "TestCoin +0.1",
        "prix": 0.1,
        "poid_liste": 8,
        "categorie": {
          "id": 3,
          "name": "Cashless",
          "poid_liste": 4,
          "icon": "fa-euro-sign",
          "couleur_backgr": "#E64A19",
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "AjoutMonnaieVirtuelle",
        "methode_choices": "RE",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|CH",
          "besoin_tag_id": "tout",
          "groupe": "groupe4",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
        "class_categorie": "cashless"
      },
      {
        "id": "96b0f7a1-e4d0-4c21-afea-4b68f08477ec",
        "name": "TestCoin +0.5",
        "prix": 0.5,
        "poid_liste": 9,
        "categorie": {
          "id": 3,
          "name": "Cashless",
          "poid_liste": 4,
          "icon": "fa-euro-sign",
          "couleur_backgr": "#E64A19",
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "AjoutMonnaieVirtuelle",
        "methode_choices": "RE",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|CH",
          "besoin_tag_id": "tout",
          "groupe": "groupe4",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
        "class_categorie": "cashless"
      },
      {
        "id": "e247df33-d61c-4fda-b56c-33e84023ae6c",
        "name": "TestCoin +1",
        "prix": 1,
        "poid_liste": 10,
        "categorie": {
          "id": 3,
          "name": "Cashless",
          "poid_liste": 4,
          "icon": "fa-euro-sign",
          "couleur_backgr": "#E64A19",
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "AjoutMonnaieVirtuelle",
        "methode_choices": "RE",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|CH",
          "besoin_tag_id": "tout",
          "groupe": "groupe4",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
        "class_categorie": "cashless"
      },
      {
        "id": "3816bf00-b2c7-41bf-a966-6d4be002af92",
        "name": "TestCoin +5",
        "prix": 5,
        "poid_liste": 11,
        "categorie": {
          "id": 3,
          "name": "Cashless",
          "poid_liste": 4,
          "icon": "fa-euro-sign",
          "couleur_backgr": "#E64A19",
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "AjoutMonnaieVirtuelle",
        "methode_choices": "RE",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|CH",
          "besoin_tag_id": "tout",
          "groupe": "groupe4",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
        "class_categorie": "cashless"
      },
      {
        "id": "5198f675-883a-401f-8e0c-b56393e4d0c4",
        "name": "TestCoin +10",
        "prix": 10,
        "poid_liste": 12,
        "categorie": {
          "id": 3,
          "name": "Cashless",
          "poid_liste": 4,
          "icon": "fa-euro-sign",
          "couleur_backgr": "#E64A19",
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "AjoutMonnaieVirtuelle",
        "methode_choices": "RE",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|CH",
          "besoin_tag_id": "tout",
          "groupe": "groupe4",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
        "class_categorie": "cashless"
      },
      {
        "id": "507a89d6-e9eb-46b5-add2-5e6f2d393776",
        "name": "TestCoin +20",
        "prix": 20,
        "poid_liste": 13,
        "categorie": {
          "id": 3,
          "name": "Cashless",
          "poid_liste": 4,
          "icon": "fa-euro-sign",
          "couleur_backgr": "#E64A19",
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "AjoutMonnaieVirtuelle",
        "methode_choices": "RE",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|CH",
          "besoin_tag_id": "tout",
          "groupe": "groupe4",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
        "class_categorie": "cashless"
      },
      {
        "id": "accb493a-5fde-4e02-934e-0df8b4152791",
        "name": "TestCoin +50",
        "prix": 50,
        "poid_liste": 14,
        "categorie": {
          "id": 3,
          "name": "Cashless",
          "poid_liste": 4,
          "icon": "fa-euro-sign",
          "couleur_backgr": "#E64A19",
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "AjoutMonnaieVirtuelle",
        "methode_choices": "RE",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|CH",
          "besoin_tag_id": "tout",
          "groupe": "groupe4",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
        "class_categorie": "cashless"
      },
      {
        "id": "c22f80fb-d16f-475f-9fdb-3a08a18b4f6c",
        "name": "Consigne",
        "prix": 1,
        "poid_liste": 15,
        "categorie": {
          "id": 4,
          "name": "Consigne",
          "poid_liste": 5,
          "icon": "fa-recycle",
          "couleur_backgr": "#FFFFFF",
          "couleur_texte": "#000000",
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "VenteArticle",
        "methode_choices": "VT",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|nfc|CH",
          "besoin_tag_id": "nfc",
          "groupe": "groupe1",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
        "class_categorie": "consigne"
      },
      {
        "id": "8f08b90d-d3f0-49da-9dbd-8be795f689ef",
        "name": "Retour Consigne",
        "prix": -1,
        "poid_liste": 16,
        "categorie": {
          "id": 4,
          "name": "Consigne",
          "poid_liste": 5,
          "icon": "fa-recycle",
          "couleur_backgr": "#FFFFFF",
          "couleur_texte": "#000000",
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "RetourConsigne",
        "methode_choices": "CR",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|nfc",
          "besoin_tag_id": "nfc",
          "groupe": "groupe2",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
        "class_categorie": "consigne"
      },
			{
    		"id": "18496268-d8e0-472a-b550-42b6fcedf642",
    		"name": "Cashback",
    		"prix": 10.5,
    		"poid_liste": 17,
    		"categorie": {
    		  "id": 4,
    		  "name": "Consigne",
    		  "poid_liste": 5,
    		  "icon": "fa-recycle",
    		  "couleur_backgr": "#FFFFFF",
    		  "couleur_texte": "#000000",
    		  "groupements": [],
    		  "tva": None
    		},
    		"url_image": None,
    		"couleur_texte": None,
    		"methode_name": "VenteArticle",
    		"methode_choices": "HB",
    		"archive": False,
    		"bt_groupement": {
    		  "moyens_paiement": "espece|carte_bancaire|nfc|CH",
    		  "besoin_tag_id": "nfc",
    		  "groupe": "groupe1",
    		  "nb_commande_max": 1000
    		},
    		"afficher_les_prix": True,
    		"nom_module": "vue_pv",
    		"monnaie_principale_name": "TestCoin",
    		"pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
    		"class_categorie": "consigne"
			},
			{
				"id": "7aa9d9fc-3e2f-4a4b-948a-cf47701e9035",
				"name": "TestCoin Cadeau +0.1",
				"prix": 0.1,
				"poid_liste": 18,
				"categorie": {
					"id": 5,
					"name": "Cadeau",
					"poid_liste": 6,
					"icon": "fa-gift",
					"couleur_backgr": "#FF00FF",
					"couleur_texte": None,
					"groupements": [],
					"tva": None
				},
				"url_image": None,
				"couleur_texte": None,
				"methode_name": "AjoutMonnaieVirtuelleCadeau",
				"methode_choices": "RC",
				"archive": False,
				"bt_groupement": {
					"moyens_paiement": "",
					"besoin_tag_id": "tout",
					"groupe": "groupe5",
					"nb_commande_max": 1000
				},
				"afficher_les_prix": True,
				"nom_module": "vue_pv",
				"monnaie_principale_name": "TestCoin",
				"pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
				"class_categorie": "cadeau"
			},
			{
    		"id": "676a91cc-9198-45a2-bbf0-b35370974a5d",
    		"name": "TestCoin Cadeau +0.5",
    		"prix": 0.5,
    		"poid_liste": 19,
    		"categorie": {
    		  "id": 5,
    		  "name": "Cadeau",
    		  "poid_liste": 6,
    		  "icon": "fa-gift",
    		  "couleur_backgr": "#FF00FF",
    		  "couleur_texte": None,
    		  "groupements": [],
    		  "tva": None
    		},
    		"url_image": None,
    		"couleur_texte": None,
    		"methode_name": "AjoutMonnaieVirtuelleCadeau",
    		"methode_choices": "RC",
    		"archive": False,
    		"bt_groupement": {
    		  "moyens_paiement": "",
    		  "besoin_tag_id": "tout",
    		  "groupe": "groupe5",
    		  "nb_commande_max": 1000
    		},
    		"afficher_les_prix": True,
    		"nom_module": "vue_pv",
    		"monnaie_principale_name": "TestCoin",
    		"pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
    		"class_categorie": "cadeau"
			},
			{
    		"id": "2f020719-ba1f-440c-b1b5-51fc2d338749",
    		"name": "TestCoin Cadeau +1",
    		"prix": 1,
    		"poid_liste": 20,
    		"categorie": {
    		  "id": 5,
    		  "name": "Cadeau",
    		  "poid_liste": 6,
    		  "icon": "fa-gift",
    		  "couleur_backgr": "#FF00FF",
    		  "couleur_texte": None,
    		  "groupements": [],
    		  "tva": None
    		},
    		"url_image": None,
    		"couleur_texte": None,
    		"methode_name": "AjoutMonnaieVirtuelleCadeau",
    		"methode_choices": "RC",
    		"archive": False,
    		"bt_groupement": {
    		  "moyens_paiement": "",
    		  "besoin_tag_id": "tout",
    		  "groupe": "groupe5",
    		  "nb_commande_max": 1000
    		},
    		"afficher_les_prix": True,
    		"nom_module": "vue_pv",
    		"monnaie_principale_name": "TestCoin",
    		"pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
    		"class_categorie": "cadeau"
			},
			{
    		"id": "c83a08ae-0ebe-410e-b9aa-c472eb7f1b44",
    		"name": "TestCoin Cadeau +5",
    		"prix": 5,
    		"poid_liste": 21,
    		"categorie": {
    		  "id": 5,
    		  "name": "Cadeau",
    		  "poid_liste": 6,
    		  "icon": "fa-gift",
    		  "couleur_backgr": "#FF00FF",
    		  "couleur_texte": None,
    		  "groupements": [],
    		  "tva": None
    		},
    		"url_image": None,
    		"couleur_texte": None,
    		"methode_name": "AjoutMonnaieVirtuelleCadeau",
    		"methode_choices": "RC",
    		"archive": False,
    		"bt_groupement": {
    		  "moyens_paiement": "",
    		  "besoin_tag_id": "tout",
    		  "groupe": "groupe5",
    		  "nb_commande_max": 1000
    		},
    		"afficher_les_prix": True,
    		"nom_module": "vue_pv",
    		"monnaie_principale_name": "TestCoin",
    		"pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
    		"class_categorie": "cadeau"
			},
			{
    		"id": "6e82efae-f6b7-4eb3-a8f4-111720bd55bc",
    		"name": "TestCoin Cadeau +10",
    		"prix": 10,
    		"poid_liste": 22,
    		"categorie": {
    		  "id": 5,
    		  "name": "Cadeau",
    		  "poid_liste": 6,
    		  "icon": "fa-gift",
    		  "couleur_backgr": "#FF00FF",
    		  "couleur_texte": None,
    		  "groupements": [],
    		  "tva": None
    		},
    		"url_image": None,
    		"couleur_texte": None,
    		"methode_name": "AjoutMonnaieVirtuelleCadeau",
    		"methode_choices": "RC",
    		"archive": False,
    		"bt_groupement": {
    		  "moyens_paiement": "",
    		  "besoin_tag_id": "tout",
    		  "groupe": "groupe5",
    		  "nb_commande_max": 1000
    		},
    		"afficher_les_prix": True,
    		"nom_module": "vue_pv",
    		"monnaie_principale_name": "TestCoin",
    		"pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
    		"class_categorie": "cadeau"
			},
			{
    		"id": "c1e15bf4-ce05-4252-94cd-4f4ec2e0f7ca",
    		"name": "TestCoin Cadeau +20",
    		"prix": 20,
    		"poid_liste": 23,
    		"categorie": {
    		  "id": 5,
    		  "name": "Cadeau",
    		  "poid_liste": 6,
    		  "icon": "fa-gift",
    		  "couleur_backgr": "#FF00FF",
    		  "couleur_texte": None,
    		  "groupements": [],
    		  "tva": None
    		},
    		"url_image": None,
    		"couleur_texte": None,
    		"methode_name": "AjoutMonnaieVirtuelleCadeau",
    		"methode_choices": "RC",
    		"archive": False,
    		"bt_groupement": {
    		  "moyens_paiement": "",
    		  "besoin_tag_id": "tout",
    		  "groupe": "groupe5",
    		  "nb_commande_max": 1000
    		},
    		"afficher_les_prix": True,
    		"nom_module": "vue_pv",
    		"monnaie_principale_name": "TestCoin",
    		"pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
    		"class_categorie": "cadeau"
			},
			{
    		"id": "f03dc538-4643-4e9c-8f17-c37977e61fcb",
    		"name": "VIDER CARTE",
    		"prix": 0,
    		"poid_liste": 24,
    		"categorie": {
    		  "id": 6,
    		  "name": "Danger",
    		  "poid_liste": 7,
    		  "icon": "fa-radiation",
    		  "couleur_backgr": "#FF0000",
    		  "couleur_texte": None,
    		  "groupements": [],
    		  "tva": None
    		},
    		"url_image": None,
    		"couleur_texte": None,
    		"methode_name": "ViderCarte",
    		"methode_choices": "VC",
    		"archive": False,
    		"bt_groupement": {
    		  "moyens_paiement": "",
    		  "besoin_tag_id": "tout",
    		  "groupe": "groupe7",
    		  "nb_commande_max": 1
    		},
    		"afficher_les_prix": True,
    		"nom_module": "vue_pv",
    		"monnaie_principale_name": "TestCoin",
    		"pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
    		"class_categorie": "danger"
			},
			{
    		"id": "817ecf5a-bb37-40f2-ba12-d8d3863e296a",
    		"name": "VOID CARTE",
    		"prix": 0,
    		"poid_liste": 25,
    		"categorie": {
    		  "id": 6,
    		  "name": "Danger",
    		  "poid_liste": 7,
    		  "icon": "fa-radiation",
    		  "couleur_backgr": "#FF0000",
    		  "couleur_texte": None,
    		  "groupements": [],
    		  "tva": None
    		},
    		"url_image": None,
    		"couleur_texte": None,
    		"methode_name": "ViderCarte",
    		"methode_choices": "VV",
    		"archive": False,
    		"bt_groupement": {
    		  "moyens_paiement": "",
    		  "besoin_tag_id": "tout",
    		  "groupe": "groupe7",
    		  "nb_commande_max": 1
    		},
    		"afficher_les_prix": True,
    		"nom_module": "vue_pv",
    		"monnaie_principale_name": "TestCoin",
    		"pv": "12083d94-cd0e-4839-bce8-6a9838efc735",
    		"class_categorie": "danger"
			},
			{
    		"id": "42ffe511-d880-4964-9b96-0981a9fe4071",
    		"name": "Paiement Fractionné",
    		"prix": 1,
    		"poid_liste": 26,
    		"categorie": None,
    		"url_image": None,
    		"couleur_texte": None,
    		"methode_name": "PaiementFractionne",
    		"methode_choices": "FR",
    		"archive": False
			}
		],
		"icon": "fa-euro-sign"
	},
	{
    "id": "f5c1b847-5a13-4790-b7f6-fdeccde90a98",
    "name": "Adhésions",
    "poid_liste": 9,
    "comportement": "A",
    "afficher_les_prix": True,
    "accepte_especes": True,
    "accepte_carte_bancaire": True,
    "accepte_cheque": False,
    "accepte_commandes": True,
    "service_direct": True,
    "articles": [
      {
        "id": "c57aa770-899f-4de0-96bd-27d710ee6fc8",
        "name": "Badgeuse co-working (Le Tiers-Lustre) Passage",
        "prix": 0,
        "poid_liste": 2,
        "categorie": {
          "id": 1,
          "name": "Badge",
          "poid_liste": 2,
          "icon": None,
          "couleur_backgr": None,
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "BG",
        "methode_choices": "BG",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "",
          "besoin_tag_id": "tout",
          "groupe": "groupe6",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "f5c1b847-5a13-4790-b7f6-fdeccde90a98",
        "class_categorie": "badge"
      },
      {
        "id": "3efd3761-a8b6-4cbc-8291-156985b8c207",
        "name": "Adhésion (Le Tiers-Lustre) Annuelle",
        "prix": 20,
        "poid_liste": 3,
        "categorie": {
          "id": 2,
          "name": "Adhésions",
          "poid_liste": 3,
          "icon": None,
          "couleur_backgr": None,
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "Adhesion",
        "methode_choices": "AD",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|CH",
          "besoin_tag_id": "tout",
          "groupe": "groupe3",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "f5c1b847-5a13-4790-b7f6-fdeccde90a98",
        "class_categorie": "adhesions"
      },
      {
        "id": "07192e0e-3596-417d-a2ba-ac2f3d17e566",
        "name": "Adhésion (Le Tiers-Lustre) Mensuelle",
        "prix": 2,
        "poid_liste": 4,
        "categorie": {
          "id": 2,
          "name": "Adhésions",
          "poid_liste": 3,
          "icon": None,
          "couleur_backgr": None,
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "Adhesion",
        "methode_choices": "AD",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|CH",
          "besoin_tag_id": "tout",
          "groupe": "groupe3",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "f5c1b847-5a13-4790-b7f6-fdeccde90a98",
        "class_categorie": "adhesions"
      },
      {
        "id": "bc489e27-c97f-49ca-a32a-7ff5af943e98",
        "name": "Adhésion (Le Tiers-Lustre) Prix libre",
        "prix": 1,
        "poid_liste": 5,
        "categorie": {
          "id": 2,
          "name": "Adhésions",
          "poid_liste": 3,
          "icon": None,
          "couleur_backgr": None,
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "Adhesion",
        "methode_choices": "AD",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|CH",
          "besoin_tag_id": "tout",
          "groupe": "groupe3",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "f5c1b847-5a13-4790-b7f6-fdeccde90a98",
        "class_categorie": "adhesions"
      },
      {
        "id": "2351c70b-801b-4d7d-8d0e-5ccd042b8a6a",
        "name": "Panier AMAP (Le Tiers-Lustre) Annuelle",
        "prix": 400,
        "poid_liste": 6,
        "categorie": {
          "id": 2,
          "name": "Adhésions",
          "poid_liste": 3,
          "icon": None,
          "couleur_backgr": None,
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "Adhesion",
        "methode_choices": "AD",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|CH",
          "besoin_tag_id": "tout",
          "groupe": "groupe3",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "f5c1b847-5a13-4790-b7f6-fdeccde90a98",
        "class_categorie": "adhesions"
      },
      {
        "id": "b3bc9e1a-ef96-4871-95f8-241b1e092696",
        "name": "Panier AMAP (Le Tiers-Lustre) Mensuelle",
        "prix": 40,
        "poid_liste": 7,
        "categorie": {
          "id": 2,
          "name": "Adhésions",
          "poid_liste": 3,
          "icon": None,
          "couleur_backgr": None,
          "couleur_texte": None,
          "groupements": [],
          "tva": None
        },
        "url_image": None,
        "couleur_texte": None,
        "methode_name": "Adhesion",
        "methode_choices": "AD",
        "archive": False,
        "bt_groupement": {
          "moyens_paiement": "espece|carte_bancaire|CH",
          "besoin_tag_id": "tout",
          "groupe": "groupe3",
          "nb_commande_max": 1000
        },
        "afficher_les_prix": True,
        "nom_module": "vue_pv",
        "monnaie_principale_name": "TestCoin",
        "pv": "f5c1b847-5a13-4790-b7f6-fdeccde90a98",
        "class_categorie": "adhesions"
        }
    ],
    "icon": None
	}
]

tables = [
  {
    "id": 1,
    "name": "S01",
    "poids": 1,
    "position_top": 0,
    "position_left": 0,
    "categorie": None,
    "statut": "L",
    "ephemere": False,
    "archive": False
  },
  {
    "id": 2,
    "name": "S02",
    "poids": 2,
    "position_top": 0,
    "position_left": 0,
    "categorie": None,
    "statut": "L",
    "ephemere": False,
    "archive": False
  },
  {
    "id": 3,
    "name": "S03",
    "poids": 3,
    "position_top": 0,
    "position_left": 0,
    "categorie": None,
    "statut": "L",
    "ephemere": False,
    "archive": False
  },
  {
    "id": 4,
    "name": "S04",
    "poids": 4,
    "position_top": 0,
    "position_left": 0,
    "categorie": None,
    "statut": "L",
    "ephemere": False,
    "archive": False
  },
  {
    "id": 5,
    "name": "S05",
    "poids": 5,
    "position_top": 0,
    "position_left": 0,
    "categorie": None,
    "statut": "L",
    "ephemere": False,
    "archive": False
  },
  {
    "id": 6,
    "name": "Ex01",
    "poids": 6,
    "position_top": 0,
    "position_left": 0,
    "categorie": None,
    "statut": "L",
    "ephemere": False,
    "archive": False
  },
  {
    "id": 7,
    "name": "Ex02",
    "poids": 7,
    "position_top": 0,
    "position_left": 0,
    "categorie": None,
    "statut": "L",
    "ephemere": False,
    "archive": False
  },
  {
    "id": 8,
    "name": "Ex03",
    "poids": 8,
    "position_top": 0,
    "position_left": 0,
    "categorie": None,
    "statut": "L",
    "ephemere": False,
    "archive": False
  },
  {
    "id": 9,
    "name": "Ex04",
    "poids": 9,
    "position_top": 0,
    "position_left": 0,
    "categorie": None,
    "statut": "L",
    "ephemere": False,
    "archive": False
  },
  {
    "id": 10,
    "name": "Ex05",
    "poids": 10,
    "position_top": 0,
    "position_left": 0,
    "categorie": None,
    "statut": "L",
    "ephemere": False,
    "archive": False
  }
]

responsable = {
  "nom": ["TEST"],
  "uuid": "17896c22-7a60-45f4-a959-175bfc8a5369",
  "edit_mode": True,
}

cards = [
	{
		"type_card": "primary_card",
		"tag_id": settings.DEMO_TAGID_CM,
		"name": "master",
		"pvs_list": [
			{"uuid": "0e724e72-3399-4642-8cb3-3df4eff94182", "name": "Bar 1", "poid_liste": 1, "icon": "fa-beer"},
  		{"uuid": "0877636e-dae1-411f-806b-87ce0560705d", "name": "Resto", "poid_liste": 2, "icon": "fa-hamburger"},
  		{"uuid": "7d4e787e-a238-4f3b-adb6-b14a9d7ccc73", "name": "Test", "poid_liste": 5, "icon": None},
			{"uuid": "789df895-e22b-4837-828e-0fe99fb43dcf", "name": "Kiosque","poid_liste": 10, "icon": None},
			{"uuid": "12083d94-cd0e-4839-bce8-6a9838efc735", "name": "Cashless","poid_liste": 200, "icon": "fa-euro-sign"},
  		{"uuid": "f5c1b847-5a13-4790-b7f6-fdeccde90a98", "name": "Adhésions", "poid_liste": 9, "icon": None}
		],
		'responsable': responsable
	},
  {
		"type_card": "client_card",
		"tag_id": settings.DEMO_TAGID_CLIENT1
	},
  {
		"type_card": "client_card",
		"tag_id": settings.DEMO_TAGID_CLIENT2
	},
  {
		"type_card": "client_card",
		"tag_id": settings.DEMO_TAGID_CLIENT3
	},
]

def get_card_from_tagid(tag_id):
	retour = {"type_card": "unknown", "tag_id": "unknown", "pvs_list": []}
	for card in cards:
		if card["tag_id"] == tag_id:
			retour = card
			break
	return retour

def get_pv_from_uuid(uuid):
	retour = {}
	for pv in pvs:
		if pv["id"] == uuid:
			retour = pv
			break
	return retour
