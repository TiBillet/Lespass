"""
Editeurs de lignes des blocs : remplacent la saisie de JSON brut dans l'admin.
/ Block line editors: replace raw JSON input in the admin.

LOCALISATION : pages/editeur_items.py

Deux champs du modele Bloc sont des listes (JSONField) :
- `contenu` : les infos pratiques d'un LIEU, ou les sous-cartes d'une SECTION
  (MEDIA_ET_CARTES, EQUIPE, FRISE, RESSOURCES) ;
- `points_gps` : les marqueurs de la carte d'un LIEU.

Avant, la personne tapait ces listes en JSON. Maintenant, l'admin affiche une
ligne de champs par element (widget EditeurLignesWidget,
pages/admin_widgets.py).
Ce module fait la partie Python pure, sans Django Forms :
1. lire les lignes envoyees par le formulaire (lire_lignes_depuis_post) ;
2. les nettoyer et les valider (nettoyer_contenu_lieu, nettoyer_contenu_cartes,
   nettoyer_points_gps).
L'admin (sauvegarde) et l'apercu en direct (pages/admin_apercu.py) appellent
les MEMES fonctions : l'apercu montre donc exactement ce qui sera enregistre.
/ This module is the pure-Python part: read the posted lines, then clean and
validate them. The admin save and the live preview call the SAME functions.

COMMENT LES LIGNES SONT POSTEES :
Chaque ligne affiche TOUTES les cles de son schema, avec des noms repetes :
`contenu_lieu__type`, `contenu_lieu__texte`, ... Le navigateur envoie les
valeurs dans l'ordre du DOM. `getlist()` rend donc une liste par cle, et le
rang i de chaque liste appartient a la ligne i. Deplacer une ligne dans la page
suffit a changer l'ordre : aucune renumerotation.
/ Each line renders ALL its schema keys, with repeated names. The browser posts
values in DOM order, so getlist() returns one aligned list per key. Moving a
line in the page is enough to reorder: no renumbering.
"""

from django.utils.translation import gettext_lazy as _

from Administration.utils import url_a_schema_dangereux

# Separateur entre le nom du champ et la cle : `contenu_lieu__titre`.
# / Separator between the field name and the key.
SEPARATEUR = "__"

# --- Schemas : les cles d'une ligne, par editeur ---
# / Schemas: a line's keys, per editor.

# Infos pratiques d'un LIEU. `titre` et `lignes` ne servent qu'au type
# "transport" ; les autres types n'utilisent que `texte`.
# / LIEU practical info. `titre` and `lignes` only serve the "transport" type.
CLES_CONTENU_LIEU = ("type", "texte", "titre", "lignes")

# Sous-cartes d'une SECTION (MEDIA_ET_CARTES, EQUIPE, FRISE, RESSOURCES).
# / A SECTION's sub-cards.
CLES_CONTENU_CARTES = ("titre", "texte", "badge", "url")

# Marqueurs de la carte d'un LIEU. / LIEU map markers.
CLES_POINTS_GPS = ("lat", "lng", "label")

# Les types d'item d'un LIEU, dans l'ordre du menu, avec leur libelle.
# Ce sont les valeurs que lit le gabarit bloc_lieu.html.
# / LIEU item types, in menu order, with their label. Read by bloc_lieu.html.
TYPES_ITEM_LIEU = [
    ("badge", _("Intitulé (ouvre un groupe)")),
    ("para", _("Paragraphe")),
    ("horaire", _("Horaires")),
    ("adresse", _("Adresse")),
    ("accessibilite", _("Accessibilité")),
    ("transport", _("Transport (titre + lignes)")),
]

# Schema de chaque editeur : sert au widget et a la vue « ligne vide ».
# / Each editor's schema: used by the widget and the "empty line" view.
CLES_PAR_EDITEUR = {
    "lieu": CLES_CONTENU_LIEU,
    "cartes": CLES_CONTENU_CARTES,
    "gps": CLES_POINTS_GPS,
}


def lire_lignes_depuis_post(donnees_postees, nom_du_champ, cles):
    """
    Reconstruit la liste des lignes a partir des donnees du formulaire.
    / Rebuilds the list of lines from the posted form data.

    LOCALISATION : pages/editeur_items.py

    :param donnees_postees: QueryDict (request.POST) ou dict de listes.
    :param nom_du_champ: nom du champ de formulaire, ex. "contenu_lieu".
    :param cles: les cles du schema, ex. CLES_CONTENU_LIEU.
    :return: liste de dicts de chaines, une par ligne (lignes vides comprises).
    """
    # Une liste de valeurs par cle, dans l'ordre du DOM.
    # / One list of values per key, in DOM order.
    valeurs_par_cle = {}
    nombre_de_lignes = 0
    for cle in cles:
        nom_complet = f"{nom_du_champ}{SEPARATEUR}{cle}"
        if hasattr(donnees_postees, "getlist"):
            valeurs = donnees_postees.getlist(nom_complet)
        else:
            valeurs = list(donnees_postees.get(nom_complet, []))
        valeurs_par_cle[cle] = valeurs
        if len(valeurs) > nombre_de_lignes:
            nombre_de_lignes = len(valeurs)

    # On reassemble ligne par ligne. Une cle absente d'une ligne vaut "".
    # / Reassemble line by line. A key missing from a line is "".
    lignes = []
    for rang in range(nombre_de_lignes):
        ligne = {}
        for cle in cles:
            valeurs = valeurs_par_cle[cle]
            if rang < len(valeurs):
                ligne[cle] = valeurs[rang]
            else:
                ligne[cle] = ""
        lignes.append(ligne)
    return lignes


def _texte(valeur):
    """
    Rend une chaine sans espaces autour ; tout ce qui n'est pas du texte
    devient "". / Returns a stripped string; non-text becomes "".
    """
    if valeur is None:
        return ""
    if isinstance(valeur, (list, tuple, dict)):
        return ""
    return str(valeur).strip()


def _decouper_lignes(valeur):
    """
    Transforme la saisie « une ligne par transport » en liste.
    Accepte aussi une liste deja faite (valeur venue de la base).
    / Turns the "one line per transport" input into a list. Also accepts an
    already-built list (value from the database).
    """
    if isinstance(valeur, (list, tuple)):
        morceaux = valeur
    else:
        morceaux = str(valeur or "").splitlines()
    lignes_propres = []
    for morceau in morceaux:
        morceau_propre = _texte(morceau)
        if morceau_propre:
            lignes_propres.append(morceau_propre)
    return lignes_propres


def nettoyer_contenu_lieu(lignes):
    """
    Nettoie les infos pratiques d'un LIEU.
    / Cleans a LIEU block's practical info.

    - une ligne sans texte, sans titre et sans lignes est ignoree ;
    - un type inconnu est une erreur (le gabarit ne saurait pas l'afficher) ;
    - on ne garde que les cles utiles au type : `titre` et `lignes` pour
      "transport", `texte` pour les autres.
    / Empty lines are skipped; an unknown type is an error; only the keys
    useful to the type are kept.

    :return: (items_propres, erreurs)
    """
    types_connus = []
    for code_type, _libelle in TYPES_ITEM_LIEU:
        types_connus.append(code_type)

    items_propres = []
    erreurs = []
    for numero, ligne in enumerate(lignes, start=1):
        if not isinstance(ligne, dict):
            continue
        type_item = _texte(ligne.get("type"))
        texte = _texte(ligne.get("texte"))
        titre = _texte(ligne.get("titre"))
        lignes_transport = _decouper_lignes(ligne.get("lignes"))

        ligne_est_vide = not texte and not titre and not lignes_transport
        if ligne_est_vide:
            continue

        if type_item not in types_connus:
            erreurs.append(
                _("Ligne %(numero)s : type « %(type)s » inconnu.")
                % {"numero": numero, "type": type_item}
            )
            continue

        if type_item == "transport":
            items_propres.append(
                {"type": "transport", "titre": titre, "lignes": lignes_transport}
            )
        else:
            items_propres.append({"type": type_item, "texte": texte})

    return items_propres, erreurs


def nettoyer_contenu_cartes(lignes):
    """
    Nettoie les sous-cartes d'une SECTION (equipe, frise, ressources...).
    / Cleans a SECTION's sub-cards.

    - une ligne sans titre, sans texte et sans badge est ignoree ;
    - une url a schema dangereux (javascript:, data:...) est videe ;
    - les cles vides ne sont pas stockees (le gabarit teste leur presence).
    / Empty lines are skipped; a dangerous-scheme url is emptied; empty keys
    are not stored.

    :return: (items_propres, erreurs)
    """
    items_propres = []
    erreurs = []
    for ligne in lignes:
        if not isinstance(ligne, dict):
            continue
        titre = _texte(ligne.get("titre"))
        texte = _texte(ligne.get("texte"))
        badge = _texte(ligne.get("badge"))
        url = _texte(ligne.get("url"))

        ligne_est_vide = not titre and not texte and not badge
        if ligne_est_vide:
            continue

        if url_a_schema_dangereux(url):
            url = ""

        item = {"titre": titre}
        if texte:
            item["texte"] = texte
        if badge:
            item["badge"] = badge
        if url:
            item["url"] = url
        items_propres.append(item)

    return items_propres, erreurs


def _nombre_ou_none(valeur):
    """
    Convertit une saisie en nombre decimal. Accepte la virgule francaise.
    Rend None si ce n'est pas un nombre.
    / Converts an input to a float. Accepts the French comma. None if invalid.
    """
    texte = _texte(valeur).replace(",", ".")
    if not texte:
        return None
    try:
        return float(texte)
    except ValueError:
        return None


def nettoyer_points_gps(lignes):
    """
    Nettoie les marqueurs de la carte d'un LIEU.
    / Cleans a LIEU block's map markers.

    - une ligne entierement vide est ignoree ;
    - latitude entre -90 et 90, longitude entre -180 et 180, sinon erreur ;
    - le libelle est optionnel.
    / Fully empty lines are skipped; lat in [-90, 90], lng in [-180, 180],
    otherwise an error; the label is optional.

    :return: (items_propres, erreurs)
    """
    items_propres = []
    erreurs = []
    for numero, ligne in enumerate(lignes, start=1):
        if not isinstance(ligne, dict):
            continue
        texte_lat = _texte(ligne.get("lat"))
        texte_lng = _texte(ligne.get("lng"))
        label = _texte(ligne.get("label"))

        ligne_est_vide = not texte_lat and not texte_lng and not label
        if ligne_est_vide:
            continue

        latitude = _nombre_ou_none(texte_lat)
        longitude = _nombre_ou_none(texte_lng)
        latitude_valide = latitude is not None and -90 <= latitude <= 90
        longitude_valide = longitude is not None and -180 <= longitude <= 180
        if not latitude_valide or not longitude_valide:
            erreurs.append(
                _(
                    "Point %(numero)s : la latitude doit être un nombre entre -90 "
                    "et 90, la longitude entre -180 et 180 (ex. 43.5568 et 1.4835)."
                )
                % {"numero": numero}
            )
            continue

        items_propres.append({"lat": latitude, "lng": longitude, "label": label})

    return items_propres, erreurs


# Nettoyeur de chaque editeur. / Each editor's cleaner.
NETTOYEUR_PAR_EDITEUR = {
    "lieu": nettoyer_contenu_lieu,
    "cartes": nettoyer_contenu_cartes,
    "gps": nettoyer_points_gps,
}


def lignes_pour_affichage(valeur_en_base, editeur):
    """
    Prepare la valeur stockee (JSON) pour l'afficher en lignes de champs.
    / Prepares the stored (JSON) value to show it as lines of inputs.

    LOCALISATION : pages/editeur_items.py

    Le JSONField a pu etre rempli par l'API ou a la main : on ne suppose rien.
    Rien ne doit changer EN SILENCE a l'enregistrement. Chaque ecart est donc
    signale par un avertissement, affiche au-dessus de l'editeur :
    - valeur qui n'est pas une liste, ou element qui n'est pas un dict : il
      est illisible, et sera retire a l'enregistrement ;
    - cle que l'editeur ne connait pas (ex. « couleur ») : elle sera perdue ;
    - type d'info pratique inconnu (ex. « wifi ») : la ligne le garde, marquee
      `type_inconnu`. Le select l'affiche tel quel, et l'enregistrement est
      refuse tant qu'un type connu n'est pas choisi (nettoyer_contenu_lieu).
    / Nothing may change SILENTLY on save: every mismatch becomes a warning
    (unreadable items, unknown keys, unknown LIEU item types).

    :return: (lignes, avertissements) — avertissements = liste de textes.
    """
    avertissements = []
    if valeur_en_base in (None, "", []):
        return [], avertissements
    if not isinstance(valeur_en_base, (list, tuple)):
        avertissements.append(
            _("Le contenu enregistré n'est pas une liste : il n'a pas pu être lu, et sera remplacé à l'enregistrement.")
        )
        return [], avertissements

    cles = CLES_PAR_EDITEUR[editeur]
    types_connus = []
    for code_type, _libelle in TYPES_ITEM_LIEU:
        types_connus.append(code_type)

    lignes = []
    nombre_d_elements_illisibles = 0
    cles_inconnues = []
    types_inconnus = []
    for item in valeur_en_base:
        if not isinstance(item, dict):
            nombre_d_elements_illisibles += 1
            continue

        for cle_de_l_item in item:
            if cle_de_l_item not in cles and cle_de_l_item not in cles_inconnues:
                cles_inconnues.append(str(cle_de_l_item))

        ligne = {}
        for cle in cles:
            valeur = item.get(cle, "")
            # Les lignes d'un transport se saisissent une par ligne de texte.
            # / Transport lines are typed one per text line.
            if cle == "lignes" and isinstance(valeur, (list, tuple)):
                valeur = "\n".join(str(morceau) for morceau in valeur)
            if valeur is None:
                valeur = ""
            ligne[cle] = valeur

        if editeur == "lieu" and ligne["type"] not in types_connus:
            ligne["type_inconnu"] = True
            if ligne["type"] not in types_inconnus:
                types_inconnus.append(str(ligne["type"]))
        lignes.append(ligne)

    if nombre_d_elements_illisibles:
        avertissements.append(
            _("%(nombre)s élément(s) enregistré(s) illisible(s) : non affiché(s), il(s) sera(ont) retiré(s) à l'enregistrement.")
            % {"nombre": nombre_d_elements_illisibles}
        )
    if cles_inconnues:
        avertissements.append(
            _("Informations non modifiables ici, perdues à l'enregistrement : %(cles)s.")
            % {"cles": ", ".join(cles_inconnues)}
        )
    if types_inconnus:
        avertissements.append(
            _("Type(s) inconnu(s) : %(types)s. Choisissez un type dans la liste pour pouvoir enregistrer.")
            % {"types": ", ".join(types_inconnus)}
        )
    return lignes, avertissements
