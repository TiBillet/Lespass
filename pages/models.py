"""
Modeles de l'app pages : Page + Bloc.
/ Models of the pages app: Page + Bloc.

LOCALISATION : pages/models.py

CONCEPT (StreamField) :
Une page n'est pas un gros bloc de HTML, ni une structure figee.
C'est une SUITE ORDONNEE de blocs types. Le gestionnaire empile des blocs et
les reordonne librement. Le catalogue des types est FERME (choices) : sept
types organises par intention (« j'ecris du texte », « je mets en avant »...),
la variation visuelle etant portee par le champ `affichage`. Voir
pages/blocs_catalogue.py, source unique du catalogue.
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
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
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


# Limite de taille des images uploadees (octets). Genereuse pour ne pas bloquer la
# prod ; alignee sur la limite nginx (client_max_body_size 12M) et l'API v2.
# / Upload size limit for images (bytes). Generous so as not to block production;
# aligned with the nginx limit (client_max_body_size 12M) and the v2 API.
LIMITE_TAILLE_IMAGE = 10 * 1024 * 1024  # 10 Mo


def valider_taille_image(fichier):
    """
    Refuse une image uploadee trop lourde (> LIMITE_TAILLE_IMAGE).
    / Rejects an uploaded image that is too large (> LIMITE_TAILLE_IMAGE).

    Appele automatiquement par full_clean() (donc par les formulaires admin).
    / Called automatically by full_clean() (so by admin forms).
    """
    if fichier and getattr(fichier, "size", 0) > LIMITE_TAILLE_IMAGE:
        raise ValidationError(
            _("Image trop volumineuse (max %(mo)s Mo)."),
            params={"mo": LIMITE_TAILLE_IMAGE // (1024 * 1024)},
            code="image_trop_grande",
        )


def valider_url_sans_schema_dangereux(valeur):
    """
    Rejette une URL a schema dangereux (javascript:, data:, vbscript:).
    / Rejects a dangerous-scheme URL (javascript:, data:, vbscript:).

    Utilise pour les champs lien saisis hors save_model de BlocAdmin (ex.
    ImageGalerie.lien_url, edite par le formset inline qui ne passe PAS par
    la neutralisation de BlocAdmin.save_model).
    / Used for link fields saved outside BlocAdmin.save_model (e.g.
    ImageGalerie.lien_url, saved by the inline formset).
    """
    # Import local : evite tout cycle d'import au chargement du module.
    # / Local import: avoids any import cycle at module load time.
    from Administration.utils import url_a_schema_dangereux

    if url_a_schema_dangereux(valeur):
        raise ValidationError(
            _("Lien non autorise (schema dangereux)."),
            code="url_dangereuse",
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


# Profondeur maximale d'un arbre de pages : la racine compte pour 1.
# Au-dela, la navigation devient illisible (un menu lateral a sept niveaux ne
# se lit plus) et l'admin ne sait pas manipuler l'arbre confortablement.
# / Maximum depth of a page tree, the root counting as 1. Beyond that,
# navigation becomes unreadable and the admin cannot handle the tree.
PROFONDEUR_MAX_ARBRE = 6


# Variations de l'image de partage d'une Page : social_card (format og:image) +
# med (apercu dans l'admin). / Page share image variations: social_card (og:image
# format) + med (admin preview).
VARIATIONS_PARTAGE = {
    "social_card": (1200, 630, True),
    "med": (480, 480),
}


class Page(models.Model):
    """
    Une page publique composee de blocs (relation un-a-plusieurs vers Bloc).
    / A public page made of blocks (one-to-many relation to Bloc).

    Servie sur /<slug>/. Sa place dans la navigation vient de `affichage_nav`,
    lu sur la racine de son arbre.
    / Served on /<slug>/. Its place in the navigation comes from
    `affichage_nav`, read on its tree's root.
    """

    # --- Place dans la navigation / Place in the navigation ---
    NAVBAR = "NAVBAR"
    SIDEBAR = "SIDEBAR"
    AUCUN = "AUCUN"

    AFFICHAGE_NAV_CHOICES = [
        (NAVBAR, _("Barre de navigation")),
        (SIDEBAR, _("Menu latéral (documentation)")),
        (AUCUN, _("Hors navigation")),
    ]

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


    # Place de la page dans la navigation du site.
    # Lu UNIQUEMENT sur la racine d'un arbre : les descendants heritent du
    # choix de leur racine. Le formulaire masque donc le champ des qu'une page
    # parente est renseignee — une valeur saisissable et silencieusement
    # ignoree serait de la magie au sens FALC.
    # / The page's place in the site navigation. Read ONLY on a tree's root:
    # descendants inherit their root's choice. The form hides the field as soon
    # as a parent is set — a settable but silently ignored value would be magic.
    affichage_nav = models.CharField(
        max_length=20,
        choices=AFFICHAGE_NAV_CHOICES,
        default=NAVBAR,
        verbose_name=_("Place dans la navigation"),
        help_text=_("Barre de navigation : la page y figure, avec ses sous-pages en "
                    "menu déroulant. Menu latéral : la page ouvre un menu de "
                    "documentation à gauche, où tout son arbre se déplie. "
                    "Hors navigation : la page reste accessible par son adresse et "
                    "par un bloc Liste, mais n'apparaît dans aucun menu."),
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

    # Titre SEO optionnel : si vide, on retombe sur `titre`. Permet un <title>
    # different du libelle de navigation (ex. plus long, avec mots-cles).
    # / Optional SEO title: if empty, falls back to `titre`. Lets the <title> differ
    # from the navigation label (e.g. longer, with keywords).
    meta_title = models.CharField(
        max_length=70,
        blank=True,
        verbose_name=_("Titre SEO"),
        help_text=_("Titre pour les moteurs/onglets. Si vide : reprend le titre de la page."),
    )

    # Image de PARTAGE (og:image / twitter:image) : aperu affiche quand la page est
    # partagee sur les reseaux sociaux. Si vide : repli sur l'image du site (config).
    # Variation social_card (1200x630) = format standard des cartes sociales.
    # / SHARE image (og:image / twitter:image): preview shown when the page is shared
    # on social networks. If empty: falls back to the site image (config). The
    # social_card variation (1200x630) is the standard social card format.
    image = StdImageField(
        upload_to="images/pages/seo/",
        blank=True,
        variations=VARIATIONS_PARTAGE,
        delete_orphans=True,
        validators=[valider_taille_image],
        verbose_name=_("Image de partage (reseaux sociaux)"),
        help_text=_("Aperu lors d'un partage sur les reseaux (1200x630 conseille). "
                    "Si vide : image du site par defaut."),
    )

    # Si True, la page demande aux moteurs de ne pas l'indexer (noindex, nofollow)
    # et elle est exclue du sitemap.
    # / If True, the page asks search engines not to index it (noindex, nofollow)
    # and it is excluded from the sitemap.
    noindex = models.BooleanField(
        default=False,
        verbose_name=_("Masquer des moteurs (noindex)"),
        help_text=_("Si coche : la page n'est pas indexee et reste hors du sitemap."),
    )

    # Page parente (auto-relation) : si renseignee, cette page est rangee sous la
    # page parente. L'arbre accepte PROFONDEUR_MAX_ARBRE niveaux, et clean() en
    # refuse davantage comme il refuse les cycles. L'URL reste plate (/<slug>/) ;
    # la hierarchie sert a la navigation, au fil d'Ariane (BreadcrumbList), au
    # menu lateral et aux blocs LISTE.
    # PROTECT : supprimer une page qui a des enfants rendrait ces enfants
    # injoignables par la navigation, sans que rien ne le signale. On force donc
    # a rattacher (ou supprimer) les enfants d'abord.
    # / Parent page (self-relation): if set, this page is filed under the parent.
    # The tree accepts PROFONDEUR_MAX_ARBRE levels; clean() rejects deeper trees
    # and cycles alike. The URL stays flat (/<slug>/); the hierarchy drives
    # navigation, breadcrumb, side menu and LISTE blocks.
    # PROTECT: deleting a page with children would leave them unreachable from
    # the navigation with no warning, so children must be moved or removed first.
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="enfants",
        verbose_name=_("Page parente (sous-menu)"),
        help_text=_("Si renseignée, cette page est rangée sous la page parente : "
                    "elle hérite de son fil d'Ariane et peut être listée "
                    "automatiquement. Six niveaux de profondeur au maximum."),
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

    def get_absolute_url(self):
        """
        Adresse publique de la page.
        / Public address of the page.

        LOCALISATION : pages/models.py

        C'est la source UNIQUE de l'adresse d'une Page. Personne ne doit
        reconstruire cette adresse ailleurs — ni en Python (f"/{slug}/"), ni
        dans un gabarit (href="/{{ page.slug }}/"), ni dans un serializer.
        La regle « la page d'accueil est servie sur la racine du site » ne
        vit qu'ici : si elle change, elle change a un seul endroit.
        / This is the SINGLE source of a Page's address. Nobody should rebuild
        it elsewhere — not in Python, not in a template, not in a serializer.
        The rule "the home page is served on the site root" lives only here.

        :return: le chemin absolu, sans protocole ni domaine (str).
            Exemples : "/" pour la page d'accueil, "/infos-pratiques/" sinon.
        """
        # La page d'accueil du tenant remplace la home par defaut : elle est
        # servie sur la racine, pas sur /<slug>/.
        # / The tenant home page replaces the default home: it is served on the
        # root, not on /<slug>/.
        if self.est_accueil:
            return "/"

        return reverse("pages:page_publique", kwargs={"slug": self.slug})

    def profondeur(self):
        """
        Rang de la page dans son arbre : 1 pour une racine, 2 pour son enfant.
        / The page's rank in its tree: 1 for a root, 2 for its child.

        LOCALISATION : pages/models.py

        La remontee s'arrete a PROFONDEUR_MAX_ARBRE meme si la chaine continue :
        une hierarchie circulaire ecrite hors validation (migration, script)
        ferait sinon boucler l'appel a l'infini.
        / The walk stops at PROFONDEUR_MAX_ARBRE even if the chain goes on: a
        circular hierarchy written outside validation would otherwise loop.
        """
        rang = 1
        ancetre = self.parent
        while ancetre is not None and rang <= PROFONDEUR_MAX_ARBRE:
            rang += 1
            ancetre = ancetre.parent
        return rang

    def clean(self):
        """
        Valide la place de la page dans l'arbre.
        / Validates the page's place in the tree.

        LOCALISATION : pages/models.py

        Trois regles, et rien de plus :

        1. AUCUN CYCLE. Une page ne peut etre ni sa propre parente, ni la
           descendante d'elle-meme. Un cycle ne se voit pas en base mais fait
           boucler sans fin tout ce qui remonte l'arbre — fil d'Ariane, menu
           lateral, navigation precedent/suivant.
        2. PROFONDEUR BORNEE. Un arbre plus profond que PROFONDEUR_MAX_ARBRE
           devient illisible en navigation, et l'admin ne sait pas le manipuler
           confortablement.
        3. LA PAGE D'ACCUEIL RESTE UNE RACINE, et n'a pas d'enfants. Elle est
           servie sur « / » tout en portant un slug : ses descendants auraient
           un rattachement ambigu.
        / Three rules: no cycle (an endless walk would hang every feature that
        climbs the tree), a bounded depth, and the home page stays a childless
        root (it is served on "/" while carrying a slug, so its descendants
        would have an ambiguous attachment).
        """
        super().clean()

        if self.est_accueil and self.parent_id:
            raise ValidationError(
                {"parent": _("La page d'accueil ne peut pas être une sous-page.")}
            )

        # Une page d'accueil qui a deja des enfants ne peut pas le rester.
        # / A home page that already has children cannot stay one.
        if self.est_accueil and self.pk and self.enfants.exists():
            raise ValidationError(
                {"est_accueil": _("Cette page a des sous-pages : elle ne peut pas "
                                  "être la page d'accueil.")}
            )

        if not self.parent_id:
            return

        if self.parent_id == self.pk:
            raise ValidationError(
                {"parent": _("Une page ne peut pas être sa propre page parente.")}
            )

        # Remontee de la chaine : on cherche la page elle-meme parmi ses
        # ancetres, et on mesure la profondeur au passage.
        # / Walk up the chain: look for the page among its own ancestors, and
        # measure the depth on the way.
        ancetre = self.parent
        rang = 1
        while ancetre is not None:
            if ancetre.pk == self.pk:
                raise ValidationError(
                    {"parent": _("Cette page est déjà une page parente de celle "
                                 "choisie : la hiérarchie tournerait en rond.")}
                )
            rang += 1
            if rang > PROFONDEUR_MAX_ARBRE:
                raise ValidationError(
                    {"parent": _("Hiérarchie trop profonde : %(max)s niveaux au "
                                 "maximum.") % {"max": PROFONDEUR_MAX_ARBRE}}
                )
            ancetre = ancetre.parent

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
    (points_gps pour la carte du bloc LIEU, contenu pour ses items typés). Pas de M2M.
    / Flat fields shared across types + 2 JSONField for structured blocks
    (points_gps for the Leaflet map, contenu for the Infos block). No M2M.
    """

    # --- Types de blocs (catalogue ferme) / Block types (closed catalogue) ---
    #
    # SEPT types, organises par INTENTION de la personne qui construit la page
    # (« j'ecris du texte », « je mets en avant », « je montre des images »...),
    # et non par rendu. La variation VISUELLE a l'interieur d'un type est portee
    # par le champ `affichage` (voir AFFICHAGES_PAR_TYPE dans blocs_catalogue).
    # Regle : JAMAIS un nouveau TYPE pour une variation purement visuelle.
    # / SEVEN types, organised by the page builder's INTENT, not by rendering.
    # The VISUAL variation inside a type is carried by the `affichage` field.
    # Rule: NEVER a new TYPE for a purely visual variation.
    TEXTE = "TEXTE"
    SECTION = "SECTION"
    IMAGES = "IMAGES"
    INTEGRATION = "INTEGRATION"
    LIEU = "LIEU"
    FAQ = "FAQ"
    LISTE = "LISTE"

    TYPE_BLOC_CHOICES = [
        (TEXTE, _("Texte (article, paragraphe — écrit en Markdown)")),
        (SECTION, _("Section mise en avant (bannière, texte + média, carte, appel à l'action, citation)")),
        (IMAGES, _("Images (une photo, une galerie, une bande de logos)")),
        (INTEGRATION, _("Contenu intégré (vidéo en ligne, formulaire, newsletter)")),
        (LIEU, _("Lieu (carte des points GPS + infos pratiques)")),
        (FAQ, _("Question / réponse")),
        (LISTE, _("Liste automatique (sous-pages ou prochains évènements)")),
    ]

    # --- Affichages : la variation VISUELLE a l'interieur d'un type ---
    # Un seul champ porte l'UNION des valeurs (Django ne sait pas conditionner
    # des choices par la valeur d'un autre champ). C'est `clean()` qui refuse un
    # affichage etranger au type, en s'appuyant sur AFFICHAGES_PAR_TYPE.
    # / A single field carries the UNION of the values (Django cannot condition
    # choices on another field). `clean()` rejects an affichage foreign to the
    # type, based on AFFICHAGES_PAR_TYPE.

    # SECTION
    BANNIERE = "BANNIERE"
    TEXTE_IMAGE_GAUCHE = "TEXTE_IMAGE_GAUCHE"
    TEXTE_IMAGE_DROITE = "TEXTE_IMAGE_DROITE"
    TEXTE_VIDEO = "TEXTE_VIDEO"
    MEDIA_ET_CARTES = "MEDIA_ET_CARTES"
    CARTE = "CARTE"
    APPEL_ACTION = "APPEL_ACTION"
    CITATION = "CITATION"
    # IMAGES
    PLEINE_LARGEUR = "PLEINE_LARGEUR"
    VIGNETTE_TITRE = "VIGNETTE_TITRE"
    GRILLE = "GRILLE"
    BANDE_LOGOS = "BANDE_LOGOS"
    # INTEGRATION
    VIDEO = "VIDEO"
    WIDGET = "WIDGET"
    NEWSLETTER = "NEWSLETTER"

    AFFICHAGE_CHOICES = [
        # SECTION
        (BANNIERE, _("Bannière d'ouverture")),
        (TEXTE_IMAGE_GAUCHE, _("Texte avec image à gauche")),
        (TEXTE_IMAGE_DROITE, _("Texte avec image à droite")),
        (TEXTE_VIDEO, _("Texte avec vidéo (fichier déposé)")),
        (MEDIA_ET_CARTES, _("Média + texte + sous-cartes (section composée)")),
        (CARTE, _("Carte (se range en grille avec les cartes voisines)")),
        (APPEL_ACTION, _("Appel à l'action (boutons mis en avant)")),
        (CITATION, _("Citation / témoignage signé")),
        # IMAGES
        (PLEINE_LARGEUR, _("Photo pleine largeur")),
        (VIGNETTE_TITRE, _("Vignette centrée (image-titre dessinée)")),
        (GRILLE, _("Galerie en grille")),
        (BANDE_LOGOS, _("Bande de logos cliquables")),
        # INTEGRATION
        (VIDEO, _("Vidéo en ligne (YouTube / Vimeo / PeerTube)")),
        (WIDGET, _("Formulaire ou widget (hôte autorisé par le ROOT)")),
        (NEWSLETTER, _("Inscription newsletter (Ghost)")),
    ]

    # --- Source de donnees du bloc LISTE ---
    # `source` n'est PAS un affichage : elle choisit une REQUETE, pas un rendu.
    # / `source` is NOT an affichage: it picks a QUERY, not a rendering.
    SOUS_PAGES = "SOUS_PAGES"
    EVENEMENTS = "EVENEMENTS"

    SOURCE_CHOICES = [
        (SOUS_PAGES, _("Les sous-pages d'une page")),
        (EVENEMENTS, _("Les prochains évènements de l'agenda")),
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

    # Variations de la photo signant une citation (petit format carre).
    # / Variations of the photo signing a quote (small square format).
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

    # La variation VISUELLE a l'interieur du type. Vide = le rendu unique du
    # type (TEXTE, LIEU, FAQ, LISTE n'ont qu'un seul rendu). `clean()` refuse
    # un affichage qui n'appartient pas au type choisi.
    # / The VISUAL variation inside the type. Empty = the type's single
    # rendering. `clean()` rejects an affichage foreign to the chosen type.
    affichage = models.CharField(
        max_length=20,
        blank=True,
        choices=AFFICHAGE_CHOICES,
        verbose_name=_("Affichage"),
        help_text=_("Comment ce bloc s'affiche. Les choix dépendent du type de bloc."),
    )

    # Bloc LISTE : d'ou viennent les elements listes. Ce n'est PAS un affichage
    # (ca choisit une requete, pas un rendu).
    # / LISTE block: where the listed items come from. NOT an affichage.
    source = models.CharField(
        max_length=20,
        blank=True,
        choices=SOURCE_CHOICES,
        verbose_name=_("Source de la liste"),
        help_text=_("Bloc Liste : ce qu'on liste (les sous-pages d'une page, ou l'agenda)."),
    )

    # Bloc LISTE + source SOUS_PAGES : de quelle page on liste les enfants.
    # Vide = la page qui porte le bloc (cas courant : un index de rubrique).
    # PROTECT et non SET_NULL : si la page visee disparaissait, un SET_NULL
    # ferait basculer le bloc en silence sur « les enfants de la page courante »
    # — il changerait de contenu au lieu de signaler le probleme.
    # / LISTE block with SOUS_PAGES source: whose children to list. Empty = the
    # page holding the block. PROTECT, not SET_NULL: SET_NULL would silently
    # switch the block to "the current page's children" instead of failing.
    page_source = models.ForeignKey(
        Page,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="blocs_qui_listent_mes_enfants",
        verbose_name=_("Page à lister"),
        help_text=_("Bloc Liste : la page dont on affiche les sous-pages. Vide = la page courante."),
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
        help_text=_("Texte secondaire sous le titre. Sert aussi de sur-titre sur une carte."),
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

    # Media principal du bloc : l'illustration posee a cote d'un texte, le
    # visuel d'une carte, le logo d'un lieu.
    # / The block's main media: the illustration beside a text, a card's
    # visual, a venue's logo.
    image = StdImageField(
        upload_to="images/pages/",
        blank=True,
        variations=VARIATIONS_IMAGE,
        delete_orphans=True,
        validators=[valider_taille_image],
        verbose_name=_("Image"),
        help_text=_("Image du bloc : illustration laterale, visuel de carte, logo d'un lieu."),
    )

    # Seconde image, quand un bloc en porte deux (le logo d'un lieu et son
    # badge de dates, par exemple). Vrai moteur d'upload, avec variations.
    # / A second image, when a block carries two (a venue's logo and its date
    # badge). Real upload engine, with variations.
    image_secondaire = StdImageField(
        upload_to="images/pages/",
        blank=True,
        variations=VARIATIONS_IMAGE,
        delete_orphans=True,
        validators=[valider_taille_image],
        verbose_name=_("Seconde image"),
        help_text=_("Image secondaire (ex. badge date, logo a cote d'une carte)."),
    )

    # Video uploadee (ex. boucle d'ambiance d'un bloc Video + texte).
    # / Uploaded video (e.g. ambient loop of a Video + text block).
    video = models.FileField(
        upload_to="videos/pages/",
        blank=True,
        verbose_name=_("Video"),
        help_text=_("Fichier video (mp4/webm) depose. Pour une video en ligne, utiliser un bloc Contenu integre."),
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

    # Contenu structure d'un bloc, en liste d'items TYPES (donnees TEXTE,
    # jamais de HTML — le HTML et les classes vivent dans le gabarit) :
    #   - LIEU : les infos pratiques posees a cote de la carte ;
    #   - SECTION en affichage MEDIA_ET_CARTES : les sous-cartes de la section.
    # Types d'item : "badge" (texte), "para" (texte), "horaire" (texte),
    # "adresse" (texte multi-lignes), "accessibilite" (texte),
    # "transport" (titre + lignes[]). / Structured content for the left column of the
    # / A block's structured content, as TYPED items (TEXT only, never HTML):
    # LIEU's practical info, or a MEDIA_ET_CARTES section's sub-cards.
    contenu = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Contenu structure (colonne gauche)"),
        help_text=_('Items typés (texte seulement) : [{"type": "transport", "titre": "BUS", "lignes": ["..."]}].'),
    )

    # Nombre maximum d'elements affiches par les blocs a liste automatique
    # (bloc LISTE, quelle que soit sa source).
    # / Maximum number of items shown by the auto-list blocks
    # (LISTE block, whatever its source).
    nombre_max = models.PositiveSmallIntegerField(
        default=6,
        verbose_name=_("Nombre d'éléments"),
        help_text=_("Nombre maximum d'éléments affichés (blocs Prochains évènements et Liste des sous-pages)."),
    )


    # URL du contenu à intégrer, PARTAGÉE par deux blocs :
    # L'affichage du bloc INTEGRATION decide de ce qu'on en fait :
    # - VIDEO : YouTube / Vimeo / PeerTube (whitelist codee, cf. tag embed_iframe) ;
    # - WIDGET : formulaire ou widget libre (whitelist ROOT, cf. tag iframe_libre) ;
    # - NEWSLETTER : l'adresse de l'instance Ghost.
    # Dans tous les cas, on n'injecte JAMAIS un iframe vers un hote arbitraire.
    # Pour une carte geographique, utiliser un bloc LIEU.
    # / The INTEGRATION block's affichage decides what happens to this URL:
    # VIDEO (coded whitelist), WIDGET (ROOT whitelist) or NEWSLETTER. We NEVER
    # inject an iframe to an arbitrary host. For a map, use a LIEU block.
    embed_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name=_("URL à intégrer (embed)"),
        help_text=_("Lien du contenu a integrer, selon l'affichage choisi. "
                    "Video : YouTube / Vimeo / PeerTube. "
                    "Formulaire ou widget : hote autorise par le ROOT. "
                    "Newsletter : adresse de l'instance Ghost (ex. https://ghost.exemple.coop/)."),
    )

    # Hauteur du cadre integre, en pixels. Un formulaire n'a pas de ratio fixe
    # (contrairement a une video 16:9) : sa hauteur se declare.
    # / Embedded frame height in pixels. A form has no fixed ratio (unlike a
    # 16:9 video), so its height is declared.
    hauteur_px = models.PositiveIntegerField(
        default=600,
        validators=[MinValueValidator(100), MaxValueValidator(4000)],
        verbose_name=_("Hauteur de l'iframe (pixels)"),
        help_text=_("Hauteur du cadre integre, en pixels (affichage Formulaire ou widget)."),
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
        validators=[valider_taille_image],
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

    def poser_affichage_par_defaut(self):
        """
        Donne un affichage au bloc quand aucun n'a ete choisi.
        / Gives the block an affichage when none was chosen.

        LOCALISATION : pages/models.py

        Un type a plusieurs rendus (SECTION, IMAGES, INTEGRATION) n'a pas de
        gabarit « generique » : le rendu cherche `bloc_<type>_<affichage>.html`
        et, sans affichage, retomberait sur un `bloc_<type>.html` qui n'existe
        pas — la page entiere sortirait en erreur. On pose donc le rendu le plus
        neutre du type plutot que de laisser le champ vide.
        / A multi-rendering type has no "generic" template: rendering looks for
        `bloc_<type>_<affichage>.html` and, with no affichage, would fall back
        to a `bloc_<type>.html` that does not exist — the whole page would
        error. So we set the type's most neutral rendering.
        """
        from pages.blocs_catalogue import AFFICHAGE_PAR_DEFAUT

        if not self.affichage:
            self.affichage = AFFICHAGE_PAR_DEFAUT.get(self.type_bloc, "")

    def save(self, *args, **kwargs):
        """
        Enregistre le bloc apres s'etre assure qu'il a un affichage.
        / Saves the block after making sure it has an affichage.

        Le defaut est pose ICI et pas seulement dans clean() : un
        `objects.create()` (migration de donnees, commande de chargement, seed)
        n'appelle jamais clean(), et produirait donc un bloc irrendable.
        / The default is set HERE, not only in clean(): an `objects.create()`
        (data migration, loading command, seed) never calls clean() and would
        otherwise produce an unrenderable block.
        """
        self.poser_affichage_par_defaut()
        super().save(*args, **kwargs)

    def clean(self):
        """
        Verifie que l'affichage choisi appartient bien au type du bloc.
        / Checks the chosen affichage belongs to the block's type.

        LOCALISATION : pages/models.py

        Le modele ne porte qu'UN champ `affichage`, avec l'UNION de toutes les
        valeurs : Django ne sait pas restreindre des choices selon la valeur
        d'un autre champ. Sans cette methode, un bloc SECTION accepterait
        « bande de logos » (un affichage du type IMAGES) et le rendu tomberait
        sur un gabarit qui n'existe pas.
        / The model carries ONE `affichage` field holding the UNION of all
        values: Django cannot restrict choices by another field's value.
        Without this method, a SECTION block would accept an IMAGES affichage
        and the rendering would look for a template that does not exist.

        La table de reference est AFFICHAGES_PAR_TYPE (pages/blocs_catalogue.py)
        — la meme que celle lue par l'API et par l'admin. Une seule source.
        / The reference table is AFFICHAGES_PAR_TYPE, the same one read by the
        API and the admin. A single source.
        """
        super().clean()

        # Import local : blocs_catalogue n'importe rien de models, mais on garde
        # le meme reflexe que les autres imports de ce fichier.
        # / Local import: same habit as the other imports of this file.
        from pages.blocs_catalogue import AFFICHAGES_PAR_TYPE

        self.poser_affichage_par_defaut()
        affichages_permis = AFFICHAGES_PAR_TYPE.get(self.type_bloc, ())

        # Un type a rendu unique (TEXTE, LIEU, FAQ, LISTE) n'accepte aucun
        # affichage : le champ doit rester vide.
        # / A single-rendering type accepts no affichage: the field stays empty.
        if not affichages_permis:
            if self.affichage:
                raise ValidationError({
                    "affichage": _(
                        "Le type de bloc « %(type)s » n'a qu'un seul affichage : "
                        "ce champ doit rester vide."
                    ) % {"type": self.get_type_bloc_display()},
                })
            return

        # Un type a plusieurs rendus n'accepte que les siens.
        # / A multi-rendering type only accepts its own.
        if self.affichage and self.affichage not in affichages_permis:
            raise ValidationError({
                "affichage": _(
                    "L'affichage « %(affichage)s » n'existe pas pour le type de "
                    "bloc « %(type)s »."
                ) % {
                    "affichage": self.affichage,
                    "type": self.get_type_bloc_display(),
                },
            })


class ImageGalerie(models.Model):
    """
    Une image rattachee a un bloc. Relation plusieurs-images-vers-un-bloc :
    c'est le seul cas du moteur ou un bloc porte plusieurs fichiers (les autres
    blocs ont un champ image plat). Editee en inline (TabularInline) dans
    l'admin du Bloc. Sert aux blocs IMAGES en galerie ou en bande de logos, et
    aux images referencees depuis un bloc TEXTE (![legende](galerie:N)).
    / An image attached to a block. Many-images-to-one-block relation: the only
    case in the engine where a block carries several files. Used by IMAGES
    blocks (grid or logo strip) and by images referenced from a TEXTE block.

    LOCALISATION : pages/models.py
    """

    uuid = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True
    )

    # Le bloc auquel cette image appartient. Suppression en cascade.
    # / The block this image belongs to. Cascade delete.
    bloc = models.ForeignKey(
        Bloc,
        on_delete=models.CASCADE,
        related_name="images_galerie",
        verbose_name=_("Bloc galerie"),
    )

    # Vrai moteur d'upload (comme le reste de TiBillet), avec variations.
    # / Real upload engine (like the rest of TiBillet), with variations.
    image = StdImageField(
        upload_to="images/pages/galerie/",
        blank=True,
        variations=VARIATIONS_PARTAGE,
        delete_orphans=True,
        validators=[valider_taille_image],
        verbose_name=_("Image"),
        help_text=_("Une photo de la galerie."),
    )

    # Légende optionnelle (texte d'alternative + sous-titre affiché).
    # / Optional caption (alt text + displayed subtitle).
    legende = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Légende"),
        help_text=_("Texte alternatif et légende de l'image (optionnel)."),
    )

    # Lien optionnel de l'image : si renseigne, l'image devient cliquable
    # (nouvel onglet). Sert surtout a une bande de logos (chaque logo mene au
    # site du partenaire), mais vaut pour toute image de galerie. Le HTML du
    # lien est dans le gabarit. Validator anti-XSS : l'inline ne passe PAS par
    # BlocAdmin.save_model, donc rien ne neutraliserait l'URL sans lui.
    # / Optional image link making the image clickable. Mostly for a logo strip,
    # but valid for any gallery image. Anti-XSS validator: the inline does not
    # go through BlocAdmin.save_model, so nothing else would neutralise it.
    lien_url = models.CharField(
        max_length=500,
        blank=True,
        validators=[valider_url_sans_schema_dangereux],
        verbose_name=_("Lien de l'image"),
        help_text=_("Lien optionnel : rend l'image cliquable (nouvel onglet). Ex. site d'un partenaire."),
    )

    # Ordre de l'image dans la galerie (croissant).
    # / Image order in the gallery (ascending).
    position = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Position"),
        help_text=_("Ordre de l'image dans la galerie (croissant)."),
    )

    class Meta:
        verbose_name = _("Image de galerie")
        verbose_name_plural = _("Images de galerie")
        ordering = ["position"]

    def __str__(self):
        return self.legende or f"Image #{self.position}"
