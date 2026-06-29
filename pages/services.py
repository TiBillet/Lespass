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


def construire_page_accueil(PageModel, BlocModel, config):
    """
    Cree une page d'accueil par defaut reproduisant la home historique.
    Idempotent : ne fait rien si une page d'accueil (est_accueil=True) existe deja.
    / Creates a default home page reproducing the historical home.
    Idempotent: does nothing if a home page (est_accueil=True) already exists.

    :param PageModel: la classe Page (reelle ou historique).
    :param BlocModel: la classe Bloc (reelle ou historique).
    :param config: l'instance Configuration du tenant (organisation, descriptions,
        modules, image...).
    :return: la Page creee, ou None si une page d'accueil existait deja.
    """
    # Idempotence : on ne touche pas a un tenant qui a deja une page d'accueil.
    # / Idempotency: leave alone any tenant that already has a home page.
    if PageModel.objects.filter(est_accueil=True).exists():
        return None

    nom_lieu = getattr(config, "organisation", "") or "Accueil"
    description_courte = getattr(config, "short_description", "") or ""
    description_longue = getattr(config, "long_description", "") or ""

    page = PageModel.objects.create(
        titre=nom_lieu,
        slug=_slug_accueil_libre(PageModel),
        position=0,
        publie=True,
        est_accueil=True,
        meta_description=description_courte[:255],
    )

    # --- Bloc HERO : titre + sous-titre + image de fond + boutons ---
    # / HERO block: title + subtitle + background image + buttons.
    hero = BlocModel(
        page=page,
        type_bloc="HERO",
        position=1,
        titre=nom_lieu,
        sous_titre=description_courte,
    )

    # NB : on NE partage PAS le fichier Configuration.img sur hero.image. Bloc.image
    # a delete_orphans=True : pointer le bloc sur le meme fichier que la Configuration
    # ferait supprimer l'image du tenant si le bloc d'accueil etait change/supprime.
    # Le hero auto-genere reste donc sans image de fond (titre + sous-titre sur le
    # fond du theme) ; la vraie home « riche » est construite par la commande de demo
    # qui UPLOAD ses propres fichiers.
    # / We do NOT share Configuration.img on hero.image: Bloc.image has
    # delete_orphans=True, so pointing the block at the Configuration's file would
    # delete the tenant image if the home block were changed/deleted. The auto home
    # hero stays background-less; the rich home is built by the demo command (uploads).

    # Boutons selon les modules actifs (comme la home historique).
    # / Buttons depending on active modules (like the historical home).
    label_agenda = getattr(config, "event_menu_name", "") or "Agenda"
    label_adhesions = getattr(config, "membership_menu_name", "") or "Adhésions"

    if getattr(config, "module_billetterie", False):
        hero.bouton_label = label_agenda
        hero.bouton_url = "/event/"

    if getattr(config, "module_adhesion", False):
        if hero.bouton_label:
            # L'agenda occupe deja le bouton principal : adhesions en second.
            # / Calendar already took the primary button: memberships as second.
            hero.bouton2_label = label_adhesions
            hero.bouton2_url = "/memberships/"
        else:
            hero.bouton_label = label_adhesions
            hero.bouton_url = "/memberships/"

    hero.save()

    # --- Bloc PARAGRAPHE : description longue (texte riche deja nettoye) ---
    # / PARAGRAPH block: long description (rich text, already sanitized).
    if description_longue.strip():
        BlocModel.objects.create(
            page=page,
            type_bloc="PARAGRAPHE",
            position=2,
            texte=description_longue,
        )

    return page
