
dir_path = "/DjangoFiles/data/csv_betabillet"

# csv line : QRCODE URL, NUMBER PRINTED, NFC FIRST TAG ID
# example :
# https://bisik.tibillet.re/qr/64f854b1-c705-451b-8d73-441f5e3c5593,64F8C6B1,B1EE252A

cards = {
    "Raffinerie": {
        1: f"{dir_path}/Raffinerie_G1.csv",
        2: f"{dir_path}/Raffinerie_G2.csv",
        3: f"{dir_path}/Raffinerie_G3.csv"
    },
}
