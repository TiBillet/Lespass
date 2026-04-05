# laboutik/serializers.py
# Serializers DRF pour la validation des entrées de la caisse LaBoutik.
# DRF serializers for LaBoutik POS input validation.
#
# Règle stack-ccc : toujours serializers.Serializer, jamais request.POST brut.
# Stack-ccc rule: always serializers.Serializer, never raw request.POST.

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class CartePrimaireSerializer(serializers.Serializer):
    """
    Valide le tag NFC envoyé par le lecteur de carte primaire.
    Validates the NFC tag sent by the primary card reader.

    LOCALISATION : laboutik/serializers.py

    Utilisé par CaisseViewSet.carte_primaire() (POST).
    Le tag_id est nettoyé (strip + majuscules) avant validation.
    Used by CaisseViewSet.carte_primaire() (POST).
    The tag_id is cleaned (strip + uppercase) before validation.
    """

    tag_id = serializers.CharField(
        max_length=50,
        error_messages={
            "required": _("Le tag NFC est requis"),
            "blank": _("Le tag NFC ne peut pas être vide"),
        },
    )

    def validate_tag_id(self, value):
        """
        Nettoie le tag_id : supprime les espaces et convertit en majuscules.
        Cleans tag_id: strips whitespace and converts to uppercase.
        """
        tag_id_nettoye = value.strip().upper()
        if not tag_id_nettoye:
            raise serializers.ValidationError(_("Le tag NFC ne peut pas être vide"))
        return tag_id_nettoye


class ArticlePanierSerializer(serializers.Serializer):
    """
    Valide un article individuel dans le panier (UUID produit + quantité).
    Validates a single article in the cart (product UUID + quantity).

    LOCALISATION : laboutik/serializers.py

    Utilisé par PanierSerializer comme élément de la liste d'articles.
    Used by PanierSerializer as an element of the articles list.
    """

    uuid = serializers.UUIDField(
        error_messages={
            "required": _("L'UUID du produit est requis"),
            "invalid": _("UUID de produit invalide"),
        },
    )
    quantite = serializers.IntegerField(
        min_value=1,
        error_messages={
            "required": _("La quantité est requise"),
            "min_value": _("La quantité doit être au moins 1"),
        },
    )


class PanierSerializer(serializers.Serializer):
    """
    Valide le panier complet envoyé par le formulaire d'addition.
    Validates the full cart sent by the addition form.

    LOCALISATION : laboutik/serializers.py

    Utilisé par PaiementViewSet.moyens_paiement() et .payer() (POST).
    Le formulaire d'addition envoie les articles avec des clés "repid-<uuid>".
    Cette méthode extrait et valide chaque article.
    Used by PaiementViewSet.moyens_paiement() and .payer() (POST).
    The addition form sends articles with "repid-<uuid>" keys.
    This method extracts and validates each article.
    """

    uuid_pv = serializers.UUIDField(
        error_messages={
            "required": _("L'UUID du point de vente est requis"),
            "invalid": _("UUID du point de vente invalide"),
        },
    )

    @staticmethod
    def extraire_articles_du_post(donnees_post):
        """
        Extrait les articles depuis les clés POST "repid-<uuid>" → quantité.
        Extracts articles from POST keys "repid-<uuid>" → quantity.

        LOCALISATION : laboutik/serializers.py

        Supporte deux formats de clé :
        - Ancien : "repid-<product_uuid>" → articles mono-tarif
        - Nouveau : "repid-<product_uuid>--<price_uuid>" → articles multi-tarif
        Supports two key formats:
        - Old: "repid-<product_uuid>" → single-rate articles
        - New: "repid-<product_uuid>--<price_uuid>" → multi-rate articles

        Pour le prix libre, un champ "custom-<product_uuid>--<price_uuid>" contient
        le montant en centimes. Sinon custom_amount_centimes est None.
        For free price, a "custom-<product_uuid>--<price_uuid>" field contains
        the amount in cents. Otherwise custom_amount_centimes is None.

        Retourne une liste de dicts :
        {'uuid': str, 'price_uuid': str|None, 'quantite': int, 'custom_amount_centimes': int|None, 'weight_amount': int|None}
        """
        # Pré-charger les montants custom (prix libre)
        # / Pre-load custom amounts (free price)
        montants_custom = {}
        for nom_champ, valeur in donnees_post.items():
            if not nom_champ.startswith("custom-"):
                continue
            cle_custom = nom_champ[7:]  # après "custom-"
            try:
                montants_custom[cle_custom] = int(valeur)
            except (ValueError, TypeError):
                continue

        # Pré-charger les quantités poids/volume (vente au poids/mesure)
        # / Pre-load weight/volume quantities (weight-based sales)
        quantites_poids = {}
        for nom_champ, valeur in donnees_post.items():
            if not nom_champ.startswith("weight-"):
                continue
            cle_weight = nom_champ[7:]  # après "weight-"
            try:
                quantites_poids[cle_weight] = int(valeur)
            except (ValueError, TypeError):
                continue

        articles = []
        for nom_champ, valeur in donnees_post.items():
            if not nom_champ.startswith("repid-"):
                continue
            reste = nom_champ[6:]  # après "repid-"

            # Separer product_uuid et price_uuid (separateur '--').
            # Formats possibles :
            #   "product_uuid"                     → mono-tarif (ancien format)
            #   "product_uuid--price_uuid"         → multi-tarif (tarif fixe)
            #   "product_uuid--price_uuid--N"      → montant variable (prix libre, poids/mesure)
            # Le 3e segment (--N) est un differenciateur unique cote JS,
            # ignore ici — seuls product_uuid et price_uuid comptent.
            # / Separate product_uuid and price_uuid ('--' separator).
            # The 3rd segment (--N) is a JS-side unique differentiator, ignored here.
            parts = reste.split("--")
            uuid_product = parts[0]
            uuid_price = parts[1] if len(parts) >= 2 else None
            # parts[2] (suffixe variable) est ignore / parts[2] (variable suffix) is ignored

            try:
                quantite = int(valeur)
            except (ValueError, TypeError):
                continue
            if quantite > 0:
                # Chercher le montant custom associé (même clé que reste)
                # / Look for associated custom amount (same key as reste)
                custom_amount = montants_custom.get(reste, None)
                weight_amount = quantites_poids.get(reste, None)

                articles.append(
                    {
                        "uuid": uuid_product,
                        "price_uuid": uuid_price,
                        "quantite": quantite,
                        "custom_amount_centimes": custom_amount,
                        "weight_amount": weight_amount,
                    }
                )
        return articles


# --------------------------------------------------------------------------- #
#  Serializers Phase 4 — Commandes de restaurant                              #
#  Phase 4 serializers — Restaurant orders                                    #
# --------------------------------------------------------------------------- #


class ArticleCommandeSerializer(serializers.Serializer):
    """
    Valide un article dans une commande (UUID produit, UUID prix, quantité).
    Validates an article in an order (product UUID, price UUID, quantity).

    LOCALISATION : laboutik/serializers.py

    Utilisé comme élément de la liste 'articles' dans CommandeSerializer.
    Used as an element of the 'articles' list in CommandeSerializer.
    """

    product_uuid = serializers.UUIDField(
        error_messages={
            "required": _("L'UUID du produit est requis"),
            "invalid": _("UUID de produit invalide"),
        },
    )
    price_uuid = serializers.UUIDField(
        error_messages={
            "required": _("L'UUID du prix est requis"),
            "invalid": _("UUID de prix invalide"),
        },
    )
    qty = serializers.IntegerField(
        min_value=1,
        error_messages={
            "required": _("La quantité est requise"),
            "min_value": _("La quantité doit être au moins 1"),
        },
    )


class CommandeSerializer(serializers.Serializer):
    """
    Valide la création d'une commande de restaurant.
    Validates the creation of a restaurant order.

    LOCALISATION : laboutik/serializers.py

    Utilisé par CommandeViewSet.ouvrir_commande() (POST).
    Used by CommandeViewSet.ouvrir_commande() (POST).
    """

    table_uuid = serializers.UUIDField(
        required=False,
        allow_null=True,
        error_messages={
            "invalid": _("UUID de table invalide"),
        },
    )
    uuid_pv = serializers.UUIDField(
        error_messages={
            "required": _("L'UUID du point de vente est requis"),
            "invalid": _("UUID du point de vente invalide"),
        },
    )
    articles = ArticleCommandeSerializer(many=True)

    def validate_articles(self, value):
        """
        Vérifie que la liste d'articles n'est pas vide.
        Checks that the articles list is not empty.
        """
        if not value:
            raise serializers.ValidationError(
                _("La commande doit contenir au moins un article")
            )
        return value


# --------------------------------------------------------------------------- #
#  Serializer Phase 5 — Cloture de caisse                                     #
#  Phase 5 serializer — Cash register closure                                 #
# --------------------------------------------------------------------------- #


class ClotureSerializer(serializers.Serializer):
    """
    Valide les donnees de cloture de caisse.
    Validates cash register closure data.

    LOCALISATION : laboutik/serializers.py

    Utilise par CaisseViewSet.cloturer() (POST).
    Le datetime_ouverture est calcule automatiquement (1ere vente apres derniere cloture).
    Used by CaisseViewSet.cloturer() (POST).
    datetime_ouverture is computed automatically (1st sale after last closure).
    """

    uuid_pv = serializers.UUIDField(
        error_messages={
            "required": _("L'UUID du point de vente est requis"),
            "invalid": _("UUID du point de vente invalide"),
        },
    )


# --------------------------------------------------------------------------- #
#  Serializer Phase 5 — Export rapport cloture                                 #
#  Phase 5 serializer — Closure report export                                  #
# --------------------------------------------------------------------------- #


class ClientIdentificationSerializer(serializers.Serializer):
    """
    Valide le formulaire d'identification client POS (adhesion, recharge, ou mixte).
    Validates the POS client identification form (membership, top-up, or mixed).

    LOCALISATION : laboutik/serializers.py

    Utilise par PaiementViewSet.identifier_client() quand le formulaire est soumis
    (pas pour le scan NFC — dans ce cas, l'identification vient de la carte).
    Used by PaiementViewSet.identifier_client() when the form is submitted
    (not for NFC scan — in that case, identification comes from the card).

    Les noms de champs (email_adhesion, prenom_adhesion, nom_adhesion) sont conserves
    pour compatibilite avec payer() qui les lit depuis le POST.
    Field names are kept for backwards compatibility with payer() which reads them from POST.
    """

    email_adhesion = serializers.EmailField(
        error_messages={
            "required": _("L'email est obligatoire"),
            "invalid": _("Email invalide"),
        },
    )
    prenom_adhesion = serializers.CharField(
        required=True,
        max_length=200,
        error_messages={
            "required": _("Le prénom est obligatoire"),
            "blank": _("Le prénom ne peut pas être vide"),
        },
    )
    nom_adhesion = serializers.CharField(
        required=True,
        max_length=200,
        error_messages={
            "required": _("Le nom est obligatoire"),
            "blank": _("Le nom ne peut pas être vide"),
        },
    )
    tag_id = serializers.CharField(
        required=False,
        allow_blank=True,
    )


class CorrectionPaiementSerializer(serializers.Serializer):
    """
    Valide les donnees d'une correction de moyen de paiement.
    Validates payment method correction data.

    LOCALISATION : laboutik/serializers.py

    Utilise par PaiementViewSet.corriger_moyen_paiement() (POST).
    Used by PaiementViewSet.corriger_moyen_paiement() (POST).

    Seuls les moyens ESP (CA), CB (CC) et CHQ (CH) sont autorises.
    Only CASH (CA), CC (CC) and CHECK (CH) are allowed.
    """

    ligne_uuid = serializers.UUIDField(
        required=True,
        error_messages={
            "required": _("L'identifiant de la ligne est obligatoire"),
            "invalid": _("Identifiant de ligne invalide"),
        },
    )
    nouveau_moyen = serializers.ChoiceField(
        choices=[
            ("CA", _("Especes")),
            ("CC", _("Carte bancaire")),
            ("CH", _("Cheque")),
        ],
        required=True,
        error_messages={
            "required": _("Le nouveau moyen de paiement est obligatoire"),
            "invalid_choice": _("Moyen de paiement invalide"),
        },
    )
    raison = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    def validate_raison(self, value):
        """Nettoie la raison (strip). / Cleans the reason (strip)."""
        return value.strip() if value else ""


class FondDeCaisseSerializer(serializers.Serializer):
    """
    Valide le montant du fond de caisse (en euros, avec virgule FR acceptee).
    Validates cash float amount (in euros, FR comma accepted).

    LOCALISATION : laboutik/serializers.py

    Utilise par CaisseViewSet.fond_de_caisse() (POST).
    Used by CaisseViewSet.fond_de_caisse() (POST).
    """

    montant_euros = serializers.CharField(
        required=True,
        error_messages={
            "required": _("Le montant est obligatoire"),
        },
    )

    def validate_montant_euros(self, value):
        """
        Convertit le montant euros (string) en centimes (int).
        Accepte la virgule comme separateur decimal (locale FR).
        / Converts euros amount (string) to cents (int).
        Accepts comma as decimal separator (FR locale).
        """
        from decimal import Decimal, InvalidOperation

        try:
            montant_nettoye = value.replace(",", ".")
            montant_decimal = Decimal(montant_nettoye)
            montant_centimes = int(round(montant_decimal * 100))
        except (InvalidOperation, ValueError):
            raise serializers.ValidationError(_("Montant invalide"))

        if montant_centimes < 0:
            raise serializers.ValidationError(_("Le montant ne peut pas etre negatif"))

        return montant_centimes


class SortieDeCaisseSerializer(serializers.Serializer):
    """
    Valide une sortie de caisse avec ventilation par coupure.
    Le total est recalcule cote serveur (ne jamais faire confiance au client).
    / Validates a cash withdrawal with denomination breakdown.
    Total is recalculated server-side (never trust the client).

    LOCALISATION : laboutik/serializers.py

    Utilise par CaisseViewSet.creer_sortie_de_caisse() (POST).
    Used by CaisseViewSet.creer_sortie_de_caisse() (POST).
    """

    uuid_pv = serializers.UUIDField(
        required=True,
        error_messages={
            "required": _("Le point de vente est obligatoire"),
            "invalid": _("Identifiant de point de vente invalide"),
        },
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class EnvoyerRapportSerializer(serializers.Serializer):
    """
    Valide l'adresse email pour l'envoi du rapport de cloture.
    Validates the email address for sending the closure report.

    LOCALISATION : laboutik/serializers.py

    Utilise par CaisseViewSet.envoyer_rapport() (POST).
    Used by CaisseViewSet.envoyer_rapport() (POST).
    """

    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        error_messages={
            "invalid": _("Adresse email invalide"),
        },
    )
