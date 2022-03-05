# For example :

tenants = {
    "m": {
        'short_description': 'Le bar en Beta Test.',
        'long_description': 'Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum ',
        'phone': "0612451245",
        'email': "demo@demo.com",
        'postal_code': '97480',
        'img': 'old_place.jpg',
        'logo': 'pic03.jpg',
        'categorie': 'S',
    },
    "Bisik": {
        'short_description': 'Le café culturel de Saint-Benoit.',
        'long_description': 'Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum ',
        'email': "demo@demo.com",
        'postal_code': '97480',
        'phone': "0612451245",
        'logo': 'bisik2_300.jpg',
        'img': 'project9.jpg',
        'categorie': 'S',
    },
    "Vavang'Art": {
        'short_description': "Le Tiers Lieux de l'entre-deux.",
        'long_description': 'Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum ',
        'email': "demo@demo.com",
        'postal_code': '97480',
        'phone': "0612451245",
        'img': 'raffinerie.jpg',
        'logo': 'raffinerie.png',
        'categorie': 'S',
    },
    "Raffinerie": {
        'domains': ["m", "raffinerie"],
        'short_description': "Friche éco-cultruelle de Savannah",
        'long_description': 'Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum ',
        'email': "demo@demo.com",
        'postal_code': '97480',
        'phone': "0612451245",
        'img': 'raffinerie.jpg',
        'logo': 'raffinerie.png',
        'categorie': 'S',
    },
    "3Peaks": {
        'short_description': "L'asso qui n'a plus de Manapany Festival",
        'long_description': 'Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum ',
        'email': "demo@demo.com",
        'phone': "0612451245",
        'postal_code': '97480',
        'logo': "3peaksLogo.png",
        'img': 'manapanyfestival.jpg',
        'categorie': 'S',
    },

    "Balaphonic Sound System": {
        'short_description': "L'éléphant du balafond",
        'long_description': 'Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum ',
        'email': "demo@demo.com",
        'phone': "0612451245",
        'logo': "bala.jpg",
        'img': 'balafonik-1.jpg',
        'categorie': 'A',

    },
    "Sly Sugar": {
        'short_description': "Raggae Dub Electro, vous reprendrez bien un peu de dub ?",
        'long_description': 'Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum ',
        'img': 'sly-sugar.jpg',
        'logo': 'sly-sugar-logo.jpg',
        'email': "demo@demo.com",
        'phone': "0612451245",
        'categorie': 'A',
    },
    "Ziskakan": {
        'short_description': "Maloya Rock depuis 40ans !",
        'long_description': 'Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum ',
        'img': 'Ziskakan.jpg',
        'logo': 'ziskakan-gilbert.jpg',
        'email': "demo@demo.com",
        'phone': "0612451245",
        'categorie': 'A',
    },
    "Sabouk": {
        'short_description': "Jazz y sabouk dans mon tête",
        'long_description': 'Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum ',
        'img': 'sabouk.jpg',
        'logo': 'sabouk.jpg',
        'email': "demo@demo.com",
        'phone': "0612451245",
        'categorie': 'A',
    },
}

dir_path = "/DjangoFiles/data/csv"

# csv line : QRCODE URL, NUMBER PRINTED, NFC FIRST TAG ID
# example :
# https://bisik.tibillet.re/qr/64f854b1-c705-451b-8d73-441f5e3c5593,64F8C6B1,B1EE252A

cards = {
    "Bisik": {
        1: f"{dir_path}/Bisik_G1.csv",
        2: f"{dir_path}/Bisik_G2.csv"
    },
    "VavangArt": {
        1: f"{dir_path}/Vavangart_G1.csv"
    },
    "Raffinerie": {
        1: f"{dir_path}/Raffinerie_G1.csv",
        2: f"{dir_path}/Raffinerie_G2.csv"
    },
    "3Peaks": {
        3: f"{dir_path}/3Peaks_G3.csv"
    }
}
