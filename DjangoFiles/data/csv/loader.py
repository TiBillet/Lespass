import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve(strict=True).parent


def get_detail_cards(tenant=None, generation=None, demo=None):
    details = [{
        "tenant": "3peaks",
        "generation": 3,
        "path_csv": Path(f"{SCRIPT_DIR}/3Peaks_G3.csv")
    }, {
        "tenant": "bisik",
        "generation": 1,
        "path_csv": Path(f"{SCRIPT_DIR}/Bisik_G1.csv")
    }, {
        "tenant": "bisik",
        "generation": 2,
        "path_csv": Path(f"{SCRIPT_DIR}/Bisik_G2.csv")
    }, {
        "tenant": "demeter",
        "generation": 1,
        "path_csv": Path(f"{SCRIPT_DIR}/Demeter_G1.csv")
    }, {
        "tenant": "raffinerie",
        "generation": 1,
        "path_csv": Path(f"{SCRIPT_DIR}/Raffinerie_G1.csv")
    }, {
        "tenant": "raffinerie",
        "generation": 2,
        "path_csv": Path(f"{SCRIPT_DIR}/Raffinerie_G2.csv")
    }, {
        "tenant": "raffinerie",
        "generation": 3,
        "path_csv": Path(f"{SCRIPT_DIR}/Raffinerie_G3.csv")
    }, {
        "tenant": "vavangart",
        "generation": 1,
        "path_csv": Path(f"{SCRIPT_DIR}/Vavangart_G1.csv")
    }]

    if tenant and generation:
        details = [detail for detail in details if detail['tenant'] == tenant and detail['generation'] == generation]

    if demo:
        details = [{
            "tenant": "demo",
            "generation": 1,
            "path_csv": Path(f"{SCRIPT_DIR}/demo.csv")
        }]

    for detail in details:
        detail: dict
        csv_file = open(detail['path_csv'])
        csv_parser = csv.reader(csv_file)
        list_csv = []
        for line in csv_parser:
            list_csv.append(line)
        detail['cards'] = list_csv

    return details
