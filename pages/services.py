"""
Services de l'app pages.
/ Services of the pages app.

LOCALISATION : pages/services.py

construire_page_accueil() fabrique une page d'accueil par defaut qui reproduit la
home historique (titre = nom du lieu, sous-titre = description courte, corps =
description longue, boutons Agenda / Adhesions selon les modules actifs, image de
fond = image de la Configuration).

La fonction prend les classes de modeles en PARAMETRES (PageModel, BlocModel) pour
etre utilisable :
  - depuis une migration de donnees (modeles historiques via apps.get_model),
  - depuis le flux d'onboarding (modeles reels).
Elle n'importe donc aucun modele au niveau module, et utilise des chaines pour
type_bloc (pas les constantes de classe, absentes des modeles historiques).
/ The function takes the model classes as PARAMETERS so it works both from a data
migration (historical models) and from the onboarding flow (real models). It
imports no model at module level and uses string literals for type_bloc.
"""
from django.template import TemplateDoesNotExist
from django.template.loader import get_template


def gabarit_skin(nom_du_gabarit):
    """
    Resolveur unifié des gabarits de skin (migration skins, CHANTIER-01).
    / Unified skin template resolver (skins migration, CHANTIER-01).

    LOCALISATION : pages/services.py

    Retourne le CHEMIN du gabarit à utiliser pour le skin courant :
    - "pages/<skin>/<nom>" si le skin fournit ce gabarit,
    - sinon "pages/classic/<nom>" — le socle, filet de sécurité permanent.

    Le skin par défaut "reunion" n'a pas de dossier pages/reunion/ : il retombe
    donc toujours sur pages/classic/ (voulu — décision 1 du plan de migration,
    zéro migration de données sur ConfigurationSite.skin).
    / The default skin "reunion" has no pages/reunion/ folder: it always falls
    back to pages/classic/ (by design — decision 1 of the migration plan).

    À terme, cette fonction remplace BaseBillet.views.get_skin_template pour
    tout le templating public. Pendant la migration, les deux coexistent.
    / Eventually replaces get_skin_template for all public templating. Both
    coexist during the migration.

    :param nom_du_gabarit: chemin relatif dans le skin, ex "shell.html"
        ou "vues/agenda.html".
    :return: chemin complet du gabarit (str) — utilisable par render()
        et par {% extends base_template %}.
    """
    # Import local pour éviter l'import circulaire BaseBillet <-> pages
    # (même pattern que dans pages/views.py).
    # / Local import to avoid the circular import between BaseBillet and pages.
    from BaseBillet.views import get_skin_courant

    skin = get_skin_courant()

    chemin_dans_le_skin = f"pages/{skin}/{nom_du_gabarit}"
    chemin_dans_le_socle = f"pages/classic/{nom_du_gabarit}"

    try:
        # Le gabarit existe-t-il dans le skin courant ?
        # / Does the template exist in the current skin?
        get_template(chemin_dans_le_skin)
        return chemin_dans_le_skin
    except TemplateDoesNotExist:
        # Non : on retombe sur le socle classic.
        # / No: fall back to the classic base.
        return chemin_dans_le_socle


def grouper_blocs(blocs):
    """
    Regroupe les blocs pour le rendu. Retourne une liste de groupes typés :
    / Groups blocks for rendering. Returns a list of typed groups:

    - {"type": "section_video", "video": bloc, "cartes": [...], "cta": bloc|None}
        Un bloc VIDEO_TEXTE absorbe les CARTE qui le suivent immediatement, plus un
        CTA eventuel : c'est la section « video a gauche / texte + cartes + bouton a
        droite » (reproduit la section 2 de la home faire_festival).
    - {"type": "grille", "blocs": [cartes]}
        Une suite de CARTE consecutives (hors section_video) -> une grille.
    - {"type": "solo", "bloc": bloc}
        Tout autre bloc, rendu seul.
    / - "section_video": a VIDEO_TEXTE block absorbs the CARTE blocks right after it,
        plus an optional CTA (the "video left / text + cards + button right" section).
    - "grille": a run of consecutive CARTE blocks -> a grid.
    - "solo": any other block, rendered alone.

    Le template page.html (par skin) decide du balisage de chaque type de groupe.
    / The (per-skin) page.html template decides the markup for each group type.
    """
    blocs = list(blocs)
    groupes = []
    i = 0
    n = len(blocs)
    while i < n:
        bloc = blocs[i]

        if bloc.type_bloc == "VIDEO_TEXTE":
            # Section composee : on absorbe les CARTE suivantes puis un CTA eventuel.
            # / Composed section: absorb the following CARTE blocks then an optional CTA.
            j = i + 1
            cartes = []
            while j < n and blocs[j].type_bloc == "CARTE":
                cartes.append(blocs[j])
                j += 1
            cta = None
            if j < n and blocs[j].type_bloc == "CTA":
                cta = blocs[j]
                j += 1
            groupes.append(
                {"type": "section_video", "video": bloc, "cartes": cartes, "cta": cta}
            )
            i = j

        elif bloc.type_bloc == "CARTE":
            # Grille de cartes consecutives.
            # / Grid of consecutive cards.
            cartes = []
            while i < n and blocs[i].type_bloc == "CARTE":
                cartes.append(blocs[i])
                i += 1
            groupes.append({"type": "grille", "blocs": cartes})

        elif bloc.type_bloc == "INFOS":
            # Bloc d'infos : s'il est suivi d'une carte Leaflet, on les affiche cote a
            # cote (infos a gauche, carte a droite). Sinon, bloc seul.
            # / Info block: if followed by a Leaflet map, render them side by side
            # (info left, map right). Otherwise standalone.
            if i + 1 < n and blocs[i + 1].type_bloc == "CARTE_LEAFLET":
                groupes.append(
                    {"type": "section_carte", "info": bloc, "carte": blocs[i + 1]}
                )
                i += 2
            else:
                groupes.append({"type": "solo", "bloc": bloc})
                i += 1

        elif bloc.type_bloc == "FAQ":
            # FAQ consecutives regroupees (rendues en 2 colonnes par le template).
            # / Consecutive FAQ blocks grouped (rendered in 2 columns by the template).
            faqs = []
            while i < n and blocs[i].type_bloc == "FAQ":
                faqs.append(blocs[i])
                i += 1
            groupes.append({"type": "faq", "blocs": faqs})

        else:
            # Bloc seul.
            # / Standalone block.
            groupes.append({"type": "solo", "bloc": bloc})
            i += 1

    return groupes


def _slug_accueil_libre(PageModel):
    """
    Retourne un slug libre pour la page d'accueil ("accueil", sinon "accueil-2"...).
    / Returns a free slug for the home page ("accueil", else "accueil-2"...).
    """
    slug = "accueil"
    compteur = 1
    while PageModel.objects.filter(slug=slug).exists():
        compteur += 1
        slug = f"accueil-{compteur}"
    return slug


def construire_page_accueil(PageModel, BlocModel, config, description_longue=None):
    """
    Cree une page d'accueil par defaut : HERO (identite) -> PARAGRAPHE (description
    longue) -> CTA (actions selon les modules actifs).
    Idempotent : ne fait rien si une page d'accueil (est_accueil=True) existe deja.
    / Creates a default home page: HERO (identity) -> PARAGRAPH (long description)
    -> CTA (actions depending on active modules).
    Idempotent: does nothing if a home page (est_accueil=True) already exists.

    :param PageModel: la classe Page (reelle ou historique).
    :param BlocModel: la classe Bloc (reelle ou historique).
    :param config: l'instance Configuration du tenant (organisation, descriptions,
        modules...).
    :param description_longue: texte du bloc PARAGRAPHE (TOUJOURS cree, meme vide).
        None = on prend celle de la config (flux migration tenants existants).
        Une chaine, meme vide = on l'utilise telle quelle (flux onboarding : evite
        le texte d'accueil hardcode ecrit par create_tenant).
    :return: la Page creee, ou None si une page d'accueil existait deja.
    """
    # Idempotence : on ne touche pas a un tenant qui a deja une page d'accueil.
    # / Idempotency: leave alone any tenant that already has a home page.
    if PageModel.objects.filter(est_accueil=True).exists():
        return None

    # gettext (pas lazy) : les libelles CTA sont figes en base a la creation,
    # dans la langue active du tenant (activate(config.language) est fait par
    # create_tenant avant l'appel). / gettext (not lazy): CTA labels are frozen
    # in DB at creation, in the tenant's active language.
    from django.utils.translation import gettext as _

    nom_lieu = getattr(config, "organisation", "") or "Accueil"
    description_courte = getattr(config, "short_description", "") or ""

    # Description longue : fournie explicitement (flux onboarding, pour ne pas
    # etre trompe par le texte d'accueil hardcode), sinon celle de la config
    # (flux migration tenants existants).
    # / Long description: explicit (onboarding, to avoid the hardcoded welcome
    # text) or the config's one (existing-tenants migration).
    if description_longue is None:
        description_longue = getattr(config, "long_description", "") or ""

    page = PageModel.objects.create(
        titre=nom_lieu,
        slug=_slug_accueil_libre(PageModel),
        position=0,
        publie=True,
        est_accueil=True,
        meta_description=description_courte[:255],
    )

    # --- Bloc HERO (pos 1) : banniere d'identite, titre + sous-titre ---
    # Pas de champ image : le fond est l'image generique du lieu (config.img),
    # lue au rendu par le template. / HERO block (pos 1): identity banner, title
    # + subtitle. No image field: the background is the venue's generic image
    # (config.img), read at render time by the template.
    BlocModel.objects.create(
        page=page,
        type_bloc="HERO",
        position=1,
        titre=nom_lieu,
        sous_titre=description_courte,
    )

    # --- Bloc PARAGRAPHE (pos 2) : description longue (texte riche deja nettoye) ---
    # TOUJOURS cree, meme vide : l'utilisateur pourra le remplir plus tard depuis
    # l'admin (le template ne rend rien tant que le texte est vide).
    # / PARAGRAPH block (pos 2): long description. ALWAYS created, even empty: the
    # user can fill it later from the admin (the template renders nothing while
    # the text is empty).
    BlocModel.objects.create(
        page=page,
        type_bloc="PARAGRAPHE",
        position=2,
        texte=description_longue,
    )

    # --- Bloc CTA (pos 3) : actions selon les modules actifs ---
    # Memes URL et memes libelles que la navbar (get_context) : agenda puis
    # adhesions. Cree uniquement s'il porte au moins une action.
    # / CTA block (pos 3): actions depending on active modules. Same URLs and
    # labels as the navbar (agenda then memberships). Created only if it carries
    # at least one action.
    cta = BlocModel(page=page, type_bloc="CTA", position=3)

    if getattr(config, "module_billetterie", False):
        cta.bouton_label = getattr(config, "event_menu_name", "") or _("Calendar")
        cta.bouton_url = "/event/"

    if getattr(config, "module_adhesion", False):
        label_adhesions = getattr(config, "membership_menu_name", "") or _("Subscriptions")
        if cta.bouton_label:
            # L'agenda occupe deja le bouton principal : adhesions en second.
            # / Calendar already took the primary button: memberships as second.
            cta.bouton2_label = label_adhesions
            cta.bouton2_url = "/memberships/"
        else:
            cta.bouton_label = label_adhesions
            cta.bouton_url = "/memberships/"

    if cta.bouton_label:
        cta.save()

    return page
