"""
Bloc « Carte figée » : lire le fichier JSON importé, le vérifier, puis le
convertir pour l'outil de carte du réseau.
/ "Frozen map" block: read the imported JSON file, check it, then convert it for
the network map tool.

LOCALISATION : pages/carte_figee.py

Une carte figée est une photo d'un moment, par exemple le bilan d'une campagne
d'événements passés. Elle n'a aucun lien avec la base : l'admin du lieu importe
un fichier JSON depuis l'éditeur de site, et la carte montre ce fichier.
/ A frozen map is a snapshot. No link to the database: the venue admin uploads
a JSON file, and the map shows that file.

LE FORMAT DU FICHIER : une liste de lieux, chacun avec ses événements.
Voir EXEMPLE_DE_FICHIER ci-dessous.
/ FILE FORMAT: a list of venues, each with its events. See EXEMPLE_DE_FICHIER.

FLUX :
1. pages/admin.py (BlocAdminForm.clean_fichier_carte_figee) appelle
   lire_fichier_carte_figee() : taille, UTF-8, JSON, puis nettoyer_carte_figee().
2. La liste propre est rangée dans Bloc.donnees_carte_figee.
   Bloc.clean() (pages/models.py) la re-vérifie avec nettoyer_carte_figee(),
   quel que soit le chemin d'écriture.
3. Au rendu, pages/templates/pages/classic/partials/bloc_carte_figee.html
   appelle le tag `donnees_explorer_carte_figee` (pages/templatetags/pages_tags.py),
   qui appelle donnees_explorer_depuis_carte_figee(). Le résultat est passé au
   widget seo/templates/seo/partials/explorer_widget.html, lu par
   seo/static/seo/explorer.js — le même outil que la page « Autour de nous ».
/ FLOW: admin form reads and cleans the file -> stored in the block -> re-checked
by Bloc.clean() -> converted at render time for the shared explorer widget.
"""

import json
import re
from datetime import datetime
from urllib.parse import urlsplit

from django.utils.html import format_html
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from pages.editeur_items import _nombre_ou_none, _texte

# Taille maximale du fichier importé : 2 Mo. Le bilan JPTO 2026 (74 lieux,
# 163 événements) pèse environ 60 Ko.
# / Max uploaded file size: 2 MB.
TAILLE_MAX_DU_FICHIER_EN_OCTETS = 2 * 1024 * 1024

# Longueurs maximales des textes du fichier. Une valeur trop longue est
# REFUSEE avec un message, jamais coupee en silence.
# / Max lengths of the file texts. Too long = refused, never silently cut.
LONGUEUR_MAX_D_UN_TEXTE = 200
LONGUEUR_MAX_D_UNE_URL = 2000

# Caracteres refuses dans une URL. explorer.js pose l'URL dans un attribut
# href="..." : un guillemet refermerait l'attribut et permettrait d'en
# ajouter un autre (onfocus=..., XSS). Les chevrons et les espaces n'ont rien
# a faire dans une URL bien formee.
# / Characters refused in a URL: a quote would close the href attribute and
# let an attacker add another one (XSS).
CARACTERES_INTERDITS_DANS_UNE_URL = "\"'<>`\\"

# Formats de date acceptes : 2026-10-02, 2026-10-02T14:00, 2026-10-02T14:00:30.
# datetime.fromisoformat accepte aussi 20261002 ou 2026-W40-1 : le navigateur
# les affiche alors « Invalid Date ». On impose donc la forme exacte d'abord.
# / Accepted date shapes. fromisoformat alone accepts shapes the browser
# shows as "Invalid Date", so the exact shape is enforced first.
FORME_D_UNE_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?")

# Exemple montré dans l'aide de l'admin (accordéon). Les clés ne se traduisent
# pas : ce sont celles que lit nettoyer_carte_figee().
# / Example shown in the admin help (accordion). Keys are not translated.
EXEMPLE_DE_FICHIER = """[
  {
    "nom": "La Cité du Faire",
    "latitude": 45.7578,
    "longitude": 4.8320,
    "adresse": "12 rue de l'Exemple, 69003 Lyon",
    "url": "https://lacitedufaire.example.org/",
    "evenements": [
      {
        "nom": "Visite guidée",
        "date": "2026-10-02T14:00",
        "url": "https://lacitedufaire.example.org/visite/",
        "tags": ["JPTO", "Visite"]
      },
      {
        "nom": "Atelier ouvert",
        "date": "2026-10-03"
      }
    ]
  },
  {
    "nom": "Tiers-lieu sans événement",
    "latitude": 48.5734,
    "longitude": 7.7521
  }
]"""


# ---------------------------------------------------------------------------
# Lecture et vérification / Reading and checking
# ---------------------------------------------------------------------------
def _url_http_ou_vide(valeur):
    """
    Rend l'URL nettoyée si c'est une adresse http:// ou https:// complète.
    Rend "" si la valeur est vide. Rend None si l'URL est refusée.
    / Returns the stripped URL if it is a full http(s) address, "" if empty,
    None if refused.

    Contraintes de sécurité : l'URL finit dans un attribut href="..." construit
    par explorer.js.
    - Une URL `javascript:` ou `data:` s'exécuterait au clic : seuls les
      schémas http et https passent.
    - Un guillemet refermerait l'attribut et permettrait d'en ajouter un autre
      (`https://x/" onfocus="...`) : les guillemets, chevrons, espaces et
      caractères de contrôle sont refusés.
    - Il faut un domaine : « https:// » seul n'est pas un lien.
    / Security: only http/https, no quote/angle bracket/space/control char,
    a host is required.
    """
    url = _texte(valeur)
    if not url:
        return ""
    if len(url) > LONGUEUR_MAX_D_UNE_URL:
        return None

    for caractere in url:
        caractere_interdit = caractere in CARACTERES_INTERDITS_DANS_UNE_URL
        caractere_invisible = (
            caractere.isspace() or ord(caractere) < 32 or ord(caractere) == 127
        )
        if caractere_interdit or caractere_invisible:
            return None

    try:
        morceaux_de_l_url = urlsplit(url)
    except ValueError:
        return None
    schema_accepte = morceaux_de_l_url.scheme.lower() in ("http", "https")
    domaine_present = bool(morceaux_de_l_url.netloc)
    if schema_accepte and domaine_present:
        return url
    return None


def _date_iso_valide(texte_de_la_date):
    """
    Vrai si le texte est une date au format « 2026-10-02 », « 2026-10-02T14:00 »
    ou « 2026-10-02T14:00:30 », et une vraie date (pas de 13e mois).
    / True if the text has one of the accepted shapes AND is a real date.
    """
    if not FORME_D_UNE_DATE.fullmatch(texte_de_la_date):
        return False
    try:
        datetime.fromisoformat(texte_de_la_date)
    except ValueError:
        return False
    return True


def _texte_trop_long(texte):
    """
    Vrai si le texte dépasse LONGUEUR_MAX_D_UN_TEXTE caractères.
    / True if the text is longer than LONGUEUR_MAX_D_UN_TEXTE.
    """
    return len(texte) > LONGUEUR_MAX_D_UN_TEXTE


def _message_texte_trop_long(debut_du_message, nom_de_la_cle):
    """
    Message d'erreur d'un texte trop long, avec la clé en cause.
    / Error message for a too long text, naming the key.
    """
    return _("%(debut)s : « %(cle)s » dépasse %(max)s caractères.") % {
        "debut": debut_du_message,
        "cle": nom_de_la_cle,
        "max": LONGUEUR_MAX_D_UN_TEXTE,
    }


def _nettoyer_un_evenement(
    evenement_lu, position_du_lieu, nom_du_lieu, position_de_l_evenement
):
    """
    Vérifie un événement d'un lieu.
    / Checks one event of a venue.

    :return: (evenement_propre ou None, erreurs)
    """
    erreurs = []
    debut_du_message = _("Lieu %(n)s (« %(nom)s »), événement %(m)s") % {
        "n": position_du_lieu,
        "nom": nom_du_lieu,
        "m": position_de_l_evenement,
    }

    if not isinstance(evenement_lu, dict):
        erreurs.append(
            _("%(debut)s : un événement doit être un objet JSON entre accolades.")
            % {"debut": debut_du_message}
        )
        return None, erreurs

    nom_de_l_evenement = _texte(evenement_lu.get("nom"))
    if not nom_de_l_evenement:
        erreurs.append(
            _("%(debut)s : le nom est obligatoire.") % {"debut": debut_du_message}
        )
    elif _texte_trop_long(nom_de_l_evenement):
        erreurs.append(_message_texte_trop_long(debut_du_message, "nom"))

    date_de_l_evenement = _texte(evenement_lu.get("date"))
    if date_de_l_evenement and not _date_iso_valide(date_de_l_evenement):
        erreurs.append(
            _("%(debut)s : la date doit être au format 2026-10-02 ou 2026-10-02T14:00.")
            % {"debut": debut_du_message}
        )

    url_de_l_evenement = _url_http_ou_vide(evenement_lu.get("url"))
    if url_de_l_evenement is None:
        erreurs.append(
            _(
                "%(debut)s : l'URL doit être une adresse complète en http:// ou "
                "https://, sans espace, guillemet ni chevron."
            )
            % {"debut": debut_du_message}
        )

    tags_lus = evenement_lu.get("tags", [])
    tags_propres = []
    if tags_lus is None:
        tags_lus = []
    if not isinstance(tags_lus, list):
        erreurs.append(
            _(
                '%(debut)s : « tags » doit être une liste de textes, par exemple ["JPTO"].'
            )
            % {"debut": debut_du_message}
        )
    else:
        for tag_lu in tags_lus:
            nom_du_tag = _texte(tag_lu)
            if not nom_du_tag:
                continue
            if _texte_trop_long(nom_du_tag):
                erreurs.append(_message_texte_trop_long(debut_du_message, "tags"))
                continue
            tags_propres.append(nom_du_tag)

    if erreurs:
        return None, erreurs

    evenement_propre = {"nom": nom_de_l_evenement}
    if date_de_l_evenement:
        evenement_propre["date"] = date_de_l_evenement
    if url_de_l_evenement:
        evenement_propre["url"] = url_de_l_evenement
    if tags_propres:
        evenement_propre["tags"] = tags_propres
    return evenement_propre, []


def _nettoyer_un_lieu(lieu_lu, position_du_lieu):
    """
    Vérifie un lieu et ses événements.
    / Checks one venue and its events.

    :return: (lieu_propre ou None, erreurs)
    """
    erreurs = []

    if not isinstance(lieu_lu, dict):
        erreurs.append(
            _("Lieu %(n)s : un lieu doit être un objet JSON entre accolades.")
            % {"n": position_du_lieu}
        )
        return None, erreurs

    nom_du_lieu = _texte(lieu_lu.get("nom"))
    if nom_du_lieu and _texte_trop_long(nom_du_lieu):
        # Le nom n'est pas recopie dans le message : il est trop long.
        # / The name is not echoed in the message: it is too long.
        debut_du_message = _("Lieu %(n)s") % {"n": position_du_lieu}
        erreurs.append(_message_texte_trop_long(debut_du_message, "nom"))
    elif nom_du_lieu:
        debut_du_message = _("Lieu %(n)s (« %(nom)s »)") % {
            "n": position_du_lieu,
            "nom": nom_du_lieu,
        }
    else:
        debut_du_message = _("Lieu %(n)s") % {"n": position_du_lieu}
        erreurs.append(
            _("%(debut)s : le nom est obligatoire.") % {"debut": debut_du_message}
        )

    # bool est un int en Python : on le refuse avant la conversion en nombre.
    # / bool is an int in Python: refuse it before the number conversion.
    latitude_lue = lieu_lu.get("latitude")
    longitude_lue = lieu_lu.get("longitude")
    latitude = None if isinstance(latitude_lue, bool) else _nombre_ou_none(latitude_lue)
    longitude = (
        None if isinstance(longitude_lue, bool) else _nombre_ou_none(longitude_lue)
    )
    if latitude is None or not -90 <= latitude <= 90:
        erreurs.append(
            _("%(debut)s : la latitude doit être un nombre entre -90 et 90.")
            % {"debut": debut_du_message}
        )
    if longitude is None or not -180 <= longitude <= 180:
        erreurs.append(
            _("%(debut)s : la longitude doit être un nombre entre -180 et 180.")
            % {"debut": debut_du_message}
        )

    url_du_lieu = _url_http_ou_vide(lieu_lu.get("url"))
    if url_du_lieu is None:
        erreurs.append(
            _(
                "%(debut)s : l'URL doit être une adresse complète en http:// ou "
                "https://, sans espace, guillemet ni chevron."
            )
            % {"debut": debut_du_message}
        )

    adresse_du_lieu = _texte(lieu_lu.get("adresse"))
    if _texte_trop_long(adresse_du_lieu):
        erreurs.append(_message_texte_trop_long(debut_du_message, "adresse"))

    evenements_lus = lieu_lu.get("evenements", [])
    if evenements_lus is None:
        evenements_lus = []
    evenements_propres = []
    if not isinstance(evenements_lus, list):
        erreurs.append(
            _("%(debut)s : « evenements » doit être une liste.")
            % {"debut": debut_du_message}
        )
    else:
        for position_de_l_evenement, evenement_lu in enumerate(evenements_lus, start=1):
            evenement_propre, erreurs_de_l_evenement = _nettoyer_un_evenement(
                evenement_lu,
                position_du_lieu,
                nom_du_lieu,
                position_de_l_evenement,
            )
            erreurs.extend(erreurs_de_l_evenement)
            if evenement_propre is not None:
                evenements_propres.append(evenement_propre)

    if erreurs:
        return None, erreurs

    lieu_propre = {
        "nom": nom_du_lieu,
        "latitude": latitude,
        "longitude": longitude,
    }
    if adresse_du_lieu:
        lieu_propre["adresse"] = adresse_du_lieu
    if url_du_lieu:
        lieu_propre["url"] = url_du_lieu
    lieu_propre["evenements"] = evenements_propres
    return lieu_propre, []


def nettoyer_carte_figee(donnees_lues):
    """
    Vérifie le contenu d'un fichier de carte figée, déjà décodé en Python.
    / Checks a frozen-map file content, already decoded.

    LOCALISATION : pages/carte_figee.py

    Règles :
    - la racine est une liste, avec au moins un lieu ;
    - un lieu a un nom, une latitude (-90 à 90) et une longitude (-180 à 180) ;
    - un événement a un nom ; sa date, si elle est là, est au format
      2026-10-02 ou 2026-10-02T14:00 ;
    - une URL est une adresse http:// ou https:// complète, sans espace,
      guillemet ni chevron ;
    - un nom, une adresse ou un tag fait au plus 200 caractères ;
    - une clé inconnue est ignorée, sans erreur.
    Toutes les erreurs sont rendues d'un coup, avec leur position.
    / Rules above. Every error is returned at once, with its position.

    Appelée par le formulaire de l'admin ET par Bloc.clean().
    / Called by the admin form AND by Bloc.clean().

    :return: (lieux_propres, erreurs). Si erreurs n'est pas vide, lieux_propres
      ne doit pas être enregistré.
    """
    if not isinstance(donnees_lues, list):
        return [], [
            _(
                "Le fichier doit contenir une liste de lieux, entre crochets [ ]. "
                "Voir l'exemple."
            )
        ]
    if not donnees_lues:
        return [], [_("Le fichier ne contient aucun lieu.")]

    lieux_propres = []
    erreurs = []
    for position_du_lieu, lieu_lu in enumerate(donnees_lues, start=1):
        lieu_propre, erreurs_du_lieu = _nettoyer_un_lieu(lieu_lu, position_du_lieu)
        erreurs.extend(erreurs_du_lieu)
        if lieu_propre is not None:
            lieux_propres.append(lieu_propre)
    return lieux_propres, erreurs


def lire_fichier_carte_figee(fichier_envoye):
    """
    Lit le fichier envoyé par l'admin, puis le vérifie.
    / Reads the file sent by the admin, then checks it.

    LOCALISATION : pages/carte_figee.py

    :param fichier_envoye: un UploadedFile Django.
    :return: (lieux_propres, erreurs)
    """
    if fichier_envoye.size > TAILLE_MAX_DU_FICHIER_EN_OCTETS:
        return [], [_("Le fichier dépasse 2 Mo.")]

    contenu_en_octets = fichier_envoye.read()
    try:
        contenu_en_texte = contenu_en_octets.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [_("Le fichier doit être encodé en UTF-8.")]

    # RecursionError : un fichier fait de milliers de [ imbriques depasse la
    # pile de Python. Ce n'est pas une JSONDecodeError : sans ce cas, la page
    # de l'admin sortirait en erreur 500.
    # / RecursionError: thousands of nested [ overflow Python's stack. It is not
    # a JSONDecodeError: without this case the admin page would 500.
    try:
        donnees_lues = json.loads(contenu_en_texte)
    except RecursionError:
        return [], [_("Le fichier est imbriqué trop profondément pour être lu.")]
    except json.JSONDecodeError as erreur_de_lecture:
        return [], [
            _(
                "Le fichier n'est pas un JSON valide (ligne %(ligne)s, colonne %(colonne)s)."
            )
            % {"ligne": erreur_de_lecture.lineno, "colonne": erreur_de_lecture.colno}
        ]

    return nettoyer_carte_figee(donnees_lues)


def resume_de_la_carte(lieux):
    """
    Phrase courte qui décrit une carte déjà chargée, pour l'éditeur.
    / Short sentence describing an already loaded map, for the editor.

    :return: par exemple « Carte actuelle : 74 lieux, 163 événements. »
    """
    nombre_de_lieux = len(lieux)
    nombre_d_evenements = 0
    for lieu in lieux:
        nombre_d_evenements += len(lieu.get("evenements", []))
    return _("Carte actuelle : %(lieux)s lieu(x), %(evenements)s événement(s).") % {
        "lieux": nombre_de_lieux,
        "evenements": nombre_d_evenements,
    }


def aide_du_champ_fichier():
    """
    Texte d'aide du champ d'import, avec l'exemple replié dans un accordéon.
    / Help text of the upload field, with the example in a collapsed accordion.

    LOCALISATION : pages/carte_figee.py — lu par pages/admin.py

    Unfold affiche le help_text avec |safe (unfold/helpers/help_text.html) :
    le <details> s'affiche donc tel quel. format_html échappe l'exemple et les
    textes traduits. Styles en ligne : le bundle Tailwind d'Unfold ne contient
    pas les classes qu'il n'utilise pas lui-même.
    / Unfold renders help_text with |safe. format_html escapes the example.
    Inline styles: Unfold's Tailwind bundle lacks unused classes.
    """
    return format_html(
        "{}"
        '<details style="margin-top: 8px;">'
        '<summary style="cursor: pointer; font-weight: 600;">{}</summary>'
        '<pre style="margin-top: 8px; padding: 12px; border-radius: 6px; '
        "background-color: var(--color-base-100, #f3f4f6); overflow-x: auto; "
        'font-size: 12px; line-height: 1.4;">{}</pre>'
        '<p style="margin-top: 8px;">{}</p>'
        '<p style="margin-top: 4px;">{}</p>'
        '<p style="margin-top: 4px;">{}</p>'
        "</details>",
        _(
            "Fichier JSON : une liste de lieux, chacun avec ses coordonnées GPS et "
            "ses événements. 2 Mo au plus. Un nouvel import remplace toute la carte."
        ),
        _("Voir un exemple de fichier"),
        EXEMPLE_DE_FICHIER,
        _(
            "Lieu — obligatoire : nom, latitude, longitude. Facultatif : adresse, url, evenements."
        ),
        _(
            "Événement — obligatoire : nom. Facultatif : date (2026-10-02 ou 2026-10-02T14:00), url, tags."
        ),
        _(
            "Les URL sont des adresses complètes en http:// ou https://. "
            "200 caractères au plus pour un nom, une adresse ou un tag. "
            "Une clé inconnue est ignorée."
        ),
    )


# ---------------------------------------------------------------------------
# Conversion pour l'outil de carte du réseau / Conversion for the network map
# ---------------------------------------------------------------------------
def _slug_du_tag(nom_du_tag, slug_par_nom, nom_par_slug):
    """
    Donne a un tag un slug UNIQUE et NON VIDE sur toute la carte.
    / Gives a tag a UNIQUE and NON-EMPTY slug across the whole map.

    explorer.js filtre les evenements par slug de tag (puces, ?tag=) :
    - un slug vide ne filtre rien (le filtre vide est « pas de filtre ») ;
    - deux noms differents avec le meme slug seraient fusionnes.
    slugify(allow_unicode=True) garde les lettres accentuees et non latines.
    Un nom qui ne donne aucun slug (emoji seul) recoit « tag-<n> ». Un slug deja
    pris par un AUTRE nom recoit un suffixe « -2 », « -3 »...
    / Empty slug = no filter; same slug for two names = merged. Fallbacks above.

    :param slug_par_nom: dict nom -> slug, partage par toute la carte.
    :param nom_par_slug: dict slug -> nom, partage par toute la carte.
    """
    if nom_du_tag in slug_par_nom:
        return slug_par_nom[nom_du_tag]

    slug_de_base = slugify(nom_du_tag, allow_unicode=True)
    if not slug_de_base:
        slug_de_base = f"tag-{len(slug_par_nom) + 1}"

    slug_retenu = slug_de_base
    numero_de_suffixe = 2
    while slug_retenu in nom_par_slug:
        slug_retenu = f"{slug_de_base}-{numero_de_suffixe}"
        numero_de_suffixe += 1

    slug_par_nom[nom_du_tag] = slug_retenu
    nom_par_slug[slug_retenu] = nom_du_tag
    return slug_retenu


def donnees_explorer_depuis_carte_figee(lieux):
    """
    Convertit la liste des lieux au format lu par explorer.js.
    / Converts the venue list to the format read by explorer.js.

    LOCALISATION : pages/carte_figee.py

    explorer.js (seo/static/seo/explorer.js) attend {"points": [...],
    "tenants": [...]} : la forme produite pour la page « Autour de nous » par
    seo/services.py (build_aggregate_points, build_explorer_data_for_tenants).
    Un lieu du fichier devient UN tenant ET UN point. Son identifiant est
    « lieu-<n> » : il ne correspond à aucun espace TiBillet.
    / One file venue becomes ONE tenant AND ONE point, with id "lieu-<n>".

    Le nom `events_futurs` vient de la page réseau, qui ne montre que les
    événements à venir. Ici les événements peuvent être passés : on garde
    quand même ce nom, car c'est la clé que lit explorer.js.
    / `events_futurs` is the key explorer.js reads, even for past events.

    Pas de limite à 5 événements par lieu, contrairement au cache de la page
    réseau : la liste doit montrer tous les événements du fichier.
    / No 5-event cap: the list must show every event of the file.

    Les liens passent par la clé `url` (lieu et événement) : explorer.js la
    préfère au lien construit avec le domaine TiBillet (lienDuLieu,
    lienDeLEvenement). `domain` reste vide.
    / Links go through `url`; `domain` stays empty.
    """
    points = []
    tenants = []
    slug_par_nom_de_tag = {}
    nom_de_tag_par_slug = {}

    for position_du_lieu, lieu in enumerate(lieux, start=1):
        identifiant_du_lieu = f"lieu-{position_du_lieu}"
        nom_du_lieu = lieu.get("nom", "")
        url_du_lieu = lieu.get("url", "")
        adresse_du_lieu = lieu.get("adresse", "")

        # Les événements triés par date ; un événement sans date va à la fin.
        # / Events sorted by date; an event without a date goes last.
        evenements_avec_date = []
        evenements_sans_date = []
        for evenement in lieu.get("evenements", []):
            if evenement.get("date"):
                evenements_avec_date.append(evenement)
            else:
                evenements_sans_date.append(evenement)
        evenements_avec_date.sort(key=lambda evenement: evenement["date"])
        evenements_dans_l_ordre = evenements_avec_date + evenements_sans_date

        evenements_pour_explorer = []
        for position_de_l_evenement, evenement in enumerate(
            evenements_dans_l_ordre, start=1
        ):
            tags_pour_explorer = []
            for nom_du_tag in evenement.get("tags", []):
                slug_du_tag = _slug_du_tag(
                    nom_du_tag, slug_par_nom_de_tag, nom_de_tag_par_slug
                )
                tags_pour_explorer.append({"slug": slug_du_tag, "name": nom_du_tag})
            evenements_pour_explorer.append(
                {
                    "uuid": f"{identifiant_du_lieu}-ev-{position_de_l_evenement}",
                    "name": evenement.get("nom", ""),
                    "datetime_iso": evenement.get("date", ""),
                    "slug": "",
                    "url": evenement.get("url", ""),
                    "tags": tags_pour_explorer,
                    "image_url": None,
                }
            )

        # `locality` porte l'adresse : c'est la ligne « 📍 » que la carte de la
        # LISTE affiche sous le nom (explorer.js, buildLieuCard). La popup, elle,
        # lit `address_display`. / `locality` carries the address: it is the
        # "📍" line the LIST card shows; the popup reads `address_display`.
        tenants.append(
            {
                "tenant_id": identifiant_du_lieu,
                "name": nom_du_lieu,
                "domain": "",
                "url": url_du_lieu,
                "short_description": "",
                "locality": adresse_du_lieu,
                "country": "",
                "logo_url": None,
            }
        )
        points.append(
            {
                "pa_id": f"{identifiant_du_lieu}:0",
                "latitude": lieu.get("latitude"),
                "longitude": lieu.get("longitude"),
                "pa_name": nom_du_lieu,
                "address_display": adresse_du_lieu,
                "is_main_address": True,
                "tenant_id": identifiant_du_lieu,
                "tenant_organisation": nom_du_lieu,
                "tenant_domain": "",
                "tenant_logo_url": None,
                "tenant_image_url": None,
                "url": url_du_lieu,
                "events_futurs": evenements_pour_explorer,
                "events_futurs_count_total": len(evenements_pour_explorer),
            }
        )

    return {"points": points, "tenants": tenants}
