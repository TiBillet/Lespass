#!/usr/bin/env python3
"""
Fusionne les fragments out_<start>.json produits par les agents, puis verifie
les placeholders de facon DETERMINISTE (msgid vs traduction).

Marche pour les deux modes (lit meta.json) :
  - sync    : fragments [{i, fr, en}]      -> verifie fr et en selon nfr/nen
  - newlang : fragments [{i, tr}]          -> verifie tr

Usage:
  python3 merge_check.py <workdir>

Sorties :
  - results.json : {"<i>": {...}}  (fr/en  ou  tr)
  - flagged.json : anomalies (vide ou placeholders qui ne correspondent pas)
Code retour 0 si tout couvert, 2 s'il manque des items ou des fragments invalides.
"""
import os, sys, json, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pohelpers import signature

def main():
    workdir = sys.argv[1]
    meta = json.load(open(os.path.join(workdir, "meta.json"), encoding="utf-8"))
    mode = meta["mode"]
    if mode == "sync":
        work = json.load(open(os.path.join(workdir, "work_sync.json"), encoding="utf-8"))
    else:
        work = json.load(open(os.path.join(workdir, f"work_{meta['code']}.json"),
                          encoding="utf-8"))

    merged = {}
    bad_frag = []
    for fp in sorted(glob.glob(os.path.join(workdir, "out_*.json"))):
        try:
            arr = json.load(open(fp, encoding="utf-8"))
        except Exception as e:
            bad_frag.append((os.path.basename(fp), str(e)))
            continue
        for o in arr:
            merged[int(o["i"])] = o

    missing = [it["i"] for it in work if it["i"] not in merged]

    flagged = []
    for it in work:
        i = it["i"]
        if i not in merged:
            continue
        src_sig = signature(it["id"])
        tr = merged[i]
        if mode == "sync":
            checks = []
            if it["nfr"]:
                checks.append(("fr", tr.get("fr")))
            if it["nen"]:
                checks.append(("en", tr.get("en")))
        else:
            checks = [("tr", tr.get("tr"))]
        for lang, val in checks:
            if val is None or val == "":
                flagged.append({"i": i, "lang": lang, "why": "vide",
                                "msgid": it["id"][:100]})
            elif signature(val) != src_sig:
                flagged.append({"i": i, "lang": lang, "why": "placeholder_mismatch",
                                "msgid": it["id"][:140], "trad": val[:140]})

    json.dump(merged, open(os.path.join(workdir, "results.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(flagged, open(os.path.join(workdir, "flagged.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"mode={mode} attendus={len(work)} couverts={len(merged)} "
          f"manquants={len(missing)} anomalies={len(flagged)}")
    if bad_frag:
        print(f"FRAGMENTS INVALIDES : {bad_frag}")
    if missing:
        print(f"MANQUANTS (i) : {missing[:40]}")
    for f in flagged[:40]:
        print("  ", json.dumps(f, ensure_ascii=False)[:200])

    sys.exit(2 if (missing or bad_frag) else 0)

if __name__ == "__main__":
    main()
