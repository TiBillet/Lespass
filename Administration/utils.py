## SANITIZER
import posixpath
import re
from typing import Optional
from urllib.parse import unquote, urlparse
import nh3
from django.utils.html import escape, urlize

# "div" : l'éditeur de l'admin (Trix) écrit chaque bloc de texte dans un <div>.
# Sans lui, nh3 retire les blocs et le texte perd ses paragraphes. Un <div> sans
# attribut ne porte ni script ni style.
# / "div": Trix writes each text block in a <div>; without it the blocks are lost.
ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u", "div",
    "ul", "ol", "li",
    "blockquote", "code", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "img", "span", "del"
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title"],
}

# Disallow image URLs pointing to potentially dangerous internal routes
DISALLOWED_IMAGE_PATH_PREFIXES = (
    "/admin",
    "/logout",
    "/deconnexion",
    "/signout",
)


def _attribute_filter(tag: str, attr: str, value: str) -> Optional[str]:
    """Filter attributes during sanitization.
    - For <img src>, remove the attribute if it targets problematic internal routes
      like /admin or logout endpoints (even if relative URLs).
    Returning None removes the attribute.
    """
    try:
        if tag == "img" and attr == "src" and isinstance(value, str):
            # On lit le chemin comme le NAVIGATEUR le lira, sinon le filtre se contourne :
            # - le navigateur retire tabulations et retours à la ligne, et lit « \ » comme « / » ;
            # - Django décode les « %xx » : « /%61dmin » arrive sur « /admin » ;
            # - « /./admin » et « /.//admin » sont normalisés en « /admin » ;
            # - un « .. » peut remonter jusqu'à la racine (« ../admin ») : refusé d'office.
            # / Read the path as the BROWSER will: strip tabs/newlines, "\" as "/",
            # percent-decode, normalize; any ".." segment is rejected.
            valeur_lue_par_le_navigateur = value
            for caractere_ignore in ("\t", "\n", "\r"):
                valeur_lue_par_le_navigateur = valeur_lue_par_le_navigateur.replace(caractere_ignore, "")
            valeur_lue_par_le_navigateur = valeur_lue_par_le_navigateur.strip().replace("\\", "/")

            parsed = urlparse(valeur_lue_par_le_navigateur)
            chemin_decode = unquote(parsed.path or "")

            segments_du_chemin = chemin_decode.split("/")
            if ".." in segments_du_chemin:
                return None  # drop src attribute

            chemin_sans_doubles_barres = re.sub(r"/{2,}", "/", chemin_decode)
            if chemin_sans_doubles_barres:
                chemin_normalise = posixpath.normpath(chemin_sans_doubles_barres)
            else:
                chemin_normalise = ""
            path = chemin_normalise.lower()

            # Only consider regular http/https/relative URLs; schemes are filtered elsewhere
            for prefix in DISALLOWED_IMAGE_PATH_PREFIXES:
                if path.startswith(prefix):
                    return None  # drop src attribute
        return value
    except Exception:
        # On any parsing error, drop the attribute to be safe
        return None



def url_a_schema_dangereux(valeur):
    """
    Vrai si l'URL utilise un schema dangereux (javascript:, data:, vbscript:).
    On retire d'abord espaces et caracteres de controle pour dejouer les
    obfuscations type "java\\tscript:". On ne teste que le debut.
    / True if the URL uses a dangerous scheme. Strips whitespace/control chars first
    to defeat obfuscations, then tests the start only.
    """
    if not valeur or not isinstance(valeur, str):
        return False
    compact = "".join(c for c in valeur if not c.isspace() and ord(c) >= 0x20).lower()
    return compact.startswith(("javascript:", "data:", "vbscript:"))


def clean_text(text: str) -> str:
    """Nettoie une chaîne de texte brut en supprimant tout HTML.
    Clean a plain text string by stripping all HTML tags.

    Utilisé pour les entrées utilisateur qui ne doivent contenir aucun HTML
    (noms de champs, valeurs de formulaire, etc.).
    Used for user inputs that should contain no HTML at all
    (field names, form values, etc.).
    """
    # nh3.clean avec tags vide supprime tout le HTML et ne garde que le texte
    # nh3.clean with empty tags strips all HTML and keeps only text
    return nh3.clean(
        text,
        tags=set(),
        attributes={},
        strip_comments=True,
    )


def clean_html(html: str) -> str:
    # Use nh3 (ammonia) to sanitize HTML; explicitly restrict URL schemes and strip comments.
    url_schemes = {"http", "https", "mailto", "tel"}
    # nh3 expects sets for tags and attributes values
    tags = set(ALLOWED_TAGS)
    attributes = {k: set(v) for k, v in ALLOWED_ATTRIBUTES.items()}
    return nh3.clean(
        html,
        tags=tags,
        attributes=attributes,
        url_schemes=url_schemes,
        attribute_filter=_attribute_filter,
        strip_comments=True,
        link_rel=None,  # allow existing rel and don't auto-insert
    )


# Morceaux de motifs pour normaliser_html_editeur.
# « Vide » = espaces, retours à la ligne et espaces insécables. nh3 écrit
# l'espace insécable « &nbsp; », que \s ne reconnaît pas.
# / Pattern parts: "empty" = whitespace and non-breaking spaces.
_VIDE = r"(?:\s|&nbsp;)*"
_VIDE_OU_BR = r"(?:\s|&nbsp;|<br>)*"

# Un bloc qui ne contient que du vide : <div> </div>, <p>&nbsp;</p>.
# / A block holding only whitespace.
_BLOC_VIDE = re.compile(r"<(div|p)>" + _VIDE + r"</\1>")

# Deux listes du même type séparées par du vide : </ul> <ul>.
# / Two lists of the same type separated by whitespace.
_LISTES_UL_VOISINES = re.compile(r"</ul>" + _VIDE + r"<ul>")
_LISTES_OL_VOISINES = re.compile(r"</ol>" + _VIDE + r"<ol>")

# Début du texte : des <br> nus, un bloc fait seulement de <br>, ou des <br>
# en tête du premier bloc.
# / Start of the text: bare <br>, a <br>-only block, <br> at the head of the first block.
_DEBUT_BR_NUS = re.compile(r"^" + _VIDE + r"(?:<br>" + _VIDE + r")+")
_DEBUT_BLOC_DE_BR = re.compile(r"^" + _VIDE + r"<(div|p)>" + _VIDE_OU_BR + r"</\1>")
_DEBUT_BR_DANS_LE_PREMIER_BLOC = re.compile(
    r"^" + _VIDE + r"<(div|p)>" + _VIDE + r"(?:<br>" + _VIDE + r")+"
)

# Fin du texte : un bloc fait seulement de <br>. Les <br> nus et les <br> en
# queue du dernier bloc sont retirés par _retirer_le_vide_de_fin, sans regex.
# / End of the text: a <br>-only block. Trailing <br> are cut without regex.
_FIN_BLOC_DE_BR = re.compile(r"<(div|p)>" + _VIDE_OU_BR + r"</\1>" + _VIDE + r"$")


def _couper_le_vide_de_fin(html: str) -> str:
    """
    Coupe à la fin du texte les espaces, les « &nbsp; » et les <br>.
    / Cuts trailing whitespace, &nbsp; and <br>.

    Parcours à reculons, en temps linéaire. Une regex non ancrée au début
    (« (<br>)+$ ») est réessayée à chaque position : sur des milliers de <br>
    de suite (texte envoyé au wizard public), elle prend plusieurs secondes.
    / Linear backwards scan: an unanchored regex is quadratic on long <br> runs.
    """
    position_de_fin = len(html)
    while position_de_fin > 0:
        if html[position_de_fin - 1].isspace():
            position_de_fin -= 1
        elif html.endswith("<br>", 0, position_de_fin):
            position_de_fin -= len("<br>")
        elif html.endswith("&nbsp;", 0, position_de_fin):
            position_de_fin -= len("&nbsp;")
        else:
            break
    return html[:position_de_fin]


def _retirer_le_vide_de_fin(html: str) -> str:
    """
    Retire le vide de fin du texte, puis celui de la fin du dernier bloc
    (<div>Texte<br><br></div> → <div>Texte</div>).
    / Removes trailing emptiness, then the one at the end of the last block.
    """
    html_sans_vide_de_fin = _couper_le_vide_de_fin(html)
    for balise_fermante in ("</div>", "</p>"):
        if html_sans_vide_de_fin.endswith(balise_fermante):
            interieur_du_dernier_bloc = html_sans_vide_de_fin[: -len(balise_fermante)]
            return _couper_le_vide_de_fin(interieur_du_dernier_bloc) + balise_fermante
    return html_sans_vide_de_fin


def normaliser_html_editeur(html: str) -> str:
    """
    Range le HTML d'un champ de texte riche, après le nettoyage par clean_html.
    / Tidies rich-text HTML, after clean_html.

    LOCALISATION : Administration/utils.py

    L'éditeur de l'admin (Trix) et le copier-coller laissent des restes :
    des lignes vides en début et en fin de texte, des blocs vides, et des
    listes coupées en plusieurs listes d'un seul point. Cette fonction les
    retire. Elle ne touche pas aux lignes vides au milieu du texte : ce sont
    celles voulues par la personne.

    Ce qu'elle fait, dans l'ordre :
    1. retire les blocs vides (<div> </div>, <p>&nbsp;</p>) ;
    2. recolle les listes voisines (</ul> <ul> → rien, idem pour <ol>) ;
    3. retire, en début de texte, les <br> nus, les blocs faits seulement de
       <br> et les <br> en tête du premier bloc ;
    4. fait de même en fin de texte ;
    5. retire les espaces du début et de la fin.
    Les étapes 3 et 4 tournent jusqu'à ce que plus rien ne change.

    CONTRAINTE : l'entrée doit être la sortie de clean_html. Les motifs
    supposent l'écriture régulière de nh3 (balises en minuscules, sans
    attribut sur <div> et <p>, « <br> » et jamais « <br/> »).

    La fonction est stable : l'appliquer deux fois donne le même résultat.
    Un enregistrement sans modification ne change donc pas le texte.

    APPELÉE PAR :
    - Administration/admin/site.py : sanitize_textfields (toutes les fiches admin)
    - api_v2/serializers.py : validate_description (création et modification d'event)
    - BaseBillet/views.py : _creer_event_depuis_brouillon (wizard public)

    :param html: HTML déjà nettoyé par clean_html (str)
    :return: HTML rangé (str)
    """
    if not html:
        return html

    # 1. Blocs vides. / Empty blocks.
    html_range = _BLOC_VIDE.sub("", html)

    # 2. Listes voisines. Trix ne produit jamais deux listes collées sans
    # bloc entre elles : les recoller ne casse rien de voulu.
    # / Neighbouring lists: Trix never writes two adjacent lists on purpose.
    html_range = _LISTES_UL_VOISINES.sub("", html_range)
    html_range = _LISTES_OL_VOISINES.sub("", html_range)

    # 3 et 4. Début et fin du texte, jusqu'à ce que plus rien ne change.
    # Exemple : <div><br></div><br><div>Texte</div> demande deux passes. La
    # première retire le bloc de <br>, ce qui met le <br> nu en tête du texte.
    # La seconde retire ce <br>.
    # / Start and end of the text, until nothing changes.
    html_avant_la_passe = None
    while html_avant_la_passe != html_range:
        html_avant_la_passe = html_range

        html_range = _DEBUT_BR_NUS.sub("", html_range)
        html_range = _DEBUT_BLOC_DE_BR.sub("", html_range)
        html_range = _DEBUT_BR_DANS_LE_PREMIER_BLOC.sub(r"<\1>", html_range)

        html_range = _retirer_le_vide_de_fin(html_range)
        html_range = _FIN_BLOC_DE_BR.sub("", html_range)

    # 5. Espaces du début et de la fin. / Leading and trailing whitespace.
    return html_range.strip()


# Une balise HTML ouvrante ou fermante : <p>, </div>, <br>, <br/>, <a href=…>.
# Le nom est suivi d'une espace, d'un / ou d'un >. Ne sont donc pas des
# balises : « a < b », « <jean@exemple.org> », « <https://exemple.org> ».
# / An HTML tag: name followed by whitespace, / or >. Mail and URL in <> are not tags.
UNE_BALISE_HTML = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^>]*)?/?>")


def texte_brut_vers_html(texte: str) -> str:
    """
    Convertit un texte brut (sans balise) en HTML de l'éditeur de l'admin.
    / Converts plain text (no tags) to the admin editor's HTML.

    LOCALISATION : Administration/utils.py

    Le wizard public (textarea) et l'API v2 peuvent envoyer du texte brut.
    Affiché tel quel en HTML, il perd ses sauts de ligne. Cette fonction :
    1. rend le texte inchangé s'il contient déjà une balise (c'est du HTML) ;
    2. échappe le texte (escape : < devient &lt;, & devient &amp;), puis rend
       les URL et les adresses mail cliquables (urlize, autoescape=False). Cet
       ordre est imposé par urlize : il décode l'URL avant d'écrire le href.
       Sur un texte non échappé, « &region=sud » serait lu comme l'entité
       « &reg » (®) et le lien serait cassé. urlize passe AVANT les <br> :
       sinon « https://x.org<br>Suite » serait lu comme une seule URL ;
    3. remplace chaque saut de ligne par « <br> » suivi d'un retour à la
       ligne. Ce retour garde un espace entre les mots quand un template
       retire les balises (striptags, pour les meta descriptions) ;
    4. entoure le tout d'un <div>, comme le fait l'éditeur.

    Le résultat passe ensuite par clean_html puis normaliser_html_editeur.

    CONTRAINTE : le texte n'est jamais décodé ici (même raison que l'étape 2).
    Seule la commande normaliser_textes_riches décode, pour les textes déjà en
    base, qui sont la sortie de nh3.

    APPELÉE PAR :
    - api_v2/serializers.py : validate_description (création et modification d'event)
    - BaseBillet/views.py : _creer_event_depuis_brouillon (wizard public)

    :param texte: texte brut ou HTML (str)
    :return: HTML (str)
    """
    if not texte or UNE_BALISE_HTML.search(texte):
        return texte

    texte_avec_sauts_unix = texte.replace("\r\n", "\n")
    texte_echappe = escape(texte_avec_sauts_unix)
    texte_avec_liens = urlize(texte_echappe, nofollow=True, autoescape=False)
    texte_avec_br = texte_avec_liens.replace("\n", "<br>\n")
    return f"<div>{texte_avec_br}</div>"

