"""
Service de calcul des rapports billetterie pour un evenement.
/ Ticketing report calculation service for an event.

Utilise par les vues admin pour afficher le bilan d'un evenement.
Tous les montants sont en centimes (int). Jamais de float pour les montants.
/ Used by admin views to display an event's report.
All amounts are in cents (int). Never use float for amounts.

LOCALISATION : BaseBillet/reports.py
"""
import logging
from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum, Count, Q, Case, When, IntegerField, Value
from django.db.models.functions import TruncDate, ExtractHour, ExtractMinute
from django.utils.translation import gettext_lazy as _

from BaseBillet.models import (
    Event,
    LigneArticle,
    Ticket,
    PaymentMethod,
    SaleOrigin,
)

logger = logging.getLogger(__name__)


class RapportBilletterieService:
    """
    Calcule les rapports billetterie pour un evenement donne.
    Chaque methode retourne un dict serialisable JSON.
    / Calculates ticketing reports for a given event.
    Each method returns a JSON-serializable dict.
    """

    def __init__(self, event):
        """
        Initialise le service avec un evenement.
        / Initialize the service with an event.

        :param event: Event instance
        """
        self.event = event

        # Queryset de base : lignes d'articles liees a cet evenement via reservation.
        # / Base queryset: article lines linked to this event via reservation.
        self.lignes = LigneArticle.objects.filter(
            reservation__event=event,
        ).select_related(
            'pricesold__price__product',
            'pricesold__productsold',
            'promotional_code',
            'reservation',
        )

        # Queryset de base : tickets lies a cet evenement via reservation.
        # / Base queryset: tickets linked to this event via reservation.
        self.tickets = Ticket.objects.filter(
            reservation__event=event,
        )

    # ------------------------------------------------------------------
    # 1. Synthese globale / Global summary
    # ------------------------------------------------------------------
    def calculer_synthese(self):
        """
        Retourne un dict avec les indicateurs globaux de l'evenement.
        / Returns a dict with the event's global indicators.

        billets_vendus = Tickets avec status K (NOT_SCANNED) ou S (SCANNED)
        ca_ttc = Somme des montants des LigneArticle VALID (centimes)
        remboursements = Somme des montants des LigneArticle REFUNDED (centimes)
        ca_net = ca_ttc - remboursements
        taux_remplissage = (vendus / jauge_max) * 100, 0.0 si jauge_max = 0
        """
        jauge_max = self.event.jauge_max or 0

        # Comptage des tickets par statut / Count tickets by status
        billets_vendus = self.tickets.filter(
            status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED],
        ).count()

        billets_scannes = self.tickets.filter(
            status=Ticket.SCANNED,
        ).count()

        billets_annules = self.tickets.filter(
            status=Ticket.CANCELED,
        ).count()

        # No-show = vendus non scannes / No-show = sold but not scanned
        no_show = billets_vendus - billets_scannes

        # CA TTC = somme des montants des lignes VALID (centimes)
        # / Gross revenue = sum of VALID line amounts (cents)
        resultat_ca = self.lignes.filter(
            status=LigneArticle.VALID,
        ).aggregate(
            ca_ttc=Sum('amount'),
        )
        ca_ttc = resultat_ca['ca_ttc'] or 0

        # Remboursements = somme des montants des lignes REFUNDED (centimes)
        # / Refunds = sum of REFUNDED line amounts (cents)
        resultat_remb = self.lignes.filter(
            status=LigneArticle.REFUNDED,
        ).aggregate(
            remboursements=Sum('amount'),
        )
        remboursements = resultat_remb['remboursements'] or 0

        ca_net = ca_ttc - remboursements

        # Taux de remplissage / Occupancy rate
        if jauge_max > 0:
            taux_remplissage = round((billets_vendus / jauge_max) * 100, 1)
        else:
            taux_remplissage = 0.0

        return {
            'jauge_max': jauge_max,
            'billets_vendus': billets_vendus,
            'billets_scannes': billets_scannes,
            'billets_annules': billets_annules,
            'no_show': no_show,
            'ca_ttc': ca_ttc,
            'remboursements': remboursements,
            'ca_net': ca_net,
            'taux_remplissage': taux_remplissage,
        }

    # ------------------------------------------------------------------
    # 2. Courbe de ventes cumulees / Cumulative sales curve
    # ------------------------------------------------------------------
    def calculer_courbe_ventes(self):
        """
        Retourne les donnees pour un graphique Chart.js de ventes cumulees par jour.
        / Returns data for a Chart.js cumulative sales chart by day.

        Format : {labels: [dates], datasets: [{label, data: [cumule]}]}
        """
        # Grouper les lignes VALID par jour / Group VALID lines by day
        ventes_par_jour = (
            self.lignes
            .filter(status=LigneArticle.VALID)
            .annotate(jour=TruncDate('datetime'))
            .values('jour')
            .annotate(montant_jour=Sum('amount'))
            .order_by('jour')
        )

        labels = []
        donnees_cumulees = []
        cumul = 0

        for vente in ventes_par_jour:
            jour = vente['jour']
            labels.append(jour.isoformat())
            cumul += vente['montant_jour'] or 0
            donnees_cumulees.append(cumul)

        return {
            'labels': labels,
            'datasets': [
                {
                    'label': str(_('Cumulative revenue (cents)')),
                    'data': donnees_cumulees,
                },
            ],
        }

    # ------------------------------------------------------------------
    # 3. Ventes par tarif / Sales by rate
    # ------------------------------------------------------------------
    def calculer_ventes_par_tarif(self):
        """
        Retourne une liste de dicts avec les ventes groupees par tarif (Price).
        / Returns a list of dicts with sales grouped by rate (Price).

        Chaque dict : {nom, price_uuid, vendus, offerts, ca_ttc, ca_ht, tva, taux_tva, rembourses}
        vendus = nombre de lignes VALID dont payment_method != 'NA' (FREE)
        offerts = nombre de lignes VALID dont payment_method = 'NA' (FREE)
        """
        lignes_valides = self.lignes.filter(status=LigneArticle.VALID)

        # Grouper par tarif (price uuid + nom) / Group by rate
        tarifs_bruts = (
            lignes_valides
            .values(
                'pricesold__price__uuid',
                'pricesold__price__name',
            )
            .annotate(
                vendus=Count(
                    'uuid',
                    filter=~Q(payment_method=PaymentMethod.FREE),
                ),
                offerts=Count(
                    'uuid',
                    filter=Q(payment_method=PaymentMethod.FREE),
                ),
                ca_ttc=Sum('amount'),
            )
            .order_by('pricesold__price__name')
        )

        resultats = []
        for tarif in tarifs_bruts:
            ca_ttc = tarif['ca_ttc'] or 0
            price_uuid = tarif['pricesold__price__uuid']

            # Recuperer le taux TVA depuis la premiere LigneArticle de ce tarif
            # / Get VAT rate from the first LigneArticle of this rate
            premiere_ligne = lignes_valides.filter(
                pricesold__price__uuid=price_uuid,
            ).first()

            taux_tva = Decimal('0')
            if premiere_ligne and premiere_ligne.vat:
                taux_tva = premiere_ligne.vat

            # Calcul HT : TTC / (1 + taux_tva / 100) / Compute excl. tax amount
            if taux_tva > 0:
                ca_ht = int(round(ca_ttc / (1 + taux_tva / 100)))
            else:
                ca_ht = ca_ttc

            tva_montant = ca_ttc - ca_ht

            # Nombre de remboursements pour ce tarif / Refund count for this rate
            rembourses = self.lignes.filter(
                status=LigneArticle.REFUNDED,
                pricesold__price__uuid=price_uuid,
            ).count()

            resultats.append({
                'nom': tarif['pricesold__price__name'] or '',
                'price_uuid': str(price_uuid) if price_uuid else '',
                'vendus': tarif['vendus'] or 0,
                'offerts': tarif['offerts'] or 0,
                'ca_ttc': ca_ttc,
                'ca_ht': ca_ht,
                'tva': tva_montant,
                'taux_tva': float(taux_tva),
                'rembourses': rembourses,
            })

        return resultats

    # ------------------------------------------------------------------
    # 4. Par moyen de paiement / By payment method
    # ------------------------------------------------------------------
    def calculer_par_moyen_paiement(self):
        """
        Retourne une liste de dicts avec les ventes groupees par moyen de paiement.
        / Returns a list of dicts with sales grouped by payment method.

        Chaque dict : {code, label, montant, pourcentage, nb_billets}
        """
        lignes_valides = self.lignes.filter(status=LigneArticle.VALID)

        # Total pour calculer les pourcentages / Total for percentage calculation
        total_ca = lignes_valides.aggregate(total=Sum('amount'))['total'] or 0

        # Grouper par moyen de paiement / Group by payment method
        moyens_bruts = (
            lignes_valides
            .values('payment_method')
            .annotate(
                montant=Sum('amount'),
                nb_billets=Count('uuid'),
            )
            .order_by('-montant')
        )

        resultats = []
        for moyen in moyens_bruts:
            code = moyen['payment_method'] or ''
            montant = moyen['montant'] or 0

            # Label humain via PaymentMethod / Human label via PaymentMethod
            try:
                label = str(PaymentMethod(code).label)
            except ValueError:
                label = code

            # Pourcentage du CA total / Percentage of total revenue
            if total_ca > 0:
                pourcentage = round((montant / total_ca) * 100, 1)
            else:
                pourcentage = 0.0

            resultats.append({
                'code': code,
                'label': label,
                'montant': montant,
                'pourcentage': pourcentage,
                'nb_billets': moyen['nb_billets'] or 0,
            })

        return resultats

    # ------------------------------------------------------------------
    # 5. Par canal de vente / By sales channel
    # ------------------------------------------------------------------
    def calculer_par_canal(self):
        """
        Retourne une liste de dicts avec les ventes groupees par canal de vente.
        Retourne None si un seul canal (section masquee dans le template).
        / Returns a list of dicts with sales grouped by sales channel.
        Returns None if only one channel (section hidden in template).
        """
        lignes_valides = self.lignes.filter(status=LigneArticle.VALID)

        # Grouper par canal / Group by channel
        canaux_bruts = (
            lignes_valides
            .values('sale_origin')
            .annotate(
                montant=Sum('amount'),
                nb_billets=Count('uuid'),
            )
            .order_by('-montant')
        )

        # Convertir en liste pour compter / Convert to list to count
        canaux_liste = list(canaux_bruts)

        # Si un seul canal, retourner None (section masquee)
        # / If only one channel, return None (hidden section)
        if len(canaux_liste) <= 1:
            return None

        resultats = []
        for canal in canaux_liste:
            code = canal['sale_origin'] or ''

            # Label humain via SaleOrigin / Human label via SaleOrigin
            try:
                label = str(SaleOrigin(code).label)
            except ValueError:
                label = code

            resultats.append({
                'code': code,
                'label': label,
                'montant': canal['montant'] or 0,
                'nb_billets': canal['nb_billets'] or 0,
            })

        return resultats

    # ------------------------------------------------------------------
    # 6. Scans / Scan statistics
    # ------------------------------------------------------------------
    def calculer_scans(self):
        """
        Retourne les statistiques de scan des tickets.
        / Returns ticket scan statistics.

        {scannes, non_scannes, annules, tranches_horaires: {labels, data} | None}
        tranches_horaires = None si aucun scanned_at renseigne.
        """
        scannes = self.tickets.filter(status=Ticket.SCANNED).count()
        non_scannes = self.tickets.filter(status=Ticket.NOT_SCANNED).count()
        annules = self.tickets.filter(status=Ticket.CANCELED).count()

        # Tranches horaires de 30 min depuis scanned_at
        # / 30-min time slots from scanned_at
        tickets_scannes = self.tickets.filter(
            status=Ticket.SCANNED,
            scanned_at__isnull=False,
        )

        if not tickets_scannes.exists():
            tranches_horaires = None
        else:
            # Annoter chaque ticket avec sa tranche de 30 min
            # / Annotate each ticket with its 30-min slot
            tickets_avec_tranche = tickets_scannes.annotate(
                heure=ExtractHour('scanned_at'),
                # Arrondir les minutes a 0 ou 30 / Floor minutes to 0 or 30
                demi_heure=Case(
                    When(
                        condition=Q(scanned_at__minute__gte=30),
                        then=Value(30),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )

            # Grouper par heure + demi-heure / Group by hour + half-hour
            tranches_brutes = (
                tickets_avec_tranche
                .values('heure', 'demi_heure')
                .annotate(nombre=Count('uuid'))
                .order_by('heure', 'demi_heure')
            )

            labels = []
            data = []
            for tranche in tranches_brutes:
                heure = tranche['heure']
                minutes = tranche['demi_heure']
                label = f"{heure:02d}:{minutes:02d}"
                labels.append(label)
                data.append(tranche['nombre'])

            tranches_horaires = {
                'labels': labels,
                'data': data,
            }

        return {
            'scannes': scannes,
            'non_scannes': non_scannes,
            'annules': annules,
            'tranches_horaires': tranches_horaires,
        }

    # ------------------------------------------------------------------
    # 7. Codes promo / Promotional codes
    # ------------------------------------------------------------------
    def calculer_codes_promo(self):
        """
        Retourne une liste de dicts avec les codes promo utilises.
        Retourne None si aucun code promo utilise.
        / Returns a list of dicts with used promo codes.
        Returns None if no promo code was used.

        {nom, taux_reduction, utilisations, manque_a_gagner}
        manque_a_gagner = prix_catalogue - prix_paye (centimes)
        """
        # Lignes VALID avec un code promo / VALID lines with a promo code
        lignes_avec_promo = self.lignes.filter(
            status=LigneArticle.VALID,
            promotional_code__isnull=False,
        )

        if not lignes_avec_promo.exists():
            return None

        # Grouper par code promo / Group by promo code
        promos_brutes = (
            lignes_avec_promo
            .values(
                'promotional_code__uuid',
                'promotional_code__name',
                'promotional_code__discount_rate',
            )
            .annotate(
                utilisations=Count('uuid'),
                total_paye=Sum('amount'),
            )
            .order_by('promotional_code__name')
        )

        resultats = []
        for promo in promos_brutes:
            code_uuid = promo['promotional_code__uuid']
            total_paye = promo['total_paye'] or 0

            # Calculer le prix catalogue total pour les lignes de ce code promo
            # prix_catalogue = pricesold.price.prix * 100 (conversion euros → centimes)
            # / Compute total catalog price for lines with this promo code
            lignes_de_ce_promo = lignes_avec_promo.filter(
                promotional_code__uuid=code_uuid,
            ).select_related('pricesold__price')

            prix_catalogue_total = 0
            for ligne in lignes_de_ce_promo:
                if ligne.pricesold and ligne.pricesold.price:
                    # Conversion Decimal euros → centimes / Convert Decimal euros to cents
                    prix_catalogue_total += int(round(ligne.pricesold.price.prix * 100))

            manque_a_gagner = prix_catalogue_total - total_paye

            resultats.append({
                'nom': promo['promotional_code__name'] or '',
                'taux_reduction': float(promo['promotional_code__discount_rate'] or 0),
                'utilisations': promo['utilisations'] or 0,
                'manque_a_gagner': manque_a_gagner,
            })

        return resultats

    # ------------------------------------------------------------------
    # 8. Remboursements / Refunds
    # ------------------------------------------------------------------
    def calculer_remboursements(self):
        """
        Retourne les statistiques de remboursement.
        / Returns refund statistics.

        {nombre, montant_total, taux}
        taux = (rembourses / (valides + rembourses)) * 100
        """
        nombre_rembourses = self.lignes.filter(
            status=LigneArticle.REFUNDED,
        ).count()

        montant_total = self.lignes.filter(
            status=LigneArticle.REFUNDED,
        ).aggregate(total=Sum('amount'))['total'] or 0

        nombre_valides = self.lignes.filter(
            status=LigneArticle.VALID,
        ).count()

        # Taux de remboursement / Refund rate
        denominateur = nombre_valides + nombre_rembourses
        if denominateur > 0:
            taux = round((nombre_rembourses / denominateur) * 100, 1)
        else:
            taux = 0.0

        return {
            'nombre': nombre_rembourses,
            'montant_total': montant_total,
            'taux': taux,
        }
