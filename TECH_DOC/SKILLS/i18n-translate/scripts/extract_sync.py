#!/usr/bin/env python3
"""
MODE SYNC — extraction.
Trouve les chaines a corriger dans locale/fr et locale/en apres un makemessages :
  - fuzzy (traduction perimee, AFFICHEE -> a corriger)
  - fuites de langue (msgstr vide alors que la source est de l'autre langue)

Les entrees deja correctes (source == langue du fichier, msgstr vide = fallback
gettext OK) sont IGNOREES : c'est ce qui evite des milliers de faux positifs.

Usage:
  python3 extract_sync.py <locale_dir> <workdir> [--batch 45]

Sorties dans <workdir> :
  - work_sync.json   : tous les items (index = champ "i"), pour merge/apply
  - in_<start>.json  : une tranche par lot (ce que chaque agent lira)
  - meta.json        : {mode, total, batch, starts:[...]}
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pohelpers import parse, source_lang

def main():
    locale_dir = sys.argv[1]
    workdir = sys.argv[2]
    batch = 45
    if "--batch" in sys.argv:
        batch = int(sys.argv[sys.argv.index("--batch") + 1])
    os.makedirs(workdir, exist_ok=True)

    fr_po = os.path.join(locale_dir, "fr/LC_MESSAGES/django.po")
    en_po = os.path.join(locale_dir, "en/LC_MESSAGES/django.po")
    fr_e = parse(fr_po)
    en_e = parse(en_po)
    keys = set(fr_e) | set(en_e)

    items = []
    empty = {"msgstr": "", "fuzzy": False, "plural": False, "refs": ""}
    for k in sorted(keys):
        ctx, mid = k
        if mid == "":
            continue  # header
        fr = fr_e.get(k, empty)
        en = en_e.get(k, empty)
        if fr["plural"] or en["plural"]:
            continue  # pluriels : on n'y touche jamais

        lang = source_lang(mid, fr["msgstr"], en["msgstr"], fr["fuzzy"], en["fuzzy"])
        need_fr = fr["fuzzy"] or (fr["msgstr"] == "" and lang == "en")
        need_en = en["fuzzy"] or (en["msgstr"] == "" and lang == "fr")
        if not (need_fr or need_en):
            continue

        items.append({
            "i": len(items), "ctx": ctx, "id": mid, "src": lang,
            "nfr": need_fr, "nen": need_en,
            "bad_fr": fr["msgstr"] if fr["fuzzy"] else "",
            "bad_en": en["msgstr"] if en["fuzzy"] else "",
        })

    # Fichier complet (pour merge + apply)
    json.dump(items, open(os.path.join(workdir, "work_sync.json"), "w",
              encoding="utf-8"), ensure_ascii=False)

    # Tranches par lot (ce que les agents liront — token-frugal)
    starts = []
    for s in range(0, len(items), batch):
        starts.append(s)
        slice_ = items[s:s + batch]
        json.dump(slice_, open(os.path.join(workdir, f"in_{s}.json"), "w",
                  encoding="utf-8"), ensure_ascii=False)

    meta = {"mode": "sync", "total": len(items), "batch": batch, "starts": starts}
    json.dump(meta, open(os.path.join(workdir, "meta.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)

    nfr = sum(1 for x in items if x["nfr"])
    nen = sum(1 for x in items if x["nen"])
    print(f"[sync] items={len(items)} (need_fr={nfr}, need_en={nen}) "
          f"lots={len(starts)} batch={batch}")
    print(f"[sync] workdir={workdir}")

if __name__ == "__main__":
    main()
