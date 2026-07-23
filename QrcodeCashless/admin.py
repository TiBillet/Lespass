"""
QrcodeCashless/admin.py — Admin CarteCashless dans Unfold (staff_admin_site).
QrcodeCashless/admin.py — CarteCashless admin in Unfold (staff_admin_site).

Le dashboard (Administration/admin/dashboard.py) propose un bouton « Cartes NFC »
pointant vers `staff_admin:QrcodeCashless_cartecashless_changelist`.
/ The dashboard "NFC cards" button reverses this changelist.

SOURCE DE VERITE : FEDOW.
Une carte NFC est d'abord creee chez Fedow (POST /card/, via fedow_connect),
puis miroitee ici. On peut donc AJOUTER une carte depuis cet admin (l'ajout
appelle Fedow), mais jamais la MODIFIER ni la SUPPRIMER : Fedow est maitre.
/ SOURCE OF TRUTH: FEDOW. A card is first created on Fedow, then mirrored here.
Adding from this admin calls Fedow. Editing/deleting is forbidden.

IMPORTANT — Filtrage par tenant :
CarteCashless et Detail sont en SHARED_APPS (schema public PostgreSQL) : PAS
d'isolation automatique. get_queryset() DOIT filtrer par tenant (via
detail.origine = la place qui a emis la carte), exactement comme fedow_core/admin.py.
Sans ca, un lieu verrait les cartes de TOUS les lieux.
/ CarteCashless and Detail are in SHARED_APPS: no automatic isolation.
get_queryset() MUST filter by tenant (via detail.origine).

Voir la spec : TECH_DOC/SESSIONS/QRCODECASHLESS/SPEC.md
"""

import logging
import re
import uuid as uuid_module

from django import forms
from django.contrib import admin, messages
from django.db import connection
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.widgets import UnfoldAdminTextInputWidget

from Administration.admin_tenant import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from fedow_connect.fedow_api import CarteInconnueDeFedow, FedowAPI
from fedow_connect.models import FedowConfig
from QrcodeCashless.models import CarteCashless, Detail

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers module-level.
# JAMAIS a l'interieur d'une classe ModelAdmin Unfold : Unfold wrappe les
# methodes de classe via son systeme @action et leur passe object_id au lieu
# des vrais arguments (piege documente dans tests/PIEGES.md).
# / Module-level helpers. NEVER inside an Unfold ModelAdmin class.
# ---------------------------------------------------------------------------

# Un tag NFC ou un numero imprime : exactement 8 caracteres hexadecimaux.
# Meme regex que Fedow applique dans CardAPI.card_tag_id_retrieve.
# / Exactly 8 hex chars. Same regex as Fedow's CardAPI.card_tag_id_retrieve.
MOTIF_HEXA_8_CARACTERES = re.compile(r"^[0-9A-F]{8}$")


def _uuid_court(valeur):
    """8 premiers caracteres d'un uuid (lisibilite admin). / First 8 chars of a uuid."""
    if not valeur:
        return "—"
    return str(valeur)[:8]


def _numero_depuis_uuid(uuid_du_qrcode):
    """
    Le numero imprime est toujours le debut de l'uuid du QR code.
    / The printed number is always the beginning of the QR code uuid.

    Exemple : l'uuid b194aeb9-0f77-4e3c-… donne le numero B194AEB9.
    C'est la convention du CSV historique de Fedow (example_csv_cards_list.csv).
    """
    return uuid_du_qrcode.hex[:8].upper()


def _uuid_prefixe_par_le_numero(numero_imprime):
    """
    Fabrique un uuid4 dont les 8 premiers caracteres sont le numero imprime.
    / Builds a uuid4 whose first 8 chars are the printed number.

    On remplace les 8 premiers caracteres hexadecimaux d'un uuid4 tire au sort.
    Le resultat reste un UUID version 4 valide : les bits de version et de
    variant vivent aux positions hexadecimales 12 et 16, hors de la zone
    remplacee.
    / The result stays a valid v4 UUID: version and variant bits live at hex
    positions 12 and 16, outside the replaced range.
    """
    uuid_tire_au_sort = uuid_module.uuid4()
    hexa_complet = numero_imprime.lower() + uuid_tire_au_sort.hex[8:]
    return uuid_module.UUID(hexa_complet)


def _deriver_les_identifiants(numero_imprime, uuid_du_qrcode):
    """
    Complete le numero imprime et l'uuid du QR code quand l'un des deux manque.
    / Fills in the printed number and QR code uuid when one is missing.

    LOCALISATION : QrcodeCashless/admin.py

    Une seule invariante : numero_imprime == uuid.hex[:8].upper()

    | numero | uuid  | resultat                                             |
    |--------|-------|------------------------------------------------------|
    | vide   | vide  | uuid4 tire, puis numero = debut de l'uuid             |
    | saisi  | vide  | uuid fabrique avec le numero en prefixe               |
    | vide   | saisi | numero = debut de l'uuid                              |
    | saisi  | saisi | verifie ; si divergence, on leve une ValidationError  |

    :param numero_imprime: str de 8 caracteres hexa majuscules, ou None
    :param uuid_du_qrcode: uuid.UUID, ou None
    :return: tuple (numero_imprime, uuid_du_qrcode) tous les deux remplis
    :raises forms.ValidationError: si les deux sont saisis et divergent
    """
    # Les deux sont vides : on tire un uuid, le numero en decoule.
    # / Both empty: draw a uuid, the number follows.
    if not numero_imprime and not uuid_du_qrcode:
        uuid_du_qrcode = uuid_module.uuid4()
        return _numero_depuis_uuid(uuid_du_qrcode), uuid_du_qrcode

    # Seul le numero est saisi : on fabrique l'uuid autour de lui.
    # / Only the number is given: build the uuid around it.
    if numero_imprime and not uuid_du_qrcode:
        return numero_imprime, _uuid_prefixe_par_le_numero(numero_imprime)

    # Seul l'uuid est saisi : le numero en decoule.
    # / Only the uuid is given: the number follows.
    if uuid_du_qrcode and not numero_imprime:
        return _numero_depuis_uuid(uuid_du_qrcode), uuid_du_qrcode

    # Les deux sont saisis : ils doivent respecter l'invariante.
    # / Both given: they must satisfy the invariant.
    numero_attendu = _numero_depuis_uuid(uuid_du_qrcode)
    if numero_imprime != numero_attendu:
        raise forms.ValidationError(
            _(
                "Le numéro imprimé doit être le début de l'UUID du QR code. "
                "Pour cet UUID, le numéro attendu est %(attendu)s."
            ),
            params={"attendu": numero_attendu},
            code="numero_incoherent",
        )
    return numero_imprime, uuid_du_qrcode


def _verifier_que_le_lieu_est_appaire_a_fedow():
    """
    Refuse l'ajout si le lieu n'a jamais fait son handshake avec Fedow.
    / Refuses the add if the venue never did its Fedow handshake.

    FedowConfig est un SingletonModel : get_solo() le cree toujours. Mais ses
    champs sont null=True. Sans cette verification, un lieu non appaire
    tomberait sur un TypeError illisible au fond de fedow_api._post().
    / FedowConfig is a SingletonModel: get_solo() always creates it, but its
    fields are null=True. Without this check, an unpaired venue would hit an
    unreadable TypeError deep inside fedow_api._post().
    """
    configuration_fedow = FedowConfig.get_solo()
    if not configuration_fedow.fedow_place_admin_apikey:
        raise forms.ValidationError(
            _(
                "Ce lieu n'est pas appairé à Fedow. Impossible de créer une carte "
                "tant que la configuration Fedow n'est pas terminée."
            ),
            code="lieu_non_appaire",
        )


def _verifier_que_la_carte_est_absente_en_local(tag_id, numero_imprime, uuid_du_qrcode):
    """
    Verifie que les trois identifiants sont libres dans CarteCashless.
    / Checks the three identifiers are free in CarteCashless.

    POURQUOI EXPLICITEMENT : tag_id, number et uuid ne sont pas des champs de
    modele du formulaire (ce sont des champs de formulaire, cf. CarteCashlessAddForm).
    ModelForm.validate_unique() ne les controle donc PAS. Sans ces trois exists(),
    un doublon irait jusqu'a l'IntegrityError PostgreSQL, soit une erreur 500.
    / ModelForm.validate_unique() does NOT check them, since they are form fields,
    not model fields. Without these exists(), a duplicate would raise IntegrityError.

    ATTENTION : CarteCashless vit dans le schema public. L'unicite est GLOBALE a
    toutes les instances. Une carte appartenant a un autre lieu declenche le
    conflit tout en restant invisible dans la liste. Le message le dit.
    / CarteCashless lives in the public schema: uniqueness is GLOBAL across all
    venues. A card owned by another venue triggers the conflict while staying
    invisible in the changelist. The message says so.
    """
    message_commun = _(
        "Cette carte est déjà enregistrée. Si elle n'apparaît pas dans la liste, "
        "c'est qu'elle appartient à un autre lieu : les cartes sont uniques sur "
        "toute l'instance."
    )

    if CarteCashless.objects.filter(tag_id=tag_id).exists():
        raise forms.ValidationError(message_commun, code="tag_id_deja_pris")

    if CarteCashless.objects.filter(number=numero_imprime).exists():
        raise forms.ValidationError(message_commun, code="numero_deja_pris")

    if CarteCashless.objects.filter(uuid=uuid_du_qrcode).exists():
        raise forms.ValidationError(message_commun, code="uuid_deja_pris")


def _creer_ou_recuperer_la_carte_chez_fedow(tag_id, numero_imprime, uuid_du_qrcode, detail):
    """
    Assure que la carte existe chez Fedow, qui en est la source de verite.
    / Ensures the card exists on Fedow, the source of truth.

    LOCALISATION : QrcodeCashless/admin.py

    FLUX :
    1. On demande la carte a Fedow (GET card/<tag_id>/).
    2. Si Fedow la connait -> RECONCILIATION. On adopte SES valeurs de numero
       imprime et d'uuid, et on ne cree rien. C'est le chemin de reparation
       quand le miroir local a diverge.
    3. Si Fedow ne la connait pas (CarteInconnueDeFedow) -> CREATION.
       On la cree chez Fedow (POST card/), puis on garde nos valeurs.
    4. Toute autre erreur (reseau, 400, 500) -> on abandonne. Rien n'est ecrit,
       ni chez Fedow ni en local.

    :param tag_id: str, 8 caracteres hexa majuscules
    :param numero_imprime: str, 8 caracteres hexa majuscules
    :param uuid_du_qrcode: uuid.UUID
    :param detail: Detail (porte la generation attendue par Fedow)
    :return: tuple (numero_imprime, uuid_du_qrcode, carte_recuperee_de_fedow)
        carte_recuperee_de_fedow vaut True si on est passe par la reconciliation.
    :raises forms.ValidationError: Fedow injoignable, ou refus de creation.
    """
    api_fedow = FedowAPI()

    # --- 1 et 2 : Fedow connait-il deja cette carte ? ---
    # / Does Fedow already know this card?
    try:
        carte_chez_fedow = api_fedow.NFCcard.retrieve(tag_id)

    except CarteInconnueDeFedow:
        # La carte n'existe pas chez Fedow : on continue vers la creation.
        # / The card does not exist on Fedow: proceed to creation.
        carte_chez_fedow = None

    except Exception as erreur_de_lecture:
        logger.error(f"Lecture de la carte {tag_id} chez Fedow : {erreur_de_lecture}")
        raise forms.ValidationError(
            _("Fedow est injoignable, la carte n'a pas été créée. Détail : %(detail)s"),
            params={"detail": str(erreur_de_lecture)},
            code="fedow_injoignable",
        )

    if carte_chez_fedow:
        # RECONCILIATION : Fedow est maitre, on adopte ses valeurs.
        # / RECONCILIATION: Fedow is master, adopt its values.
        logger.info(f"Carte {tag_id} deja connue de Fedow : reconciliation locale.")
        return (
            carte_chez_fedow["number_printed"],
            carte_chez_fedow["qrcode_uuid"],
            True,
        )

    # --- 3 : creation chez Fedow ---
    # / Creation on Fedow
    # Fedow cree l'Origin automatiquement depuis la place signataire et la
    # generation qu'on lui passe. La generation vient du Detail choisi.
    # / Fedow auto-creates the Origin from the signing place and the generation.
    cartes_a_creer = [
        {
            "first_tag_id": tag_id,
            "qrcode_uuid": str(uuid_du_qrcode),
            "number_printed": numero_imprime,
            "generation": detail.generation,
            "is_primary": False,
        }
    ]

    try:
        api_fedow.NFCcard.create_cards(cartes_a_creer)

    except Exception as erreur_de_creation:
        logger.error(f"Creation de la carte {tag_id} chez Fedow : {erreur_de_creation}")
        raise forms.ValidationError(
            _("Fedow a refusé la création de la carte. Détail : %(detail)s"),
            params={"detail": str(erreur_de_creation)},
            code="fedow_refuse_la_creation",
        )

    return numero_imprime, uuid_du_qrcode, False


def _obtenir_la_generation_par_defaut_du_lieu():
    """
    Renvoie une generation de cartes (Detail) pour le lieu courant, creee au besoin.
    / Returns a card generation (Detail) for the current venue, created if needed.

    LOCALISATION : QrcodeCashless/admin.py

    Filet de securite quand le gestionnaire ajoute une carte sans choisir de
    generation. Sans Detail, la carte serait INVISIBLE dans la liste (le
    changelist filtre sur detail.origine) et ne serait JAMAIS creee chez Fedow.
    / Safety net when the manager adds a card without picking a generation.
    Without a Detail the card is invisible (changelist filters on detail.origine)
    and never created on Fedow.

    On reutilise la generation la plus haute (la plus recente) du lieu s'il y en a
    une, sinon on cree la generation 1. On NE fait PAS get_or_create(origine,
    generation) : le couple (origine, generation) n'a AUCUNE contrainte d'unicite,
    et un lieu peut deja porter plusieurs generations 1 (donnees de demo + creations
    manuelles) -> get_or_create leverait MultipleObjectsReturned.
    / We reuse the venue's highest (most recent) generation, else create generation
    1. We do NOT get_or_create on (origine, generation): the pair has no unique
    constraint and a venue may already carry several generation-1 rows, which would
    raise MultipleObjectsReturned.

    :return: Detail rattache au lieu courant (connection.tenant)
    """
    lieu_courant = connection.tenant

    # Le lieu a-t-il deja une generation ? On prend la plus haute (la plus recente).
    # / Does the venue already have a generation? Take the highest (most recent) one.
    generation_existante = (
        Detail.objects.filter(origine=lieu_courant).order_by("-generation").first()
    )
    if generation_existante is not None:
        return generation_existante

    # Aucune generation pour ce lieu : on cree la generation 1.
    # base_url prefixe l'UUID dans le QR code imprime, deduit du domaine du lieu,
    # exactement comme DetailAdmin.save_model. On ne remplit que si ca tient dans
    # les 60 caracteres du champ.
    # / No generation for this venue: create generation 1. base_url prefixes the
    # printed QR code UUID, derived from the venue's domain like DetailAdmin does.
    base_url = None
    domaine_du_lieu = lieu_courant.get_primary_domain()
    if domaine_du_lieu:
        adresse_des_qrcodes = f"https://{domaine_du_lieu.domain}/qr/"
        longueur_maximale = Detail._meta.get_field("base_url").max_length
        if len(adresse_des_qrcodes) <= longueur_maximale:
            base_url = adresse_des_qrcodes

    return Detail.objects.create(
        origine=lieu_courant,
        generation=1,
        base_url=base_url,
    )


# ---------------------------------------------------------------------------
# Detail — les generations de cartes / Card generations
# ---------------------------------------------------------------------------


@admin.register(Detail, site=staff_admin_site)
class DetailAdmin(ModelAdmin):
    """
    Admin des generations de cartes (Detail), volontairement CACHE de la sidebar.
    / Card generations admin, deliberately HIDDEN from the sidebar.

    Detail est l'equivalent local de Fedow.Origin(place, generation).

    has_module_permission() renvoie False : le modele disparait de l'index et de
    la sidebar, mais ses vues restent accessibles. Seul effet visible : le bouton
    « + » a cote du select « detail » du formulaire d'ajout de carte, que Django
    greffe automatiquement (RelatedFieldWidgetWrapper) des qu'une cle etrangere
    pointe vers un modele enregistre sur le meme admin site.
    / has_module_permission() returns False: the model vanishes from the index and
    sidebar but its views stay reachable. Only visible effect: the "+" button next
    to the card form's "detail" select, added by Django automatically.
    """

    # L'utilisateur ne choisit QUE le numero de generation, et une image en option.
    # origine et base_url sont deduits du lieu courant dans save_model().
    # / The user only picks the generation number, and optionally an image.
    # origine and base_url are derived from the current venue in save_model().
    fields = ["generation", "img"]
    list_display = ["__str__", "generation"]

    def get_queryset(self, request):
        """Detail est en SHARED_APPS : on filtre sur le lieu courant.
        / Detail is in SHARED_APPS: filter on the current venue."""
        queryset = super().get_queryset(request)
        return queryset.filter(origine=connection.tenant)

    def save_model(self, request, obj, form, change):
        """
        Force l'origine au lieu courant, et deduit l'adresse des QR codes.
        / Forces the origin to the current venue, and derives the QR code address.

        L'origine n'est jamais choisie : une generation de cartes appartient
        toujours au lieu qui la cree. Le champ n'est meme pas affiche.
        / The origin is never chosen: a card generation always belongs to the
        venue that creates it. The field is not even displayed.

        base_url est l'adresse qui prefixe l'UUID dans le QR code imprime, au
        format « https://mon-lieu.tld/qr/ » (convention du CSV historique de
        Fedow). On la deduit du domaine du lieu plutot que de la faire saisir.
        On ne l'ecrase pas si elle est deja renseignee.
        / base_url prefixes the UUID in the printed QR code. Derived from the
        venue's domain rather than typed in. Never overwritten if already set.
        """
        obj.origine = connection.tenant

        if not obj.base_url:
            domaine_du_lieu = connection.tenant.get_primary_domain()
            if domaine_du_lieu:
                adresse_des_qrcodes = f"https://{domaine_du_lieu.domain}/qr/"
                # Le champ est limite a 60 caracteres : on ne remplit que si ca
                # tient, plutot que de lever une DataError PostgreSQL.
                # / The field caps at 60 chars: only fill it if it fits.
                longueur_maximale = Detail._meta.get_field("base_url").max_length
                if len(adresse_des_qrcodes) <= longueur_maximale:
                    obj.base_url = adresse_des_qrcodes
                else:
                    logger.warning(
                        f"base_url non renseignee : « {adresse_des_qrcodes} » "
                        f"depasse {longueur_maximale} caracteres."
                    )

        super().save_model(request, obj, form, change)

    # --- Permissions ---

    def has_module_permission(self, request):
        """False = modele masque de l'index et de la sidebar admin.
        / False = model hidden from the admin index and sidebar."""
        return False

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# CarteCashless — le formulaire d'ajout / The add form
# ---------------------------------------------------------------------------


# Template du bloc d'aide affiche en tete du formulaire d'ajout.
# Rendu a la volee dans get_fieldsets() (et non ici), pour que les traductions
# suivent la langue de l'utilisateur et pas celle du chargement du module.
# / Help block template, rendered on the fly in get_fieldsets() so translations
# follow the user's language rather than the module import language.
TEMPLATE_AIDE_AJOUT_CARTE = "admin/cartecashless/aide_ajout.html"


class CarteCashlessAddForm(forms.ModelForm):
    """
    Formulaire d'ajout d'une carte NFC, a l'unite.
    / Add form for a single NFC card.

    LOCALISATION : QrcodeCashless/admin.py

    tag_id, number et uuid sont declares ici comme champs de FORMULAIRE, et non
    comme champs de modele. Le modele les marque editable=False (ils ne changent
    jamais apres creation) : un ModelForm refuserait de les afficher. En les
    redeclarant, Django ne les confronte jamais a ce flag, et AUCUNE MIGRATION
    n'est necessaire. C'est le meme tour de passe-passe que MembershipAddForm
    (Administration/admin_tenant.py) avec ses champs email et contribution.
    / tag_id, number and uuid are declared as FORM fields, not model fields.
    The model marks them editable=False, so a ModelForm would refuse to render
    them. Redeclaring them means Django never confronts them with the flag, and
    NO MIGRATION is needed. Same trick as MembershipAddForm.

    detail reste un champ de modele : ModelChoiceField valide nativement la valeur
    postee contre le queryset restreint par formfield_for_foreignkey(). Un pk forge
    pointant vers la generation d'un autre lieu est rejete sans code supplementaire.
    / detail stays a model field: ModelChoiceField natively validates the posted
    value against the queryset restricted by formfield_for_foreignkey().
    """

    tag_id = forms.CharField(
        required=True,
        min_length=8,
        max_length=8,
        widget=UnfoldAdminTextInputWidget(),
        label=_("Tag ID"),
        help_text=_(
            "8 caractères hexadécimaux. Identifiant physique de la puce NFC, "
            "lisible avec l'application Mifare Classic Tool."
        ),
    )

    number = forms.CharField(
        required=False,
        min_length=8,
        max_length=8,
        widget=UnfoldAdminTextInputWidget(),
        label=_("Numéro imprimé"),
        help_text=_("8 caractères hexadécimaux. Généré si laissé vide."),
    )

    uuid = forms.UUIDField(
        required=False,
        widget=UnfoldAdminTextInputWidget(),
        label=_("UUID du QR code"),
        help_text=_("Généré si laissé vide."),
    )

    class Meta:
        model = CarteCashless
        fields = ["detail"]

    def __init__(self, *args, **kwargs):
        """
        Pre-selectionne la generation la plus haute (la plus recente) du lieu.
        / Pre-selects the venue's highest (most recent) generation.

        Confort d'affichage : le gestionnaire voit tout de suite a quelle
        generation la carte sera rattachee, plutot qu'un select vide. Si le lieu
        n'a encore AUCUNE generation, on ne pose rien — pas de plantage : le filet
        de clean() en fabriquera une par defaut a l'enregistrement.
        / Display comfort: the manager immediately sees which generation the card
        will be tied to, rather than an empty select. If the venue has NO
        generation yet, we set nothing — no crash: clean()'s net creates one on save.
        """
        super().__init__(*args, **kwargs)

        generation_la_plus_haute = (
            Detail.objects.filter(origine=connection.tenant)
            .order_by("-generation")
            .first()
        )
        if generation_la_plus_haute is not None:
            self.fields["detail"].initial = generation_la_plus_haute

    def clean_tag_id(self):
        """Majuscules, puis 8 caracteres hexadecimaux exactement.
        / Uppercase, then exactly 8 hex chars."""
        tag_id_saisi = self.cleaned_data["tag_id"].strip().upper()
        if not MOTIF_HEXA_8_CARACTERES.fullmatch(tag_id_saisi):
            raise forms.ValidationError(
                _("Le Tag ID doit contenir exactement 8 caractères hexadécimaux (0-9, A-F)."),
                code="tag_id_invalide",
            )
        return tag_id_saisi

    def clean_number(self):
        """Majuscules, puis 8 caracteres hexadecimaux exactement. Optionnel.
        / Uppercase, then exactly 8 hex chars. Optional."""
        numero_saisi = self.cleaned_data.get("number")
        if not numero_saisi:
            return None

        numero_saisi = numero_saisi.strip().upper()
        if not MOTIF_HEXA_8_CARACTERES.fullmatch(numero_saisi):
            raise forms.ValidationError(
                _(
                    "Le numéro imprimé doit contenir exactement 8 caractères "
                    "hexadécimaux (0-9, A-F)."
                ),
                code="numero_invalide",
            )
        return numero_saisi

    def clean(self):
        """
        Valide, derive les identifiants, et cree la carte chez Fedow.
        / Validates, derives identifiers, and creates the card on Fedow.

        POURQUOI L'APPEL RESEAU EST ICI ET PAS DANS save_model() :
        save_model() ne peut pas lever de ValidationError — Django ne l'attrape
        pas et l'admin renvoie une erreur 500. Seule une erreur levee depuis
        clean() s'affiche en tete de formulaire, avec les valeurs saisies
        conservees. is_valid() n'est appele qu'une fois par _changeform_view et
        il n'y a pas de formset : pas de double execution.
        / save_model() cannot raise ValidationError (Django lets it bubble into a
        500). Only clean() errors render nicely. is_valid() runs once per
        _changeform_view and there is no formset: no double execution.

        FLUX :
        1. Le lieu est-il appaire a Fedow ?
        2. Deriver le numero imprime et l'uuid du QR code.
        3. Ces identifiants sont-ils libres en local ?
        4. Creer la carte chez Fedow, ou la recuperer si elle y est deja.
        5. Si on l'a recuperee, revalider l'unicite : les valeurs viennent de
           Fedow et peuvent entrer en collision avec une autre carte locale.
        """
        donnees_nettoyees = super().clean()

        # Si tag_id est invalide, Django a deja pose l'erreur : on ne va pas plus
        # loin. / If tag_id is invalid, Django already posted the error: stop here.
        tag_id = donnees_nettoyees.get("tag_id")
        if not tag_id:
            return donnees_nettoyees

        # Le gestionnaire n'a pas choisi de generation : on fabrique (ou reutilise)
        # celle par defaut du lieu courant. Sans ce filet, la carte serait
        # invisible dans la liste et jamais creee chez Fedow.
        # / No generation chosen: fabricate/reuse the venue's default one. Without
        # this net, the card would be invisible in the list and never created on
        # Fedow.
        detail = donnees_nettoyees.get("detail")
        if not detail:
            detail = _obtenir_la_generation_par_defaut_du_lieu()
            donnees_nettoyees["detail"] = detail

        # 1. Le lieu est-il appaire a Fedow ?
        # / Is the venue paired with Fedow?
        _verifier_que_le_lieu_est_appaire_a_fedow()

        # 2. Completer le numero imprime et l'uuid du QR code.
        # / Fill in the printed number and the QR code uuid.
        numero_imprime, uuid_du_qrcode = _deriver_les_identifiants(
            donnees_nettoyees.get("number"),
            donnees_nettoyees.get("uuid"),
        )

        # 3. La carte est-elle libre en local ? A faire AVANT d'interroger Fedow :
        #    si elle existe des deux cotes, on veut l'erreur de doublon, pas une
        #    reconciliation. / Is the card free locally? Before querying Fedow.
        _verifier_que_la_carte_est_absente_en_local(tag_id, numero_imprime, uuid_du_qrcode)

        # 4. Creation chez Fedow, ou reconciliation si Fedow la connait deja.
        # / Creation on Fedow, or reconciliation if Fedow already knows it.
        numero_imprime, uuid_du_qrcode, carte_recuperee_de_fedow = (
            _creer_ou_recuperer_la_carte_chez_fedow(
                tag_id, numero_imprime, uuid_du_qrcode, detail
            )
        )

        # 5. La reconciliation nous a rendu des valeurs venues de Fedow. Elles
        #    n'ont pas ete testees a l'etape 3 : une autre carte locale pourrait
        #    deja porter ce numero ou cet uuid. On revalide pour eviter un 500.
        # / Reconciliation returned Fedow's values, untested at step 3. Re-check.
        if carte_recuperee_de_fedow:
            _verifier_que_la_carte_est_absente_en_local(
                tag_id, numero_imprime, uuid_du_qrcode
            )

        donnees_nettoyees["number"] = numero_imprime
        donnees_nettoyees["uuid"] = uuid_du_qrcode

        # Memorise pour que save_model() puisse prevenir l'utilisateur.
        # / Remembered so save_model() can inform the user.
        self.carte_recuperee_de_fedow = carte_recuperee_de_fedow

        return donnees_nettoyees


@admin.register(CarteCashless, site=staff_admin_site)
class CarteCashlessAdmin(ModelAdmin):
    """
    Admin des cartes NFC (CarteCashless).
    NFC cards admin.

    AJOUT autorise : le formulaire cree d'abord la carte chez Fedow.
    MODIFICATION et SUPPRESSION interdites : Fedow est la source de verite.
    / ADD allowed: the form creates the card on Fedow first.
    CHANGE and DELETE forbidden: Fedow is the source of truth.
    """

    list_display = ["tag_id", "number", "user", "wallet_court", "origine_court"]
    search_fields = ["tag_id", "number", "user__email"]

    add_form = CarteCashlessAddForm

    # Les champs du formulaire d'ajout. La description (bloc d'aide) est ajoutee
    # dans get_fieldsets(), car elle demande un rendu de template.
    # / Add form fields. The description (help block) is added in get_fieldsets(),
    # since it requires rendering a template.
    add_fields = ("detail", "tag_id", "number", "uuid")

    # --- Colonnes calculees / Computed columns ---

    def wallet_court(self, obj):
        """UUID court du wallet effectif (ephemere si carte anonyme, sinon celui du user).
        / Short UUID of the effective wallet (ephemeral if anonymous, else the user's)."""
        wallet = obj.wallet_ephemere or (obj.user.wallet if obj.user_id else None)
        return _uuid_court(wallet.uuid if wallet else None)

    wallet_court.short_description = _("Wallet")

    def origine_court(self, obj):
        """Lieu (tenant) qui a emis la carte, via detail.origine.
        / Venue (tenant) that issued the card, via detail.origine."""
        if obj.detail_id and obj.detail.origine_id:
            return obj.detail.origine.name
        return "—"

    origine_court.short_description = _("Lieu d'origine")

    # --- Formulaire d'ajout / Add form ---

    def get_form(self, request, obj=None, **kwargs):
        """
        Si c'est un ajout, on utilise le formulaire dedie.
        / On add, use the dedicated form.

        fields=None est INDISPENSABLE, et doit etre pose APRES defaults.update(kwargs).
        En effet, ModelAdmin._changeform_view() appelle get_form() en passant
        explicitement fields=flatten_fieldsets(self.get_fieldsets(...)), soit la
        liste ["detail", "tag_id", "number", "uuid"]. Or tag_id, number et uuid SONT
        des champs du modele (marques editable=False) : modelform_factory refuse
        alors de les inclure et Django leve :
            FieldError: 'tag_id' cannot be specified for CarteCashless model form
            as it is a non-editable field.
        En forcant fields=None apres l'update, modelform_factory retombe sur le
        Meta.fields du formulaire (["detail"]) et conserve ses champs declares.
        Les fieldsets, eux, continuent de piloter l'affichage.
        / fields=None is REQUIRED, and must be set AFTER defaults.update(kwargs):
        _changeform_view() explicitly passes fields=flatten_fieldsets(...), which
        would overwrite it. tag_id/number/uuid ARE model fields (editable=False),
        so modelform_factory rejects them. With fields=None it falls back on the
        form's Meta.fields (["detail"]) and keeps its declared fields. The
        fieldsets still drive the rendering.
        """
        defaults = {}
        defaults.update(kwargs)
        if obj is None:
            defaults["form"] = self.add_form
            defaults["fields"] = None
        return super().get_form(request, obj, **defaults)

    def get_fieldsets(self, request, obj=None):
        """
        Le bloc d'aide n'apparait que sur le formulaire d'ajout.
        / The help block only shows on the add form.

        La description est rendue ici, a chaque requete, et non une seule fois au
        chargement du module : ainsi les traductions suivent la langue de
        l'utilisateur connecte.
        / The description is rendered per request, not once at module import, so
        translations follow the logged-in user's language.
        """
        if obj is None:
            aide = mark_safe(render_to_string(TEMPLATE_AIDE_AJOUT_CARTE))
            return ((None, {"description": aide, "fields": self.add_fields}),)
        return super().get_fieldsets(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Le select « detail » ne montre que les generations du lieu courant.
        / The "detail" select only shows the current venue's generations.

        Detail est en SHARED_APPS : sans ce filtre, l'admin verrait les
        generations de tous les lieux, et pourrait y rattacher ses cartes.
        / Detail is in SHARED_APPS: without this filter, the admin would see
        every venue's generations.
        """
        if db_field.name == "detail":
            kwargs["queryset"] = Detail.objects.filter(origine=connection.tenant)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """
        Recopie les identifiants valides sur l'objet. AUCUN appel reseau ici :
        Fedow a deja ete contacte dans CarteCashlessAddForm.clean().
        / Copies the validated identifiers onto the object. NO network call here:
        Fedow was already contacted in CarteCashlessAddForm.clean().
        """
        if not change:
            obj.tag_id = form.cleaned_data["tag_id"]
            obj.number = form.cleaned_data["number"]
            obj.uuid = form.cleaned_data["uuid"]

            if getattr(form, "carte_recuperee_de_fedow", False):
                messages.add_message(
                    request,
                    messages.INFO,
                    _(
                        "Cette carte existait déjà chez Fedow. Elle a été récupérée "
                        "telle quelle, avec son numéro imprimé et son UUID d'origine."
                    ),
                )

        super().save_model(request, obj, form, change)

    # --- Queryset filtre par tenant / Tenant-filtered queryset ---

    def get_queryset(self, request):
        """
        Filtre les cartes par tenant courant (la place d'emission, detail.origine).
        Filters cards by current tenant (the issuing place, detail.origine).

        SHARED_APPS oblige : sans ce filtre, un lieu verrait les cartes de tous les lieux.
        SHARED_APPS requires this: without it, a venue would see all venues' cards.
        """
        queryset = super().get_queryset(request)
        tenant_actuel = connection.tenant
        return queryset.filter(detail__origine=tenant_actuel).select_related(
            "user", "user__wallet", "detail", "detail__origine", "wallet_ephemere"
        )

    # --- Permissions / Permissions ---

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        """Fedow est maitre : une carte ne se modifie pas depuis Lespass.
        / Fedow is master: a card is never edited from Lespass."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Fedow est maitre : une carte ne se supprime pas depuis Lespass.
        / Fedow is master: a card is never deleted from Lespass."""
        return False
