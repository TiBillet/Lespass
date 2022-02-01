# For example :

domains = {
    "Bisik": ["bisik.django-local.org"],
    "VavangArt": ["vavangart.django-local.org"],
    "La Raffinerie": ["m.django-local.org",
                      "raffinerie.django-local.org"],
    "Demo": ["demo.django-local.org"],
    "3Peaks": ["3peaks.django-local.org"]
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
    "La Raffinerie": {
        1: f"{dir_path}/Raffinerie_G1.csv",
        2: f"{dir_path}/Raffinerie_G2.csv"
    },
    "3Peaks": {
        3: f"{dir_path}/3Peaks_G3.csv"
    }
}
