"""
Rassemble les evenements du reseau federe et en fait des "fiches".
/ Gather the federated network's events into "fiches" (plain dicts).

LOCALISATION : newsletter/collecte.py

Ce module connait la base. Il ne connait NI Ghost NI le HTML.
/ This module knows the database. It knows NOTHING about Ghost or HTML.
"""

import logging
from datetime import timedelta

from django.db import DatabaseError, connection
from django.utils import timezone
from django.utils.translation import gettext as _
from django_tenants.utils import tenant_context

from BaseBillet.models import (
    Configuration,
    Event,
    FederatedPlace,
    FederationConfiguration,
    Product,
)
from Customers.models import Client
from seo.services import build_stdimage_variation_url, get_tenant_uuids_with_event_tags

logger = logging.getLogger(__name__)

# La variation 960x540 : `crop` (480x270) est trop petite pour un email sur ecran dense.
# / The 960x540 variation: `crop` (480x270) is too small for a modern email.
VARIATION_IMAGE_POUR_EMAIL = "crop_hdr"
LARGEUR_IMAGE_POUR_EMAIL = 960
HAUTEUR_IMAGE_POUR_EMAIL = 540


def _formater_montant(montant):
    """
    Met un Decimal en forme francaise, sans centimes inutiles.
    / Format a Decimal the French way, dropping useless cents.

    12.00 -> "12"     12.50 -> "12,50"

    ATTENTION : ne PAS passer par normalize(), qui rabote les zeros significatifs
    (Decimal("12.50").normalize() donne 12.5 -> on afficherait "12,5", pas "12,50").
    / Do NOT use normalize(): it strips meaningful zeros ("12,5" instead of "12,50").

    :param montant: un Decimal
    :return: le montant en texte (str), sans le symbole euro
    """
    montant_est_un_entier = montant == montant.to_integral_value()
    if montant_est_un_entier:
        return str(int(montant))

    # Deux decimales, virgule francaise. / Two decimals, French comma.
    return f"{montant:.2f}".replace(".", ",")


def calculer_tarif(event):
    """
    Rend le tarif d'un evenement, sous forme de texte pret a afficher.
    / Return an event's price as display-ready text.

    LOCALISATION : newsletter/collecte.py

    On ne garde que les produits de BILLETTERIE (BILLET ou FREERES) publies et non
    archives, et parmi leurs prix, ceux qui sont publies. Un produit d'adhesion ou une
    recharge cashless ne fait pas le tarif d'un evenement.
    / Keep only published, non-archived ticketing products, and their published prices.

    ON N'UTILISE PAS event.published_prices() : cette methode refait un
    `Price.objects.filter(...)` NEUF, ce qui court-circuite le prefetch_related de la
    collecte et provoque une requete SQL PAR EVENEMENT. En iterant sur les relations
    (event.products -> produit.prices), on consomme le prefetch : zero requete de plus.
    / We do NOT use event.published_prices(): it builds a FRESH queryset, bypassing the
    caller's prefetch_related and causing one SQL query PER EVENT. Iterating the
    prefetched relations costs zero extra query.

    L'ORDRE DES CAS EST SIGNIFICATIF : un event a plusieurs prix dont un a prix libre
    matche a la fois "prix libre" et "plusieurs prix". Le premier cas qui matche gagne.
    / CASE ORDER MATTERS: the first matching case wins.

    :param event: un Event
    :return: le tarif en texte, ou None si l'event n'a pas de billetterie
    """
    prix_de_billetterie = []
    categories = set()

    for produit in event.products.all():
        produit_est_de_la_billetterie = produit.categorie_article in (
            Product.BILLET,
            Product.FREERES,
        )
        if not produit_est_de_la_billetterie:
            continue

        if not produit.publish or produit.archive:
            continue

        for prix in produit.prices.all():
            if not prix.publish:
                continue
            prix_de_billetterie.append(prix)
            categories.add(produit.categorie_article)

    # Cas 1 : pas de billetterie du tout -> aucune ligne tarif.
    # / Case 1: no ticketing at all.
    if not prix_de_billetterie:
        return None

    montants = [prix.prix for prix in prix_de_billetterie]

    # Cas 2 : que de la reservation gratuite, ou tous les montants a zero.
    # / Case 2: free booking only, or every amount is zero.
    tous_les_montants_sont_nuls = all(montant == 0 for montant in montants)
    if categories == {Product.FREERES} or tous_les_montants_sont_nuls:
        return _("Gratuit")

    # Cas 3 : prix libre. Le montant en base est le MINIMUM accepte.
    # / Case 3: open price. The stored amount is the MINIMUM accepted.
    montants_a_prix_libre = [
        prix.prix for prix in prix_de_billetterie if prix.free_price
    ]
    if montants_a_prix_libre:
        minimum = _formater_montant(min(montants_a_prix_libre))
        return _("Prix libre, à partir de %(montant)s €") % {"montant": minimum}

    # Cas 4 : un seul tarif.
    # / Case 4: a single price.
    if len(montants) == 1:
        return _("%(montant)s €") % {"montant": _formater_montant(montants[0])}

    # Cas 5 : plusieurs tarifs -> on annonce le plus bas.
    # / Case 5: several prices -> announce the lowest.
    minimum = _formater_montant(min(montants))
    return _("À partir de %(montant)s €") % {"montant": minimum}


def _construire_liste_des_tenants(tenant_courant):
    """
    Construit la liste des tenants a parcourir, avec leurs filtres de tags.
    / Build the list of tenants to walk through, with their tag filters.

    LOCALISATION : newsletter/collecte.py

    Trois sources, dans cet ordre :
    1. le tenant courant lui-meme (aucun filtre) ;
    2. ses lieux federes choisis a la main (FederatedPlace, avec leurs deux filtres) ;
    3. la federation automatique par tags (FederationConfiguration.tags_federation) :
       les tenants du reseau qui ont un event public portant un des tags choisis. On ne
       veut d'eux QUE ces events-la, d'ou tag_filter (et non tag_exclude).

    Les SLUGS des tags sont extraits ICI, dans le contexte du tenant courant. Les objets
    Tag appartiennent au schema de CHAQUE tenant : comparer les pk ne marcherait pas.
    / Tag SLUGS are extracted HERE, in the current tenant's context.

    UN MEME VOISIN PEUT ETRE FEDERE DEUX FOIS : FederatedPlace.tenant n'est pas unique.
    L'agenda, lui, ne dedoublonne pas et affiche donc l'UNION des deux jeux de filtres.
    On FUSIONNE les slugs plutot que de jeter le doublon : sinon la newsletter montrerait
    MOINS d'events que le site, pour la meme configuration.
    / The SAME neighbour can be federated TWICE. The agenda shows the UNION of both filter
    sets, so we MERGE the slugs instead of dropping the duplicate.

    :param tenant_courant: le Client du tenant qui genere la newsletter
    :return: list[dict] avec les cles `tenant`, `slugs_filter`, `slugs_exclude`
    """
    tenants_a_parcourir = []
    uuids_deja_vus = set()

    # 1. Le tenant courant, sans aucun filtre.
    # / 1. The current tenant, unfiltered.
    tenants_a_parcourir.append(
        {
            "tenant": tenant_courant,
            "slugs_filter": [],
            "slugs_exclude": [],
        }
    )
    uuids_deja_vus.add(str(tenant_courant.uuid))

    # 2. Les lieux federes choisis a la main, avec fusion des doublons.
    # / 2. Hand-picked federated places, merging duplicates.
    entrees_par_voisin = {}
    lieux_federes = FederatedPlace.objects.select_related("tenant").prefetch_related(
        "tag_filter", "tag_exclude"
    )
    for lieu in lieux_federes:
        uuid_du_voisin = str(lieu.tenant.uuid)

        # Un FederatedPlace qui pointe vers le tenant courant lui-meme : on l'ignore.
        # Le tenant courant est deja dans la liste, et SANS filtre — lui en ajouter
        # masquerait ses propres events.
        # / A FederatedPlace pointing at the current tenant is ignored: it is already in
        # the list, unfiltered. Adding filters would hide its own events.
        if uuid_du_voisin == str(tenant_courant.uuid):
            continue

        slugs_filter_du_lieu = [tag.slug for tag in lieu.tag_filter.all()]
        slugs_exclude_du_lieu = [tag.slug for tag in lieu.tag_exclude.all()]

        entree_deja_vue = entrees_par_voisin.get(uuid_du_voisin)
        if entree_deja_vue:
            # Deuxieme FederatedPlace vers le meme voisin : on fusionne les deux jeux.
            # / Second FederatedPlace to the same neighbour: merge both sets.
            entree_deja_vue["slugs_filter"].extend(slugs_filter_du_lieu)
            entree_deja_vue["slugs_exclude"].extend(slugs_exclude_du_lieu)
            continue

        entrees_par_voisin[uuid_du_voisin] = {
            "tenant": lieu.tenant,
            "slugs_filter": slugs_filter_du_lieu,
            "slugs_exclude": slugs_exclude_du_lieu,
        }
        uuids_deja_vus.add(uuid_du_voisin)

    tenants_a_parcourir.extend(entrees_par_voisin.values())

    # 3. La federation automatique par tags.
    # / 3. Tag-based auto federation.
    slugs_de_federation = [
        tag.slug for tag in FederationConfiguration.get_solo().tags_federation.all()
    ]
    if slugs_de_federation:
        uuids_thematiques = get_tenant_uuids_with_event_tags(slugs_de_federation)
        uuids_a_ajouter = uuids_thematiques - uuids_deja_vus
        for tenant_thematique in Client.objects.filter(uuid__in=uuids_a_ajouter):
            tenants_a_parcourir.append(
                {
                    "tenant": tenant_thematique,
                    # On ne veut de ce tenant QUE ses events thematiques, pas tout son agenda.
                    # / We only want this tenant's thematic events, not its whole agenda.
                    "slugs_filter": slugs_de_federation,
                    "slugs_exclude": [],
                }
            )

    return tenants_a_parcourir


def _formater_lieu(adresse_postale):
    """
    Met une PostalAddress en une ligne lisible. / Render a PostalAddress on one line.

    :param adresse_postale: une PostalAddress, ou None
    :return: le lieu en texte, ou "" si pas d'adresse
    """
    if not adresse_postale:
        return ""

    morceaux = []
    for morceau in (
        adresse_postale.name,
        adresse_postale.street_address,
        adresse_postale.postal_code,
        adresse_postale.address_locality,
    ):
        if morceau:
            morceaux.append(str(morceau).strip())

    return ", ".join(morceaux)


def _construire_fiche(event, domaine_du_proprietaire, nom_de_lorganisateur):
    """
    Transforme un Event en "fiche" : un dict plat, pret pour le template.
    / Turn an Event into a flat dict, ready for the template.

    LOCALISATION : newsletter/collecte.py

    APPELE DEPUIS le tenant PROPRIETAIRE de l'event (on est dans son tenant_context).
    / CALLED FROM the event's OWNING tenant context.

    :param event: un Event
    :param domaine_du_proprietaire: le domaine du tenant qui organise (str)
    :param nom_de_lorganisateur: Configuration.organisation du proprietaire (str)
    :return: le dict de la fiche
    """
    # L'image : URL ABSOLUE sur le domaine du PROPRIETAIRE. Un email ne resout pas les
    # URLs relatives, et l'event peut appartenir a un voisin.
    #
    # On passe par event.get_img() (et non event.img brut) : c'est ce que fait l'agenda.
    # La methode retombe sur l'image du LIEU, puis sur celle de la CONFIGURATION du
    # tenant. Sans elle, un event sans image propre aurait une image sur le site et
    # AUCUNE dans l'email. La variation crop_hdr existe sur les trois modeles (Event,
    # PostalAddress, Configuration) : l'URL construite est valide dans les trois cas.
    # / Use event.get_img() (not raw event.img), like the agenda: it falls back to the
    # venue's image, then the tenant's config image. crop_hdr exists on all three models.
    image_url = None
    image_a_afficher = event.get_img()
    if image_a_afficher:
        chemin_de_limage = build_stdimage_variation_url(
            image_a_afficher.name, VARIATION_IMAGE_POUR_EMAIL
        )
        if chemin_de_limage:
            image_url = f"https://{domaine_du_proprietaire}{chemin_de_limage}"

    # Le lien "Reserver" : on utilise event.full_url TEL QUEL. Ce champ est calcule a
    # chaque save() et gere DEJA le cas is_external (il pointe alors vers le site tiers).
    # Le reconstruire a la main enverrait les abonnes vers une page de reservation qui
    # n'existe pas pour les events externes.
    # / Use event.full_url AS IS: it already handles is_external.
    url_event = event.full_url or ""

    libelle_bouton = event.reservation_button_name or _("Réserver")

    return {
        "nom": event.name,
        "date_debut": event.datetime,
        "date_fin": event.end_datetime,
        "organisateur": nom_de_lorganisateur,
        "description_courte": event.short_description or "",
        # ATTENTION : long_description est du HTML (widget Wysiwyg dans l'admin).
        # Le template l'emet BRUT, sous la carte, sans <p> autour. Voir SPEC §7.2.
        # / long_description is HTML (Wysiwyg widget). Emitted RAW, under the card.
        "description_longue": event.long_description or "",
        "lieu": _formater_lieu(event.postal_address),
        "image_url": image_url,
        "tarif": calculer_tarif(event),
        "url_event": url_event,
        "libelle_bouton": libelle_bouton,
    }


def collecter_evenements_du_reseau(nombre_de_jours):
    """
    Rassemble les evenements a venir du tenant courant ET de son reseau federe.
    / Gather upcoming events from the current tenant AND its federated network.

    LOCALISATION : newsletter/collecte.py

    LE CONTRAT : montrer le meme ensemble d'evenements que l'agenda du site
    (EventMVT.federated_events_filter, BaseBillet/views.py). En oublier un filtre, c'est
    envoyer aux abonnes des evenements qu'ils ne retrouveront pas sur le site.
    / THE CONTRACT: show the same event set as the site's agenda.

    AUCUN ECART : les memes filtres que le moteur, un par un. `archived=False` en fait
    partie — le moteur de l'agenda l'oubliait, il a ete corrige (BaseBillet/views.py).
    / NO DIVERGENCE: the same filters as the engine, one by one.

    C'est possible sans aucun appel HTTP entre instances : FederatedPlace.tenant est une
    FK vers Client, donc les voisins sont d'autres SCHEMAS de la meme base Postgres.
    / No HTTP call between instances: neighbours are other SCHEMAS of the same database.

    :param nombre_de_jours: la largeur de la fenetre (7 ou 30)
    :return: la liste des fiches, triee par date de debut croissante
    """
    tenant_courant = connection.tenant

    # On part d'hier, comme l'agenda : un event commence hier soir est encore d'actualite.
    # / Start yesterday, like the agenda does.
    debut_de_la_fenetre = timezone.now() - timedelta(days=1)
    fin_de_la_fenetre = timezone.now() + timedelta(days=nombre_de_jours)

    # Les slugs sont extraits ICI, dans le contexte du tenant courant.
    # / Slugs are extracted HERE, in the current tenant's context.
    tenants_a_parcourir = _construire_liste_des_tenants(tenant_courant)

    toutes_les_fiches = []

    for entree in tenants_a_parcourir:
        tenant = entree["tenant"]
        slugs_filter = entree["slugs_filter"]
        slugs_exclude = entree["slugs_exclude"]

        # Un voisin mal configure (sans domaine primaire) ne doit pas faire echouer TOUT
        # le brouillon : on le saute en le signalant.
        # / A misconfigured neighbour must not kill the whole draft.
        domaine_primaire = tenant.get_primary_domain()
        if not domaine_primaire:
            logger.warning(
                f"collecter_evenements_du_reseau : le tenant '{tenant.schema_name}' n'a "
                f"pas de domaine primaire. Ses evenements sont ignores."
            )
            continue

        # tenant_context() et NON schema_context() : ce dernier pose un FakeTenant, et
        # tout modele qui lit connection.tenant.uuid plante. Voir tests/PIEGES.md.
        # / tenant_context(), NOT schema_context().
        #
        # Le try/except couvre le meme principe que le garde-fou du domaine ci-dessus :
        # UN voisin casse (migrations en retard -> table absente, schema corrompu) ne doit
        # PAS faire echouer TOUT le brouillon. On le saute en le journalisant, et les
        # autres lieux du reseau restent dans la newsletter.
        # / One broken neighbour (stale migrations, missing table) must NOT kill the whole
        # draft. Skip it with a warning; the rest of the network still makes it in.
        try:
            fiches_de_ce_tenant = _collecter_chez_un_tenant(
                tenant,
                domaine_primaire.domain,
                debut_de_la_fenetre,
                fin_de_la_fenetre,
                slugs_filter,
                slugs_exclude,
                tenant_est_un_voisin=(tenant.uuid != tenant_courant.uuid),
            )
        except DatabaseError as erreur_de_base:
            logger.error(
                f"collecter_evenements_du_reseau : le schema du tenant "
                f"'{tenant.schema_name}' est inexploitable ({erreur_de_base}). "
                f"Ses evenements sont ignores."
            )
            continue

        toutes_les_fiches.extend(fiches_de_ce_tenant)

    toutes_les_fiches.sort(key=lambda fiche: fiche["date_debut"])
    return toutes_les_fiches


def _collecter_chez_un_tenant(
    tenant,
    domaine_du_proprietaire,
    debut_de_la_fenetre,
    fin_de_la_fenetre,
    slugs_filter,
    slugs_exclude,
    tenant_est_un_voisin,
):
    """
    Collecte les fiches d'UN SEUL tenant, dans son propre schema.
    / Collect one single tenant's fiches, inside its own schema.

    LOCALISATION : newsletter/collecte.py

    Extrait de collecter_evenements_du_reseau pour que l'appelant puisse entourer CE
    tenant-la d'un try/except : un voisin casse ne doit pas faire tomber tout le brouillon.
    / Extracted so the caller can wrap THIS tenant in a try/except.

    :return: la liste des fiches de ce tenant
    """
    with tenant_context(tenant):
        # Le prefetch porte EXACTEMENT ce que la suite consomme :
        # `products` et `products__prices` sont lus par calculer_tarif().
        # On ne prefetch PAS `tag` : le filtrage des tags se fait en SQL (JOIN), et
        # _construire_fiche ne lit jamais les tags. Un prefetch inutilise est une
        # requete gratuite par tenant, et un commentaire qui ment.
        # / The prefetch covers EXACTLY what is consumed downstream. No `tag` prefetch:
        # tag filtering happens in SQL, and _construire_fiche never reads tags.
        evenements = (
            Event.objects.select_related("postal_address")
            .prefetch_related("products", "products__prices")
            .filter(
                published=True,
                datetime__gte=debut_de_la_fenetre,
                datetime__lt=fin_de_la_fenetre,
                archived=False,
            )
            .exclude(
                # Les Actions sont des creneaux de benevolat : ils s'affichent dans la
                # page de leur event parent, jamais seuls. Inutile de filtrer aussi sur
                # `parent` : Event.save() force categorie=ACTION des qu'il y a un parent.
                # / Actions are volunteering slots, shown inside their parent event.
                categorie=Event.ACTION,
            )
        )

        # Le veto `private` ne s'applique QU'AUX VOISINS, comme dans l'agenda :
        # `private` veut dire "non federable", pas "secret". Un event prive du tenant
        # courant reste donc dans SA propre newsletter.
        # / The `private` veto applies to NEIGHBOURS only, like the agenda does.
        if tenant_est_un_voisin:
            evenements = evenements.filter(private=False)

        # Les deux filtres de tags, dans le sens annonce par les libelles de l'admin.
        # Matching par SLUG : les Tag appartiennent au schema de chaque tenant.
        # / The two tag filters, matching the admin labels. Slug-based.
        if slugs_filter:
            evenements = evenements.filter(tag__slug__in=slugs_filter)
        if slugs_exclude:
            evenements = evenements.exclude(tag__slug__in=slugs_exclude)

        # distinct() : un .filter() sur un M2M duplique une ligne par tag qui matche.
        # / distinct(): an M2M .filter() yields one row per matching tag.
        evenements = evenements.distinct()

        # L'organisateur est lu DANS le contexte du proprietaire : la newsletter
        # melange plusieurs lieux, il faut dire qui organise quoi.
        # / The organiser is read INSIDE the owner's context.
        nom_de_lorganisateur = Configuration.get_solo().organisation

        fiches_de_ce_tenant = []
        for event in evenements:
            fiches_de_ce_tenant.append(
                _construire_fiche(
                    event,
                    domaine_du_proprietaire,
                    nom_de_lorganisateur,
                )
            )

        return fiches_de_ce_tenant
