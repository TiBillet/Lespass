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
    :param description_longue: texte du bloc TEXTE (TOUJOURS cree, meme vide).
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

    # Le couple (type_bloc, affichage) est ecrit en CHAINES et non via les
    # constantes du modele : la fonction recoit aussi des modeles HISTORIQUES
    # (migration de donnees), qui ne portent pas les constantes de classe.
    # Un affichage vide sur un bloc SECTION laisserait le rendu chercher un
    # gabarit « bloc_section.html » qui n'existe pas.
    # / The (type_bloc, affichage) pair is written as STRINGS, not via the model
    # constants: this function also receives HISTORICAL models (data migration),
    # which carry no class constants. An empty affichage on a SECTION block
    # would send the renderer looking for a template that does not exist.

    # --- Banniere d'identite (pos 1) : titre + sous-titre ---
    # Pas de champ image : le fond est l'image generique du lieu (config.img),
    # lue au rendu par le template. / Identity banner (pos 1): title + subtitle.
    # No image field: the background is the venue's generic image, read at
    # render time by the template.
    BlocModel.objects.create(
        page=page,
        type_bloc="SECTION",
        affichage="BANNIERE",
        position=1,
        titre=nom_lieu,
        sous_titre=description_courte,
    )

    # --- Texte (pos 2) : description longue ---
    # TOUJOURS cree, meme vide : l'utilisateur pourra le remplir plus tard depuis
    # l'admin (le template ne rend rien tant que le texte est vide).
    # / Text (pos 2): long description. ALWAYS created, even empty: the user can
    # fill it later from the admin (the template renders nothing while empty).
    BlocModel.objects.create(
        page=page,
        type_bloc="TEXTE",
        position=2,
        texte=description_longue,
    )

    # --- Appel a l'action (pos 3) : actions selon les modules actifs ---
    # Memes URL et memes libelles que la navbar (get_context) : agenda puis
    # adhesions. Cree uniquement s'il porte au moins une action.
    # / Call to action (pos 3): actions depending on active modules. Same URLs
    # and labels as the navbar. Created only if it carries at least one action.
    cta = BlocModel(
        page=page, type_bloc="SECTION", affichage="APPEL_ACTION", position=3
    )

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


def _arbre_des_pages_publiees(PageModel):
    """
    Charge toutes les pages publiees en UNE requete et les range par parent.
    / Loads every published page in ONE query and indexes them by parent.

    LOCALISATION : pages/services.py

    L'arbre est construit en memoire plutot qu'en base : a l'echelle d'un site
    (quelques dizaines a quelques centaines de pages), une seule requete suivie
    d'un tri Python coute moins qu'une requete recursive, et se lit sans
    connaitre les CTE.
    / The tree is built in memory rather than in SQL: at a site's scale, one
    query plus a Python pass costs less than a recursive query, and reads
    without knowing CTEs.

    Ne retourne QUE les pages publiees : une page en brouillon ne doit
    apparaitre dans aucun menu, meme pour un administrateur connecte.
    / Returns ONLY published pages: a draft must appear in no menu.

    :return: (racines, enfants_par_parent) — les pages de premier niveau, et
        l'index uuid_du_parent -> [pages enfants], les deux tries pour
        l'affichage.
    """
    pages = list(
        PageModel.objects.filter(publie=True)
        .select_related("parent")
        .order_by("position", "titre")
    )

    racines = []
    enfants_par_parent = {}
    for page in pages:
        if page.parent_id:
            enfants_par_parent.setdefault(page.parent_id, []).append(page)
        else:
            racines.append(page)
    return racines, enfants_par_parent


def _maillon_de_navigation(page, enfants=()):
    """
    Traduit une page en entree de menu.
    / Turns a page into a menu entry.
    """
    return {
        "name": f"page-{page.slug}",
        "url": page.get_absolute_url(),
        "label": page.titre,
        "icon": "house-door" if page.est_accueil else "file-earmark-text",
        "children": [_maillon_de_navigation(enfant) for enfant in enfants],
    }


def construire_navbar_pages(PageModel):
    """
    Construit les entrees de barre de navigation issues des pages du tenant.
    / Builds the navigation bar entries coming from the tenant's pages.

    LOCALISATION : pages/services.py

    Une racine apparait dans la barre selon son `affichage_nav` :
      - NAVBAR  : elle y figure, ses enfants directs en menu deroulant ;
      - SIDEBAR : elle y figure aussi, mais SANS deroulant — son arbre se
        deplie dans le menu lateral de la page, pas dans la barre du haut ;
      - AUCUN   : elle n'y figure pas.
    Les descendants n'ont jamais d'entree propre : ils vivent dans le
    deroulant de leur racine ou dans le menu lateral.
    / A root appears in the bar according to its `affichage_nav`. Descendants
    never get their own entry: they live in their root's dropdown or in the
    side menu.
    """
    racines, enfants_par_parent = _arbre_des_pages_publiees(PageModel)

    entrees = []
    for racine in racines:
        if racine.affichage_nav == PageModel.AUCUN:
            continue
        # Une racine en menu lateral n'ouvre pas de deroulant : son arbre est
        # deja donne en entier par le menu de gauche, le repeter en haut
        # ferait deux navigations pour une seule structure.
        # / A side-menu root opens no dropdown: its tree is already given in
        # full by the left menu.
        enfants = ()
        if racine.affichage_nav == PageModel.NAVBAR:
            enfants = enfants_par_parent.get(racine.pk, ())
        entrees.append(_maillon_de_navigation(racine, enfants))
    return entrees


def _racine_de(page):
    """
    Remonte jusqu'a la racine de l'arbre auquel la page appartient.
    / Walks up to the root of the tree the page belongs to.

    La remontee est bornee : une hierarchie circulaire ecrite hors validation
    ferait sinon boucler sans fin.
    / The walk is bounded: a circular hierarchy written outside validation
    would otherwise loop forever.
    """
    from pages.models import PROFONDEUR_MAX_ARBRE

    courante = page
    rang = 0
    while courante.parent is not None and rang < PROFONDEUR_MAX_ARBRE:
        courante = courante.parent
        rang += 1
    return courante


def _parcours_en_profondeur(racine, enfants_par_parent, profondeur=1):
    """
    Met l'arbre a plat dans l'ordre de lecture : une page, puis ses enfants.
    / Flattens the tree in reading order: a page, then its children.

    C'est l'ordre du menu lateral ET celui de la navigation precedent/suivant :
    les deux decrivent le meme parcours, donc ils ne peuvent pas diverger.
    / This is both the side menu's order and the previous/next order: they
    describe the same walk, so they cannot drift apart.
    """
    entrees = [{"page": racine, "profondeur": profondeur}]
    for enfant in enfants_par_parent.get(racine.pk, ()):
        entrees.extend(
            _parcours_en_profondeur(enfant, enfants_par_parent, profondeur + 1)
        )
    return entrees


def construire_menu_lateral(PageModel, page_courante):
    """
    Construit le menu lateral de la page, et ses voisines precedente/suivante.
    / Builds the page's side menu, plus its previous/next neighbours.

    LOCALISATION : pages/services.py

    Le menu n'existe que pour une page dont la RACINE est en SIDEBAR : c'est
    une navigation de documentation, elle n'a pas de sens sur une page isolee.
    / The menu only exists for a page whose ROOT is in SIDEBAR: it is a
    documentation navigation, meaningless on a standalone page.

    Precedent/suivant suivent le MEME parcours que le menu, et restent DANS
    l'arbre courant : une chaine qui traverserait deux arbres enchainerait la
    derniere page d'une rubrique sur la premiere d'une autre, sans rapport.
    / Previous/next follow the SAME walk as the menu and stay INSIDE the
    current tree: a chain crossing two trees would link the last page of one
    section to the first of an unrelated one.

    :return: un dict {entrees, precedente, suivante}, vide si la page n'est pas
        dans un arbre affiche en menu lateral.
    """
    if page_courante is None:
        return {}

    racine = _racine_de(page_courante)
    if racine.affichage_nav != PageModel.SIDEBAR:
        return {}
    # Racine en brouillon : elle n'a pas d'adresse publique. Le parcours part
    # d'elle sans condition, donc la lister mettrait en tete du menu un lien
    # qui renvoie 404 a un visiteur. Aucun menu vaut mieux qu'un menu qui ment.
    # / Draft root: it has no public address. The walk starts from it
    # unconditionally, so listing it would put a link 404-ing for visitors at
    # the top of the menu. No menu beats a lying menu.
    if not racine.publie:
        return {}

    _, enfants_par_parent = _arbre_des_pages_publiees(PageModel)
    parcours = _parcours_en_profondeur(racine, enfants_par_parent)

    entrees = [
        {
            "titre": entree["page"].titre,
            "url": entree["page"].get_absolute_url(),
            "profondeur": entree["profondeur"],
            "est_la_page_courante": entree["page"].pk == page_courante.pk,
        }
        for entree in parcours
    ]

    # Position de la page dans le parcours : elle en est absente si elle est en
    # brouillon (l'arbre ne liste que les pages publiees) — on ne propose alors
    # aucune voisine plutot que de designer les mauvaises.
    # / The page is missing from the walk when it is a draft (the tree only
    # lists published pages): we then offer no neighbour rather than the wrong
    # ones.
    rang = next(
        (i for i, entree in enumerate(parcours)
         if entree["page"].pk == page_courante.pk),
        None,
    )
    if rang is None:
        return {"entrees": entrees, "precedente": None, "suivante": None}

    return {
        "entrees": entrees,
        "precedente": parcours[rang - 1]["page"] if rang > 0 else None,
        "suivante": parcours[rang + 1]["page"] if rang + 1 < len(parcours) else None,
    }
