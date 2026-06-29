"""
Modeles de l'app pages : Page + Bloc.
/ Models of the pages app: Page + Bloc.

LOCALISATION : pages/models.py

CONCEPT (StreamField) :
Une page n'est pas un gros bloc de HTML, ni une structure figee.
C'est une SUITE ORDONNEE de blocs types. Le gestionnaire empile des blocs
(Hero, Paragraphe, Image+texte, CTA, Temoignage) et les reordonne librement.
Le catalogue des types est ferme (choices) : la page reste toujours propre.
/ A page is neither a big HTML blob nor a rigid structure. It is an ORDERED
SEQUENCE of typed blocks. The catalogue of block types is closed (choices).

ISOLATION MULTI-TENANT :
L'app pages est en dual-list (SHARED_APPS + TENANT_APPS dans settings.py).
La table existe donc dans le schema public ET dans chaque schema tenant,
chaque schema gardant ses propres pages (aucune fuite entre tenants).
/ The pages app is dual-listed. The table lives in the public schema AND in
each tenant schema, each schema keeping its own pages (no cross-tenant leak).
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from solo.models import SingletonModel
from stdimage import StdImageField

# ---------------------------------------------------------------------------
# Slugs reserves : URLs deja prises par le site (routes BaseBillet, admin...).
# Une Page ne peut pas prendre un de ces slugs, sinon sa route /<slug>/ entrerait
# en collision avec une vue existante.
# / Reserved slugs: URLs already taken by the site (BaseBillet routes, admin...).
# A Page cannot use one of these, otherwise its /<slug>/ route would collide.
# ---------------------------------------------------------------------------
SLUGS_RESERVES = frozenset({
    # Routes publiques BaseBillet (cf. BaseBillet/urls.py)
    # / BaseBillet public routes
    # NB : "infos-pratiques" et "le-faire-festival" ne sont PLUS reserves : ce sont
    # desormais des Page (routes legacy retirees).
    # / "infos-pratiques" and "le-faire-festival" are no longer reserved: now Pages.
    "connexion", "deconnexion", "emailconfirmation",
    "event", "memberships", "badge", "federation",
    "my_account", "qrcodescanpay", "qr", "home", "login", "specialadminaction",
    # Routes techniques / fichiers
    # / Technical routes / files
    "admin", "api", "static", "media", "robots.txt", "humans.txt",
})


def valider_slug_non_reserve(valeur):
    """
    Verifie que le slug n'est pas dans la liste des slugs reserves.
    / Checks the slug is not in the reserved slugs list.

    Appele automatiquement par full_clean() (donc par les formulaires admin).
    / Called automatically by full_clean() (so by admin forms).
    """
    if valeur in SLUGS_RESERVES:
        raise ValidationError(
            _("Ce slug est reserve par le site et ne peut pas etre utilise : %(slug)s"),
            params={"slug": valeur},
            code="slug_reserve",
        )


class ConfigurationSite(SingletonModel):
    """
    Configuration du site web (app pages) — un singleton par tenant.
    / Website configuration (pages app) — one singleton per tenant.

    LOCALISATION : pages/models.py

    Porte les reglages d'apparence du site public. Premier reglage : le skin
    (theme graphique). Le champ a ete deplace depuis BaseBillet.Configuration.
    / Holds the public site appearance settings. First setting: the skin
    (graphic theme). The field was moved from BaseBillet.Configuration.
    """

    # Choix du theme graphique (skin) pour l'affichage du site.
    # Par defaut : "reunion" (theme existant). Option : "faire_festival".
    # / Graphic theme (skin) choice for the site display.
    # Default: "reunion" (existing theme). Option: "faire_festival".
    skin = models.CharField(
        max_length=50,
        default="reunion",
        choices=[
            ("reunion", "Réunion (thème par défaut)"),
            ("faire_festival", "Faire Festival (thème brutaliste)"),
        ],
        verbose_name=_("Thème graphique du site"),
        help_text=_("Sélectionnez le thème visuel à utiliser pour l'affichage du site web."),
    )

    class Meta:
        verbose_name = _("Configuration du site")
        verbose_name_plural = _("Configuration du site")

    def __str__(self):
        return f"Configuration du site (skin : {self.skin})"


class Page(models.Model):
    """
    Une page publique composee de blocs (relation un-a-plusieurs vers Bloc).
    / A public page made of blocks (one-to-many relation to Bloc).

    Servie sur /<slug>/. Visible dans la navbar si publie=True, triee par position.
    / Served on /<slug>/. Shown in the navbar if publie=True, ordered by position.
    """

    # Identifiant unique (convention du projet : UUID en cle primaire).
    # / Unique identifier (project convention: UUID primary key).
    uuid = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True
    )

    # Titre affiche dans la navbar et en haut de la page.
    # / Title shown in the navbar and at the top of the page.
    titre = models.CharField(
        max_length=200,
        verbose_name=_("Titre"),
        help_text=_("Titre de la page, affiche dans la navigation."),
    )

    # Slug = la fin de l'URL publique : /<slug>/. Rempli automatiquement depuis
    # le titre dans l'admin, mais reste modifiable. Valide contre les slugs reserves.
    # / Slug = the end of the public URL: /<slug>/. Auto-filled from the title in the
    # admin, but editable. Validated against reserved slugs.
    slug = models.SlugField(
        max_length=200,
        unique=True,
        validators=[valider_slug_non_reserve],
        verbose_name=_("Slug (URL)"),
        help_text=_("Adresse de la page : /<slug>/. Genere depuis le titre, modifiable."),
    )

    # Position dans la navbar. Plus le nombre est petit, plus la page est a gauche.
    # / Position in the navbar. The smaller the number, the more to the left.
    position = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Position"),
        help_text=_("Ordre d'apparition dans la navigation (croissant)."),
    )

    # Si False, la page n'est ni servie publiquement ni listee dans la navbar.
    # / If False, the page is neither served publicly nor listed in the navbar.
    publie = models.BooleanField(
        default=False,
        verbose_name=_("Publiee"),
        help_text=_("Si decoche, la page reste un brouillon (invisible du public)."),
    )

    # Si True, cette page est servie sur la racine du site (/), a la place de la
    # page d'accueil par defaut. Une seule page d'accueil a la fois par tenant
    # (garanti par save() ci-dessous).
    # / If True, this page is served on the site root (/), instead of the default
    # home page. Only one home page at a time per tenant (enforced by save() below).
    est_accueil = models.BooleanField(
        default=False,
        verbose_name=_("Page d'accueil"),
        help_text=_("Si coche, cette page est servie sur la racine du site (/). Une seule a la fois."),
    )

    # Description courte pour les moteurs de recherche (donnee SEO = champ de modele,
    # jamais un bloc de contenu).
    # / Short description for search engines (SEO data = model field, never a block).
    meta_description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Meta description (SEO)"),
        help_text=_("Resume court affiche par les moteurs de recherche."),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Cree le"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Modifie le"))

    class Meta:
        verbose_name = _("Page")
        verbose_name_plural = _("Pages")
        ordering = ["position", "titre"]

    def __str__(self):
        statut = _("publiee") if self.publie else _("brouillon")
        return f"{self.titre} ({statut})"

    def save(self, *args, **kwargs):
        """
        Enregistre la page, puis garantit qu'il n'y a qu'une seule page d'accueil.
        / Saves the page, then ensures there is only one home page.

        Si cette page est cochee comme page d'accueil, on decoche toutes les
        autres pages du meme schema (donc du meme tenant).
        / If this page is set as home, we unset all the other pages of the same
        schema (so of the same tenant).
        """
        super().save(*args, **kwargs)
        if self.est_accueil:
            Page.objects.exclude(pk=self.pk).filter(est_accueil=True).update(
                est_accueil=False
            )


class Bloc(models.Model):
    """
    Un bloc de contenu rattache a une Page. Le champ type_bloc est le PIVOT :
    il decide quel gabarit afficher cote public ET quels champs montrer dans
    l'admin (via conditional_fields natif d'Unfold).
    / A content block attached to a Page. The type_bloc field is the PIVOT:
    it decides which template to render publicly AND which fields to show in the
    admin (via Unfold's native conditional_fields).

    Champs PLATS partages entre types + 2 JSONField pour les blocs structures
    (points_gps pour la carte Leaflet, contenu pour le bloc Infos). Pas de M2M.
    / Flat fields shared across types + 2 JSONField for structured blocks
    (points_gps for the Leaflet map, contenu for the Infos block). No M2M.
    """

    # --- Types de blocs (catalogue ferme) / Block types (closed catalogue) ---
    HERO = "HERO"
    PARAGRAPHE = "PARAGRAPHE"
    IMAGE_TEXTE = "IMAGE_TEXTE"
    CTA = "CTA"
    TEMOIGNAGE = "TEMOIGNAGE"
    VIDEO_TEXTE = "VIDEO_TEXTE"
    CARTE = "CARTE"
    IMAGE = "IMAGE"
    CARTE_LEAFLET = "CARTE_LEAFLET"
    FAQ = "FAQ"
    INFOS = "INFOS"

    TYPE_BLOC_CHOICES = [
        (HERO, _("Hero (banniere d'ouverture)")),
        (PARAGRAPHE, _("Paragraphe riche")),
        (IMAGE_TEXTE, _("Image + texte")),
        (CTA, _("Appel a l'action (CTA)")),
        (TEMOIGNAGE, _("Temoignage")),
        (VIDEO_TEXTE, _("Video + texte")),
        (CARTE, _("Carte (regroupee en grille si plusieurs a la suite)")),
        (IMAGE, _("Image seule")),
        (CARTE_LEAFLET, _("Carte Leaflet (points GPS)")),
        (INFOS, _("Infos structurees (badges, horaires, transports) - a cote d'une carte")),
        (FAQ, _("Question / reponse (regroupee en 2 colonnes si plusieurs a la suite)")),
    ]

    # --- Position de l'image pour le bloc Image+texte / Image side for Image+text ---
    GAUCHE = "GAUCHE"
    DROITE = "DROITE"
    IMAGE_POSITION_CHOICES = [
        (GAUCHE, _("Image a gauche")),
        (DROITE, _("Image a droite")),
    ]

    # Variations d'image generees automatiquement (memes tailles que Event).
    # / Auto-generated image variations (same sizes as Event).
    VARIATIONS_IMAGE = {
        "fhd": (1920, 1920),
        "hdr": (1280, 1280),
        "med": (480, 480),
        "thumbnail": (150, 90),
        "crop_hdr": (960, 540, True),
        "crop": (480, 270, True),
        "social_card": (1200, 630, True),
    }

    # Variations pour la photo d'auteur d'un temoignage (petit format carre).
    # / Variations for a testimonial author photo (small square format).
    VARIATIONS_PHOTO_AUTEUR = {
        "med": (480, 480),
        "thumbnail": (150, 150, True),
    }

    uuid = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True
    )

    # La Page a laquelle ce bloc appartient. Si la page est supprimee, ses blocs aussi.
    # / The Page this block belongs to. If the page is deleted, its blocks go too.
    page = models.ForeignKey(
        Page,
        on_delete=models.CASCADE,
        related_name="blocs",
        verbose_name=_("Page"),
    )

    # Le pivot : decide le gabarit et les champs visibles.
    # / The pivot: decides the template and the visible fields.
    type_bloc = models.CharField(
        max_length=20,
        choices=TYPE_BLOC_CHOICES,
        verbose_name=_("Type de bloc"),
        help_text=_("Choisit le gabarit du bloc. Les champs s'adaptent automatiquement."),
    )

    # Ordre du bloc dans la page (croissant). Reordonnable par glisser-deposer.
    # / Block order within the page (ascending). Reorderable by drag-and-drop.
    position = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Position"),
        help_text=_("Ordre du bloc dans la page (croissant)."),
    )

    # --- Champs de contenu plats, partages entre types (cf. matrice SPEC.md) ---
    # / Flat content fields, shared across types (see matrix in SPEC.md).

    titre = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Titre"),
        help_text=_("Titre principal du bloc."),
    )

    sous_titre = models.CharField(
        max_length=300,
        blank=True,
        verbose_name=_("Sous-titre"),
        help_text=_("Texte secondaire sous le titre (Hero et CTA)."),
    )

    # Sur-titre d'une carte (ex. « JOUR 01 »), affiche en en-tete.
    # / Card eyebrow (e.g. "JOUR 01"), shown as a header.
    surtitre = models.CharField(
        max_length=120,
        blank=True,
        verbose_name=_("Sur-titre (carte)"),
        help_text=_("Petit titre en haut d'une carte (ex. « JOUR 01 »)."),
    )

    # Petit badge optionnel sur une carte (ex. « gratuit »).
    # / Optional small badge on a card (e.g. "gratuit").
    badge = models.CharField(
        max_length=60,
        blank=True,
        verbose_name=_("Badge (carte)"),
        help_text=_("Petite pastille sur la carte (ex. « gratuit »)."),
    )

    # Texte riche : edite avec l'editeur WYSIWYG d'Unfold, nettoye (clean_html)
    # a l'enregistrement cote admin.
    # / Rich text: edited with Unfold's WYSIWYG editor, sanitized (clean_html) on
    # save in the admin.
    texte = models.TextField(
        blank=True,
        verbose_name=_("Texte"),
        help_text=_("Contenu riche (paragraphe, description, citation)."),
    )

    # Image principale (fond du Hero, ou image laterale d'Image+texte).
    # / Main image (Hero background, or side image of Image+text).
    image = StdImageField(
        upload_to="images/pages/",
        blank=True,
        variations=VARIATIONS_IMAGE,
        delete_orphans=True,
        verbose_name=_("Image"),
        help_text=_("Image du bloc (fond du Hero ou illustration laterale)."),
    )

    # Seconde image uploadee (ex. badge date du Hero, logo a cote d'une carte).
    # Vrai moteur d'upload (comme le reste de TiBillet), avec variations.
    # / Second uploaded image (e.g. Hero date badge, logo next to a map). Real
    # upload engine (like the rest of TiBillet), with variations.
    image_secondaire = StdImageField(
        upload_to="images/pages/",
        blank=True,
        variations=VARIATIONS_IMAGE,
        delete_orphans=True,
        verbose_name=_("Seconde image"),
        help_text=_("Image secondaire (ex. badge date, logo a cote d'une carte)."),
    )

    # Video uploadee (ex. boucle d'ambiance d'un bloc Video + texte).
    # / Uploaded video (e.g. ambient loop of a Video + text block).
    video = models.FileField(
        upload_to="videos/pages/",
        blank=True,
        verbose_name=_("Video"),
        help_text=_("Fichier video (mp4/webm) pour le bloc Video + texte."),
    )

    # Points GPS pour le bloc carte Leaflet : liste de marqueurs.
    # Forme attendue : [{"lat": 43.55, "lng": 1.48, "label": "La Cite"}, ...]
    # La carte se centre sur le 1er point. Vigilance : un JSONField n'est pas valide
    # comme un champ de formulaire classique ; saisir une liste d'objets bien formee.
    # / GPS points for the Leaflet map block: list of markers.
    # Expected shape: [{"lat": .., "lng": .., "label": ..}, ...]. The map centers on
    # the first point. NB: a JSONField is not validated like a regular form field.
    points_gps = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Points GPS (carte Leaflet)"),
        help_text=_('Liste de marqueurs : [{"lat": 43.55, "lng": 1.48, "label": "La Cité"}].'),
    )

    # Contenu structure de la colonne gauche du bloc CARTE_LEAFLET : liste d'items
    # TYPES (donnees TEXTE, jamais de HTML). Le HTML/les classes sont dans le template.
    # Types d'item : "badge" (texte), "para" (texte), "horaire" (texte),
    # "adresse" (texte multi-lignes), "accessibilite" (texte),
    # "transport" (titre + lignes[]). / Structured content for the left column of the
    # CARTE_LEAFLET block: list of TYPED items (TEXT data only, never HTML). The HTML
    # and CSS classes live in the template.
    contenu = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Contenu structure (colonne gauche)"),
        help_text=_('Items typés (texte seulement) : [{"type": "transport", "titre": "BUS", "lignes": ["..."]}].'),
    )

    # Cote ou s'affiche l'image dans le bloc Image+texte.
    # / Side where the image is shown in the Image+text block.
    image_position = models.CharField(
        max_length=10,
        choices=IMAGE_POSITION_CHOICES,
        default=GAUCHE,
        blank=True,
        verbose_name=_("Position de l'image"),
        help_text=_("Cote ou afficher l'image (bloc Image + texte)."),
    )

    # --- Boutons (Hero, Image+texte, CTA) / Buttons ---
    # URL en CharField (pas URLField) pour autoriser les liens internes relatifs
    # (ex: /event/) autant que les liens externes (https://...).
    # / URL as CharField (not URLField) to allow internal relative links (e.g.
    # /event/) as well as external links (https://...).

    bouton_label = models.CharField(
        max_length=80,
        blank=True,
        verbose_name=_("Libelle du bouton"),
        help_text=_("Texte du bouton principal."),
    )
    bouton_url = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("Lien du bouton"),
        help_text=_("Lien interne (/event/) ou externe (https://...)."),
    )
    bouton2_label = models.CharField(
        max_length=80,
        blank=True,
        verbose_name=_("Libelle du second bouton"),
        help_text=_("Texte du bouton secondaire (optionnel)."),
    )
    bouton2_url = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("Lien du second bouton"),
        help_text=_("Lien du bouton secondaire (optionnel)."),
    )

    # --- Temoignage / Testimonial ---
    auteur_nom = models.CharField(
        max_length=120,
        blank=True,
        verbose_name=_("Nom de l'auteur"),
        help_text=_("Personne qui temoigne."),
    )
    auteur_role = models.CharField(
        max_length=160,
        blank=True,
        verbose_name=_("Role de l'auteur"),
        help_text=_("Fonction ou statut (ex: adherente, benevole)."),
    )
    auteur_photo = StdImageField(
        upload_to="images/pages/auteurs/",
        blank=True,
        variations=VARIATIONS_PHOTO_AUTEUR,
        delete_orphans=True,
        verbose_name=_("Photo de l'auteur"),
        help_text=_("Portrait de la personne qui temoigne (optionnel)."),
    )

    class Meta:
        verbose_name = _("Bloc")
        verbose_name_plural = _("Blocs")
        ordering = ["position"]

    def __str__(self):
        libelle_type = self.get_type_bloc_display()
        if self.titre:
            return f"{libelle_type} — {self.titre}"
        return f"{libelle_type} (#{self.position})"
