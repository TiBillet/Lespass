"""
Les clôtures du lieu : la journée glissante (J), le filet automatique, les clôtures
semaine, mois et année, et l'email de clôture.
/ The venue's closures: the sliding day (J), the automatic safety net, the week, month
and year closures, and the closure email.

LOCALISATION : comptabilite/tasks.py

LES RÈGLES (fiche F §3 ; tronc D19, D28)
- J demandée (le « Z de fin de service » : bouton, commande) : de la fin de la J
  précédente au moment de la clôture. La première J d'un lieu commence à sa première
  vente réglée. Sans vente réglée dans la plage, aucune J n'est créée. La fin de la J
  est fixée sous le verrou du lieu des ventes (court) : aucune vente ne s'encaisse
  pendant qu'on fixe sa plage. Le rapport est calculé hors verrou ; la clôture est
  numérotée sous le verrou des clôtures du lieu, et deux appels ne créent jamais deux J.
- Le filet (tâche horaire) fait le Z que personne n'a fait : le seuil du jour est
  l'heure de fermeture du lieu + 2 h, en heure locale (`Configuration.heure_de_fermeture`,
  `Configuration.fuseau_horaire`) ; avant ce seuil, c'est le seuil de la veille. Le
  filet crée la J [fin de la dernière J, seuil[ si la dernière J finit avant le seuil
  courant (ou n'existe pas) et qu'il y a une vente dans cette plage. La J du filet FINIT
  AU SEUIL : les ventes d'après le seuil sont du service suivant, elles attendent la J
  suivante (un service n'est jamais coupé en deux). Jamais une égalité d'heure : une
  tâche manquée est rattrapée à l'heure suivante. Le seuil est comparé en UTC (les nuits
  de changement d'heure).
- H, M, A : la semaine (lundi-dimanche), le mois, l'année, en heure locale du lieu.
  Calculés sur les ventes de la période, jamais comme la somme des J. Une période sans
  aucune vente n'a pas de clôture. Une période déjà clôturée ne l'est pas deux fois
  (unicité `(niveau, début, fin)`). Un lieu qui change de fuseau peut créer une seconde
  M du même mois (bornes différentes) : rare, accepté.
  Une période n'est clôturée qu'APRÈS LE FILET DU JOUR OÙ ELLE FINIT (le seuil de ce
  jour-là) : la J de la dernière soirée de la période, qui finit à ce seuil, est créée
  avant elle, et la période porte les perpétuels de cette J.
  La tâche horaire crée TOUTES les périodes finies qui manquent depuis la dernière
  clôture du niveau (sinon depuis la première vente du lieu), dans l'ordre
  chronologique : une tâche arrêtée plusieurs semaines rattrape tout au premier passage.
- Le rapport stocké (`rapport_json`) = `RapportDesVentes(debut, fin)` (toutes les
  sections), plus dans l'en-tête : niveau, numéro de clôture, perpétuels. Les sections
  « caisse espèces » et « intégrité » ne sont stockées que dans une J : un fond de
  caisse n'a de sens que pour une journée, et chaque J a déjà vérifié la chaîne des
  ventes de sa plage (une année la revérifierait vente par vente).
- Perpétuels : J = ceux de la J précédente + cette J ; H / M / A = ceux de la dernière J.
- Une seule chaîne de clôtures, tous niveaux (`comptabilite/integrite.py`).
/ Rules: sliding J under the venue lock; hourly net at closing time + 2 h, local
time; calendar H / M / A computed on sales, none when empty, after the net of their
last day, every missing one caught up; stored report; perpetual totals; one chain.

FLUX :
- `TiBillet/celery.py` `cron_clotures_automatiques` (chaque heure) →
  `generer_les_clotures_automatiques` → une sous-tâche Celery par lieu
  `generer_les_clotures_automatiques_du_lieu.delay(schema)` ;
- la commande `generer_cloture` → `generer_cloture_pour_tenant`.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-F-rapport-unique.md (§3).
Tests : tests/pytest/test_cloture_unique.py
"""
import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from celery import shared_task
from django.db import connection, transaction
from django.db.models import Min
from django.utils import timezone
from django_tenants.utils import tenant_context

from BaseBillet.models import Configuration
from BaseBillet.models_vente import Vente

# Import au niveau module pour que les tests puissent le mocker via
# patch("comptabilite.tasks.CeleryMailerClass").
# / Module-level import so tests can mock via patch("comptabilite.tasks.CeleryMailerClass").
from BaseBillet.tasks import CeleryMailerClass
from comptabilite.integrite import calculer_hmac_cloture
from comptabilite.models import ClotureCaisse
from comptabilite.presentation import euros_a_la_francaise
from comptabilite.rapport import RapportDesVentes
from Customers.models import Client
from laboutik.models import LaboutikConfiguration

logger = logging.getLogger(__name__)

# Le filet passe deux heures après l'heure de fermeture du lieu (tronc D28).
# / The safety net runs two hours after the venue's closing time.
DELAI_DU_FILET_APRES_LA_FERMETURE = timedelta(hours=2)

FUSEAU_UTC = ZoneInfo("UTC")

# Les niveaux calendaires, clôturés par la tâche horaire après la J.
# / Calendar levels, closed by the hourly task after the J.
NIVEAUX_CALENDAIRES = [
    ClotureCaisse.NIVEAU_HEBDOMADAIRE,
    ClotureCaisse.NIVEAU_MENSUEL,
    ClotureCaisse.NIVEAU_ANNUEL,
]


def _debut_du_jour(jour, fuseau_du_lieu):
    """
    Minuit (0 h) d'un jour, en heure locale du lieu.
    / Midnight of a day, in the venue's local time.
    """
    return datetime.combine(jour, time(0, 0), tzinfo=fuseau_du_lieu)


def _bornes_de_la_periode_qui_contient(niveau, jour, fuseau_du_lieu):
    """
    Les bornes (début, fin) de la semaine, du mois ou de l'année qui contient `jour`,
    en heure locale du lieu. La fin est exclue.
    / Bounds of the week, month or year containing `jour`, in local time. End excluded.

    H : [lundi de la semaine 0 h, lundi suivant 0 h[
    M : [1ᵉʳ du mois 0 h, 1ᵉʳ du mois suivant 0 h[
    A : [1ᵉʳ janvier 0 h, 1ᵉʳ janvier de l'année suivante 0 h[

    Les bornes sont construites à partir de dates (jour, mois, année), puis posées à
    minuit dans le fuseau du lieu : un changement d'heure dans la période ne décale
    rien.
    / Bounds are built from dates, then set at local midnight: DST changes shift nothing.

    :param niveau: "H", "M" ou "A"
    :param jour: une date (jour du calendrier du lieu)
    :param fuseau_du_lieu: le fuseau du lieu
    :return: (debut, fin), deux datetimes dans le fuseau du lieu
    """
    if niveau == ClotureCaisse.NIVEAU_HEBDOMADAIRE:
        lundi_de_la_semaine = jour - timedelta(days=jour.weekday())
        lundi_suivant = lundi_de_la_semaine + timedelta(days=7)
        return (
            _debut_du_jour(lundi_de_la_semaine, fuseau_du_lieu),
            _debut_du_jour(lundi_suivant, fuseau_du_lieu),
        )

    if niveau == ClotureCaisse.NIVEAU_MENSUEL:
        premier_du_mois = date(jour.year, jour.month, 1)
        if jour.month == 12:
            premier_du_mois_suivant = date(jour.year + 1, 1, 1)
        else:
            premier_du_mois_suivant = date(jour.year, jour.month + 1, 1)
        return (
            _debut_du_jour(premier_du_mois, fuseau_du_lieu),
            _debut_du_jour(premier_du_mois_suivant, fuseau_du_lieu),
        )

    if niveau == ClotureCaisse.NIVEAU_ANNUEL:
        premier_janvier_de_l_annee = date(jour.year, 1, 1)
        premier_janvier_de_l_annee_suivante = date(jour.year + 1, 1, 1)
        return (
            _debut_du_jour(premier_janvier_de_l_annee, fuseau_du_lieu),
            _debut_du_jour(premier_janvier_de_l_annee_suivante, fuseau_du_lieu),
        )

    raise ValueError(f"Niveau calendaire inconnu : {niveau}")


def _bornes_de_la_periode_precedente(niveau, maintenant_local):
    """
    Les bornes (début, fin) de la semaine, du mois ou de l'année qui précède
    `maintenant_local`, en heure locale du lieu : la période qui contient la veille du
    début de la période en cours. La fin est exclue.
    / Bounds of the previous week, month or year, in local time. End excluded.

    :param niveau: "H", "M" ou "A"
    :param maintenant_local: le moment présent, dans le fuseau du lieu
    :return: (debut, fin), deux datetimes dans le fuseau du lieu
    """
    fuseau_du_lieu = maintenant_local.tzinfo
    debut_de_la_periode_en_cours, _fin_de_la_periode_en_cours = (
        _bornes_de_la_periode_qui_contient(
            niveau, maintenant_local.date(), fuseau_du_lieu
        )
    )
    veille_du_debut = debut_de_la_periode_en_cours.date() - timedelta(days=1)
    return _bornes_de_la_periode_qui_contient(niveau, veille_du_debut, fuseau_du_lieu)


def _seuil_du_filet_d_un_jour(jour, fuseau_du_lieu, heure_de_fermeture):
    """
    Le seuil du filet d'un jour : l'heure de fermeture + 2 h, ce jour-là, en heure
    locale du lieu, rendu en UTC. L'heure du seuil repasse par minuit : fermeture
    02:00 → seuil à 4 h ; fermeture 23:00 → seuil à 1 h du même jour.
    Une heure qui n'existe pas (passage à l'heure d'été) prend le décalage d'avant le
    changement ; une heure qui existe deux fois (passage à l'heure d'hiver) est la
    première.
    / The net threshold of a day: closing time + 2 h, that day, local, returned in UTC.

    :param jour: une date (jour du calendrier du lieu)
    :param fuseau_du_lieu: le fuseau du lieu
    :param heure_de_fermeture: `Configuration.heure_de_fermeture` (une heure)
    :return: le seuil de ce jour, datetime en UTC
    """
    minutes_de_la_fermeture = heure_de_fermeture.hour * 60 + heure_de_fermeture.minute
    minutes_du_delai = int(DELAI_DU_FILET_APRES_LA_FERMETURE.total_seconds() // 60)
    minutes_du_seuil = (minutes_de_la_fermeture + minutes_du_delai) % (24 * 60)
    heure_du_seuil = time(minutes_du_seuil // 60, minutes_du_seuil % 60)
    return datetime.combine(jour, heure_du_seuil, tzinfo=fuseau_du_lieu).astimezone(
        FUSEAU_UTC
    )


def _filet_du_jour_de_la_fin_passe(fin, fuseau_du_lieu, heure_de_fermeture):
    """
    Vrai si le filet du jour où une période finit est passé : maintenant ≥ le seuil
    de ce jour-là (l'heure de fermeture + 2 h, en heure locale du lieu).
    Exemple : le mois d'avril finit le 1ᵉʳ mai à 0 h ; fermeture 02:00 → il est
    clôturable à partir du 1ᵉʳ mai à 4 h.
    C'est la contrainte qui donne à une H / M / A les bons perpétuels : la J de la
    dernière soirée de la période finit à ce seuil, et la tâche horaire la crée avant
    les H / M / A. Une H / M / A créée avant ce seuil prendrait les perpétuels de la J
    d'avant cette soirée.
    / True when the net of the period's last day has passed: an H / M / A then carries
    the perpetual totals of the J of its last evening.

    :param fin: la fin de la période (exclue), datetime avec fuseau
    :param fuseau_du_lieu: le fuseau du lieu
    :param heure_de_fermeture: `Configuration.heure_de_fermeture`
    """
    jour_de_la_fin = fin.astimezone(fuseau_du_lieu).date()
    seuil_du_jour_de_la_fin = _seuil_du_filet_d_un_jour(
        jour_de_la_fin, fuseau_du_lieu, heure_de_fermeture
    )
    maintenant_en_utc = timezone.now().astimezone(FUSEAU_UTC)
    return maintenant_en_utc >= seuil_du_jour_de_la_fin


def _seuil_courant_du_filet(maintenant_local, heure_de_fermeture):
    """
    Le seuil courant du filet : l'heure de fermeture + 2 h d'aujourd'hui, en heure
    locale du lieu ; avant ce seuil, celui de la veille.
    Exemple : fermeture 02:00 → seuil à 4 h ; à 3 h 30 le 11, le seuil courant est le
    10 à 4 h ; à 4 h 30 le 11, c'est le 11 à 4 h. Fermeture 23:00 → seuil à 1 h.
    / The current net threshold: today's closing time + 2 h, local; before it,
    yesterday's.

    LES COMPARAISONS SE FONT EN UTC. Python compare deux heures du MÊME fuseau à
    l'horloge, sans regarder le décalage : la nuit d'un changement d'heure, « 3 h CEST »
    serait vue après « 2 h 30 » alors que, en UTC, le seuil n'est pas encore atteint (et
    la J finirait dans le futur).
    / Comparisons are made in UTC: Python compares same-zone datetimes by wall clock,
    ignoring the offset, which is wrong on DST nights.

    :param maintenant_local: le moment présent, dans le fuseau du lieu
    :param heure_de_fermeture: `Configuration.heure_de_fermeture` (une heure)
    :return: le seuil courant, datetime en UTC
    """
    fuseau_du_lieu = maintenant_local.tzinfo
    maintenant_en_utc = maintenant_local.astimezone(FUSEAU_UTC)

    seuil_d_aujourd_hui_en_utc = _seuil_du_filet_d_un_jour(
        maintenant_local.date(), fuseau_du_lieu, heure_de_fermeture
    )
    if maintenant_en_utc >= seuil_d_aujourd_hui_en_utc:
        return seuil_d_aujourd_hui_en_utc

    veille = maintenant_local.date() - timedelta(days=1)
    return _seuil_du_filet_d_un_jour(veille, fuseau_du_lieu, heure_de_fermeture)


def _prendre_le_verrou_des_ventes_du_lieu():
    """
    Prend le verrou du lieu des ventes, le même que `encaisser_vente`
    (`BaseBillet/services_vente.py`) : tant qu'il est tenu, aucune vente ne
    s'encaisse. Il est relâché à la fin de la transaction : à appeler DANS
    `transaction.atomic()`, et à tenir le moins longtemps possible.
    / Takes the venue's sales lock (same as encaisser_vente), released at commit.
    """
    nom_du_verrou_du_lieu = f"vente-{connection.schema_name}"
    with connection.cursor() as curseur:
        curseur.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            [nom_du_verrou_du_lieu],
        )


def _prendre_le_verrou_des_clotures_du_lieu():
    """
    Prend le verrou des clôtures du lieu : deux clôtures (tous niveaux) ne lisent
    jamais le même dernier numéro ni la même empreinte précédente. Il ne bloque pas la
    caisse. Relâché à la fin de la transaction : à appeler DANS `transaction.atomic()`.
    / Takes the venue's closure lock (numbering and chaining); does not block sales.
    """
    nom_du_verrou_du_lieu = f"cloture-{connection.schema_name}"
    with connection.cursor() as curseur:
        curseur.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            [nom_du_verrou_du_lieu],
        )


def _ventes_reglees_entre(debut, fin):
    """
    Les ventes réglées de [debut, fin[, toutes natures, origines et unités : le même
    périmètre que le rapport des ventes.
    / Settled sales of [debut, fin[, same scope as the sales report.
    """
    return Vente.objects.filter(
        statut=Vente.Statut.REGLEE,
        datetime_encaissement__gte=debut,
        datetime_encaissement__lt=fin,
    )


def _enregistrer_la_cloture(
    niveau, debut, fin, sections_du_rapport, responsable=None, point_de_vente=None
):
    """
    Numérote, chaîne et enregistre une clôture. À appeler DANS une transaction, sous
    le verrou des clôtures du lieu : deux clôtures ne lisent jamais le même dernier
    numéro ni la même empreinte précédente.
    / Numbers, chains and saves a closure. Call inside a transaction, under the
    closure lock.

    Le responsable et le point de vente sont informatifs : ils ne sont pas dans
    l'empreinte de la clôture (`comptabilite/integrite.py`, `calculer_hmac_cloture`).
    / Operator and point of sale are informative, outside the closure fingerprint.

    :param niveau: "J", "H", "M" ou "A"
    :param debut: début de la période (inclus)
    :param fin: fin de la période (exclue)
    :param sections_du_rapport: le dictionnaire des sections (`RapportDesVentes`)
    :param responsable: l'utilisateur qui a lancé la clôture, ou None (automatique)
    :param point_de_vente: le `laboutik.PointDeVente` d'où elle est lancée, ou None
    :return: la `ClotureCaisse` enregistrée
    """
    en_tete = sections_du_rapport["en_tete"]
    total_general = sections_du_rapport["chiffre_affaires"]["total_ttc_en_centimes"]
    nombre_de_ventes = en_tete["nombre_de_ventes"]

    # Numéro et empreinte précédente : la dernière clôture, tous niveaux.
    # / Number and previous fingerprint: the last closure, every level.
    derniere_cloture = ClotureCaisse.objects.order_by("-numero_sequentiel").first()
    if derniere_cloture is None:
        numero_de_la_cloture = 1
        empreinte_precedente = ""
    else:
        numero_de_la_cloture = derniere_cloture.numero_sequentiel + 1
        empreinte_precedente = derniere_cloture.hmac_hash

    # Perpétuels : ceux de la dernière J ; une J y ajoute les siens.
    # / Perpetual totals: the last J's; a J adds its own.
    derniere_j = ClotureCaisse.derniere_journaliere()
    total_perpetuel = 0
    nombre_ventes_perpetuel = 0
    if derniere_j is not None:
        total_perpetuel = derniere_j.total_perpetuel
        nombre_ventes_perpetuel = derniere_j.nombre_ventes_perpetuel
    if niveau == ClotureCaisse.NIVEAU_JOURNALIER:
        total_perpetuel = total_perpetuel + total_general
        nombre_ventes_perpetuel = nombre_ventes_perpetuel + nombre_de_ventes

    # L'en-tête du rapport reçoit ce que seule la clôture connaît.
    # / The report header receives what only the closure knows.
    en_tete["niveau"] = niveau
    en_tete["numero_de_cloture"] = numero_de_la_cloture
    en_tete["total_perpetuel_en_centimes"] = total_perpetuel
    en_tete["nombre_de_ventes_perpetuel"] = nombre_ventes_perpetuel

    cloture = ClotureCaisse(
        niveau=niveau,
        numero_sequentiel=numero_de_la_cloture,
        datetime_debut=debut,
        datetime_fin=fin,
        numero_premiere_vente=en_tete["numero_premiere_vente"],
        numero_derniere_vente=en_tete["numero_derniere_vente"],
        total_general=total_general,
        total_ht=sections_du_rapport["chiffre_affaires"]["total_ht_en_centimes"],
        total_tva=sections_du_rapport["chiffre_affaires"]["total_tva_en_centimes"],
        total_argent_recu=sections_du_rapport["reconciliation"]["argent_recu_en_centimes"],
        nombre_transactions=nombre_de_ventes,
        total_perpetuel=total_perpetuel,
        nombre_ventes_perpetuel=nombre_ventes_perpetuel,
        rapport_json=sections_du_rapport,
        previous_hmac=empreinte_precedente,
        responsable=responsable,
        point_de_vente=point_de_vente,
    )
    cle_du_lieu = LaboutikConfiguration.get_solo().get_or_create_hmac_key()
    cloture.hmac_hash = calculer_hmac_cloture(cloture, cle_du_lieu, empreinte_precedente)
    cloture.save()
    return cloture


def _creer_la_cloture_journaliere(
    seuil_du_filet=None, responsable=None, point_de_vente=None
):
    """
    Crée la J du lieu courant : [fin de la J précédente, maintenant[.
    / Creates the current venue's J: [end of the previous J, now[.

    LA FIN :
    - Z demandé (`seuil_du_filet` = None) : maintenant ;
    - filet automatique : le seuil courant (fermeture + 2 h). Le filet fait le Z que
      personne n'a fait ; les ventes d'après le seuil sont du service suivant, elles
      attendent la J suivante : un service n'est jamais coupé en deux.

    TROIS TEMPS :
    1. Sous le verrou des VENTES, dans une transaction courte : la fin de la J est
       fixée, la dernière J est relue (elle donne le début), puis le verrou est
       relâché. C'est la contrainte qui fige la J : une vente prend son heure
       d'encaissement et son numéro sous ce même verrou. Toute vente encaissée après
       le relâchement a donc une heure postérieure à « maintenant » (et au seuil, qui
       est passé) : elle n'entre jamais dans [debut, fin[, elle sera dans la J suivante.
    2. Le rapport de [debut, fin[ est calculé HORS de tout verrou : il peut prendre
       plusieurs secondes (des milliers de ventes un jour de festival), la caisse
       continue d'encaisser pendant ce temps.
    3. Sous le verrou des CLÔTURES : si une autre J a été créée entre-temps (la
       dernière J n'est plus celle lue au temps 1), rien n'est créé ; sinon la J est
       numérotée, chaînée, enregistrée.
    Le temps 1 ne relâche le verrou des ventes que s'il n'y a pas de transaction
    autour : la transaction du temps 1 est donc DURABLE (`atomic(durable=True)`), et
    un appel dans une transaction déjà ouverte lève RuntimeError.
    / Three steps: fix the end under the sales lock (short), compute the report with no
    lock, then number and chain under the closure lock, unless another J was created
    meanwhile. Calling this inside an open transaction raises RuntimeError.

    :param seuil_du_filet: pour le filet automatique, le seuil courant (en UTC) : si la
        dernière J finit à ce seuil ou après, rien n'est créé ; sinon la J finit au
        seuil. None pour un Z demandé (la J finit maintenant).
    :param responsable: l'utilisateur qui demande le Z (bouton de la caisse), ou None
    :param point_de_vente: le point de vente d'où le Z est demandé, ou None
    :return: la `ClotureCaisse` créée, ou None (aucune vente dans la plage, J déjà
        faite depuis le seuil, ou J créée entre-temps par un autre appel)
    """
    # 1. La fin et le début, sous le verrou des ventes (transaction courte, durable).
    # / 1. End and start, under the sales lock (short, durable transaction).
    with transaction.atomic(durable=True):
        _prendre_le_verrou_des_ventes_du_lieu()
        z_demande = seuil_du_filet is None
        if z_demande:
            fin = timezone.now()
        else:
            fin = seuil_du_filet

        derniere_j_lue = ClotureCaisse.derniere_journaliere()

        # Le filet : une J par jour au plus, à partir du seuil.
        # / The net: at most one J per day, from the threshold on.
        filet_deja_passe = (
            not z_demande
            and derniere_j_lue is not None
            and derniere_j_lue.datetime_fin >= seuil_du_filet
        )
        if filet_deja_passe:
            return None

        # Le début : la fin de la J précédente, sinon la première vente réglée.
        # / Start: the previous J's end, otherwise the first settled sale.
        if derniere_j_lue is not None:
            debut = derniere_j_lue.datetime_fin
        else:
            debut = Vente.objects.filter(statut=Vente.Statut.REGLEE).aggregate(
                premiere_heure=Min("datetime_encaissement")
            )["premiere_heure"]
            lieu_sans_aucune_vente = debut is None
            if lieu_sans_aucune_vente:
                return None

        # Aucune vente dans [debut, fin[ : rien à clôturer. Pour le filet, une vente
        # d'après le seuil n'y est pas : elle attend la J suivante.
        # / No sale in [debut, fin[: nothing to close.
        aucune_vente_dans_la_plage = not _ventes_reglees_entre(debut, fin).exists()
        if aucune_vente_dans_la_plage:
            return None

    # 2. Le rapport, hors de tout verrou : [debut, fin[ ne bouge plus.
    # / 2. The report, with no lock: [debut, fin[ is frozen.
    sections_du_rapport = RapportDesVentes(debut, fin).toutes_les_sections()

    # 3. Numéro, perpétuels, empreinte, sous le verrou des clôtures.
    # / 3. Number, perpetual totals, fingerprint, under the closure lock.
    with transaction.atomic():
        _prendre_le_verrou_des_clotures_du_lieu()
        derniere_j_maintenant = ClotureCaisse.derniere_journaliere()
        if derniere_j_lue is None:
            pk_de_la_derniere_j_lue = None
        else:
            pk_de_la_derniere_j_lue = derniere_j_lue.pk
        if derniere_j_maintenant is None:
            pk_de_la_derniere_j_maintenant = None
        else:
            pk_de_la_derniere_j_maintenant = derniere_j_maintenant.pk
        une_j_creee_entre_temps = (
            pk_de_la_derniere_j_maintenant != pk_de_la_derniere_j_lue
        )
        if une_j_creee_entre_temps:
            return None
        return _enregistrer_la_cloture(
            ClotureCaisse.NIVEAU_JOURNALIER,
            debut,
            fin,
            sections_du_rapport,
            responsable=responsable,
            point_de_vente=point_de_vente,
        )


def creer_la_cloture_journaliere_de_la_caisse(responsable, point_de_vente):
    """
    Le « Z de fin de service » demandé au bouton « Clôturer » de la caisse : crée la
    J du lieu courant, maintenant, avec l'opérateur et le point de vente. Ne parle
    pas au broker : c'est la vue qui demande ensuite l'e-mail
    (`demander_l_email_automatique_si_configure`), après les effets du bouton.
    / The end-of-service Z requested by the register button: creates the current
    venue's J now, with operator and point of sale. No broker call here.

    LOCALISATION : comptabilite/tasks.py

    À appeler HORS de toute transaction (le temps 1 de `_creer_la_cloture_journaliere`
    est durable : ses verrous courts n'en seraient plus).
    / Call OUTSIDE any transaction (step 1 is durable).

    APPELÉE PAR : `laboutik/views.py`, `CaisseViewSet.cloturer`.

    :param responsable: l'utilisateur connecté, ou None
    :param point_de_vente: le `laboutik.PointDeVente` du bouton
    :return: la `ClotureCaisse` créée, ou None (aucune vente depuis la dernière J)
    """
    return _creer_la_cloture_journaliere(
        responsable=responsable,
        point_de_vente=point_de_vente,
    )


def _creer_la_cloture_d_une_periode(niveau, debut, fin):
    """
    Crée la clôture H, M ou A de [debut, fin[ dans le lieu courant, si elle n'existe
    pas, que le filet du jour où elle finit est passé, et que la période a au moins une
    vente réglée.
    / Creates the H / M / A closure of [debut, fin[ if absent, after the net of its
    last day, and not empty.

    LA BARRIÈRE : juste avant de calculer le rapport de la période, le verrou des
    ventes du lieu est pris puis relâché, dans une transaction courte et durable. Une vente prend
    son heure d'encaissement et son numéro sous ce verrou (`encaisser_vente`) : un
    encaissement commencé avant la barrière est donc terminé quand elle est franchie,
    et aucune vente ne peut plus entrer dans la période (finie). Sans elle, une vente
    encaissée juste avant la fin, mais pas encore enregistrée, manquerait au rapport.
    Cette contrainte n'est pas testable sans deux connexions réelles à la base.
    Le rapport est ensuite calculé HORS de tout verrou ; le numéro et l'empreinte sont
    posés sous le verrou des clôtures, qui ne bloque pas la caisse.
    La barrière n'en est une que s'il n'y a pas de transaction autour : un appel dans
    une transaction déjà ouverte lève RuntimeError (`atomic(durable=True)`).
    / The barrier: the sales lock is taken then released in a short durable transaction
    just before computing the report, so any settlement started before is done.
    Not testable without two real connections. Raises RuntimeError inside an open
    transaction.

    La période déjà clôturée est vue deux fois, pour deux raisons différentes : avant
    le calcul (ne pas recalculer un mois chaque heure), et sous le verrou des clôtures
    (un autre appel a pu la créer pendant le calcul).
    / The "already closed" check runs before the computation (cost) and under the lock
    (race).

    :return: la `ClotureCaisse` créée, ou None (période déjà clôturée, filet du jour de
        la fin pas encore passé, ou période sans vente)
    """
    periode_deja_cloturee = ClotureCaisse.objects.filter(
        niveau=niveau, datetime_debut=debut, datetime_fin=fin
    ).exists()
    if periode_deja_cloturee:
        return None

    configuration = Configuration.get_solo()
    filet_du_jour_de_la_fin_passe = _filet_du_jour_de_la_fin_passe(
        fin, configuration.get_tzinfo(), configuration.heure_de_fermeture
    )
    if not filet_du_jour_de_la_fin_passe:
        return None

    # Pas de clôture vide : un lieu inactif accumulerait des clôtures à zéro.
    # / No empty closure: an idle venue would pile up zero closures.
    periode_sans_vente = not _ventes_reglees_entre(debut, fin).exists()
    if periode_sans_vente:
        return None

    # La barrière : tout encaissement commencé avant est terminé après elle.
    # / The barrier: every settlement started before is done after it.
    with transaction.atomic(durable=True):
        _prendre_le_verrou_des_ventes_du_lieu()

    # Les sections d'une période : celles d'une J (`toutes_les_sections()`), SANS la
    # caisse espèces (un fond de caisse n'a de sens que pour une journée) et SANS
    # l'intégrité (chaque J l'a vérifiée sur sa plage ; une année la revérifierait vente
    # par vente, plusieurs requêtes par vente). Elles ne sont donc même pas calculées.
    # / A period's sections: a J's, without the cash drawer and without integrity (not
    # even computed).
    rapport_de_la_periode = RapportDesVentes(debut, fin)
    sections_du_rapport = {
        "en_tete": rapport_de_la_periode.section_en_tete(),
        "chiffre_affaires": rapport_de_la_periode.section_chiffre_affaires(),
        "reglements": rapport_de_la_periode.section_reglements(),
        "reconciliation": rapport_de_la_periode.section_reconciliation(),
        "offerts": rapport_de_la_periode.section_offerts(),
        "annexe": rapport_de_la_periode.section_annexe(),
        "points": rapport_de_la_periode.section_points(),
        "marge_brute": rapport_de_la_periode.section_marge_brute(),
        "detail": rapport_de_la_periode.section_detail(),
    }

    with transaction.atomic():
        _prendre_le_verrou_des_clotures_du_lieu()
        periode_cloturee_entre_temps = ClotureCaisse.objects.filter(
            niveau=niveau, datetime_debut=debut, datetime_fin=fin
        ).exists()
        if periode_cloturee_entre_temps:
            return None
        return _enregistrer_la_cloture(niveau, debut, fin, sections_du_rapport)


def demander_l_email_automatique_si_configure(schema_name, cloture):
    """
    Demande l'email de la clôture si le lieu a des destinataires et que la périodicité
    du rapport est le niveau de cette clôture.
    / Requests the closure email when configured for this level.

    APPELÉE PAR : les tâches de clôture de ce module, et `laboutik/views.py`
    `CaisseViewSet.cloturer` (après les effets du bouton, dans un try/except).
    """
    configuration = Configuration.get_solo()
    if configuration.rapport_periodicite == cloture.niveau and configuration.rapport_emails:
        envoyer_email_cloture.delay(schema_name, str(cloture.uuid))


@shared_task
def generer_cloture_pour_tenant(
    schema_name,
    niveau,
    datetime_debut_iso=None,
    datetime_fin_iso=None,
):
    """
    Crée une clôture pour un lieu, maintenant.
    / Creates one closure for one venue, now.

    LOCALISATION : comptabilite/tasks.py

    - J : la J glissante (le « Z de fin de service »), sans bornes : elles viennent de
      la J précédente et du moment présent. Des bornes données → ValueError.
    - H, M, A : la période précédente, en heure locale du lieu ; ou les bornes données
      (texte ISO). Des bornes données doivent porter un fuseau, et être une vraie
      semaine / un vrai mois / une vraie année du lieu, en heure locale : sinon
      ValueError. Une période déjà clôturée ne l'est pas deux fois ; une période dont
      le filet du dernier jour n'est pas passé n'est pas encore clôturée.
    Hors de toute transaction : sinon RuntimeError (les verrous courts des ventes).

    :return: l'uuid (texte) de la clôture créée, None si rien n'est créé (aucune vente,
        période déjà clôturée, ou filet du jour de la fin pas encore passé)
    """
    if niveau == ClotureCaisse.NIVEAU_JOURNALIER:
        bornes_donnees = datetime_debut_iso is not None or datetime_fin_iso is not None
        if bornes_donnees:
            raise ValueError(
                "La clôture journalière n'accepte pas de bornes : elle va de la fin de "
                "la clôture journalière précédente au moment présent."
            )

    tenant = Client.objects.get(schema_name=schema_name)
    with tenant_context(tenant):
        if niveau == ClotureCaisse.NIVEAU_JOURNALIER:
            cloture = _creer_la_cloture_journaliere()
        else:
            fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
            if datetime_debut_iso and datetime_fin_iso:
                debut, fin = _bornes_donnees_verifiees(
                    niveau, datetime_debut_iso, datetime_fin_iso, fuseau_du_lieu
                )
            else:
                maintenant_local = timezone.localtime(timezone.now(), fuseau_du_lieu)
                debut, fin = _bornes_de_la_periode_precedente(niveau, maintenant_local)
            cloture = _creer_la_cloture_d_une_periode(niveau, debut, fin)

        if cloture is None:
            logger.info(
                f"[{schema_name}] Clôture {niveau} : rien à clôturer (aucune vente, "
                f"période déjà clôturée, ou filet du dernier jour pas encore passé)."
            )
            return None

        logger.info(
            f"[{schema_name}] Clôture {niveau} n° {cloture.numero_sequentiel} "
            f"(total={cloture.total_general} c, {cloture.nombre_transactions} ventes)."
        )
        demander_l_email_automatique_si_configure(schema_name, cloture)
        return str(cloture.uuid)


def _bornes_donnees_verifiees(niveau, datetime_debut_iso, datetime_fin_iso, fuseau_du_lieu):
    """
    Lit et vérifie des bornes H / M / A données à la main (commande `generer_cloture`).
    / Reads and checks hand-given H / M / A bounds.

    - Une borne sans fuseau (« 2026-02-01T00:00 ») est ambiguë : refusée.
    - Les bornes doivent être exactement la semaine (lundi-dimanche), le mois ou l'année
      qui finit à la borne de fin, EN HEURE LOCALE DU LIEU : la même période que celle
      que la tâche horaire aurait clôturée. Sinon deux clôtures M d'un même mois
      pourraient exister, avec des bornes différentes.
    / A bound without time zone is refused; the bounds must be the venue's local week,
    month or year.

    :return: (debut, fin), deux datetimes avec fuseau
    :raise ValueError: borne sans fuseau, ou période qui n'est pas celle du lieu
    """
    debut = datetime.fromisoformat(datetime_debut_iso)
    fin = datetime.fromisoformat(datetime_fin_iso)

    borne_sans_fuseau = debut.tzinfo is None or fin.tzinfo is None
    if borne_sans_fuseau:
        raise ValueError(
            "Les bornes données doivent porter un fuseau horaire "
            "(ex. 2026-02-01T00:00+01:00)."
        )

    # La période attendue : celle qui précède la borne de fin, en heure du lieu.
    # / The expected period: the one before the end bound, in the venue's time.
    fin_en_heure_du_lieu = fin.astimezone(fuseau_du_lieu)
    debut_attendu, fin_attendue = _bornes_de_la_periode_precedente(
        niveau, fin_en_heure_du_lieu
    )
    bornes_du_lieu = debut == debut_attendu and fin == fin_attendue
    if not bornes_du_lieu:
        raise ValueError(
            f"Les bornes ne sont pas une période {niveau} du lieu en heure locale "
            f"({fuseau_du_lieu}) : attendu {debut_attendu.isoformat()} → "
            f"{fin_attendue.isoformat()}."
        )
    return debut, fin


def _periodes_finies_a_cloturer(niveau, fuseau_du_lieu, heure_de_fermeture):
    """
    Les périodes d'un niveau qui peuvent manquer, dans l'ordre chronologique : de la
    période qui suit la dernière clôture du niveau (sinon de celle qui contient la
    première vente réglée du lieu) jusqu'à la dernière période dont le filet du jour de
    la fin est passé. Une tâche arrêtée trois semaines a ainsi trois semaines à
    rattraper. Les périodes déjà clôturées ou sans vente en font partie : la création
    les écarte (`_creer_la_cloture_d_une_periode`).
    / The periods of a level that may be missing, in chronological order, from the
    last closure of the level (or the venue's first sale) to the last finished one.

    :param niveau: "H", "M" ou "A"
    :param fuseau_du_lieu: le fuseau du lieu
    :param heure_de_fermeture: `Configuration.heure_de_fermeture`
    :return: la liste des (debut, fin), datetimes dans le fuseau du lieu
    """
    derniere_cloture_du_niveau = (
        ClotureCaisse.objects.filter(niveau=niveau).order_by("-datetime_fin").first()
    )
    if derniere_cloture_du_niveau is not None:
        moment_de_depart = derniere_cloture_du_niveau.datetime_fin
    else:
        moment_de_depart = Vente.objects.filter(statut=Vente.Statut.REGLEE).aggregate(
            premiere_heure=Min("datetime_encaissement")
        )["premiere_heure"]
        lieu_sans_aucune_vente = moment_de_depart is None
        if lieu_sans_aucune_vente:
            return []

    periodes_finies = []
    jour_de_depart = moment_de_depart.astimezone(fuseau_du_lieu).date()
    debut, fin = _bornes_de_la_periode_qui_contient(
        niveau, jour_de_depart, fuseau_du_lieu
    )
    while _filet_du_jour_de_la_fin_passe(fin, fuseau_du_lieu, heure_de_fermeture):
        periodes_finies.append((debut, fin))
        debut, fin = _bornes_de_la_periode_qui_contient(
            niveau, fin.date(), fuseau_du_lieu
        )
    return periodes_finies


@shared_task
def generer_les_clotures_automatiques_du_lieu(schema_name):
    """
    La sous-tâche horaire d'un lieu : le filet J, puis toutes les semaines, tous les
    mois et toutes les années finis qui ne sont pas encore clôturés, dans l'ordre
    chronologique.
    / The hourly sub-task of one venue: the J net, then every finished H, M, A not yet
    closed, in chronological order.

    LOCALISATION : comptabilite/tasks.py

    FLUX : `generer_les_clotures_automatiques` (chaque heure) → une sous-tâche Celery
    par lieu → CETTE FONCTION. La J d'abord : une période n'est clôturée qu'après le
    filet du jour où elle finit, et la J de ce filet porte les perpétuels qu'elle
    reprend.

    Une erreur est journalisée avec le schéma du lieu, puis remontée : Celery note la
    sous-tâche en échec, les autres lieux ne sont pas touchés.
    / An error is logged with the venue's schema, then raised again.

    :param schema_name: le schéma du lieu
    """
    try:
        tenant = Client.objects.get(schema_name=schema_name)
        with tenant_context(tenant):
            configuration = Configuration.get_solo()
            maintenant_local = timezone.localtime(
                timezone.now(), configuration.get_tzinfo()
            )

            # Le filet J : le Z que personne n'a fait, jusqu'au seuil courant.
            # / The J net: the Z nobody made, up to the current threshold.
            seuil_courant = _seuil_courant_du_filet(
                maintenant_local, configuration.heure_de_fermeture
            )
            cloture_j = _creer_la_cloture_journaliere(seuil_du_filet=seuil_courant)
            if cloture_j is not None:
                logger.info(
                    f"[{schema_name}] Filet : clôture J n° {cloture_j.numero_sequentiel} "
                    f"({cloture_j.nombre_transactions} ventes)."
                )
                demander_l_email_automatique_si_configure(schema_name, cloture_j)

            # Les semaines, mois, années finis qui manquent, dans l'ordre du
            # calendrier : chacun une seule fois.
            # / Every missing finished week, month, year, in calendar order, once each.
            fuseau_du_lieu = configuration.get_tzinfo()
            for niveau in NIVEAUX_CALENDAIRES:
                periodes_finies = _periodes_finies_a_cloturer(
                    niveau, fuseau_du_lieu, configuration.heure_de_fermeture
                )
                for debut, fin in periodes_finies:
                    cloture_de_la_periode = _creer_la_cloture_d_une_periode(
                        niveau, debut, fin
                    )
                    if cloture_de_la_periode is None:
                        continue
                    logger.info(
                        f"[{schema_name}] Clôture {niveau} n° "
                        f"{cloture_de_la_periode.numero_sequentiel} créée."
                    )
                    demander_l_email_automatique_si_configure(schema_name, cloture_de_la_periode)
    except Exception:
        logger.exception(f"[{schema_name}] Échec des clôtures automatiques du lieu.")
        raise


def generer_les_clotures_automatiques():
    """
    La tâche horaire de tous les lieux : une sous-tâche Celery par lieu (tous les
    schémas sauf `public`).
    / The hourly task of every venue: one Celery sub-task per venue.

    LOCALISATION : comptabilite/tasks.py

    FLUX : `TiBillet/celery.py` `cron_clotures_automatiques` (chaque heure) → CETTE
    FONCTION → `generer_les_clotures_automatiques_du_lieu.delay(schema)` par lieu.

    Une sous-tâche par lieu : un lieu lent ou en erreur ne retient pas les autres (une
    seule tâche pour tous les lieux tomberait sous la limite de temps de Celery). Un
    envoi qui échoue est journalisé et n'empêche pas les envois suivants.
    / One sub-task per venue: a slow or failing venue does not hold the others; a failed
    send is logged and the next ones go on.
    """
    schemas_des_lieux = list(
        Client.objects.exclude(schema_name="public").values_list("schema_name", flat=True)
    )
    for schema_name in schemas_des_lieux:
        try:
            generer_les_clotures_automatiques_du_lieu.delay(schema_name)
        except Exception:
            logger.exception(
                f"[{schema_name}] Échec de l'envoi de la tâche des clôtures du lieu."
            )


@shared_task
def envoyer_email_cloture(schema_name, cloture_uuid):
    """
    L'envoi AUTOMATIQUE de l'email d'une clôture (demandé à sa création) : seulement
    si la périodicité du rapport du lieu est le niveau de la clôture.
    / AUTOMATIC closure e-mail: only when the report periodicity is the closure level.

    :return: True si l'email est envoyé, False sinon
    """
    return _envoyer_l_email_de_la_cloture(
        schema_name, cloture_uuid, respecter_la_periodicite=True
    )


@shared_task
def envoyer_email_cloture_demande(schema_name, cloture_uuid):
    """
    L'envoi DEMANDÉ de l'email d'une clôture (bouton « Envoyer par e-mail » de la
    caisse) : c'est un clic explicite, la périodicité du rapport ne compte pas. Les
    destinataires sont toujours ceux du lieu.
    / REQUESTED closure e-mail (register button): the periodicity does not apply.

    APPELÉE PAR : `laboutik/views.py`, `CaisseViewSet.envoyer_rapport`.

    :return: True si l'email est envoyé, False sinon
    """
    return _envoyer_l_email_de_la_cloture(
        schema_name, cloture_uuid, respecter_la_periodicite=False
    )


def _envoyer_l_email_de_la_cloture(schema_name, cloture_uuid, respecter_la_periodicite):
    """
    Envoie l'email d'une clôture aux destinataires de `Configuration.rapport_emails`,
    avec le PDF de la clôture en pièce jointe. Rien n'est envoyé si la liste des
    destinataires est vide ; ni, quand `respecter_la_periodicite` est vrai, si la
    périodicité du rapport n'est pas le niveau de la clôture.
    / Sends a closure email with its PDF to the venue's recipients. Nothing without
    recipients; nor, for the automatic sending, for another level than the periodicity.

    :param respecter_la_periodicite: True pour l'envoi automatique, False pour l'envoi
        demandé à la caisse
    :return: True si l'email est envoyé, False sinon
    """
    tenant = Client.objects.get(schema_name=schema_name)

    with tenant_context(tenant):
        from comptabilite.pdf import generer_pdf_cloture

        try:
            cloture = ClotureCaisse.objects.get(uuid=cloture_uuid)
        except ClotureCaisse.DoesNotExist:
            logger.warning(
                f"[{schema_name}] Clôture {cloture_uuid} introuvable : pas d'email."
            )
            return False

        config = Configuration.get_solo()

        # Rien à envoyer sans destinataire, ou pour un autre niveau que la périodicité.
        # / Nothing to send without recipients, or for another level.
        if not config.rapport_emails or not config.rapport_emails.strip():
            return False
        niveau_hors_periodicite = config.rapport_periodicite != cloture.niveau
        if respecter_la_periodicite and niveau_hors_periodicite:
            return False

        # Les destinataires : séparés par des virgules, sans les espaces autour.
        # / Recipients: comma-separated, trimmed.
        emails = []
        for adresse_saisie in config.rapport_emails.split(","):
            adresse_sans_espaces = adresse_saisie.strip()
            if adresse_sans_espaces:
                emails.append(adresse_sans_espaces)
        if not emails:
            return False

        # Le PDF de la clôture, en pièce jointe.
        # / The closure PDF, attached.
        pdf_bytes, pdf_filename, _type_du_pdf = generer_pdf_cloture(cloture)

        # Le sujet : le lieu, le niveau et le numéro de la clôture.
        # / The subject: venue, level and closure number.
        subject = (
            f"[{config.organisation}] "
            f"Clôture {cloture.get_niveau_display()} "
            f"n° {cloture.numero_sequentiel}"
        )

        # Le total montré est le chiffre d'affaires TTC (`total_general`), écrit à la
        # française par la même fonction que tous les lecteurs du rapport.
        # / The total shown is the revenue incl. tax, written by the shared formatter.
        chiffre_affaires_ttc_en_euros = euros_a_la_francaise(cloture.total_general)

        # La période en heure du lieu, jamais celle du serveur (un lieu en Martinique
        # lit ses heures à lui).
        # / The period in the venue's time zone, never the server's.
        fuseau_du_lieu = config.get_tzinfo()
        debut_en_heure_du_lieu = timezone.localtime(
            cloture.datetime_debut, fuseau_du_lieu
        ).strftime("%d/%m/%Y %H:%M")
        fin_en_heure_du_lieu = timezone.localtime(
            cloture.datetime_fin, fuseau_du_lieu
        ).strftime("%d/%m/%Y %H:%M")

        mailer = CeleryMailerClass(
            email=emails,
            title=subject,
            template="comptabilite/email/cloture_rapport_email.html",
            context={
                "config": config,
                "cloture": cloture,
                "chiffre_affaires_ttc_en_euros": chiffre_affaires_ttc_en_euros,
                "debut_en_heure_du_lieu": debut_en_heure_du_lieu,
                "fin_en_heure_du_lieu": fin_en_heure_du_lieu,
            },
            attached_files={pdf_filename: pdf_bytes},
        )
        result = mailer.send()
        logger.info(
            f"[{schema_name}] Email de la clôture n° {cloture.numero_sequentiel} "
            f"envoyé à {len(emails)} destinataire(s) : result={result}"
        )
        return True
