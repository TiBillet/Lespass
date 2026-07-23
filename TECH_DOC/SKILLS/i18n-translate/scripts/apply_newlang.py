#!/usr/bin/env python3
"""
MODE NEWLANG — application.
Ecrit les traductions de results.json dans locale/<code>/LC_MESSAGES/django.po.
  - pose le msgstr pour chaque chaine traduite
  - SAUTE les pluriels et les anomalies placeholders (flagged.json)
Le fichier cible vient de `makemessages -l <code>` : pas de fuzzy a retirer.

Usage:
  python3 apply_newlang.py <locale_dir> <code> <workdir> [--write]
  sans --write : DRY-RUN.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pohelpers import joinfield, esc

def main():
    locale_dir = sys.argv[1]
    code = sys.argv[2]
    workdir = sys.argv[3]
    write = "--write" in sys.argv

    work = json.load(open(os.path.join(workdir, f"work_{code}.json"), encoding="utf-8"))
    results = json.load(open(os.path.join(workdir, "results.json"), encoding="utf-8"))
    flagged = json.load(open(os.path.join(workdir, "flagged.json"), encoding="utf-8"))
    flagged_i = {f["i"] for f in flagged}
    key2i = {(it["ctx"], it["id"]): it["i"] for it in work}

    path = os.path.join(locale_dir, f"{code}/LC_MESSAGES/django.po")
    chunks = open(path, encoding="utf-8").read().split("\n\n")
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
            val = results.get(str(i), {}).get("tr")
            if val not in (None, ""):
                if i in flagged_i:
                    skipped_flag += 1
                else:
                    do = True
        elif i is not None and is_plural:
            skipped_plural += 1

        if not do:
            out.append(chunk)
            continue

        val = results[str(i)]["tr"]
        new_lines = []
        in_msgstr = False
        for l in lines:
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
    print(f"[{code}] appliquees={applied} skip_anomalie={skipped_flag} "
          f"skip_pluriel={skipped_plural} {tag}")
    print(f"Anomalies a traiter a la main : {len(flagged)}")

if __name__ == "__main__":
    main()
