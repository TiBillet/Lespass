#!/usr/bin/env python3
"""
Helpers partages pour la manipulation des fichiers gettext .po.
/ Shared helpers for gettext .po manipulation.

Toute la logique delicate (et durement testee) vit ici, en un seul endroit :
- parsing des blocs .po (avec continuations multi-lignes)
- echappement / desechappement .po (le piege du double-echappement)
- detection de la langue SOURCE par croisement FR<->EN
- signature de placeholders pour la verification deterministe

Les autres scripts importent ce module. On factorise pour ne PAS dupliquer
l'echappement, qui est l'endroit ou tout casse si on se trompe.
"""
import re

# ----------------------------------------------------------------------------
# Parsing .po
# ----------------------------------------------------------------------------

def joinfield(lines, key):
    """
    Concatene un champ .po multi-lignes (ex: msgid "" puis lignes "..." suivantes).
    / Join a multi-line .po field into a single string (raw, still .po-escaped).
    """
    out = []
    active = False
    for l in lines:
        if l.startswith(key + ' "'):
            active = True
            out.append(l[len(key) + 2:-1])
        elif active and l.startswith('"'):
            out.append(l[1:-1])
        elif active:
            active = False
    return "".join(out)

def parse(path):
    """
    Parse un .po en dict {(msgctxt, msgid): entry}.
    / Parse a .po file into {(msgctxt, msgid): entry}.

    entry = {msgstr, fuzzy(bool), plural(bool), refs(str)}.
    Les pluriels (msgid_plural / msgstr[0]) sont marques plural=True : on les
    laisse tranquilles partout (ecrire un pluriel mal forme casse la compilation).
    """
    entries = {}
    with open(path, encoding="utf-8") as f:
        block = []
        for line in f:
            if line.strip() == "":
                if block:
                    _add(entries, block)
                    block = []
            else:
                block.append(line.rstrip("\n"))
        if block:
            _add(entries, block)
    return entries

def _add(entries, block):
    ctx = joinfield(block, "msgctxt")
    mid = joinfield(block, "msgid")
    mstr = joinfield(block, "msgstr")
    fuzzy = any(l.startswith("#,") and "fuzzy" in l for l in block)
    plural = any(l.startswith("msgid_plural") for l in block)
    refs = " ".join(l for l in block if l.startswith("#:"))[:300]
    entries[(ctx, mid)] = {
        "msgid": mid, "msgstr": mstr, "fuzzy": fuzzy,
        "plural": plural, "refs": refs,
    }

# ----------------------------------------------------------------------------
# Echappement .po  (LE piege : toujours desescaper avant de re-echaper)
# ----------------------------------------------------------------------------

def unesc(s):
    """
    Ramene une chaine a sa forme LOGIQUE (sans echappement .po).
    / Normalise .po escaping to the logical string.

    Indispensable AVANT de comparer ou de re-echaper : un agent peut nous
    rendre soit "  (echappe) soit " (brut). Sans desescapage prealable, on
    double-echappe et le .po casse.
    """
    return (s.replace('\\\\', '\x00')
             .replace('\\"', '"')
             .replace('\\n', '\n')
             .replace('\\t', '\t')
             .replace('\x00', '\\'))

def esc(s):
    """
    Echappe une chaine logique pour l'ecrire dans un .po (forme une-ligne).
    / Escape a logical string for writing into a .po (single-line form).
    On desescape d'abord pour etre robuste a une entree deja echappee.
    """
    s = unesc(s)
    return (s.replace('\\', '\\\\')
             .replace('"', '\\"')
             .replace('\n', '\\n')
             .replace('\t', '\\t'))

# ----------------------------------------------------------------------------
# Detection de la langue SOURCE du msgid
# ----------------------------------------------------------------------------

ACC = set("àâäéèêëîïôöûüçœÀÂÉÈÊËÎÏÔÖÛÜÇŒ")
FR_WORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "vous", "votre", "vos",
    "pour", "avec", "sur", "dans", "est", "sont", "ce", "cette", "ou", "aux",
    "au", "et", "en", "par", "pas", "plus", "mais", "comme", "tout", "tous",
    "faire", "ajouter", "creer", "valider", "annuler", "supprimer", "modifier",
    "enregistrer", "retour",
}
EN_WORDS = {
    "the", "you", "your", "with", "for", "this", "that", "must", "have", "has",
    "are", "and", "not", "please", "add", "create", "delete", "edit", "save",
    "cancel", "back", "of", "to", "in", "on", "is", "can", "will", "new", "all",
    "from", "by", "an", "a",
}

def _lang_words(s):
    if any(c in ACC for c in s):
        return "fr"
    toks = set(re.findall(r"[a-zA-Z]+", s.lower()))
    fr = len(toks & FR_WORDS)
    en = len(toks & EN_WORDS)
    if fr > en:
        return "fr"
    if en > fr:
        return "en"
    return "amb"

def source_lang(mid, fr_str, en_str, fr_fuzzy, en_fuzzy):
    """
    Determine la langue SOURCE du msgid (deterministe).
    / Determine the source language of msgid.

    Regle 0 (PRIORITAIRE) : des accents francais dans le msgid -> source FR,
      quoi que disent les msgstr. Un msgid FR peut etre REFORMULE en FR dans le
      .po fr (ex: msgid "Système cashless..." -> msgstr "Système monnaie locale...").
      Dans ce cas le contexte croise conclurait a tort que le msgid est anglais,
      et la traduction EN serait sautee. Les accents tranchent : c'est du francais.
    Regle 1 : si le fichier EN traduit X (en_str != X, non fuzzy) -> X est FR.
    Regle 2 : si le fichier FR traduit X (fr_str != X, non fuzzy) -> X est EN.
      Un msgstr FUZZY est ignore comme preuve (trad perimee, non fiable).
    Sinon : mots-outils.
    """
    if any(c in ACC for c in mid):
        return "fr"
    en_translates = (not en_fuzzy) and en_str != "" and en_str != mid
    fr_translates = (not fr_fuzzy) and fr_str != "" and fr_str != mid
    if en_translates and not fr_translates:
        return "fr"
    if fr_translates and not en_translates:
        return "en"
    return _lang_words(mid)

# ----------------------------------------------------------------------------
# Signature de placeholders (verification deterministe)
# ----------------------------------------------------------------------------

PH = re.compile(r'%\([^)]+\)[a-zA-Z]|%[sdifeEgGxXoruc%]|\{[^}]*\}')
HTML = re.compile(r'</?[a-zA-Z][^>]*>')

def signature(s):
    """
    Multiset (trie) des placeholders et balises HTML d'une chaine.
    / Sorted multiset of placeholders and HTML tags.
    On compare la SOURCE et la TRADUCTION : memes placeholders, peu importe l'ordre.
    Desescapage prealable pour ne pas confondre \\" et ".
    """
    if s is None:
        return None
    s = unesc(s)
    return (tuple(sorted(PH.findall(s))), tuple(sorted(HTML.findall(s))))
