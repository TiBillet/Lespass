"""
Apercu des blocs dans l'admin, et gestion des blocs depuis la fiche d'une Page.
/ Block previews in the admin, and block management from a Page form.

LOCALISATION : pages/admin_apercu.py

Ce module ne contient que des FONCTIONS de module (pas de methodes de
ModelAdmin : Unfold enveloppe ces methodes avec son systeme d'actions). Elles
sont branchees par BlocAdmin.get_urls() et PageAdmin.get_urls()
(pages/admin.py), derriere admin_site.admin_view().
/ Module-level FUNCTIONS only (Unfold wraps ModelAdmin methods). Wired by
BlocAdmin.get_urls() and PageAdmin.get_urls(), behind admin_site.admin_view().

UN SEUL MOTEUR DE RENDU : rendre_document_apercu().
Il rend un document HTML complet, avec le skin du lieu, qui ne contient qu'un
bloc. Deux usages :
- fiche Bloc : apercu EN DIRECT d'un bloc pas encore enregistre
  (vue_apercu_bloc_en_direct, POST, iframe srcdoc) ;
- fiche Page : apercu de TOUTE la page, blocs en base, avec une barre
  d'actions posee sur chaque bloc (vue_apercu_page, GET, une seule iframe src).
/ A single renderer: a full HTML document with the venue's skin. Used live on
the Bloc form (one unsaved block) and on the Page form (all saved blocks, each
with an action bar, in a single iframe).

MODELES DE BLOC : pour la personne qui edite, un bloc est UN choix, le
« modele » (ex. « Section › Carte »). En base, il reste deux champs : le type
(l'intention) et l'affichage (la forme). modeles_de_bloc() construit la liste
des modeles a partir du catalogue ; le formulaire les redecoupe a l'envoi.
/ BLOCK MODELS: for the editor, a block is ONE choice, the "model". In the
database it stays two fields (type + affichage).

SECURITE : l'apercu passe par nettoyer_bloc(), la meme fonction que
BlocAdmin.save_model. On n'affiche donc jamais un HTML que l'enregistrement
aurait filtre.
/ SECURITY: the preview goes through nettoyer_bloc(), like save_model.
"""

import uuid

from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.utils.http import urlencode
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST
from rest_framework import serializers

from Administration.admin.site import sanitize_textfields
from Administration.utils import url_a_schema_dangereux
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from pages.admin_widgets import GABARIT_LIGNE_PAR_EDITEUR, contexte_d_une_ligne, ligne_vide
from pages.blocs_catalogue import AFFICHAGES_PAR_TYPE, CHAMPS_PAR_AFFICHAGE
from pages.editeur_items import (
    CLES_CONTENU_CARTES,
    CLES_CONTENU_LIEU,
    CLES_PAR_EDITEUR,
    CLES_POINTS_GPS,
    lire_lignes_depuis_post,
    nettoyer_contenu_cartes,
    nettoyer_contenu_lieu,
    nettoyer_points_gps,
)
from django.templatetags.static import static

from pages.models import Bloc, ImageGalerie, Page
from pages.services import deplacer_bloc, gabarit_skin, renumeroter_blocs

# Champs lien d'un bloc : un schema dangereux (javascript:...) y est vide.
# / A block's link fields: a dangerous scheme is emptied.
CHAMPS_URL_DU_BLOC = ("bouton_url", "bouton2_url", "embed_url")

# Noms des champs de formulaire des editeurs de lignes (voir BlocAdminForm).
# / Form field names of the line editors (see BlocAdminForm).
CHAMP_CONTENU_LIEU = "contenu_lieu"
CHAMP_CONTENU_CARTES = "contenu_cartes"
CHAMP_POINTS_GPS = "points_gps_editeur"

# Champ de formulaire « Modele de bloc » : type et affichage en une valeur.
# / "Block model" form field: type and affichage in one value.
CHAMP_MODELE = "modele"
SEPARATEUR_MODELE = ":"


def uuid_ou_none(valeur):
    """
    Convertit une valeur en UUID, ou rend None si ce n'en est pas un.
    / Converts a value to a UUID, or returns None if it is not one.

    LOCALISATION : pages/admin_apercu.py

    Les cles primaires de Page et Bloc sont des UUID. Une requete ORM avec
    « abc » comme cle leve une ValidationError, donc une erreur 500. On
    verifie la valeur AVANT toute requete : un identifiant invalide donne
    une 404 (ou une redirection de l'admin), jamais une 500.
    / Page and Bloc keys are UUIDs; querying with "abc" raises a
    ValidationError (500). Check first: invalid ids give a 404, never a 500.
    """
    try:
        return uuid.UUID(str(valeur))
    except (ValueError, TypeError, AttributeError):
        return None


def _uuid_ou_404(valeur):
    """
    Comme uuid_ou_none, mais leve une 404 pour un identifiant invalide.
    / Like uuid_ou_none, but raises a 404 for an invalid id.
    """
    uuid_valide = uuid_ou_none(valeur)
    if uuid_valide is None:
        raise Http404()
    return uuid_valide


# ---------------------------------------------------------------------------
# Modeles de bloc : type + affichage en un seul choix
# / Block models: type + affichage as a single choice
# ---------------------------------------------------------------------------
def valeur_du_modele(type_bloc, affichage):
    """
    Assemble type et affichage en une valeur de modele : "SECTION:CARTE".
    Un type a rendu unique n'a pas d'affichage : "TEXTE:".
    / Joins type and affichage into a model value.
    """
    return f"{type_bloc}{SEPARATEUR_MODELE}{affichage or ''}"


def decouper_modele(valeur):
    """
    L'inverse de valeur_du_modele : "SECTION:CARTE" -> ("SECTION", "CARTE").
    / The reverse of valeur_du_modele.
    """
    type_bloc, separateur, affichage = str(valeur).partition(SEPARATEUR_MODELE)
    return type_bloc, affichage


def modeles_de_bloc():
    """
    Les modeles de bloc, groupes par type, dans l'ordre du catalogue.
    / Block models, grouped by type, in catalogue order.

    LOCALISATION : pages/admin_apercu.py

    Sert au select « Modele de bloc » de la fiche Bloc et aux menus
    « + Ajouter un bloc » de la fiche Page. Lu dans AFFICHAGES_PAR_TYPE :
    un affichage ajoute au catalogue apparait ici sans rien toucher.
    Les libelles sont traduits a l'appel (appeler cette fonction a chaque
    requete, jamais une fois au chargement du module).
    / Used by the "Block model" select and the "+ Add a block" menus. Read
    from AFFICHAGES_PAR_TYPE. Labels are translated at call time.

    :return: liste de groupes {"type_bloc", "libelle", "modeles": [...]},
      chaque modele etant {"valeur", "type_bloc", "affichage", "libelle"}.
    """
    libelle_par_affichage = dict(Bloc.AFFICHAGE_CHOICES)

    groupes = []
    for code_type, libelle_type in Bloc.TYPE_BLOC_CHOICES:
        # « Section mise en avant (bannière, …) » -> « Section mise en avant » :
        # la parenthese d'exemples est remplacee par la liste des modeles.
        # / The examples in parentheses are replaced by the model list.
        libelle_court = str(libelle_type).split(" (")[0]
        affichages = AFFICHAGES_PAR_TYPE.get(code_type, ())

        modeles = []
        if not affichages:
            modeles.append(
                {
                    "valeur": valeur_du_modele(code_type, ""),
                    "type_bloc": code_type,
                    "affichage": "",
                    "libelle": libelle_court,
                }
            )
        for affichage in affichages:
            modeles.append(
                {
                    "valeur": valeur_du_modele(code_type, affichage),
                    "type_bloc": code_type,
                    "affichage": affichage,
                    "libelle": str(libelle_par_affichage.get(affichage, affichage)),
                }
            )
        groupes.append({"type_bloc": code_type, "libelle": libelle_court, "modeles": modeles})
    return groupes


def libelle_du_modele(bloc):
    """
    « Section › Carte », ou juste « Texte » pour un type a rendu unique.
    / "Section › Card", or just "Text" for a single-rendering type.
    """
    libelle_type = str(bloc.get_type_bloc_display()).split(" (")[0]
    if not bloc.affichage or not AFFICHAGES_PAR_TYPE.get(bloc.type_bloc):
        return libelle_type
    return f"{libelle_type} › {bloc.get_affichage_display()}"


def libelle_court_du_modele(bloc):
    """
    Libelle court pour la barre d'actions : « Carte », « Bannière d'ouverture »,
    ou « Texte » pour un type a rendu unique (sans parenthese d'exemples).
    / Short label for the action bar.
    """
    if bloc.affichage and AFFICHAGES_PAR_TYPE.get(bloc.type_bloc):
        return str(bloc.get_affichage_display()).split(" (")[0]
    return str(bloc.get_type_bloc_display()).split(" (")[0]


def url_d_ajout_d_un_bloc(page, modele, inserer_apres):
    """
    URL du formulaire d'ajout, pre-rempli : page, type, affichage, place.
    / Pre-filled add form URL: page, type, affichage, position.
    Django lit les parametres GET comme valeurs initiales du formulaire ;
    `inserer_apres` est relu par BlocAdmin.save_model.
    """
    parametres = urlencode(
        {
            "page": page.pk,
            "type_bloc": modele["type_bloc"],
            "affichage": modele["affichage"],
            "inserer_apres": inserer_apres,
        }
    )
    return f"{reverse('staff_admin:pages_bloc_add')}?{parametres}"


def menu_d_ajout(page, inserer_apres):
    """
    Les modeles de bloc, chacun avec son lien d'ajout a cette place.
    / Block models, each with its add link at this position.
    """
    groupes = modeles_de_bloc()
    for groupe in groupes:
        for modele in groupe["modeles"]:
            modele["url"] = url_d_ajout_d_un_bloc(page, modele, inserer_apres)
    return groupes


# ---------------------------------------------------------------------------
# Regles partagees avec BlocAdmin.save_model
# / Rules shared with BlocAdmin.save_model
# ---------------------------------------------------------------------------
def nettoyer_bloc(bloc, texte_markdown=""):
    """
    Nettoie un bloc avant de l'enregistrer OU de l'afficher en apercu.
    / Cleans a block before saving it OR showing it as a preview.

    LOCALISATION : pages/admin_apercu.py

    - Bloc TEXTE : `texte` est de la SOURCE Markdown, pas du HTML. On ne la
      passe pas dans clean_html (elle serait mutilee). Elle vient du champ de
      formulaire texte_markdown, pose APRES le nettoyage des autres champs.
      La securite est assuree au rendu par le filtre rendre_markdown.
    - Autres types : sanitize_textfields (clean_html) sur les champs texte.
    - Tous : une URL a schema dangereux (javascript:, data:, vbscript:) est
      videe, car elle produirait un XSS au clic.
    / TEXTE: Markdown source, not cleaned here (rendre_markdown does it at render
    time). Others: clean_html. All: dangerous-scheme URLs are emptied.
    """
    sanitize_textfields(bloc)
    if bloc.type_bloc == Bloc.TEXTE:
        bloc.texte = texte_markdown or ""

    for nom_du_champ_url in CHAMPS_URL_DU_BLOC:
        valeur = getattr(bloc, nom_du_champ_url, "")
        if url_a_schema_dangereux(valeur):
            setattr(bloc, nom_du_champ_url, "")


def affichage_utilise_contenu(type_bloc, affichage):
    """
    Vrai si le gabarit de ce couple (type, affichage) lit la liste `contenu`
    en sous-cartes. Lu dans le catalogue, jamais recopie.
    / True if this (type, affichage) template reads `contenu` as sub-cards.
    """
    champs_par_affichage = CHAMPS_PAR_AFFICHAGE.get(type_bloc, {})
    champs_rendus = champs_par_affichage.get(affichage, [])
    return "contenu" in champs_rendus


def appliquer_editeurs_de_lignes(bloc, contenu_lieu, contenu_cartes, points_gps):
    """
    Recopie les editeurs de lignes dans les champs JSON du bloc.
    / Copies the line editors into the block's JSON fields.

    LOCALISATION : pages/admin_apercu.py

    Les trois editeurs sont postes en meme temps : ceux qui ne concernent pas
    le type choisi sont seulement caches par Alpine. C'est donc le TYPE (et
    l'affichage) qui decide quel editeur alimente `contenu`. Un bloc dont
    l'affichage ne lit pas `contenu` garde sa valeur intacte.
    / All three editors are posted (unused ones are only hidden by Alpine), so
    the TYPE (and affichage) decides which one feeds `contenu`. A block whose
    affichage ignores `contenu` keeps its value untouched.
    """
    if bloc.type_bloc == Bloc.LIEU:
        bloc.contenu = contenu_lieu
        bloc.points_gps = points_gps
        return
    if bloc.type_bloc == Bloc.SECTION and affichage_utilise_contenu(
        bloc.type_bloc, bloc.affichage
    ):
        bloc.contenu = contenu_cartes


# ---------------------------------------------------------------------------
# Validation des donnees de l'apercu en direct
# / Live preview data validation
# ---------------------------------------------------------------------------
def _longueur_max_du_modele(nom_du_champ):
    """
    Longueur maximale d'un champ texte du modele Bloc.
    / Max length of a Bloc text field.
    """
    return Bloc._meta.get_field(nom_du_champ).max_length


def _bornes_du_modele(nom_du_champ):
    """
    Bornes d'un champ entier du modele Bloc, lues dans ses validateurs : ceux
    declares (ex. hauteur_px : 100 a 4000) et ceux que Django ajoute selon le
    type (ex. PositiveSmallIntegerField : 0 a 32767).
    / Bounds of a Bloc integer field, read from its validators.

    :return: dict {"min_value": ..., "max_value": ...}, a passer au champ DRF.
    """
    from django.core.validators import MaxValueValidator, MinValueValidator

    bornes = {}
    for validateur in Bloc._meta.get_field(nom_du_champ).validators:
        if isinstance(validateur, MinValueValidator):
            bornes["min_value"] = validateur.limit_value
        if isinstance(validateur, MaxValueValidator):
            bornes["max_value"] = validateur.limit_value
    return bornes


class ApercuBlocSerializer(serializers.Serializer):
    """
    Valide le formulaire (non enregistre) de la fiche Bloc pour l'apercu.
    / Validates the (unsaved) Bloc form for the preview.

    Tous les champs sont optionnels : on previsualise un bloc EN COURS de
    saisie. Les URL sont des CharField et non des URLField : pendant la
    frappe, « https://you » n'est pas encore une URL valide, et l'apercu ne
    doit pas se bloquer pour autant.
    / All fields are optional: we preview a block BEING typed. URLs are
    CharFields: a half-typed URL must not block the preview.
    """

    type_bloc = serializers.ChoiceField(
        choices=Bloc.TYPE_BLOC_CHOICES,
        error_messages={"invalid_choice": _("Choisissez un type de bloc.")},
    )
    affichage = serializers.CharField(required=False, allow_blank=True)
    page = serializers.UUIDField(
        required=False,
        allow_null=True,
        error_messages={"invalid": _("Choisissez la page du bloc.")},
    )
    # Longueurs et bornes LUES SUR LE MODELE (_longueur_max_du_modele,
    # _bornes_du_modele) : l'apercu et l'enregistrement refusent exactement
    # les memes valeurs. Les recopier ici a la main les ferait diverger.
    # / Lengths and bounds READ FROM THE MODEL: preview and save reject exactly
    # the same values.
    titre = serializers.CharField(
        required=False, allow_blank=True, max_length=_longueur_max_du_modele("titre")
    )
    sous_titre = serializers.CharField(
        required=False, allow_blank=True, max_length=_longueur_max_du_modele("sous_titre")
    )
    badge = serializers.CharField(
        required=False, allow_blank=True, max_length=_longueur_max_du_modele("badge")
    )
    texte = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    texte_markdown = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )
    bouton_label = serializers.CharField(
        required=False, allow_blank=True, max_length=_longueur_max_du_modele("bouton_label")
    )
    bouton_url = serializers.CharField(
        required=False, allow_blank=True, max_length=_longueur_max_du_modele("bouton_url")
    )
    bouton2_label = serializers.CharField(
        required=False, allow_blank=True, max_length=_longueur_max_du_modele("bouton2_label")
    )
    bouton2_url = serializers.CharField(
        required=False, allow_blank=True, max_length=_longueur_max_du_modele("bouton2_url")
    )
    auteur_nom = serializers.CharField(
        required=False, allow_blank=True, max_length=_longueur_max_du_modele("auteur_nom")
    )
    auteur_role = serializers.CharField(
        required=False, allow_blank=True, max_length=_longueur_max_du_modele("auteur_role")
    )
    embed_url = serializers.CharField(
        required=False, allow_blank=True, max_length=_longueur_max_du_modele("embed_url")
    )
    hauteur_px = serializers.IntegerField(required=False, **_bornes_du_modele("hauteur_px"))
    source = serializers.ChoiceField(
        choices=Bloc.SOURCE_CHOICES, required=False, allow_blank=True
    )
    nombre_max = serializers.IntegerField(required=False, **_bornes_du_modele("nombre_max"))
    page_source = serializers.UUIDField(required=False, allow_null=True)
    # Lignes deja reassemblees par la vue (lire_lignes_depuis_post).
    # / Lines already reassembled by the view.
    contenu_lieu = serializers.ListField(child=serializers.DictField(), required=False)
    contenu_cartes = serializers.ListField(
        child=serializers.DictField(), required=False
    )
    points_gps_editeur = serializers.ListField(
        child=serializers.DictField(), required=False
    )

    def validate_contenu_lieu(self, lignes):
        items_propres, erreurs = nettoyer_contenu_lieu(lignes)
        if erreurs:
            raise serializers.ValidationError(erreurs)
        return items_propres

    def validate_contenu_cartes(self, lignes):
        items_propres, erreurs = nettoyer_contenu_cartes(lignes)
        if erreurs:
            raise serializers.ValidationError(erreurs)
        return items_propres

    def validate_points_gps_editeur(self, lignes):
        items_propres, erreurs = nettoyer_points_gps(lignes)
        if erreurs:
            raise serializers.ValidationError(erreurs)
        return items_propres

    def validate(self, donnees):
        # Garde-fou : le select « Modele de bloc » ne propose que des couples
        # valides, mais la requete peut etre forgee (ou les champs caches
        # desynchronises). Un affichage etranger au type est vide : le modele
        # posera l'affichage par defaut du type, et l'apercu reste affichable.
        # / Safety net: the model select only offers valid pairs, but a request
        # can be forged. A foreign affichage is emptied; the default applies.
        affichages_permis = AFFICHAGES_PAR_TYPE.get(donnees["type_bloc"], ())
        affichage_choisi = donnees.get("affichage", "")
        if affichage_choisi not in affichages_permis:
            donnees["affichage"] = ""
        return donnees


def _donnees_postees_pour_le_serializer(donnees_postees):
    """
    Transforme le POST du formulaire Bloc en dict simple pour le serializer.
    / Turns the Bloc form POST into a plain dict for the serializer.

    Les champs vides numeriques ou UUID sont omis (plutot que "" invalide).
    Les editeurs de lignes sont reassembles ici.
    / Empty numeric/UUID fields are omitted. Line editors are reassembled here.
    """
    champs_simples = (
        "type_bloc",
        "affichage",
        "titre",
        "sous_titre",
        "badge",
        "texte",
        "texte_markdown",
        "bouton_label",
        "bouton_url",
        "bouton2_label",
        "bouton2_url",
        "auteur_nom",
        "auteur_role",
        "embed_url",
        "source",
    )
    champs_omis_si_vides = ("page", "page_source", "hauteur_px", "nombre_max")

    donnees = {}
    for nom in champs_simples:
        if nom in donnees_postees:
            donnees[nom] = donnees_postees.get(nom)
    for nom in champs_omis_si_vides:
        valeur = donnees_postees.get(nom, "")
        if valeur:
            donnees[nom] = valeur

    # Le select « Modele de bloc » fait foi : il porte le type ET l'affichage
    # (ex. "SECTION:CARTE"). Les champs caches type_bloc / affichage suivent
    # ce select dans le navigateur, mais on ne compte pas sur ce JavaScript.
    # / The "block model" select is authoritative: it carries type AND affichage.
    modele = donnees_postees.get(CHAMP_MODELE, "")
    if modele:
        type_bloc, affichage = decouper_modele(modele)
        donnees["type_bloc"] = type_bloc
        donnees["affichage"] = affichage

    donnees[CHAMP_CONTENU_LIEU] = lire_lignes_depuis_post(
        donnees_postees, CHAMP_CONTENU_LIEU, CLES_CONTENU_LIEU
    )
    donnees[CHAMP_CONTENU_CARTES] = lire_lignes_depuis_post(
        donnees_postees, CHAMP_CONTENU_CARTES, CLES_CONTENU_CARTES
    )
    donnees[CHAMP_POINTS_GPS] = lire_lignes_depuis_post(
        donnees_postees, CHAMP_POINTS_GPS, CLES_POINTS_GPS
    )
    return donnees


# ---------------------------------------------------------------------------
# Rendu / Rendering
# ---------------------------------------------------------------------------
def rendre_document_apercu(request, page, elements, avec_outils=False):
    """
    Rend le document HTML complet d'un apercu, avec le skin du lieu.
    / Renders the full HTML preview document, with the venue skin.

    LOCALISATION : pages/admin_apercu.py

    Meme contexte que la page publique (pages/views.py:rendre_page), mais :
    - `embed=True` : les shells n'affichent ni navbar ni pied de page ;
    - `apercu_admin=True` : le skin V2 n'affiche pas l'en-tete du lieu ;
    - `sans_panneaux_globaux=True` : pas de panneaux connexion / contact.
    Le gabarit est pages/<skin>/apercu.html, repli sur classic. La boucle des
    blocs est commune aux skins : admin/pages/apercu/_blocs.html.
    / Same context as the public page, without navbar, footer, venue header or
    global panels. Template: pages/<skin>/apercu.html, classic fallback.

    :param elements: liste de dicts {"bloc": Bloc, ...}. Avec `avec_outils`,
      chaque element porte aussi les donnees de sa barre d'actions.
    :param avec_outils: True pour la fiche Page (barres ↑ ↓ ✎ 🗑 +).

    Rien n'est JAMAIS enregistre ici. / Nothing is EVER saved here.
    """
    # Import local : BaseBillet.views importe pages (meme raison que
    # pages/views.py). / Local import to avoid a circular import.
    from BaseBillet.views import get_context, get_skin_courant

    blocs = []
    for element in elements:
        blocs.append(element["bloc"])

    contexte = get_context(request)
    contexte["skin_courant"] = get_skin_courant()
    contexte["page_courante"] = page
    contexte["blocs"] = blocs
    contexte["elements_apercu"] = elements
    contexte["avec_outils"] = avec_outils
    contexte["embed"] = True
    contexte["apercu_admin"] = True
    contexte["sans_panneaux_globaux"] = True
    return render_to_string(gabarit_skin("apercu.html"), contexte, request=request)


def _bloc_depuis_le_formulaire(donnees_valides, bloc_uuid):
    """
    Construit un bloc NON ENREGISTRE a partir du formulaire valide.
    / Builds an UNSAVED block from the validated form.

    Si le bloc existe deja, on part de sa version en base : ses images
    enregistrees et sa galerie (references galerie:N) restent visibles. Les
    fichiers choisis mais pas encore envoyes sont montres ensuite, sous forme
    d'images de remplacement (poser_les_images_de_remplacement).
    / If the block exists, start from its stored version so saved images and
    the gallery stay visible. Chosen, not-yet-uploaded files are shown later as
    placeholders.

    :return: (bloc, message_d_erreur ou None)
    """
    bloc = None
    uuid_du_bloc = uuid_ou_none(bloc_uuid) if bloc_uuid else None
    if uuid_du_bloc is not None:
        bloc = Bloc.objects.select_related("page").filter(pk=uuid_du_bloc).first()
    if bloc is None:
        bloc = Bloc()

    page_uuid = donnees_valides.get("page")
    if page_uuid:
        page_choisie = Page.objects.filter(pk=page_uuid).first()
        if page_choisie is not None:
            bloc.page = page_choisie
    if bloc.page_id is None:
        return None, _("Choisissez la page du bloc pour voir l'aperçu.")

    champs_recopies_tels_quels = (
        "type_bloc",
        "affichage",
        "titre",
        "sous_titre",
        "badge",
        "texte",
        "bouton_label",
        "bouton_url",
        "bouton2_label",
        "bouton2_url",
        "auteur_nom",
        "auteur_role",
        "embed_url",
        "hauteur_px",
        "source",
        "nombre_max",
    )
    for nom in champs_recopies_tels_quels:
        if nom in donnees_valides:
            setattr(bloc, nom, donnees_valides[nom])

    page_source_uuid = donnees_valides.get("page_source")
    if page_source_uuid:
        bloc.page_source = Page.objects.filter(pk=page_source_uuid).first()
    else:
        bloc.page_source = None

    bloc.poser_affichage_par_defaut()
    nettoyer_bloc(bloc, donnees_valides.get("texte_markdown", ""))
    appliquer_editeurs_de_lignes(
        bloc,
        contenu_lieu=donnees_valides.get(CHAMP_CONTENU_LIEU, []),
        contenu_cartes=donnees_valides.get(CHAMP_CONTENU_CARTES, []),
        points_gps=donnees_valides.get(CHAMP_POINTS_GPS, []),
    )
    return bloc, None


# ---------------------------------------------------------------------------
# Images de remplacement : une image choisie mais pas encore envoyee
# / Placeholder images: an image chosen but not uploaded yet
# ---------------------------------------------------------------------------
# L'apercu en direct n'envoie pas les fichiers (ce serait un envoi complet a
# chaque frappe). Quand une image est choisie dans le formulaire, on montre a
# sa place une image de remplacement : on voit ou elle s'affichera, et a
# quelle taille. Le navigateur dit quels champs ont un fichier choisi dans
# `fichiers_choisis` (voir admin/pages/bloc/apercu_panneau.html).
# / The live preview does not send files. When an image is chosen, a
# placeholder shows where and how big it will be. The browser lists the file
# inputs holding a chosen file in `fichiers_choisis`.

# Champs image du bloc, et l'image de remplacement de chacun.
# / The block's image fields, and each one's placeholder.
IMAGE_DE_REMPLACEMENT_PAR_CHAMP = {
    "image": "pages/admin/image_a_venir.svg",
    "image_secondaire": "pages/admin/image_a_venir.svg",
    "auteur_photo": "pages/admin/image_a_venir_carree.svg",
}

# Prefixe des lignes de l'encart « Images de galerie » (formset de l'inline) :
# le related_name de ImageGalerie.bloc. / Prefix of the gallery inline rows.
PREFIXE_GALERIE = "images_galerie"

# Nombre maximum de lignes de galerie lues dans l'apercu (plafond de securite).
# / Maximum gallery rows read by the preview (safety cap).
NOMBRE_MAX_DE_LIGNES_DE_GALERIE = 1000


class TailleDeRemplacement:
    """
    Une variation d'image de remplacement : ce que les gabarits lisent sur
    `bloc.image.hdr` (url, width, height).
    / A placeholder variation: what templates read on `bloc.image.hdr`.
    """

    def __init__(self, url, largeur, hauteur):
        self.url = url
        self.width = largeur
        self.height = hauteur


class ImageDeRemplacement(TailleDeRemplacement):
    """
    Remplace un fichier image (StdImageFieldFile) dans un bloc NON enregistre.
    / Stands in for an image file in an UNSAVED block.

    LOCALISATION : pages/admin_apercu.py

    Les gabarits lisent `bloc.image` (vrai si une image existe), puis
    `bloc.image.url` ou une variation (`bloc.image.hdr.url`, `.width`,
    `.height`...). Cet objet offre exactement ces attributs, pour chaque
    variation declaree sur le modele, avec une taille au bon format : la mise
    en page de l'apercu est celle qu'aura la vraie image.
    / Offers exactly what templates read, for every declared variation, with
    realistic sizes so the preview layout matches the real image.

    :param variations: les variations du champ, telles que StdImage les range
      (`champ.variations`) : nom -> {"width", "height", "crop", ...}.
    :param rapport: largeur / hauteur de l'image de remplacement (16/9, 1).
    """

    def __init__(self, url, variations, rapport):
        largeur_de_base = 1600
        super().__init__(url, largeur_de_base, round(largeur_de_base / rapport))
        self.name = url
        for nom_variation, variation in variations.items():
            largeur_max = variation.get("width") or largeur_de_base
            hauteur_max = variation.get("height") or largeur_de_base
            est_recadree = bool(variation.get("crop"))
            if est_recadree:
                # Recadrage : la variation a exactement ces dimensions.
                # / Cropped: the variation has exactly these dimensions.
                largeur, hauteur = largeur_max, hauteur_max
            else:
                # Sinon, l'image tient dans la boite en gardant son format.
                # / Otherwise the image fits the box, keeping its ratio.
                largeur = min(largeur_max, round(hauteur_max * rapport))
                hauteur = round(largeur / rapport)
            setattr(self, nom_variation, TailleDeRemplacement(url, largeur, hauteur))

    def __bool__(self):
        # « Il y a une image » : les gabarits testent {% if bloc.image %}.
        # / "There is an image": templates test {% if bloc.image %}.
        return True


def _image_de_remplacement(nom_du_champ, variations):
    chemin = IMAGE_DE_REMPLACEMENT_PAR_CHAMP.get(nom_du_champ, "pages/admin/image_a_venir.svg")
    rapport = 1 if chemin.endswith("_carree.svg") else 16 / 9
    return ImageDeRemplacement(static(chemin), variations, rapport)


def _poser_un_fichier_sans_le_valider(objet, nom_du_champ, valeur):
    """
    Pose une valeur sur un champ fichier d'un objet NON enregistre, sans
    passer par le descripteur de StdImage (qui voudrait calculer les
    variations d'un vrai fichier). Django rend ensuite la valeur telle quelle.
    / Sets a file field value on an UNSAVED object, bypassing StdImage's
    descriptor. Django then returns the value as is.
    """
    objet.__dict__[nom_du_champ] = valeur


def poser_les_images_de_remplacement(bloc, donnees_postees):
    """
    Montre dans l'apercu les images choisies, ou retirees, mais pas encore
    enregistrees.
    / Shows in the preview the images chosen, or removed, but not saved yet.

    LOCALISATION : pages/admin_apercu.py

    - Champ image du bloc (image, seconde image, photo d'auteur) :
      * un fichier choisi -> image de remplacement ;
      * la case « Effacer » cochee -> plus d'image.
    - Encart « Images de galerie » : la galerie de l'apercu est reconstruite
      depuis les lignes du formulaire. Une ligne cochee « Supprimer »
      disparait ; un fichier choisi (ligne neuve ou remplacement) devient une
      image de remplacement. Les references galerie:N du Markdown suivent.
    / Block image fields: chosen file -> placeholder; "clear" ticked -> no
    image. Gallery: rebuilt from the form rows (deleted rows removed, chosen
    files become placeholders).

    Rien n'est enregistre. / Nothing is saved.
    """
    fichiers_choisis = set()
    for nom in donnees_postees.get("fichiers_choisis", "").split(","):
        if nom.strip():
            fichiers_choisis.add(nom.strip())

    for nom_du_champ in IMAGE_DE_REMPLACEMENT_PAR_CHAMP:
        if nom_du_champ in fichiers_choisis:
            variations = bloc._meta.get_field(nom_du_champ).variations
            _poser_un_fichier_sans_le_valider(
                bloc, nom_du_champ, _image_de_remplacement(nom_du_champ, variations)
            )
        elif donnees_postees.get(f"{nom_du_champ}-clear") == "on":
            _poser_un_fichier_sans_le_valider(bloc, nom_du_champ, None)

    _reconstruire_la_galerie(bloc, donnees_postees, fichiers_choisis)


def _reconstruire_la_galerie(bloc, donnees_postees, fichiers_choisis):
    """
    Remplace la galerie du bloc (pour l'apercu seulement) par ce que montre
    le formulaire. Sans encart « Images de galerie » dans la page, la galerie
    en base est gardee telle quelle.
    / Replaces the block gallery (preview only) with what the form shows.
    Without the gallery inline, the stored gallery is kept.

    Le resultat est pose dans le cache de `prefetch_related` : les gabarits et
    rendre_bloc_markdown lisent `bloc.images_galerie.all()`, qui le renvoie
    sans requete.
    / The result goes into the prefetch cache read by images_galerie.all().
    """
    nombre_de_lignes = donnees_postees.get(f"{PREFIXE_GALERIE}-TOTAL_FORMS", "")
    if not nombre_de_lignes.isdigit():
        return
    # Plafond : la valeur vient du navigateur. Sans lui, un POST forge avec
    # TOTAL_FORMS=100000000 ferait tourner la boucle cent millions de fois.
    # (Meme plafond que les formsets Django, cf. forms.formsets.MAX_NUM_FORMS.)
    # / Cap: the value comes from the browser; a forged POST would spin the
    # loop 10^8 times. Same cap as Django formsets.
    nombre_de_lignes = min(int(nombre_de_lignes), NOMBRE_MAX_DE_LIGNES_DE_GALERIE)

    images_en_base = {}
    if not bloc._state.adding:
        for image_en_base in ImageGalerie.objects.filter(bloc=bloc):
            images_en_base[str(image_en_base.pk)] = image_en_base

    variations_galerie = ImageGalerie._meta.get_field("image").variations
    images_pour_l_apercu = []
    for rang in range(nombre_de_lignes):
        prefixe = f"{PREFIXE_GALERIE}-{rang}"
        if donnees_postees.get(f"{prefixe}-DELETE") == "on":
            continue

        image_existante = images_en_base.get(donnees_postees.get(f"{prefixe}-id", ""))
        fichier_choisi = f"{prefixe}-image" in fichiers_choisis
        if image_existante is None and not fichier_choisi:
            # Ligne neuve restee vide. / New row left empty.
            continue

        if image_existante is not None:
            image_pour_l_apercu = image_existante
        else:
            image_pour_l_apercu = ImageGalerie(bloc=bloc)
        image_pour_l_apercu.legende = donnees_postees.get(f"{prefixe}-legende", "")
        image_pour_l_apercu.lien_url = donnees_postees.get(f"{prefixe}-lien_url", "")
        if fichier_choisi:
            _poser_un_fichier_sans_le_valider(
                image_pour_l_apercu,
                "image",
                _image_de_remplacement("image", variations_galerie),
            )
        images_pour_l_apercu.append(image_pour_l_apercu)

    # Un QuerySet deja « rempli » : on le pose comme le ferait prefetch_related.
    # / An already "filled" QuerySet, set as prefetch_related would.
    galerie = ImageGalerie.objects.none()
    galerie._result_cache = images_pour_l_apercu
    galerie._prefetch_done = True
    if not hasattr(bloc, "_prefetched_objects_cache"):
        bloc._prefetched_objects_cache = {}
    bloc._prefetched_objects_cache[PREFIXE_GALERIE] = galerie


# ---------------------------------------------------------------------------
# Vues : fiche Bloc / Views: Bloc form
# ---------------------------------------------------------------------------
@require_POST
def vue_apercu_bloc_en_direct(request):
    """
    Apercu en direct du bloc en cours de saisie (fiche Bloc).
    / Live preview of the block being edited (Bloc form).

    LOCALISATION : pages/admin_apercu.py

    FLUX :
    1. admin/pages/bloc/apercu_panneau.html envoie tout le formulaire (hx-post)
       a chaque frappe (avec un delai), et au chargement de la fiche.
    2. Les lignes des editeurs sont reassemblees, puis ApercuBlocSerializer
       valide le tout.
    3. Un bloc NON enregistre est construit et nettoye (nettoyer_bloc).
    4. On renvoie une <iframe srcdoc> qui contient le document rendu.
    Les erreurs sont renvoyees en HTTP 200 : htmx ne remplace pas le contenu
    sur une reponse 4xx, et l'apercu resterait fige sans explication.
    / Returns an <iframe srcdoc>. Errors come back as HTTP 200 because htmx
    does not swap 4xx responses.
    """
    if not TenantAdminPermissionWithRequest(request):
        return HttpResponseForbidden()

    donnees = _donnees_postees_pour_le_serializer(request.POST)
    serializer_apercu = ApercuBlocSerializer(data=donnees)
    if not serializer_apercu.is_valid():
        return render(
            request,
            "admin/pages/bloc/partials/apercu_erreurs.html",
            {"erreurs": serializer_apercu.errors},
        )

    donnees_valides = serializer_apercu.validated_data
    bloc_uuid = request.POST.get("bloc_uuid", "")
    bloc_non_enregistre, message_d_erreur = _bloc_depuis_le_formulaire(
        donnees_valides, bloc_uuid
    )
    if message_d_erreur:
        return render(
            request,
            "admin/pages/bloc/partials/apercu_erreurs.html",
            {"message": message_d_erreur},
        )

    poser_les_images_de_remplacement(bloc_non_enregistre, request.POST)
    document_html = rendre_document_apercu(
        request, bloc_non_enregistre.page, [{"bloc": bloc_non_enregistre}]
    )
    return render(
        request,
        "admin/pages/bloc/partials/apercu_iframe.html",
        {
            "document_html": document_html,
        },
    )


@require_GET
def vue_ligne_vide(request):
    """
    Renvoie une ligne vide pour un editeur de lignes (bouton « + Ajouter »).
    / Returns an empty line for a line editor ("+ Add" button).

    LOCALISATION : pages/admin_apercu.py

    Parametres GET : `editeur` (lieu, cartes, gps) et `nom` (nom du champ de
    formulaire). Le nom est limite aux trois champs connus : il est recopie
    dans les attributs `name` du HTML renvoye.
    / GET params: editor and field name. The name is restricted to the three
    known fields, since it is copied into the returned HTML.
    """
    if not TenantAdminPermissionWithRequest(request):
        return HttpResponseForbidden()

    editeur = request.GET.get("editeur", "")
    nom_du_champ = request.GET.get("nom", "")
    noms_autorises = (CHAMP_CONTENU_LIEU, CHAMP_CONTENU_CARTES, CHAMP_POINTS_GPS)
    if editeur not in CLES_PAR_EDITEUR or nom_du_champ not in noms_autorises:
        return HttpResponseForbidden()

    contexte = contexte_d_une_ligne(nom_du_champ, editeur, ligne_vide(editeur))
    return render(request, GABARIT_LIGNE_PAR_EDITEUR[editeur], contexte)


# ---------------------------------------------------------------------------
# Vues : fiche Page / Views: Page form
# ---------------------------------------------------------------------------
def _elements_avec_outils(page):
    """
    Les blocs d'une page, chacun avec les donnees de sa barre d'actions.
    / A page's blocks, each with its action bar data.

    LOCALISATION : pages/admin_apercu.py

    Pour chaque bloc : son rang (1, 2, 3...), son modele, les URL de ses
    actions, et l'URL de son menu « + » (charge a la demande par
    vue_menu_ajout). `inserer_apres=<rang>` est relu par BlocAdmin.save_model
    pour placer le nouveau bloc.
    / Per block: rank, model label, action URLs and the "+" menu URL (loaded
    on demand by vue_menu_ajout).
    """
    blocs_dans_l_ordre = list(page.blocs.order_by("position", "pk").prefetch_related("images_galerie"))
    nombre_de_blocs = len(blocs_dans_l_ordre)

    elements = []
    for rang, bloc in enumerate(blocs_dans_l_ordre, start=1):
        elements.append(
            {
                "bloc": bloc,
                "rang": rang,
                "est_le_premier": rang == 1,
                "est_le_dernier": rang == nombre_de_blocs,
                "libelle_modele": libelle_du_modele(bloc),
                "libelle_court": libelle_court_du_modele(bloc),
                "url_modifier": reverse("staff_admin:pages_bloc_change", args=[bloc.pk]),
                "url_monter": reverse("staff_admin:pages_bloc_deplacer", args=[bloc.pk, "monter"]),
                "url_descendre": reverse("staff_admin:pages_bloc_deplacer", args=[bloc.pk, "descendre"]),
                "url_retirer": reverse("staff_admin:pages_bloc_retirer", args=[bloc.pk]),
                # Le menu « + » n'est pas construit ici : il est charge a la
                # premiere ouverture (vue_menu_ajout). On ne passe que son URL.
                # / The "+" menu is not built here: loaded on first open.
                "url_menu_ajout": (
                    reverse("staff_admin:pages_page_menu_ajout", args=[page.pk])
                    + f"?inserer_apres={rang}"
                ),
                "testid_menu": f"page-bloc-{rang}-ajouter",
            }
        )
    return elements


@require_GET
@xframe_options_sameorigin
def vue_apercu_page(request, object_id):
    """
    Apercu de TOUTE la page, dans une seule iframe de la fiche Page.
    / Preview of the WHOLE page, in a single iframe of the Page form.

    LOCALISATION : pages/admin_apercu.py

    Les blocs sont rendus a la suite, dans la vraie grille du skin : des cartes
    voisines se rangent cote a cote, comme sur le site. Chaque bloc recoit une
    barre d'actions (admin/pages/apercu/_outils_bloc.html), posee par-dessus
    par pages/static/pages/admin/apercu_page_outils.js.
    `xframe_options_sameorigin` autorise l'affichage en iframe dans l'admin (le
    reglage par defaut de Django l'interdit).
    / Blocks rendered in the real skin grid, each with an overlaid action bar.
    xframe_options_sameorigin allows it in an admin iframe.
    """
    if not TenantAdminPermissionWithRequest(request):
        return HttpResponseForbidden()

    page = get_object_or_404(Page, pk=_uuid_ou_404(object_id))
    elements = _elements_avec_outils(page)
    return HttpResponse(rendre_document_apercu(request, page, elements, avec_outils=True))


@require_GET
def vue_menu_ajout(request, object_id):
    """
    Liste des modeles de bloc pour le menu « + » d'UN bloc (charge a la demande).
    / Block model list for ONE block's "+" menu (loaded on demand).

    LOCALISATION : pages/admin_apercu.py

    FLUX :
    1. admin/pages/apercu/_outils_bloc.html inclut _menu_modeles.html avec
       `url_chargement` (l'URL de cette vue, ?inserer_apres=<rang>).
    2. A la premiere ouverture du menu (evenement `toggle` du <details>), htmx
       fait un hx-get ici, une seule fois.
    3. On renvoie _menu_modeles_liens.html : les modeles groupes par type,
       chaque lien pre-rempli pour inserer le bloc a cette place.
    Avant, la barre de chaque bloc embarquait deja le menu complet (~25 liens) :
    une page de 50 blocs en portait ~1250.
    / Returns the model links for one position, on the menu's first opening,
    instead of embedding the full menu in every block bar.
    """
    if not TenantAdminPermissionWithRequest(request):
        return HttpResponseForbidden()

    page = get_object_or_404(Page, pk=_uuid_ou_404(object_id))
    valeur = request.GET.get("inserer_apres", "")
    if not valeur.isdigit():
        raise Http404()
    inserer_apres = int(valeur)

    return render(
        request,
        "admin/pages/apercu/_menu_modeles_liens.html",
        {
            "groupes": menu_d_ajout(page, inserer_apres),
            "cible": "_top",
            "testid": f"page-bloc-{inserer_apres}-ajouter",
        },
    )


def _recharger_l_apercu():
    """
    Reponse qui demande a htmx de recharger le document de l'iframe.
    / Response asking htmx to reload the iframe document.

    Les boutons ↑ ↓ 🗑 vivent DANS l'iframe de la fiche Page : apres l'action,
    l'en-tete HX-Refresh recharge ce document, qui reaffiche les blocs dans
    leur nouvel ordre. Le formulaire de la page, hors iframe, n'est pas touche.
    / The buttons live INSIDE the iframe: HX-Refresh reloads that document
    only; the page form outside the iframe is untouched.
    """
    reponse = HttpResponse("")
    reponse["HX-Refresh"] = "true"
    return reponse


@require_POST
def vue_deplacer_bloc(request, object_id, sens):
    """
    Monte ou descend un bloc d'un cran, puis recharge l'apercu de la page.
    / Moves a block one step up or down, then reloads the page preview.

    LOCALISATION : pages/admin_apercu.py
    Boutons ↑ ↓ de admin/pages/apercu/_outils_bloc.html.
    """
    if not TenantAdminPermissionWithRequest(request):
        return HttpResponseForbidden()
    if sens not in ("monter", "descendre"):
        return HttpResponseForbidden()

    bloc = get_object_or_404(Bloc.objects.select_related("page"), pk=_uuid_ou_404(object_id))
    deplacer_bloc(bloc, sens)
    return _recharger_l_apercu()


@require_POST
def vue_retirer_bloc(request, object_id):
    """
    Supprime un bloc depuis la fiche Page, puis recharge l'apercu.
    / Deletes a block from the Page form, then reloads the preview.

    LOCALISATION : pages/admin_apercu.py

    Le bouton 🗑 demande une confirmation (hx-confirm) : la suppression est
    definitive. Les positions sont renumerotees ensuite.
    / The 🗑 button asks for confirmation: deletion is final.
    """
    if not TenantAdminPermissionWithRequest(request):
        return HttpResponseForbidden()

    bloc = get_object_or_404(Bloc.objects.select_related("page"), pk=_uuid_ou_404(object_id))
    page = bloc.page
    # Suppression et renumerotation dans UNE transaction : pendant ce temps,
    # un deplacement concurrent attend (verrou pose par renumeroter_blocs).
    # / Delete and renumber in ONE transaction; a concurrent move waits.
    with transaction.atomic():
        bloc.delete()
        renumeroter_blocs(page)
    return _recharger_l_apercu()
