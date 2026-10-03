#!/usr/bin/env python3
"""
MODE SYNC — extraction.
Trouve les chaines a corriger dans locale/fr et locale/en apres un makemessages :
  - fuzzy (traduction perimee, AFFICHEE -> a corriger)
  - fuites de langue (msgstr vide alors que la source est de l'autre langue)
  - msgstr NON fuzzy ecrit dans la mauvaise langue (ex: francais dans locale/en)

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
from _pohelpers import parse, source_lang, msgstr_wrong_lang

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
    nb_wrong = {"fr": 0, "en": 0}
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

        # msgstr non fuzzy mais ecrit dans la mauvaise langue (fuite affichee).
        # / Non-fuzzy msgstr written in the wrong language (displayed leak).
        wrong_fr = (not fr["fuzzy"]) and fr["msgstr"] != "" and msgstr_wrong_lang(fr["msgstr"], "fr")
        wrong_en = (not en["fuzzy"]) and en["msgstr"] != "" and msgstr_wrong_lang(en["msgstr"], "en")
        if wrong_fr:
            nb_wrong["fr"] += 1
        if wrong_en:
            nb_wrong["en"] += 1

        need_fr = fr["fuzzy"] or wrong_fr or (fr["msgstr"] == "" and lang == "en")
        need_en = en["fuzzy"] or wrong_en or (en["msgstr"] == "" and lang == "fr")
        if not (need_fr or need_en):
            continue

        items.append({
            "i": len(items), "ctx": ctx, "id": mid, "src": lang,
            "nfr": need_fr, "nen": need_en,
            "bad_fr": fr["msgstr"] if (fr["fuzzy"] or wrong_fr) else "",
            "bad_en": en["msgstr"] if (en["fuzzy"] or wrong_en) else "",
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
    print(f"[sync] msgstr dans la mauvaise langue : fr={nb_wrong['fr']} en={nb_wrong['en']}")
    print(f"[sync] workdir={workdir}")

if __name__ == "__main__":
    main()
