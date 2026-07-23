#!/usr/bin/env python3
"""
MODE SYNC — application.
Ecrit les traductions de results.json dans locale/fr et locale/en :
  - pose le msgstr corrige
  - retire le flag `fuzzy` et les indices `#|` (msgid precedent)
  - SAUTE les pluriels et les anomalies placeholders (listees dans flagged.json)

Usage:
  python3 apply_sync.py <locale_dir> <workdir> [--write]
  sans --write : DRY-RUN (compte seulement).
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pohelpers import joinfield, esc

def apply_file(path, lang, key2i, work, results, flagged_keys, write):
    raw = open(path, encoding="utf-8").read()
    chunks = raw.split("\n\n")
    applied = skipped_flag = skipped_plural = 0
    out = []
    for chunk in chunks:
        lines = chunk.split("\n")
        ctx = joinfield(lines, "msgctxt")
        mid = joinfield(lines, "msgid")
        i = key2i.get((ctx, mid))
        is_plural = any(l.startswith("msgid_plural") for l in lines)
        do = False
        if i is not None and not is_plural:
            it = work[i]
            need = it["nfr"] if lang == "fr" else it["nen"]
            val = results.get(str(i), {}).get(lang)
            if need and val not in (None, ""):
                if (i, lang) in flagged_keys:
                    skipped_flag += 1
                else:
                    do = True
        elif i is not None and is_plural:
            it = work[i]
            if (it["nfr"] if lang == "fr" else it["nen"]):
                skipped_plural += 1

        if not do:
            out.append(chunk)
            continue

        val = results[str(i)][lang]
        new_lines = []
        in_msgstr = False
        for l in lines:
            if l.startswith("#|"):
                continue
            if l.startswith("#,"):
                flags = [x.strip() for x in l[2:].split(",") if x.strip() and x.strip() != "fuzzy"]
                if flags:
                    new_lines.append("#, " + ", ".join(flags))
                continue
            if l.startswith("msgstr "):
                in_msgstr = True
                new_lines.append('msgstr "' + esc(val) + '"')
                continue
            if in_msgstr and l.startswith('"'):
                continue
            in_msgstr = False
            new_lines.append(l)
        out.append("\n".join(new_lines))
        applied += 1

    if write:
        open(path, "w", encoding="utf-8").write("\n\n".join(out))
    tag = "(ECRIT)" if write else "(dry-run)"
    print(f"[{lang}] appliquees={applied} skip_anomalie={skipped_flag} "
          f"skip_pluriel={skipped_plural} {tag}")

def main():
    locale_dir = sys.argv[1]
    workdir = sys.argv[2]
    write = "--write" in sys.argv

    work = json.load(open(os.path.join(workdir, "work_sync.json"), encoding="utf-8"))
    results = json.load(open(os.path.join(workdir, "results.json"), encoding="utf-8"))
    flagged = json.load(open(os.path.join(workdir, "flagged.json"), encoding="utf-8"))
    flagged_keys = {(f["i"], f["lang"]) for f in flagged}
    key2i = {(it["ctx"], it["id"]): it["i"] for it in work}

    apply_file(os.path.join(locale_dir, "fr/LC_MESSAGES/django.po"), "fr",
               key2i, work, results, flagged_keys, write)
    apply_file(os.path.join(locale_dir, "en/LC_MESSAGES/django.po"), "en",
               key2i, work, results, flagged_keys, write)
    print(f"Anomalies a traiter a la main : {len(flagged)}")

if __name__ == "__main__":
    main()
