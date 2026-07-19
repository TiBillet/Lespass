"""
Bascule du catalogue de blocs : 19 types de rendu -> 7 types d'intention.
/ Block catalogue switch: 19 rendering types -> 7 intent types.

LOCALISATION : pages/migrations/0004_...

Les anciens types decrivaient un RENDU (« hero », « image + texte », « carte »).
Les nouveaux decrivent une INTENTION (« je mets en avant », « je montre des
images »), et la variation visuelle passe dans le champ `affichage`.

ORDRE DES OPERATIONS — deux contraintes a respecter si on retouche ce fichier :
1. AddField   : les nouvelles colonnes existent avant qu'on ecrive dedans.
2. AlterField : type_bloc accepte les nouveaux codes.
3. RunPython  : la conversion LIT `image_position`, `affichage_image` et
   `surtitre`. Aucune suppression de colonne ne doit passer avant elle, sinon
   la conversion lit des colonnes disparues.
Les suppressions vivent donc dans la migration 0005, qui reste SEPAREE :
Postgres refuse un ALTER TABLE sur une table qui vient de recevoir des
UPDATE/DELETE dans la meme transaction (« pending trigger events »).
/ Operation ORDER — two constraints to respect when editing this file: the
RunPython READS the old columns, so no column drop may run before it; and the
drops live in migration 0005, kept SEPARATE because Postgres refuses an ALTER
TABLE on a table that just received UPDATEs/DELETEs in the same transaction.

MULTI-TENANT : l'app `pages` est en dual-list (SHARED_APPS ET TENANT_APPS), et
ses tables existent donc AUSSI dans le schema public. Cette migration ne pose
donc AUCUN garde « si public, on sort » : elle doit tourner dans tous les
schemas, public compris, sinon les pages du public resteraient sur l'ancien
catalogue.
/ MULTI-TENANT: the `pages` app is dual-listed, its tables exist in the public
schema too. No "skip if public" guard here on purpose.
"""

from django.db import migrations, models
import django.db.models.deletion


# Correspondance ancien type -> (nouveau type, affichage).
# Un affichage a None signifie « decide au cas par cas » (cf. la fonction).
# / Old type -> (new type, affichage). None means "decided case by case".
CORRESPONDANCE_DES_TYPES = {
    "HERO": ("SECTION", "BANNIERE"),
    "CTA": ("SECTION", "APPEL_ACTION"),
    "TEMOIGNAGE": ("SECTION", "CITATION"),
    "VIDEO_TEXTE": ("SECTION", "TEXTE_VIDEO"),
    "CARTE": ("SECTION", "CARTE"),
    "IMAGE_TEXTE": ("SECTION", None),      # depend de image_position
    "PARAGRAPHE": ("TEXTE", ""),
    "MARKDOWN": ("TEXTE", ""),
    "IMAGE": ("IMAGES", None),             # depend de affichage_image
    "GALERIE": ("IMAGES", "GRILLE"),
    "PARTENAIRES": ("IMAGES", "BANDE_LOGOS"),
    "EMBED": ("INTEGRATION", "VIDEO"),
    "IFRAME": ("INTEGRATION", "WIDGET"),
    "NEWSLETTER": ("INTEGRATION", "NEWSLETTER"),
    "CARTE_LEAFLET": ("LIEU", ""),
    "INFOS": ("LIEU", ""),
    "FAQ": ("FAQ", ""),
    "EVENEMENTS": ("LISTE", ""),
    "LISTE_SOUS_PAGES": ("LISTE", ""),
}


def convertir_les_blocs_vers_le_catalogue_a_sept_types(apps, schema_editor):
    """
    Convertit chaque bloc vers son nouveau couple (type, affichage).
    / Converts every block to its new (type, affichage) pair.

    Quatre conversions ne sont pas de simples renommages :

    1. INFOS + CARTE_LEAFLET adjacents FUSIONNENT en un seul bloc LIEU.
       Les deux etaient concus pour etre poses cote a cote, et un regroupement
       implicite les recollait au rendu. Le bloc INFOS est absorbe (son
       `contenu` passe dans le LIEU) puis supprime. Sans ce cas, on obtiendrait
       deux blocs LIEU a moitie vides empiles.
    2. IMAGE_TEXTE lit `image_position` (GAUCHE/DROITE) pour choisir entre
       TEXTE_IMAGE_GAUCHE et TEXTE_IMAGE_DROITE.
    3. IMAGE lit `affichage_image` (PLEINE_LARGEUR/VIGNETTE_TITRE).
    4. CARTE deplace son `surtitre` (l'ancien sur-titre « JOUR 01 ») vers
       `sous_titre`, qui est libre sur ce rendu.
    """
    Bloc = apps.get_model("pages", "Bloc")

    # --- 1. Fusion INFOS + CARTE_LEAFLET ------------------------------------
    # On parcourt page par page, dans l'ordre d'affichage, pour reperer les
    # paires adjacentes. / Page by page, in display order, to spot pairs.
    uuids_des_blocs_infos_absorbes = []

    identifiants_de_pages = (
        Bloc.objects.filter(type_bloc__in=["INFOS", "CARTE_LEAFLET"])
        .values_list("page_id", flat=True)
        .distinct()
    )

    for identifiant_de_page in identifiants_de_pages:
        blocs_de_la_page = list(
            Bloc.objects.filter(page_id=identifiant_de_page).order_by("position")
        )

        for rang, bloc_courant in enumerate(blocs_de_la_page):
            if bloc_courant.type_bloc != "INFOS":
                continue

            bloc_suivant = (
                blocs_de_la_page[rang + 1] if rang + 1 < len(blocs_de_la_page) else None
            )
            suivant_est_une_carte = (
                bloc_suivant is not None and bloc_suivant.type_bloc == "CARTE_LEAFLET"
            )

            if not suivant_est_une_carte:
                # INFOS orphelin : il devient un LIEU a lui tout seul.
                # / Orphan INFOS: becomes a LIEU on its own.
                continue

            # La carte recupere le contenu structure du bloc INFOS, et prend sa
            # position (le LIEU s'affiche la ou commencait le couple).
            # / The map takes the INFOS structured content and its position.
            bloc_suivant.contenu = bloc_courant.contenu
            bloc_suivant.position = bloc_courant.position
            bloc_suivant.save(update_fields=["contenu", "position"])
            uuids_des_blocs_infos_absorbes.append(bloc_courant.uuid)

    if uuids_des_blocs_infos_absorbes:
        Bloc.objects.filter(uuid__in=uuids_des_blocs_infos_absorbes).delete()

    # --- 2. La source des blocs LISTE, AVANT de perdre l'ancien type --------
    # EVENEMENTS et LISTE_SOUS_PAGES deviennent tous les deux LISTE : c'est le
    # champ `source` qui garde la difference. Il DOIT etre pose avant la
    # conversion generique, sinon les deux anciens types deviennent
    # indiscernables et toutes les listes afficheraient la meme chose.
    # / EVENEMENTS and LISTE_SOUS_PAGES both become LISTE: `source` keeps them
    # apart and MUST be set before the generic conversion erases the old type.
    Bloc.objects.filter(type_bloc="EVENEMENTS").update(source="EVENEMENTS")
    Bloc.objects.filter(type_bloc="LISTE_SOUS_PAGES").update(source="SOUS_PAGES")

    # --- 3. Conversion type par type ----------------------------------------
    for ancien_type, (nouveau_type, affichage) in CORRESPONDANCE_DES_TYPES.items():
        blocs_a_convertir = Bloc.objects.filter(type_bloc=ancien_type)

        if affichage is not None:
            blocs_a_convertir.update(type_bloc=nouveau_type, affichage=affichage)
            continue

        # Cas ou l'affichage depend d'un ancien champ : un par un.
        # / Cases where the affichage depends on an old field: one by one.
        for bloc in blocs_a_convertir:
            if ancien_type == "IMAGE_TEXTE":
                image_a_droite = bloc.image_position == "DROITE"
                bloc.affichage = (
                    "TEXTE_IMAGE_DROITE" if image_a_droite else "TEXTE_IMAGE_GAUCHE"
                )
            elif ancien_type == "IMAGE":
                en_vignette = bloc.affichage_image == "VIGNETTE_TITRE"
                bloc.affichage = "VIGNETTE_TITRE" if en_vignette else "PLEINE_LARGEUR"

            bloc.type_bloc = nouveau_type
            bloc.save(update_fields=["type_bloc", "affichage"])

    # --- 4. Le sur-titre des anciennes CARTE passe en sous-titre -------------
    # `surtitre` disparait ; sur le rendu CARTE, `sous_titre` etait inutilise.
    # / `surtitre` is going away; on the CARTE rendering `sous_titre` was free.
    for bloc in Bloc.objects.filter(type_bloc="SECTION", affichage="CARTE").exclude(surtitre=""):
        bloc.sous_titre = bloc.surtitre
        bloc.save(update_fields=["sous_titre"])


class Migration(migrations.Migration):

    # HORS TRANSACTION UNIQUE — obligatoire ici.
    # Cette migration mele du DDL (ajout de colonnes, dont une cle etrangere qui
    # cree un index) et du DML (les UPDATE/DELETE de la conversion). Postgres
    # refuse ce melange dans une seule transaction :
    #     OperationalError: cannot CREATE INDEX "pages_bloc" because it has
    #     pending trigger events
    # `atomic = False` laisse Django enchainer chaque operation dans sa propre
    # transaction. Contrepartie assumee : en cas d'echec au milieu, il n'y a pas
    # de rollback automatique — d'ou l'interet de relire l'etat des schemas.
    # / OUTSIDE A SINGLE TRANSACTION — required: this migration mixes DDL
    # (adding columns, incl. a FK that creates an index) and DML (the conversion
    # UPDATEs/DELETEs), which Postgres refuses in one transaction. Trade-off: no
    # automatic rollback if it fails midway.
    atomic = False

    dependencies = [
        ('pages', '0003_bloc_newsletter'),
    ]

    operations = [
        migrations.AddField(
            model_name='bloc',
            name='affichage',
            field=models.CharField(blank=True, choices=[('BANNIERE', "Bannière d'ouverture"), ('TEXTE_IMAGE_GAUCHE', 'Texte avec image à gauche'), ('TEXTE_IMAGE_DROITE', 'Texte avec image à droite'), ('TEXTE_VIDEO', 'Texte avec vidéo (fichier déposé)'), ('CARTE', 'Carte (se range en grille avec les cartes voisines)'), ('APPEL_ACTION', "Appel à l'action (boutons mis en avant)"), ('CITATION', 'Citation / témoignage signé'), ('PLEINE_LARGEUR', 'Photo pleine largeur'), ('VIGNETTE_TITRE', 'Vignette centrée (image-titre dessinée)'), ('GRILLE', 'Galerie en grille'), ('BANDE_LOGOS', 'Bande de logos cliquables'), ('VIDEO', 'Vidéo en ligne (YouTube / Vimeo / PeerTube)'), ('WIDGET', 'Formulaire ou widget (hôte autorisé par le ROOT)'), ('NEWSLETTER', 'Inscription newsletter (Ghost)')], help_text="Comment ce bloc s'affiche. Les choix dépendent du type de bloc.", max_length=20, verbose_name='Affichage'),
        ),
        migrations.AddField(
            model_name='bloc',
            name='page_source',
            field=models.ForeignKey(blank=True, help_text='Bloc Liste : la page dont on affiche les sous-pages. Vide = la page courante.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='blocs_qui_listent_mes_enfants', to='pages.page', verbose_name='Page à lister'),
        ),
        migrations.AddField(
            model_name='bloc',
            name='source',
            field=models.CharField(blank=True, choices=[('SOUS_PAGES', "Les sous-pages d'une page"), ('EVENEMENTS', "Les prochains évènements de l'agenda")], help_text="Bloc Liste : ce qu'on liste (les sous-pages d'une page, ou l'agenda).", max_length=20, verbose_name='Source de la liste'),
        ),
        migrations.AlterField(
            model_name='bloc',
            name='type_bloc',
            field=models.CharField(choices=[('TEXTE', 'Texte (article, paragraphe — écrit en Markdown)'), ('SECTION', "Section mise en avant (bannière, texte + média, carte, appel à l'action, citation)"), ('IMAGES', 'Images (une photo, une galerie, une bande de logos)'), ('INTEGRATION', 'Contenu intégré (vidéo en ligne, formulaire, newsletter)'), ('LIEU', 'Lieu (carte des points GPS + infos pratiques)'), ('FAQ', 'Question / réponse'), ('LISTE', 'Liste automatique (sous-pages ou prochains évènements)')], help_text="Choisit le gabarit du bloc. Les champs s'adaptent automatiquement.", max_length=20, verbose_name='Type de bloc'),
        ),
        migrations.RunPython(
            convertir_les_blocs_vers_le_catalogue_a_sept_types,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
