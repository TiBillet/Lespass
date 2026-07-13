#!/usr/bin/env python3
"""
MODE NEWLANG — extraction.
Prepare la traduction d'une nouvelle langue <code> depuis zero.
Prerequis : le mainteneur a deja lance `makemessages -l <code>` -> le fichier
locale/<code>/LC_MESSAGES/django.po existe avec des msgstr vides.

Pour CHAQUE chaine a traduire (msgstr vide dans le fichier cible, hors pluriel),
on fournit a l'agent une DOUBLE REFERENCE : le rendu francais ET le rendu anglais.
Voir les deux desambiguise le sens bien mieux qu'une seule langue source.

Usage:
  python3 extract_newlang.py <locale_dir> <code> <workdir> [--batch 45]

Sorties dans <workdir> :
  - work_<code>.json : tous les items (index = "i"), pour merge/apply
  - in_<start>.json  : une tranche par lot
  - meta.json        : {mode, code, total, batch, starts:[...]}
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pohelpers import parse, source_lang

def best_text(mid, entry, src_is_this_lang):
    """Meilleur rendu connu dans une langue : msgstr si present, sinon msgid si source."""
    if entry["msgstr"] and not entry["fuzzy"]:
        return entry["msgstr"]
    if src_is_this_lang:
        return mid
    return ""

def main():
    locale_dir = sys.argv[1]
    code = sys.argv[2]
    workdir = sys.argv[3]
    batch = 45
    if "--batch" in sys.argv:
        batch = int(sys.argv[sys.argv.index("--batch") + 1])
    os.makedirs(workdir, exist_ok=True)

    fr_po = os.path.join(locale_dir, "fr/LC_MESSAGES/django.po")
    en_po = os.path.join(locale_dir, "en/LC_MESSAGES/django.po")
    tgt_po = os.path.join(locale_dir, f"{code}/LC_MESSAGES/django.po")
    if not os.path.exists(tgt_po):
        sys.exit(f"ERREUR : {tgt_po} introuvable. Lance d'abord `makemessages -l {code}` "
                 f"(c'est au mainteneur de le faire).")

    fr_e = parse(fr_po)
    en_e = parse(en_po)
    tgt_e = parse(tgt_po)
    empty = {"msgstr": "", "fuzzy": False, "plural": False, "refs": ""}

    items = []
    for k in sorted(tgt_e):
        ctx, mid = k
        if mid == "":
            continue
        tgt = tgt_e[k]
        if tgt["plural"]:
            continue
        if tgt["msgstr"] != "":
            continue  # deja traduit (reprise possible sans tout refaire)

        fr = fr_e.get(k, empty)
        en = en_e.get(k, empty)
        src = source_lang(mid, fr["msgstr"], en["msgstr"], fr["fuzzy"], en["fuzzy"])
        fr_ref = best_text(mid, fr, src == "fr")
        en_ref = best_text(mid, en, src == "en")

        items.append({
            "i": len(items), "ctx": ctx, "id": mid,
            "fr": fr_ref, "en": en_ref,
        })

    json.dump(items, open(os.path.join(workdir, f"work_{code}.json"), "w",
              encoding="utf-8"), ensure_ascii=False)

    starts = []
    for s in range(0, len(items), batch):
        starts.append(s)
        json.dump(items[s:s + batch], open(os.path.join(workdir, f"in_{s}.json"),
                  "w", encoding="utf-8"), ensure_ascii=False)

    meta = {"mode": "newlang", "code": code, "total": len(items),
            "batch": batch, "starts": starts}
    json.dump(meta, open(os.path.join(workdir, "meta.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"[newlang:{code}] a_traduire={len(items)} lots={len(starts)} batch={batch}")
    print(f"[newlang:{code}] workdir={workdir}")

if __name__ == "__main__":
    main()
