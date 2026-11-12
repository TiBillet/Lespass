"""
Observatoire des instances : la page de l'admin, en LECTURE SEULE.
/ Instance observatory: the admin page, READ-ONLY.

LOCALISATION : seo/views_observatoire.py

ROUTE : GET /admin/observatoire/, ajoutee par StaffAdminSite.get_urls()
(Administration/admin/site.py). Lien dans le menu « Root Configuration »
(Administration/admin/dashboard.py).

CE QUE FAIT CETTE VUE
Elle lit le dernier calcul dans SEOCache et l'affiche. Elle ne lance JAMAIS le
calcul : seuls le beat Celery et `manage.py refresh_observatoire` le font. Un
clic repete ne peut donc pas charger le serveur.
/ Reads the last computation from SEOCache and shows it. Never computes.

QUI PEUT LA VOIR : le superadmin seulement. Deux controles, l'un apres l'autre :
1. admin_view() (StaffAdminSite.has_permission) : admin du lieu ou superadmin ;
2. RootPermissionWithRequest, ICI : superadmin seulement.
Le premier ne suffit pas : un admin de lieu le passe. `is_staff` n'est lu nulle part.
/ Superadmin only: admin_view lets any venue admin in, so the check below is required.

FLUX :
1. GET seulement, sinon 405.
2. Pas superadmin : 403.
3. Lecture de SEOCache(OBSERVATOIRE). Un cache absent ou d'un format inconnu
   vaut « aucun calcul ».
4. Rendu de seo/observatoire.html, avec les textes traduits pour le JS
   (seo/static/seo/observatoire.js, via json_script).
"""

from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext

from ApiBillet.permissions import RootPermissionWithRequest
from Customers.models import Client
from seo.models import SEOCache
from seo.observatoire import CATEGORIES_D_ASSET_EN_EUROS


def textes_de_la_page():
    """
    Les textes affiches par le JS, traduits dans la langue de la requete.
    Le projet n'a pas de catalogue JavaScript : le JS n'ecrit aucun texte, il lit
    ce dictionnaire. Les marqueurs {nom} sont remplis par le JS (fonction texte()).
    / Texts shown by the JS, translated. The JS fills the {name} markers.
    """
    _ = gettext
    return {
        # Synthese / Summary
        "tuile_instances": _("Instances"),
        "tuile_instances_detail": _("créées depuis {annee}"),
        "tuile_actives": _("Vraiment actives"),
        "tuile_actives_detail": _("dont {nombre} très actives"),
        "tuile_peu_utilisees": _("Peu utilisées"),
        "tuile_peu_utilisees_detail": _("un usage réel, mais faible"),
        # Methodes de calcul des tuiles de la synthese (bulle « ? »). Les {marqueurs}
        # sont les seuils de classement EN COURS : la bulle suit les reglages.
        # / Methods of the summary tiles ("?" bubble), filled with the CURRENT thresholds.
        "aide_methode": _("Méthode de calcul"),
        "aide_usage_reel": _(
            "Un mois d'« usage réel » : au moins 10 inscriptions, 200 € de CA, 5 adhésions ou 200 € de recharges dans le mois."
        ),
        "methode_instances": _(
            "Lieux lus par le dernier calcul (sans le lieu racine ni les emplacements en attente). « Créées depuis » : la plus ancienne année de création."
        ),
        "methode_actives": _(
            "Très actif + actif. Actif : au moins {actif_ca} € de CA ou {actif_inscriptions} inscriptions sur 12 mois. Très actif : en plus, au moins {tres_actif_mois} mois d'usage réel sur 12. Seuils réglables plus bas."
        ),
        "methode_peu_utilisees": _(
            "Au moins un mois d'usage réel sur 12, sans atteindre le seuil « Actif » ({actif_ca} € de CA ou {actif_inscriptions} inscriptions sur 12 mois). Même valeur que « peu utilisé » dans le niveau d'activité."
        ),
        "methode_sommeil": _(
            "Aucun mois d'usage réel sur 12. Bidouillage : des événements créés ou au moins {bidouillage_connexions} connexions admin quand même. Sommeil : rien. Les abandons comptent aussi en sommeil."
        ),
        "methode_abandons": _(
            "Au plus {abandon_mois} mois d'usage réel en tout, plus rien depuis {abandon_silence} mois, moins de {abandon_ca} € de CA sur toute la période, et pas de retour à la même saison un an plus tard."
        ),
        "methode_ca": _(
            "Chiffre d'affaires TTC des tickets Z de Lespass (clôtures mensuelles, puis journalières du mois en cours), sur les 12 derniers mois, tous lieux. Hors ventes de caisse des lieux encore sur LaBoutik V1 : elles arriveront avec l'import."
        ),
        "methode_recharges": _(
            "Recharges encaissées lues dans les clôtures, sur les 12 derniers mois. En ligne = payées par Stripe. Ce n'est pas le total du bloc « depuis le début », qui lit Fedow legacy."
        ),
        "methode_cartes": _(
            "Meilleur mois des 12 derniers : cartes distinctes ayant servi dans le mois, moteur Fedow V2 seulement (migration en cours)."
        ),
        "tuile_sommeil": _("En sommeil ou bidouillage"),
        "tuile_sommeil_detail": _("{nombre} avec un admin qui bidouille"),
        "tuile_abandons": _("Testées puis abandonnées"),
        "tuile_abandons_detail": _("vrai usage, puis rien depuis {mois} mois"),
        "tuile_ca": _("CA sur 12 mois"),
        "tuile_ca_detail": _("billetterie, adhésions, caisse"),
        "tuile_recharges": _("Recharges sur 12 mois"),
        "tuile_recharges_detail": _("{pourcentage} % en ligne"),
        "tuile_cartes": _("Cartes NFC actives"),
        "tuile_cartes_detail": _("meilleur mois : {mois}"),
        # Qualification / Qualification
        "total": _("Total"),
        "matrice_case": _("{nombre} instances, taille {taille}, nature {nature}"),
        "legende_nature": _(
            "Taille = CA des 12 derniers mois. « Ponctuel » : activité concentrée "
            "qui ne revient pas l'année suivante."
        ),
        "encart_abandon": _(
            "{nombre} instances testées puis abandonnées : au plus {mois_max} mois "
            "d'usage réel, puis plus rien depuis {silence} mois, sans retour à la "
            "même saison. Les 24 mois évitent de confondre un festival en "
            "intersaison avec un abandon : {festivals} festivals reviennent bien "
            "d'une année sur l'autre."
        ),
        # Seuils / Thresholds
        "seuil_actifCA": _("Actif : CA 12 mois d'au moins (€)"),
        "seuil_actifInscr": _("… ou au moins N inscriptions sur 12 mois"),
        "seuil_tresActifMois": _("Très actif : au moins N mois d'usage réel sur 12"),
        "seuil_bidouillageCnx": _(
            "Bidouillage : au moins N connexions admin sans usage réel"
        ),
        "seuil_petitMax": _("Petit : CA 12 mois inférieur à (€)"),
        "seuil_moyenMax": _("Moyen : CA 12 mois inférieur à (€)"),
        "seuil_festivalConcentration": _(
            "Festival : part du CA sur 2 mois consécutifs ≥ (%)"
        ),
        "seuil_mixtePic": _("Mixte : meilleur mois ≥ N × le mois médian"),
        "seuil_adhesionsPart": _("Adhésions : part des adhésions dans le CA ≥ (%)"),
        "seuil_abandonSilence": _("Abandon : plus d'usage réel depuis N mois"),
        "seuil_abandonMoisMax": _("Abandon : au plus N mois d'usage réel en tout"),
        "seuil_abandonCAMax": _("Abandon : CA total inférieur à (€)"),
        "seuil_baisse": _("En baisse : CA 12 mois sous N % de l'année d'avant"),
        # Explorateur / Explorer
        "graphique_sans_historique": _(
            "Indicateur sans historique mensuel : choisis « Moyenne par groupe », "
            "« Classement » ou « Nuage »."
        ),
        "graphique_annee_precedente": _(
            "En clair : l'année précédente, pour comparaison"
        ),
        "graphique_equivalent_texte": _(
            "Graphique de l'indicateur « {indicateur} » pour {nombre} instances. "
            "Les valeurs de chaque instance sont dans la liste ci-dessous."
        ),
        "periode_meilleur_mois": _("meilleur mois sur 12"),
        "periode_valeur_actuelle": _("valeur actuelle"),
        "periode_12_mois": _("12 derniers mois"),
        "unite_par_instance": _("{unite} par instance"),
        "unite_par_instance_periode": _("{unite} par instance ({periode})"),
        "moyenne_par_instance_de": _("{indicateur}, moyenne par instance"),
        "classement_titre": _(
            "{nombre} instances avec une valeur non nulle ({periode}) · couleur = nature"
        ),
        "classement_titre_120": _(
            "{nombre} instances avec une valeur non nulle ({periode}), 120 premières "
            "· couleur = nature"
        ),
        "selection_nombre": _("{nombre} instances dans la sélection"),
        "selection_case": _("case {taille} × {nature}"),
        "fiche_source": _("Où se trouve la donnée"),
        "fiche_axe_vertical": _("Axe vertical : {indicateur}"),
        # Liste / List
        "nombre_d_instances": _("{nombre} instances"),
        "colonne_nom": _("Instance"),
        "colonne_nature": _("Nature"),
        "colonne_taille": _("Taille"),
        "colonne_activite": _("Activité"),
        "colonne_tendance": _("Tendance"),
        "colonne_reels12": _("Mois d'usage (12)"),
        "colonne_ca12": _("CA 12 mois"),
        "colonne_rech": _("Recharges"),
        "colonne_cartes": _("Cartes (pic)"),
        "colonne_cnx": _("Connexions admin"),
        "colonne_cat": _("Catégorie déclarée"),
        "colonne_mois": _("Mois"),
        "colonne_instances": _("Instances"),
        "colonne_part": _("Part"),
        "colonne_part_du_total": _("Part du total"),
        "colonne_rang": _("Rang"),
        "pastille_abandon": _("abandon"),
        "pastille_ecart": _("écart"),
        # Sur mesure : groupes et choix / Custom: groups and choices
        "groupe_nature": _("Nature"),
        "groupe_activite": _("Activité"),
        "groupe_taille": _("Taille"),
        "groupe_categorie": _("Catégorie déclarée"),
        "groupe_instances": _("Instances"),
        "groupe_composantes": _("Composantes"),
        "exemples": _("Exemples :"),
        "exemple_cartes_ca": _("Cartes actives selon le CA"),
        "exemple_ca_nature": _("CA moyen par mois, selon la nature"),
        "exemple_recharges": _("Recharges en ligne contre sur place"),
        "exemple_scans": _("Les plus grands publics"),
        "exemple_repartition_nature": _("Répartition du CA par nature"),
        "exemple_composantes": _("D'où vient le CA"),
        "exemple_instances_utilisees": _("Instances utilisées, mois par mois"),
        "periode_12": _("les 12 derniers mois"),
        "periode_prec": _("les 12 mois précédents"),
        "periode_tout": _("toute la période"),
        "periode_n_mois": _("les {nombre} mois"),
        "calcul_total": _("le total"),
        "calcul_moyenne": _("la moyenne par instance"),
        "calcul_mediane": _("la médiane par instance"),
        "calcul_libelle_total": _("Total"),
        "calcul_libelle_moyenne": _("Moyenne par instance"),
        "calcul_libelle_mediane": _("Médiane par instance"),
        "calcul_sans_objet": _(
            "Sans objet pour un classement : chaque instance a sa propre valeur."
        ),
        "vue_mois": _("mois par mois"),
        "vue_nature": _("par nature"),
        "vue_activite": _("par niveau d'activité"),
        "vue_taille": _("par taille"),
        "vue_categorie": _("par catégorie déclarée"),
        "vue_classement": _("instance par instance"),
        "distinguer_aucune": _("sans distinction"),
        "distinguer_nature": _("en distinguant la nature"),
        "distinguer_activite": _("en distinguant l'activité"),
        "distinguer_taille": _("en distinguant la taille"),
        "couleur_nature": _("couleur selon la nature"),
        "couleur_activite": _("couleur selon l'activité"),
        "couleur_taille": _("couleur selon la taille"),
        "couleur_aucune": _("sans couleur"),
        "decoupe_nature": _("la nature"),
        "decoupe_activite": _("l'activité"),
        "decoupe_taille": _("la taille"),
        "decoupe_categorie": _("la catégorie déclarée"),
        "decoupe_instances": _("les instances"),
        "decoupe_composantes": _("ses composantes"),
        "nom_periode": _("Période"),
        "nom_calcul": _("Calcul"),
        "nom_indicateur": _("Indicateur"),
        "nom_decoupage": _("Découpage"),
        "nom_distinction": _("Distinction"),
        "nom_premier_indicateur": _("Premier indicateur"),
        "nom_second_indicateur": _("Second indicateur"),
        "nom_couleur": _("Couleur"),
        "nom_indicateur_a_decouper": _("Indicateur à découper"),
        "phrase_suivre": _(
            "Je veux voir {calcul} pour {indicateur} {vue} sur {periode}, {distinction}."
        ),
        "phrase_croiser": _(
            "Je veux voir le lien entre {premier} et {second}, instance par instance, "
            "sur {periode}, {couleur}."
        ),
        "phrase_repartir": _(
            "Je veux découper {indicateur} selon {decoupe} sur {periode}."
        ),
        "aide_suivre": _(
            "« Instance par instance » donne un classement. « En distinguant » trace "
            "une courbe ou une barre par valeur."
        ),
        "aide_croiser": _(
            "Le premier indicateur se lit en hauteur, le second en largeur. Chaque "
            "pastille est une instance."
        ),
        "aide_repartir": _(
            "« Ses composantes » découpe le chiffre d'affaires en billetterie, "
            "adhésions et caisse, et les recharges en ligne et sur place."
        ),
        "champ_axe_vertical": _("Axe vertical"),
        "champ_indicateur_a_repartir": _("Indicateur à répartir"),
        "champ_indicateur": _("Indicateur"),
        "champ_decouper_selon": _("Découper selon"),
        "champ_regrouper_par": _("Regrouper par"),
        "champ_une_courbe_par": _("Une courbe par"),
        "champ_une_barre_par": _("Une barre par"),
        "champ_couleur": _("Couleur"),
        # Lecture des graphiques / Chart reading
        "lien_aucun": _("pas de lien net"),
        "lien_faible": _("un lien faible"),
        "lien_modere": _("un lien modéré"),
        "lien_fort": _("un lien fort"),
        "lien_meme_sens": _(" : les deux augmentent ensemble"),
        "lien_sens_inverse": _(" : quand l'un augmente, l'autre baisse"),
        "lien_phrase": _(
            "On observe {force} (corrélation de rang {correlation}){sens}."
        ),
        "composante_billetterie": _("Billetterie"),
        "composante_adhesions": _("Adhésions"),
        "composante_caisse": _("Caisse"),
        "composante_en_ligne": _("En ligne"),
        "composante_sur_place": _("Sur place"),
        "autres_instances": _("Autres ({nombre} instances)"),
        "autres": _("Autres ({nombre})"),
        "au_total": _("au total"),
        "par_instance_meilleur_mois": _("meilleur mois"),
        "par_instance_valeur_actuelle": _("valeur actuelle"),
        "par_instance_total": _("total"),
        "lecture_nuage": _(
            "Axe vertical : {vertical}. Axe horizontal : {horizontal}. Période : "
            "{periode}. {nombre} instances, une pastille par instance{couleur}."
        ),
        "lecture_couleur": _(" (couleur : {groupe})"),
        "lecture_mois": _(
            "{indicateur}, mois par mois, sur {periode}. {calcul}{zeros}{courbes}."
        ),
        "lecture_zeros_exclus_du_mois": _(" (instances à zéro ce mois-là exclues)"),
        "lecture_une_courbe_par": _(". Une courbe par valeur de « {groupe} »"),
        "lecture_groupe": _(
            "{indicateur} ({valeur} sur {periode}) regroupé par « {groupe} ». "
            "{calcul}{zeros}{barres}. Le nombre d'instances du groupe est entre "
            "parenthèses."
        ),
        "lecture_zeros_exclus": _(", instances à zéro exclues"),
        "lecture_une_barre_par": _(". Une barre par valeur de « {groupe} »"),
        "anneau_sans_composantes": _(
            "{indicateur} n'a pas de composantes. Les composantes existent pour le "
            "chiffre d'affaires (billetterie, adhésions, caisse) et pour les recharges "
            "(en ligne, sur place)."
        ),
        "anneau_vide": _(
            "Rien à répartir : {indicateur} vaut 0 pour les instances choisies, sur "
            "{periode}."
        ),
        "lecture_anneau": _(
            "Indicateur réparti : {indicateur} ({valeur} sur {periode}{additionne}) "
            "selon {decoupe}. {nombre} parts. La plus grande, {part}, pèse "
            "{pourcentage} %{autres}."
        ),
        "lecture_additionne": _(", additionné entre instances"),
        "lecture_autres": _(". « Autres » regroupe les plus petites parts"),
        "lecture_classement": _(
            "Classement des instances par {indicateur} ({valeur} sur {periode}). "
            "{nombre} instances{limite}{couleur}."
        ),
        "lecture_150_premieres": _(", les 150 premières affichées"),
        "titre_repartition": _("Répartition : {indicateur}"),
        "titre_selon": _("{indicateur} selon {autre}"),
        "titre_mois_par_mois": _("{indicateur}, mois par mois"),
        "titre_par_groupe": _("{indicateur} par {groupe}"),
        "titre_classement": _("Classement : {indicateur}"),
        "voir_les_donnees": _("Voir les données du graphique ({nombre} lignes)"),
    }


def indicateurs_de_la_page():
    """
    Le libelle, l'unite, la definition et la source de chaque indicateur.
    L'unite « € » n'est pas traduite : le JS s'en sert pour formater les montants.
    / Label, unit, definition and source of each indicator.
    """
    _ = gettext
    source_des_clotures = _(
        "Clôtures comptables du lieu (mensuelles, puis journalières du mois en cours)"
    )
    return {
        "ca_total": {
            "libelle": _("Chiffre d'affaires"),
            "avec_article": _("le chiffre d'affaires"),
            "unite": "€",
            "definition": _(
                "Chiffre d'affaires TTC des tickets Z : ventes moins avoirs, sans les recharges."
            ),
            "source": source_des_clotures,
        },
        "ca_billetterie": {
            "libelle": _("CA billetterie"),
            "avec_article": _("le CA billetterie"),
            "unite": "€",
            "definition": _("Articles reliés à une réservation."),
            "source": source_des_clotures,
        },
        "ca_adhesions": {
            "libelle": _("CA adhésions"),
            "avec_article": _("le CA adhésions"),
            "unite": "€",
            "definition": _("Articles reliés à une adhésion."),
            "source": source_des_clotures,
        },
        "ca_caisse": {
            "libelle": _("CA caisse"),
            "avec_article": _("le CA caisse"),
            "unite": "€",
            "definition": _(
                "Ventes faites à la caisse LaBoutik, toutes méthodes. Un avoir fait depuis l'admin n'en est pas déduit."
            ),
            "source": source_des_clotures,
        },
        "recharges": {
            "libelle": _("Recharges cashless"),
            "avec_article": _("les recharges cashless"),
            "unite": "€",
            "definition": _("Argent chargé sur les cartes, en ligne et sur place."),
            "source": source_des_clotures,
        },
        "recharges_ligne": {
            "libelle": _("Recharges en ligne"),
            "avec_article": _("les recharges en ligne"),
            "unite": "€",
            "definition": _("Recharges payées par Stripe."),
            "source": source_des_clotures,
        },
        "recharges_place": {
            "libelle": _("Recharges sur place"),
            "avec_article": _("les recharges sur place"),
            "unite": "€",
            "definition": _("Recharges encaissées par le lieu à son point de vente."),
            "source": source_des_clotures,
        },
        "cartes_actives": {
            "libelle": _("Cartes NFC actives"),
            "avec_article": _("les cartes NFC actives"),
            "unite": _("cartes"),
            "definition": _(
                "Cartes distinctes ayant servi au moins une fois dans le mois. Par instance : le meilleur mois."
            ),
            "source": _(
                "Moteur Fedow V2 interne (fedow_core). En cours de migration : beaucoup de données sont encore dans le Fedow legacy."
            ),
        },
        "connexions_admin": {
            "libelle": _("Connexions admin"),
            "avec_article": _("les connexions admin"),
            "unite": _("connexions"),
            "definition": _("Ouvertures de session d'un compte admin du lieu."),
            "source": _(
                "Aucune pour l'instant : la donnée n'est pas encore enregistrée."
            ),
        },
        "evenements": {
            "libelle": _("Événements"),
            "avec_article": _("les événements"),
            "unite": _("événements"),
            "definition": _("Événements dont la date tombe dans le mois."),
            "source": _("Événements du lieu"),
        },
        "inscriptions": {
            "libelle": _("Inscriptions"),
            "avec_article": _("les inscriptions"),
            "unite": _("billets"),
            "definition": _("Billets vendus dans le mois, gratuits compris."),
            "source": source_des_clotures,
        },
        "billets_scannes": {
            "libelle": _("Billets scannés"),
            "avec_article": _("les billets scannés"),
            "unite": _("billets"),
            "definition": _(
                "Billets contrôlés à l'entrée : la fréquentation réelle. Rangés au mois de l'événement."
            ),
            "source": _("Billets du lieu, statut scanné"),
        },
        "adhesions": {
            "libelle": _("Adhésions"),
            "avec_article": _("les adhésions"),
            "unite": _("adhésions"),
            "definition": _("Adhésions vendues dans le mois."),
            "source": source_des_clotures,
        },
        "usagers": {
            "libelle": _("Usagers distincts"),
            "avec_article": _("les usagers distincts"),
            "unite": _("personnes"),
            "definition": _(
                "Clients distincts des ventes réglées du mois. Par instance : le meilleur mois."
            ),
            "source": _("Ventes du lieu"),
        },
        "reel": {
            "libelle": _("Instances utilisées"),
            "avec_article": _("les instances utilisées"),
            "unite": _("instances"),
            "definition": _(
                "Instances avec un usage réel dans le mois (10 inscriptions, 200 €, 5 adhésions ou 200 € de recharges). Par instance : nombre de mois d'usage réel."
            ),
            "source": _("Calculé à partir des indicateurs ci-dessus"),
        },
        "pdv": {
            "libelle": _("Points de vente"),
            "avec_article": _("les points de vente"),
            "unite": _("points de vente"),
            "definition": _("Points de vente configurés dans la caisse."),
            "source": _("Caisse LaBoutik du lieu"),
        },
        "admins": {
            "libelle": _("Comptes admin"),
            "avec_article": _("les comptes admin"),
            "unite": _("comptes"),
            "definition": _("Personnes ayant les droits d'admin sur le lieu."),
            "source": _("Comptes du réseau (schéma public)"),
        },
    }


def libelles_de_la_page():
    """
    Les libelles des natures, activites, tailles, tendances et categories.
    Le JS travaille avec des cles ASCII (tres_actif...) et affiche ces libelles.
    / Labels of natures, activity levels, sizes, trends and categories.
    """
    _ = gettext
    libelles_des_categories = {}
    for code_de_la_categorie, libelle_de_la_categorie in Client.CATEGORIE_CHOICES:
        libelles_des_categories[code_de_la_categorie] = str(libelle_de_la_categorie)
    return {
        "natures": {
            "festival": _("festival"),
            "mixte": _("mixte"),
            "lieu": _("lieu"),
            "adhesions": _("adhésions"),
            "ponctuel": _("ponctuel"),
            "indetermine": _("indéterminé"),
        },
        "activites": {
            "tres_actif": _("très actif"),
            "actif": _("actif"),
            "peu_utilise": _("peu utilisé"),
            "bidouillage": _("bidouillage"),
            "sommeil": _("sommeil"),
        },
        "tailles": {"petit": _("petit"), "moyen": _("moyen"), "gros": _("gros")},
        "tendances": {
            "nouveau": _("nouveau"),
            "en_baisse": _("en baisse"),
            "en_hausse": _("en hausse"),
            "stable": _("stable"),
        },
        "categories": libelles_des_categories,
    }


def lire_le_dernier_calcul():
    """
    Le dernier calcul rangé dans SEOCache, ou None s'il n'y en a pas encore.
    Seule la commande refresh_observatoire ecrit cette ligne. Lecture seule.
    / The last stored computation, or None. Only the command writes it. Read-only.
    """
    ligne_du_cache = SEOCache.objects.filter(
        cache_type=SEOCache.OBSERVATOIRE,
        tenant__isnull=True,
    ).first()
    if ligne_du_cache is None:
        return None
    return ligne_du_cache.data


def page_observatoire(request):
    """
    La page de l'observatoire, dans le cadre de l'admin Unfold.
    / The observatory page, inside the Unfold admin frame.

    :param request: HttpRequest Django (deja passee par admin_view)
    :return: HttpResponse (200), 403 si pas superadmin, 405 si pas GET
    """
    # 1. Lecture seule : aucune autre methode que GET.
    # / 1. Read-only: GET only.
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    # 2. INDISPENSABLE : admin_view() laisse passer tout admin du lieu. Les chiffres
    # de tout le reseau sont reserves au superadmin.
    # / 2. MANDATORY: admin_view() lets any venue admin in. Network figures are
    #      superadmin only.
    if not RootPermissionWithRequest(request):
        return HttpResponseForbidden(gettext("Page réservée au superadmin."))

    # 3. Le dernier calcul, et sa date lisible.
    # / 3. The last computation, and its readable date.
    calcul = lire_le_dernier_calcul()
    date_du_calcul = None
    jours_depuis_le_calcul = None
    if calcul is not None:
        date_du_calcul = parse_datetime(calcul.get("calcule_le") or "")
        if date_du_calcul is not None:
            if timezone.is_naive(date_du_calcul):
                date_du_calcul = timezone.make_aware(date_du_calcul)
            jours_depuis_le_calcul = (
                timezone.localdate() - timezone.localtime(date_du_calcul).date()
            ).days

    # 4. Le bloc « Le reseau depuis le debut » : les montants passent de centimes a
    # unites, et les recharges des deux moteurs forment une seule liste, la plus
    # grosse en tete. Absent d'un calcul plus ancien : le bloc n'est pas affiche.
    # / 4. The "since the beginning" block: cents to units, one sorted list.
    reseau = None
    total_des_recharges_en_euros = 0
    recharges_par_asset = []
    if calcul is not None and calcul.get("reseau"):
        reseau = calcul["reseau"]
        total_des_recharges_en_euros = (
            reseau.get("total_des_recharges_en_centimes", 0) / 100
        )
        for moteur, cle_des_recharges in [
            ("Fedow legacy", "recharges_legacy"),
            ("V2", "recharges_v2"),
        ]:
            for recharge in reseau.get(cle_des_recharges) or []:
                est_en_euros = recharge.get("categorie") in CATEGORIES_D_ASSET_EN_EUROS
                recharges_par_asset.append(
                    {
                        **recharge,
                        "moteur": moteur,
                        "total_affiche": (recharge.get("total") or 0) / 100,
                        "unite": "€" if est_en_euros else recharge.get("devise", ""),
                    }
                )
        recharges_par_asset.sort(
            key=lambda recharge: recharge["total_affiche"], reverse=True
        )

    # 5. Rendu. `donnees_observatoire` part au JS par json_script.
    # / 4. Render. `donnees_observatoire` goes to the JS via json_script.
    from Administration.admin.site import staff_admin_site

    contexte = {
        **staff_admin_site.each_context(request),
        "title": gettext("Observatoire des instances"),
        "calcul": calcul,
        "date_du_calcul": date_du_calcul,
        "jours_depuis_le_calcul": jours_depuis_le_calcul,
        "reseau": reseau,
        "total_des_recharges_en_euros": total_des_recharges_en_euros,
        "recharges_par_asset": recharges_par_asset,
        "donnees_observatoire": {
            "calcul": calcul,
            "textes": textes_de_la_page(),
            "indicateurs": indicateurs_de_la_page(),
            "libelles": libelles_de_la_page(),
        },
    }
    reponse = render(request, "seo/observatoire.html", contexte)
    # Des chiffres internes : jamais gardes par un cache (navigateur ou proxy).
    # / Internal figures: never kept by any cache.
    reponse["Cache-Control"] = "no-store"
    return reponse
