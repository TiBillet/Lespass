import re
import uuid as uuid_module
from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection, transaction
from django.db import connection, IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets, status, serializers
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.core.cache import cache

from ApiBillet.permissions import TenantAdminApiPermission
from ApiBillet.views import get_permission_Api_ALL_Admin
from AuthBillet.models import TibilletUser
from BaseBillet.models import Event, PostalAddress, LigneArticle, Product, Reservation, Membership, logger
from crowds.models import Initiative, BudgetItem, Participation, Vote
from .permissions import SemanticApiKeyPermission
from .serializers import (
    EventSchemaSerializer,
    EventCreateSerializer,
    PostalAddressAsSchemaSerializer,
    PostalAddressCreateSerializer, SemanticProductFromSaleLineSerializer,
    ProductCreateSerializer,
    ProductSchemaSerializer,
    ReservationCreateSerializer,
    ReservationSchemaSerializer,
    MembershipCreateSerializer,
    MembershipSchemaSerializer,
    MembershipStatusSerializer,
    WalletRefillCreateSerializer,
    InitiativeSchemaSerializer,
    InitiativeCreateSerializer,
    BudgetItemSchemaSerializer,
    BudgetItemCreateSerializer,
    ParticipationSchemaSerializer,
    ParticipationCreateSerializer,
    PageSchemaSerializer,
    PageCreateSerializer,
    BlocSchemaSerializer,
    BlocCreateSerializer,
    CHAMPS_PAGE_AUTORISES,
    CHAMPS_BLOC_AUTORISES,
    CHAMPS_TEXTE_RICHE,
    CHAMPS_FICHIER,
    CHAMPS_URL_A_NEUTRALISER,
    _validate_uploaded_image,
)
from pages.models import Page, Bloc, valider_slug_non_reserve
from Administration.utils import clean_html, url_a_schema_dangereux


def get_objet_par_uuid_ou_404(model, uuid_recu, **filtres_supplementaires):
    """
    Recupere un objet via son uuid, ou leve Http404 si l'uuid est mal forme.
    / Get an object by its uuid, or raise Http404 if the uuid is malformed.

    LOCALISATION : api_v2/views.py

    Pourquoi : le routeur DRF capture n'importe quelle chaine dans l'URL
    (regex `[^/.]+`). Un robot peut appeler /api/v2/events/<slug>/ avec un
    slug au lieu d'un uuid. Sans cette verification, Django essaie de
    convertir le slug en UUID pour le filtre ORM, leve ValidationError,
    et renvoie une 500. On veut une 404 propre : la ressource n'existe pas.
    / The DRF router captures any string in the URL. A crawler may pass a
    slug instead of a uuid. Without this guard Django raises ValidationError
    on the UUIDField (-> HTTP 500). We want a clean 404 instead.

    Voir piege 9.76 (tests/PIEGES.md) : meme correctif sur detail_vente().
    / See pitfall 9.76: same fix applied to detail_vente().
    """
    # On verifie d'abord que la chaine recue est un uuid valide.
    # / First check the received string is a valid uuid.
    try:
        uuid_module.UUID(str(uuid_recu))
    except (ValueError, TypeError, AttributeError):
        # uuid mal forme -> la ressource ne peut pas exister -> 404
        # / malformed uuid -> resource cannot exist -> 404
        raise Http404("Invalid identifier")

    return get_object_or_404(model, uuid=uuid_recu, **filtres_supplementaires)


def get_event_par_identifiant_ou_404(identifiant):
    """
    Resout un evenement a partir d'un identifiant qui peut etre un uuid OU le slug
    utilise par le controleur front (EventMVT). Leve Http404 si rien ne correspond.
    / Resolve an event from an identifier that can be a uuid OR the front slug.

    LOCALISATION : api_v2/views.py

    Deux formes acceptees, comme cote front (cf EventMVT.retrieve dans BaseBillet) :
    - uuid complet (ex: 7d51dee7-1234-...) -> lookup direct par uuid ;
    - slug (ex: mon-evenement-260620-0900-7d51dee7) -> les 8 derniers caracteres
      hex sont le debut de l'uuid (Event.slug se termine par uuid.hex[:8]). On
      cherche via uuid__startswith (un LIKE texte : pas de ValidationError), puis
      en dernier recours via slug__startswith.
    / Two accepted forms, like the front: a full uuid, or the slug whose last 8 hex
      are the start of the uuid (uuid__startswith), with a slug__startswith fallback.

    Pas de filtre `published` : on resout n'importe quel evenement, comme
    EventMVT.retrieve. / No `published` filter: resolve any event, like the front.
    """
    identifiant = str(identifiant)

    # 1. Identifiant deja sous forme d'uuid valide -> lookup direct.
    # / Identifier is already a valid uuid -> direct lookup.
    try:
        uuid_module.UUID(identifiant)
        event = Event.objects.filter(uuid=identifiant).first()
        if event is None:
            raise Http404("Event not found")
        return event
    except (ValueError, TypeError, AttributeError):
        # Pas un uuid : on tente la resolution par slug.
        # / Not a uuid: fall through to slug resolution.
        pass

    # 2. Slug front : les 8 derniers caracteres hex sont le debut de l'uuid.
    # / Front slug: the last 8 hex characters are the start of the uuid.
    correspondance_hex8 = re.search(r'([0-9a-fA-F]{8})$', identifiant)
    if correspondance_hex8:
        debut_uuid = correspondance_hex8.group(1)
        event = Event.objects.filter(uuid__startswith=debut_uuid).first()
        if event is not None:
            return event

    # 3. Dernier recours : recherche par slug complet.
    # / Last resort: lookup by full slug.
    event = Event.objects.filter(slug__startswith=identifiant).first()
    if event is None:
        raise Http404("Event not found")
    return event


def _ressemble_uuid(valeur) -> bool:
    """True si la chaine est un UUID valide. / True if the string is a valid UUID."""
    try:
        uuid_module.UUID(str(valeur))
        return True
    except (ValueError, TypeError):
        return False


def _appliquer_fichiers_multipart(request, bloc):
    """Applique les fichiers uploades IMAGE (multipart) sur les champs fichier du bloc.
    / Applies uploaded IMAGE (multipart) files onto the block's file fields.

    Images validees par Pillow. L'upload de fichier VIDEO est volontairement retire :
    pour une video, utiliser le bloc EMBED (embed_url YouTube/Vimeo/PeerTube, rendu en iframe).
    / Images validated by Pillow. Video file upload is intentionally removed:
    use the EMBED block (embed_url) for videos.
    """
    if not hasattr(request, "FILES"):
        return
    from api_v2.serializers import _validate_uploaded_image
    # Upload de fichiers IMAGE uniquement (image principale, secondaire, photo d'auteur).
    # L'upload de fichiers VIDEO est volontairement retire : pour une video, utiliser le
    # bloc EMBED (embed_url YouTube/Vimeo/PeerTube, rendu en iframe). Cela evite d'heberger
    # des fichiers video lourds. / IMAGE files only. Video file upload is intentionally
    # removed: use the EMBED block (embed_url) for videos. Avoids hosting heavy video files.
    for nom_fichier in ("image", "image_secondaire", "auteur_photo"):
        fichier = request.FILES.get(nom_fichier)
        if fichier:
            _validate_uploaded_image(fichier)
            setattr(bloc, nom_fichier, fichier)


class CrowdInitiativeViewSet(viewsets.ViewSet):
    """
    Semantic Project API for Crowds initiatives.

    Header: Authorization: Api-Key <key>
    Response: schema.org/Project-like JSON.
    """

    permission_classes = [SemanticApiKeyPermission]
    lookup_field = "uuid"
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def list(self, request):
        queryset = Initiative.objects.filter(archived=False)
        serializer = InitiativeSchemaSerializer(queryset, many=True)
        return Response({"results": serializer.data})

    def retrieve(self, request, uuid=None):
        initiative = get_object_or_404(Initiative, uuid=uuid, archived=False)
        serializer = InitiativeSchemaSerializer(initiative)
        return Response(serializer.data)

    def create(self, request):
        input_serializer = InitiativeCreateSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        initiative = input_serializer.save()
        output_serializer = InitiativeSchemaSerializer(initiative)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, uuid=None):
        initiative = get_object_or_404(Initiative, uuid=uuid)
        initiative.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="budget-items")
    def budget_items(self, request, uuid=None):
        initiative = get_object_or_404(Initiative, uuid=uuid)
        if request.method.lower() == "get":
            items = initiative.budget_items.all().order_by("-created_at")
            serializer = BudgetItemSchemaSerializer(items, many=True)
            return Response({"results": serializer.data})

        input_serializer = BudgetItemCreateSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        state = input_serializer.validated_data.get("actionStatus") or BudgetItem.State.REQUESTED
        if state in [BudgetItem.State.APPROVED, BudgetItem.State.REJECTED]:
            if not (request.user.is_staff or request.user.is_superuser):
                state = BudgetItem.State.REQUESTED
        item = BudgetItem.objects.create(
            initiative=initiative,
            contributor=request.user,
            description=input_serializer.validated_data.get("description") or "",
            amount=input_serializer.amount or 0,
            state=state,
            validator=request.user if state == BudgetItem.State.APPROVED else None,
        )
        serializer = BudgetItemSchemaSerializer(item)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="votes")
    def votes(self, request, uuid=None):
        initiative = get_object_or_404(Initiative, uuid=uuid, archived=False)
        if request.method.lower() == "post":
            obj, created = Vote.objects.get_or_create(initiative=initiative, user=request.user)
            count = Vote.objects.filter(initiative=initiative).count()
            return Response({"count": count, "created": created}, status=status.HTTP_201_CREATED)
        count = Vote.objects.filter(initiative=initiative).count()
        return Response({"count": count})

    @action(detail=True, methods=["get", "post"], url_path="participations")
    def participations(self, request, uuid=None):
        initiative = get_object_or_404(Initiative, uuid=uuid, archived=False)
        if request.method.lower() == "post":
            input_serializer = ParticipationCreateSerializer(data=request.data, context={"request": request})
            input_serializer.is_valid(raise_exception=True)
            participation = Participation.objects.create(
                initiative=initiative,
                participant=request.user,
                description=input_serializer.validated_data.get("description") or "",
                amount=getattr(input_serializer, "amount", None),
                state=Participation.State.REQUESTED,
            )
            serializer = ParticipationSchemaSerializer(participation)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        items = initiative.participations.select_related("participant").all()
        serializer = ParticipationSchemaSerializer(items, many=True)
        return Response({"results": serializer.data})


class EventViewSet(viewsets.ViewSet):
    """
    Semantic Event API (list + retrieve + create + delete) implemented with classic ViewSet.

    Header: Authorization: Api-Key <key>
    Response: JSON-LD compliant with https://schema.org/Event
    """

    permission_classes = [SemanticApiKeyPermission]
    lookup_field = "uuid"
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    # Bornes du parametre `next_days`. Au-dela d'un an, autant tout demander.
    # / Bounds for the `next_days` parameter.
    NEXT_DAYS_MINIMUM = 1
    NEXT_DAYS_MAXIMUM = 366

    def list(self, request):
        """
        Liste les evenements publies. / List published events.

        Parametres de filtrage du temps (facultatifs) :
        - `only_futur=1`  : les evenements a venir (depuis hier)
        - `next_days=30`  : les evenements des N prochains jours (depuis hier)
        `next_days` l'emporte sur `only_futur` s'ils sont fournis tous les deux.

        On part d'HIER, et non de maintenant : un evenement commence hier soir est
        encore d'actualite. L'agenda du site part lui aussi d'hier.
        / We start from YESTERDAY, not now: an event that started last night is still
        relevant. The site's agenda also starts from yesterday.

        EN REVANCHE, cette API est PLUS LARGE que l'agenda : elle garde aussi les
        evenements EN COURS — commences il y a longtemps, mais qui ne sont pas encore
        termines (un festival d'une semaine, par exemple). C'est le role du
        `end_datetime__gte`, que l'agenda n'a pas.
        / BUT this API is BROADER than the agenda: it also keeps ONGOING events (started
        long ago, not finished yet — a week-long festival). That is what `end_datetime__gte`
        does; the agenda has no such clause.
        """
        only_futur = request.GET.get("only_futur", None)
        next_days = request.GET.get("next_days", None)
        filter = request.GET.get("filter", None)

        queryset = Event.objects.filter(published=True)

        # timezone.now() est deja "aware" (UTC) et se compare correctement a un
        # DateTimeField. Inutile de bricoler la timezone du tenant : le filtrage se fait
        # sur un instant, pas sur un affichage.
        # / timezone.now() is already aware (UTC) and compares correctly to a DateTimeField.
        debut_de_la_fenetre = timezone.now() - timedelta(days=1)

        # Un evenement est retenu s'il COMMENCE apres la borne, ou s'il SE TERMINE apres
        # (donc s'il est en cours). / Keep events starting after the bound, or still running.
        est_a_venir_ou_en_cours = Q(datetime__gte=debut_de_la_fenetre) | Q(
            end_datetime__gte=debut_de_la_fenetre
        )

        if next_days:
            try:
                nombre_de_jours = int(next_days)
            except (TypeError, ValueError):
                return Response(
                    {"error": _("next_days doit être un nombre entier de jours.")},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not (self.NEXT_DAYS_MINIMUM <= nombre_de_jours <= self.NEXT_DAYS_MAXIMUM):
                return Response(
                    {
                        "error": _(
                            "next_days doit être compris entre %(mini)s et %(maxi)s."
                        )
                        % {
                            "mini": self.NEXT_DAYS_MINIMUM,
                            "maxi": self.NEXT_DAYS_MAXIMUM,
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            fin_de_la_fenetre = timezone.now() + timedelta(days=nombre_de_jours)
            queryset = queryset.filter(est_a_venir_ou_en_cours).filter(
                datetime__lt=fin_de_la_fenetre
            )

        elif only_futur:
            queryset = queryset.filter(est_a_venir_ou_en_cours)

        if filter:
            # Filter by name and descriptions
            queryset = queryset.filter(
                Q(name__icontains=filter) |
                Q(short_description__icontains=filter) |
                Q(long_description__icontains=filter)
            )

        serializer = EventSchemaSerializer(queryset, many=True)
        # Non-paginated wrapper for consistency with tests
        return Response({"results": serializer.data})

    def retrieve(self, request, uuid=None):
        # Accepte un uuid OU le slug du front (cf EventMVT.retrieve cote front).
        # / Accepts a uuid OR the front slug (see EventMVT.retrieve on the front).
        event = get_event_par_identifiant_ou_404(uuid)
        serializer = EventSchemaSerializer(event)
        return Response(serializer.data)

    def create(self, request):
        input_serializer = EventCreateSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        event = input_serializer.save()
        # Handle optional image uploads (multipart) with strict validation
        updated_fields = []
        if hasattr(request, "FILES"):
            img_f = request.FILES.get("img")
            if img_f:
                # validated in serializer.validate()
                event.img = img_f
                updated_fields.append("img")
            sticker_f = request.FILES.get("sticker_img")
            if sticker_f:
                event.sticker_img = sticker_f
                updated_fields.append("sticker_img")
            if updated_fields:
                event.save(update_fields=updated_fields)
        output_serializer = EventSchemaSerializer(event)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, uuid=None):
        event = get_objet_par_uuid_ou_404(Event, uuid)
        event.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="link-address", permission_classes=[SemanticApiKeyPermission])
    def link_address(self, request, uuid=None, **kwargs):
        """
        Link a PostalAddress to this Event.
        Accepts either:
        - {"postalAddressId": <int>} to link an existing address, or
        - a schema.org PostalAddress payload to create & link on the fly.
        Returns the updated Event representation.
        """
        event = get_objet_par_uuid_ou_404(Event, uuid)
        addr_id = request.data.get("postalAddressId")
        address = None
        if addr_id:
            try:
                address = PostalAddress.objects.get(id=int(addr_id))
            except (PostalAddress.DoesNotExist, ValueError, TypeError):
                return Response({"detail": "postalAddressId not found"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Try to create from schema.org body
            pa_serializer = PostalAddressCreateSerializer(data=request.data, context={"request": request})
            if not pa_serializer.is_valid():
                return Response(pa_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            address = pa_serializer.save()
        # Link and save
        event.postal_address = address
        event.save(update_fields=["postal_address"])
        return Response(EventSchemaSerializer(event).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="link-product", permission_classes=[SemanticApiKeyPermission])
    def link_product(self, request, uuid=None, **kwargs):
        """
        Attache un ou plusieurs produits EXISTANTS a cet evenement.
        / Attach one or several EXISTING products to this event.

        LOCALISATION : api_v2/views.py — EventViewSet

        Un meme produit peut etre partage sur plusieurs evenements grace a la
        relation ManyToMany Event.products. Cette route relie des produits
        DEJA crees, sans en creer de nouveau (contrairement a
        POST /api/v2/products/ qui cree le produit puis l'attache).
        / The same product can be shared across several events via the
        ManyToMany Event.products. This route links ALREADY created products
        without creating a new one.

        Formes de body acceptees (souples) :
        - {"productId": "<uuid>"}                          (un seul produit)
        - {"productIds": ["<uuidA>", "<uuidB>"]}           (plusieurs)
        - {"product": {"@type": "Product", "identifier": "<uuid>"}}
        - {"products": ["<uuid>", {"identifier": "<uuid>"}]}

        Renvoie l'evenement mis a jour (schema.org/Event).
        / Returns the updated Event (schema.org/Event).
        """
        event = get_objet_par_uuid_ou_404(Event, uuid)

        # On rassemble les valeurs depuis les cles tolerees.
        # / Collect values from the accepted keys.
        valeurs_brutes = []
        for cle in ("productIds", "products", "productId", "product"):
            valeur = request.data.get(cle)
            if valeur is None:
                continue
            if isinstance(valeur, list):
                valeurs_brutes.extend(valeur)
            else:
                valeurs_brutes.append(valeur)

        # On extrait l'UUID de chaque valeur (string directe ou objet schema.org).
        # / Extract the UUID from each value (plain string or schema.org object).
        product_uuids = []
        for valeur in valeurs_brutes:
            if isinstance(valeur, str):
                nettoye = valeur.strip()
                if nettoye:
                    product_uuids.append(nettoye)
            elif isinstance(valeur, dict):
                identifier = valeur.get("identifier") or valeur.get("id") or valeur.get("uuid")
                if identifier:
                    product_uuids.append(str(identifier).strip())

        # Dedoublonnage en gardant l'ordre / De-duplicate keeping order
        product_uuids = list(dict.fromkeys(product_uuids))

        if not product_uuids:
            return Response(
                {"detail": _("No product identifier provided. Use productId or productIds.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # On verifie que TOUS les produits existent AVANT d'attacher quoi que ce
        # soit (pas d'attachement partiel si un uuid est faux).
        # / Verify ALL products exist BEFORE attaching anything (no partial link).
        produits = []
        for product_uuid in product_uuids:
            try:
                uuid_module.UUID(str(product_uuid))
            except (ValueError, TypeError, AttributeError):
                return Response(
                    {"detail": f"Invalid product identifier: {product_uuid}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                produits.append(Product.objects.get(uuid=product_uuid))
            except Product.DoesNotExist:
                return Response(
                    {"detail": f"Product not found: {product_uuid}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Attachement M2M (idempotent : add() ne cree pas de doublon)
        # / M2M attachment (idempotent: add() does not duplicate)
        for produit in produits:
            event.products.add(produit)

        return Response(EventSchemaSerializer(event).data, status=status.HTTP_200_OK)


class PostalAddressViewSet(viewsets.ViewSet):
    """
    Semantic PostalAddress API (list, retrieve, create, delete) using classic ViewSet.

    Header: Authorization: Api-Key <key>
    Representation: schema.org/PostalAddress
    """

    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def list(self, request):
        qs = PostalAddress.objects.all()
        ser = PostalAddressAsSchemaSerializer(qs, many=True)
        # Keep the same list wrapper convention as Events
        return Response({"results": ser.data})

    def retrieve(self, request, pk=None):
        instance = get_object_or_404(PostalAddress, id=pk)
        data = PostalAddressAsSchemaSerializer(instance).data
        return Response(data)

    def create(self, request):
        ser = PostalAddressCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        addr = ser.save()
        # Handle optional image uploads (multipart)
        if hasattr(request, "FILES"):
            updated = []
            img_f = request.FILES.get("img")
            if img_f:
                addr.img = img_f
                updated.append("img")
            sticker_f = request.FILES.get("sticker_img")
            if sticker_f:
                addr.sticker_img = sticker_f
                updated.append("sticker_img")
            if updated:
                addr.save(update_fields=updated)
        out = PostalAddressAsSchemaSerializer(addr).data
        return Response(out, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        instance = get_object_or_404(PostalAddress, id=pk)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductViewSet(viewsets.ViewSet):
    """
    Semantic Product API (list + retrieve + create).
    API Produit semantique (liste + detail + creation).

    Header: Authorization: Api-Key <key>
    Response: JSON-LD compliant with https://schema.org/Product
    """

    permission_classes = [SemanticApiKeyPermission]
    # Le lookup detail se fait par uuid (le routeur passe `uuid`, pas `pk`).
    # Sans ca, DRF utilise `pk` et `retrieve(uuid=...)` leve un TypeError.
    # / Detail lookup is by uuid (the router passes `uuid`, not `pk`).
    lookup_field = "uuid"
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def list(self, request):
        queryset = Product.objects.filter(archive=False, publish=True)
        serializer = ProductSchemaSerializer(queryset, many=True)
        return Response({"results": serializer.data})

    def retrieve(self, request, uuid=None):
        product = get_object_or_404(Product, uuid=uuid, archive=False)
        serializer = ProductSchemaSerializer(product)
        return Response(serializer.data)

    def create(self, request):
        input_serializer = ProductCreateSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        product = input_serializer.save()
        output_serializer = ProductSchemaSerializer(product)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)



class ReservationViewSet(viewsets.ViewSet):
    """
    Semantic Reservation API (create + retrieve).
    API Reservation semantique (creation + detail).
    """

    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    lookup_field = "uuid"

    def create(self, request):
        input_serializer = ReservationCreateSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        reservation = input_serializer.save()
        output_serializer = ReservationSchemaSerializer(reservation)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, uuid=None):
        reservation = get_object_or_404(Reservation, uuid=uuid)
        serializer = ReservationSchemaSerializer(reservation)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MembershipViewSet(viewsets.ViewSet):
    """
    Semantic Membership API (create + retrieve).
    API Adhesion semantique (creation + detail).
    """

    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    lookup_field = "uuid"

    def create(self, request):
        input_serializer = MembershipCreateSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        membership = input_serializer.save()
        output_serializer = MembershipSchemaSerializer(membership)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, uuid=None):
        membership = get_object_or_404(Membership, uuid=uuid)
        serializer = MembershipSchemaSerializer(membership)
        return Response(serializer.data, status=status.HTTP_200_OK)


    @action(detail=False, methods=["get"], url_path="by-wallet")
    def by_wallet(self, request):
        """
        Liste les adhesions d'un porteur a partir de son wallet Fedow.
        / Lists a holder's memberships from their Fedow wallet uuid.
        Auth + IP + permission `membership` geres par SemanticApiKeyPermission.
        """
        wallet_uuid = request.query_params.get("wallet_uuid")
        if not wallet_uuid:
            return Response({"detail": "wallet_uuid is required"}, status=status.HTTP_400_BAD_REQUEST)

        user = TibilletUser.objects.filter(wallet__uuid=wallet_uuid).first()
        memberships = user.memberships.all() if user else Membership.objects.none()
        serializer = MembershipStatusSerializer(memberships, many=True)
        return Response(
            {"wallet_uuid": wallet_uuid, "memberships": serializer.data},
            status=status.HTTP_200_OK,
        )


# Plafond par recharge cadeau, en unite brute (cf SPEC API_GIFT_REFILL).
# / Per-call gift refill cap, in raw unit.
GIFT_REFILL_MAX_AMOUNT = 10000


class WalletRefillViewSet(viewsets.ViewSet):
    """
    Recharge de tokens cadeau (TNF) sur la tirelire d'un user.
    / Gift token (TNF) wallet refill.

    LOCALISATION : api_v2/views.py

    Header : Authorization: Api-Key <key> (cle restreinte a un asset cadeau via
    ExternalApiKey.gift_asset).
    Header OBLIGATOIRE : Idempotency-Key. Comme cet endpoint credite des tokens,
    la cle d'idempotence est exigee (anti double-credit). Elle est stockee en
    base sur LigneArticle.idempotency_key (contrainte d'unicite = verrou).
    / MANDATORY header: Idempotency-Key. This endpoint credits tokens, so the
    idempotency key is required (anti double-credit). Stored in DB on
    LigneArticle.idempotency_key (unique constraint = lock).

    FLUX :
    1. Recupere l'objet cle API pour connaitre l'asset cadeau autorise.
    2. Valide le payload (email, asset uuid, amount entier positif).
    3. Resout l'asset et verifie qu'il est de categorie cadeau (TNF).
    4. Verifie que l'asset demande est bien celui autorise sur la cle.
    5. Verifie le plafond.
    6. Exige la cle d'idempotence (400 si absente).
    7. Cree/recupere l'user, verifie Fedow.
    8. Verrou d'idempotence en base, puis credite la tirelire.
    """
    permission_classes = [SemanticApiKeyPermission]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def create(self, request):
        from ApiBillet.permissions import get_apikey_valid
        from fedow_public.models import AssetFedowPublic
        from fedow_connect.models import FedowConfig
        from fedow_connect.fedow_api import FedowAPI
        from AuthBillet.utils import get_or_create_user

        # 1. Recupere l'objet cle API pour connaitre l'asset autorise
        # / Get the API key object to know the allowed asset
        api_key = get_apikey_valid(self)
        if not api_key or not api_key.gift_asset_id:
            return Response({"detail": _("API key not allowed for gift refill.")},
                            status=status.HTTP_403_FORBIDDEN)

        # 2. Validation du payload / Validate payload
        input_serializer = WalletRefillCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        email = input_serializer.validated_data["email"]
        asset_uuid = input_serializer.validated_data["asset"]
        amount = input_serializer.validated_data["amount"]

        # 3. Resolution de l'asset / Resolve asset
        asset = get_object_or_404(AssetFedowPublic, uuid=asset_uuid)

        # 4. Categorie rechargeable obligatoire (non adossee a l'euro)
        # / Refillable category required (not euro-backed)
        if asset.category not in AssetFedowPublic.REFILLABLE_CATEGORIES:
            return Response({"detail": _("This asset category cannot be topped up.")},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # 5. L'asset doit etre celui autorise sur la cle / Must match key asset
        if asset.uuid != api_key.gift_asset_id:
            return Response({"detail": _("Asset not allowed for this API key.")},
                            status=status.HTTP_403_FORBIDDEN)

        # 6. Plafond / Cap
        if amount > GIFT_REFILL_MAX_AMOUNT:
            return Response({"detail": _("Amount above the maximum allowed.")},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # 6. Cle d'idempotence OBLIGATOIRE (anti double-credit, stockee en base).
        # La cle est fournie par le client (header Idempotency-Key). Comme cet
        # endpoint credite des tokens, on l'EXIGE : sans cle, pas de filet.
        # / Mandatory idempotency key (anti double-credit, stored in DB). The key
        # is client-provided (Idempotency-Key header). This endpoint credits
        # tokens, so we REQUIRE it: no key, no safety net.
        from BaseBillet.models import LigneArticle

        idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY")
        if not idempotency_key or not str(idempotency_key).strip():
            return Response(
                {"detail": _("Idempotency-Key header is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        idempotency_key = str(idempotency_key).strip()

        # 7. User / User
        user = get_or_create_user(email)
        if not user:
            return Response({"detail": _("Invalid email.")},
                            status=status.HTTP_406_NOT_ACCEPTABLE)

        # Fedow dispo ? / Fedow available?
        if not FedowConfig.get_solo().can_fedow():
            return Response({"detail": _("Fedow service unavailable.")},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # 8. Verrou d'idempotence en base.
        # La contrainte d'unicite sur LigneArticle.idempotency_key garantit
        # qu'une seule ligne existe par cle. On gere les rejeux :
        # - meme cle + corps DIFFERENT -> 409 (cle reutilisee a tort)
        # - meme cle + ligne VALID     -> 208 (on renvoie la transaction stockee)
        # - meme cle + ligne CREATED   -> 409 (un credit est deja en cours)
        # - meme cle + ligne FAILED    -> on RETENTE (rien n'a ete credite)
        # / DB idempotency lock. Unique constraint guarantees one line per key.
        ligne_existante = LigneArticle.objects.filter(
            idempotency_key=idempotency_key,
        ).first()

        if ligne_existante is not None:
            # Le corps doit etre identique a la 1ere requete portant cette cle.
            # On compare l'email du DESTINATAIRE RESOLU (user.email), pas l'email
            # brut du payload : get_or_create_user peut normaliser l'email, et on
            # veut qu'un meme destinataire ne declenche pas un faux 409. Un
            # destinataire different (autre user) declenche bien un 409.
            # / The body must match the first request using this key. We compare
            # the RESOLVED recipient email (user.email), not the raw payload email:
            # get_or_create_user may normalize it. A different recipient -> 409.
            email_precedent = (ligne_existante.metadata or {}).get("email", "")
            corps_identique = (
                ligne_existante.amount == amount
                and str(ligne_existante.asset) == str(asset.uuid)
                and email_precedent == getattr(user, "email", "")
            )
            if not corps_identique:
                return Response(
                    {"detail": _("Idempotency-Key already used with different parameters.")},
                    status=status.HTTP_409_CONFLICT,
                )

            if ligne_existante.status == LigneArticle.VALID:
                # Rejeu d'une recharge deja faite : on renvoie la transaction
                # stockee sans recrediter. / Replay of a done refill.
                return Response(
                    self._payload_money_transfer_depuis_ligne(ligne_existante),
                    status=status.HTTP_208_ALREADY_REPORTED,
                )

            if ligne_existante.status == LigneArticle.CREATED:
                # Un credit est en cours (requete concurrente ou interrompue).
                # / A credit is in progress (concurrent or interrupted request).
                return Response(
                    {"detail": _("A refill with this key is already in progress.")},
                    status=status.HTTP_409_CONFLICT,
                )

            # Statut FAILED : le credit precedent a echoue, rien n'a ete credite.
            # On REUTILISE la ligne et on retente. / FAILED: retry with same line.
            ligne_article = ligne_existante
            LigneArticle.objects.filter(pk=ligne_article.pk).update(
                status=LigneArticle.CREATED,
            )
        else:
            # Premiere requete pour cette cle : on cree la ligne "recharge cadeau"
            # AVANT d'appeler Fedow (Fedow exige metadata.ligne_article_uuid, et
            # on garde une trace comptable). La contrainte d'unicite fait office
            # de verrou contre les requetes concurrentes : la 2e create leve
            # IntegrityError -> 409. On enveloppe dans un savepoint atomic pour
            # que l'IntegrityError n'invalide pas une transaction de requete plus
            # large (ATOMIC_REQUESTS).
            # / First request for this key: create the line BEFORE calling Fedow.
            # The unique constraint acts as a lock; concurrent create raises
            # IntegrityError -> 409. Wrapped in an atomic savepoint so the error
            # does not break a wider request transaction.
            try:
                with transaction.atomic():
                    ligne_article = self._creer_ligne_article_recharge(
                        asset, amount, user, api_key, idempotency_key,
                    )
            except IntegrityError:
                return Response(
                    {"detail": _("A refill with this key is already in progress.")},
                    status=status.HTTP_409_CONFLICT,
                )

        # 9. Credit / Refill
        # IMPORTANT : l'endpoint Fedow refill_from_lespass_to_user_wallet est, par
        # defaut, concu pour la RECOMPENSE D'ADHESION : son serializer exige
        # membership_uuid / product_uuid / price_uuid (cf Fedow
        # TransactionRefilFromLespassSerializer.validate_metadata). Une recharge
        # cadeau directe n'a aucun de ces objets. Fedow prevoit pour ce cas un
        # bypass : le flag `rewarded_from_ticket_scanned` (un credit direct sans
        # contexte de vente, deja utilise pour les recompenses de scan de ticket).
        # On le reutilise ici pour un credit direct, et on garde `ligne_article_uuid`
        # pour notre tracabilite comptable.
        # / The Fedow refill endpoint is meant for MEMBERSHIP REWARD and requires
        # membership/product/price uuids. A direct gift refill has none. Fedow
        # offers a bypass flag `rewarded_from_ticket_scanned` (direct credit with
        # no sale context). We reuse it, keeping ligne_article_uuid for our audit.
        fedowAPI = FedowAPI()
        metadata = {
            "reason": f"API gift refill: {amount} {asset.name}",
            "api_key": api_key.name,
            "ligne_article_uuid": str(ligne_article.uuid),
            "rewarded_from_ticket_scanned": True,  # bypass validation vente Fedow
            "idempotency_key": idempotency_key,
        }
        try:
            reward_tx = fedowAPI.transaction.refill_from_lespass_to_user_wallet(
                user=user, amount=amount, asset=asset, metadata=metadata,
            )
        except Exception as e:
            # Echec Fedow : la ligne passe FAILED (via .update() -> aucun signal)
            # et on renvoie une erreur propre au lieu de la 500 brute precedente.
            # / Fedow failure: mark the line FAILED (via .update() -> no signal)
            # and return a clean error instead of the previous raw 500.
            LigneArticle.objects.filter(pk=ligne_article.pk).update(
                status=LigneArticle.FAILED,
            )
            logger.error(
                f"WalletRefill : echec Fedow, ligne {ligne_article.uuid} -> FAILED : {e}"
            )
            return Response({"detail": _("Wallet provider error.")},
                            status=status.HTTP_502_BAD_GATEWAY)

        # Succes : on stocke l'uuid de la transaction Fedow dans la metadata
        # (pour pouvoir reconstruire la reponse sur un rejeu idempotent), et la
        # ligne passe VALID (via .update() -> aucun trigger).
        # / Success: store the Fedow transaction uuid in metadata (to rebuild the
        # response on an idempotent replay), and mark the line VALID.
        tx_uuid = str(reward_tx.get("uuid"))
        metadata_ligne = dict(ligne_article.metadata or {})
        metadata_ligne["fedow_tx_uuid"] = tx_uuid
        LigneArticle.objects.filter(pk=ligne_article.pk).update(
            status=LigneArticle.VALID,
            metadata=metadata_ligne,
        )

        # 10. Reponse schema.org MoneyTransfer
        payload = {
            "@context": "https://schema.org",
            "@type": "MoneyTransfer",
            "identifier": tx_uuid,
            "amount": amount,
            "asset": str(asset.uuid),
            "recipient": {"@type": "Person", "email": email},
        }
        return Response(payload, status=status.HTTP_201_CREATED)

    def _payload_money_transfer_depuis_ligne(self, ligne_article):
        """
        Reconstruit le payload schema.org MoneyTransfer depuis une LigneArticle
        deja creditee (utilise pour le rejeu idempotent en 208).
        / Rebuild the schema.org MoneyTransfer payload from an already-credited
        LigneArticle (used for the idempotent 208 replay).

        LOCALISATION : api_v2/views.py — WalletRefillViewSet
        """
        meta = ligne_article.metadata or {}
        return {
            "@context": "https://schema.org",
            "@type": "MoneyTransfer",
            "identifier": meta.get("fedow_tx_uuid", ""),
            "amount": ligne_article.amount,
            "asset": str(ligne_article.asset) if ligne_article.asset else "",
            "recipient": {"@type": "Person", "email": meta.get("email", "")},
        }

    def _creer_ligne_article_recharge(self, asset, amount, user, api_key, idempotency_key=None):
        """
        Cree une LigneArticle qui trace une recharge cadeau (audit comptable).
        / Create a LigneArticle tracing a gift refill (accounting audit).

        LOCALISATION : api_v2/views.py — WalletRefillViewSet

        Un produit RECHARGE_CASHLESS dedie par asset (decision : un produit par
        asset). Tarif a 0 € : la recharge est OFFERTE (payment_method=FREE).
        Le ProductSold / PriceSold sont crees a la main pour NE PAS declencher
        d'appel Stripe (get_or_create_price_sold appelle get_id_price_stripe).
        / One RECHARGE_CASHLESS product per asset. 0 € price: the refill is
        OFFERED (payment_method=FREE). ProductSold/PriceSold created by hand to
        avoid the Stripe call done by get_or_create_price_sold.

        La ligne est creee en CREATED. Aucun trigger ne se declenche :
        _state.adding=True a la creation (cf signals.py), et trigger_R
        (RECHARGE_CASHLESS) n'existe pas. Le credit reel est fait par l'appel
        Fedow direct, pas par cette ligne -> pas de double credit.
        / Created as CREATED. No trigger fires (adding=True + no trigger_R).
        """
        from decimal import Decimal

        from BaseBillet.models import (
            Product, Price, ProductSold, PriceSold, LigneArticle,
            PaymentMethod, SaleOrigin,
        )
        from AuthBillet.models import Wallet

        # Produit + tarif de recharge dedies a cet asset (idempotent).
        # / Refill product + price dedicated to this asset (idempotent).
        produit, _created = Product.objects.get_or_create(
            categorie_article=Product.RECHARGE_CASHLESS,
            name=f"Recharge {asset.name}",
        )
        prix, _created = Price.objects.get_or_create(
            product=produit,
            name="Recharge API",
            defaults={"prix": Decimal("0")},
        )
        productsold, _created = ProductSold.objects.get_or_create(
            product=produit, event=None,
        )
        pricesold, _created = PriceSold.objects.get_or_create(
            productsold=productsold, price=prix, prix=Decimal("0"),
        )

        # wallet : seulement si c'est un vrai Wallet (None sinon). On ne fait pas
        # confiance aveuglement a user.wallet (peut etre absent).
        # / wallet: only a real Wallet (None otherwise).
        wallet = user.wallet if isinstance(getattr(user, "wallet", None), Wallet) else None

        return LigneArticle.objects.create(
            pricesold=pricesold,
            amount=amount,  # unites brutes de l'asset creditees / raw asset units credited
            qty=Decimal("1"),
            asset=asset.uuid,
            wallet=wallet,
            payment_method=PaymentMethod.FREE,  # recharge offerte / offered refill
            sale_origin=SaleOrigin.LESPASS,
            status=LigneArticle.CREATED,
            idempotency_key=idempotency_key,
            metadata={
                "source": "api_v2_wallet_refill",
                "api_key": api_key.name,
                "email": getattr(user, "email", ""),
            },
        )


class SaleViewSet(viewsets.ViewSet):
    """
    Ventes (LigneArticle) — LIST et RETRIEVE uniquement.

    - Permission: clé API + administrateur du tenant (TenantAdminApiPermission).
    - LIST: nécessite deux paramètres de requête obligatoires `start` et `end` au format ISO 8601
      avec fuseau horaire (TZ aware). Exemple: 2025-01-01T00:00:00+01:00
      Filtre les ventes dont `datetime` est comprise dans l'intervalle [start, end].
    - RETRIEVE: retourne une vente (ligne) par son UUID.

    Sémantique schema.org: chaque élément correspond à un OrderItem (ligne de commande).

    Commentaire FALC (Facile À Lire et à Comprendre):
    - Cette route liste des lignes de vente.
    - Pour la liste, vous devez donner un début et une fin de période avec l'heure et le fuseau (ex: +01:00).
    - Vous devez utiliser une clé API autorisée et être administrateur du tenant.
    """

    permission_classes = [TenantAdminApiPermission]

    def list(self, request):
        # Récupère les paramètres de dates (chaînes ISO 8601 avec TZ)
        start_str = request.query_params.get('start')
        end_str = request.query_params.get('end')

        if not start_str or not end_str:
            return Response({
                'detail': "Paramètres 'start' et 'end' obligatoires (ISO 8601, avec fuseau horaire).",
                'exemple': "?start=2025-01-01T00:00:00+01:00&end=2025-01-31T23:59:59+01:00",
            }, status=status.HTTP_400_BAD_REQUEST)

        # Parse et validation TZ-aware
        from django.utils.dateparse import parse_datetime
        try:
            start_dt = parse_datetime(start_str)
            end_dt = parse_datetime(end_str)
        except Exception:
            start_dt = None
            end_dt = None

        if not start_dt or not end_dt or start_dt.tzinfo is None or end_dt.tzinfo is None:
            return Response({
                'detail': "Dates invalides. Utilisez un format ISO 8601 avec fuseau horaire (TZ aware).",
                'exemple': "2025-01-01T00:00:00+01:00",
            }, status=status.HTTP_400_BAD_REQUEST)

        if end_dt < start_dt:
            return Response({
                'detail': "La date de fin doit être postérieure à la date de début.",
            }, status=status.HTTP_400_BAD_REQUEST)

        # Paramètre de filtre status (par défaut: uniquement VALID)
        status_param = (request.query_params.get('status') or '').strip()

        # Mapping nom lisible -> code interne
        status_map = {
            'CANCELED': 'C', 'CANCELLED': 'C', 'C': 'C',
            'REFUNDED': 'R', 'R': 'R',
            'CREATED': 'O', 'O': 'O',
            'UNPAID': 'U', 'U': 'U',
            'FREERES': 'F', 'F': 'F',
            'PAID': 'P', 'P': 'P',
            'VALID': 'V', 'V': 'V',
            'FAILED': 'D', 'D': 'D',
            'ALL': 'ALL',
        }

        # Normalise et valide
        normalized = 'V'  # défaut: VALID uniquement
        if status_param:
            key = status_param.upper()
            if key not in status_map:
                return Response({
                    'detail': "Paramètre 'status' invalide. Valeurs acceptées: ALL, CANCELED, REFUNDED, CREATED, UNPAID, FREERES, PAID, VALID, FAILED (ou leurs codes C,R,O,U,F,P,V,D).",
                }, status=status.HTTP_400_BAD_REQUEST)
            normalized = status_map[key]

        # Mise en cache de la liste pour atténuer les charges (anti DDoS applicatif)
        # Clé de cache par tenant + paramètres (inclut le filtre de status)
        schema = getattr(connection, 'schema_name', 'public')
        cache_key = f"api:sales:list:{schema}:{start_dt.isoformat()}:{end_dt.isoformat()}:{normalized}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        # Filtre des lignes de vente dans l'intervalle inclusif, avec select_related pour éviter le N+1
        queryset = (
            LigneArticle.objects
            .select_related(
                'pricesold',
                'pricesold__productsold',
                'pricesold__productsold__product',
                'pricesold__price',
            )
            .filter(datetime__gte=start_dt, datetime__lte=end_dt)
            .order_by('-datetime')
        )

        # Applique le filtre de statut, sauf si ALL
        if normalized != 'ALL':
            queryset = queryset.filter(status=normalized)

        # Sérialisation sémantique obligatoire (schema.org Product)
        items = [
            SemanticProductFromSaleLineSerializer(obj, context={'request': request}).data
            for obj in queryset
        ]

        payload = {
            '@context': 'https://schema.org',
            '@type': 'ItemList',
            'itemListElement': items,
            'startDate': start_dt.isoformat(),
            'endDate': end_dt.isoformat(),
        }

        # Cache court (60s)
        cache.set(cache_key, payload, timeout=60)
        return Response(payload)

    def retrieve(self, request, pk=None):
        # Cache du détail, par tenant + pk
        schema = getattr(connection, 'schema_name', 'public')
        cache_key = f"api:sales:detail:{schema}:{pk}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        # pk est un UUID de LigneArticle — on optimise les relations nécessaires au sérializer
        qs = (
            LigneArticle.objects
            .select_related(
                'pricesold',
                'pricesold__productsold',
                'pricesold__productsold__product',
                'pricesold__price',
            )
        )
        ligne = get_object_or_404(qs, pk=pk)

        # Retour sémantique Product obligatoire
        data = SemanticProductFromSaleLineSerializer(ligne, context={'request': request}).data

        # Cache léger (120s)
        cache.set(cache_key, data, timeout=120)
        return Response(data)

    def get_permissions(self):
        # Pour toutes les actions (LIST et RETRIEVE dans ce ViewSet), on exige:
        # - clé API valide avec droit "sale"
        # - utilisateur admin du tenant
        return get_permission_Api_ALL_Admin(self)


class PageViewSet(viewsets.ViewSet):
    """API semantique des Pages (WebPage). / Semantic Pages API (WebPage).

    Header: Authorization: Api-Key <key> (droit `page`).
    """
    permission_classes = [SemanticApiKeyPermission]
    lookup_field = "uuid"
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def list(self, request):
        qs = Page.objects.all().order_by("position", "titre")
        return Response({"results": PageSchemaSerializer(qs, many=True).data})

    def retrieve(self, request, uuid=None):
        # uuid OU slug. / uuid OR slug.
        page = Page.objects.filter(uuid=uuid).first() if _ressemble_uuid(uuid) \
            else Page.objects.filter(slug=uuid).first()
        if not page:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(PageSchemaSerializer(page).data)

    def create(self, request):
        ser = PageCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        # Page + blocs imbriques crees ensemble (tout ou rien).
        # / Page + nested blocks created together (all or nothing).
        with transaction.atomic():
            page = ser.save()
        return Response(PageSchemaSerializer(page).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, uuid=None):
        page = get_object_or_404(Page, uuid=uuid)
        # PATCH meta seulement. / PATCH meta only.
        meta = {}
        for prop in (request.data.get("additionalProperty") or []):
            if prop.get("name") in CHAMPS_PAGE_AUTORISES:
                meta[prop["name"]] = prop.get("value")
        if "name" in request.data:
            page.titre = request.data["name"]
        if "description" in request.data:
            page.meta_description = request.data["description"]
        for nom_champ, valeur in meta.items():
            if nom_champ == "slug":
                valider_slug_non_reserve(valeur)
            setattr(page, nom_champ, valeur)

        # Page parente (isPartOf) : uuid/slug pour definir, vide/null pour retirer.
        # / Parent page (isPartOf): uuid/slug to set, empty/null to remove.
        if "isPartOf" in request.data:
            identifiant_parent = request.data["isPartOf"]
            if identifiant_parent:
                from api_v2.serializers import _resoudre_page
                parent = _resoudre_page(identifiant_parent)
                if not parent:
                    return Response({"isPartOf": [_("Page parente introuvable.")]},
                                    status=status.HTTP_400_BAD_REQUEST)
                page.parent = parent
            else:
                page.parent = None

        try:
            page.full_clean(exclude=["uuid"])
        except DjangoValidationError as e:
            return Response(e.message_dict, status=status.HTTP_400_BAD_REQUEST)
        page.save()
        return Response(PageSchemaSerializer(page).data)

    def destroy(self, request, uuid=None):
        page = get_object_or_404(Page, uuid=uuid)
        page.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="block-types")
    def block_types(self, request):
        """Catalogue des types de blocs + champs autorises (pour les agents/MCP).
        / Catalogue of block types + allowed fields (for agents/MCP)."""
        from pages.blocs_catalogue import CHAMPS_PAR_TYPE
        libelles = dict(Bloc.TYPE_BLOC_CHOICES)
        types = [
            {"type": code, "label": str(libelles.get(code, code)), "fields": champs}
            for code, champs in CHAMPS_PAR_TYPE.items()
        ]
        return Response({"blockTypes": types})

    @action(detail=True, methods=["post"], url_path="blocs")
    def ajouter_bloc(self, request, uuid=None):
        page = get_object_or_404(Page, uuid=uuid)
        # JSON -> dict normal ; multipart -> QueryDict (on aplatit en scalaires).
        # / JSON -> plain dict; multipart -> QueryDict (flatten to scalars).
        # Note : en DRF, request.data = _full_data qui inclut les fichiers uploadés.
        # On utilise .dict() pour aplatir les scalaires, puis on retire les champs fichier
        # qui sont des objets File (pas des chaînes). Ces fichiers seront appliqués
        # après le save du sérialiseur via _appliquer_fichiers_multipart.
        # / In DRF, request.data = _full_data which includes uploaded files.
        # We use .dict() to flatten scalars, then remove file fields (File objects, not strings).
        # These files are applied after the serializer save via _appliquer_fichiers_multipart.
        if hasattr(request.data, "dict"):
            donnees = request.data.dict()
            # Retire les champs fichier : ce sont des objets File, pas des scalaires.
            # / Remove file fields: they are File objects, not scalars.
            for champ_fichier in CHAMPS_FICHIER:
                donnees.pop(champ_fichier, None)
        else:
            donnees = dict(request.data)
        donnees.setdefault("position", page.blocs.count())
        ser = BlocCreateSerializer(data=donnees, context={"page": page})
        ser.is_valid(raise_exception=True)
        bloc = ser.save()
        _appliquer_fichiers_multipart(request, bloc)
        bloc.save()
        return Response(BlocSchemaSerializer(bloc).data, status=status.HTTP_201_CREATED)


class BlocViewSet(viewsets.ViewSet):
    """API semantique des Blocs (WebPageElement). / Semantic Blocs API."""
    permission_classes = [SemanticApiKeyPermission]
    lookup_field = "uuid"
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def retrieve(self, request, uuid=None):
        bloc = get_object_or_404(Bloc, uuid=uuid)
        return Response(BlocSchemaSerializer(bloc).data)

    def partial_update(self, request, uuid=None):
        bloc = get_object_or_404(Bloc, uuid=uuid)
        if "headline" in request.data:
            bloc.titre = request.data["headline"] or ""
        if "alternativeHeadline" in request.data:
            bloc.sous_titre = request.data["alternativeHeadline"] or ""
        if "text" in request.data:
            # MARKDOWN : `texte` est de la SOURCE markdown, pas du HTML — pas de
            # clean_html (mutilerait autoliens/tableaux). Securite au rendu via nh3
            # (rendre_markdown). Meme exception qu'a la creation et dans l'admin.
            # / MARKDOWN: `texte` is markdown source, not HTML — no clean_html.
            if bloc.type_bloc == "MARKDOWN":
                bloc.texte = request.data["text"] or ""
            else:
                bloc.texte = clean_html(request.data["text"] or "")
        # En multipart, additionalProperty est absent ou une string brute (pas une liste).
        # On protege la boucle pour n'iterer que sur de vraies listes.
        # / In multipart, additionalProperty is absent or a raw string (not a list).
        # Guard the loop so we only iterate over actual lists.
        proprietes = request.data.get("additionalProperty")
        if isinstance(proprietes, list):
            for prop in proprietes:
                nom = prop.get("name")
                if nom not in CHAMPS_BLOC_AUTORISES:
                    continue  # securite : jamais setattr hors whitelist
                if nom in CHAMPS_FICHIER:
                    continue  # securite : les fichiers ne se settent jamais via string
                valeur = prop.get("value")
                if nom in CHAMPS_TEXTE_RICHE:
                    valeur = clean_html(valeur or "")
                if nom in ("points_gps", "contenu") and not isinstance(valeur, list):
                    raise serializers.ValidationError(
                        {nom: _("Ce champ doit etre une liste.")})
                setattr(bloc, nom, valeur)
        # Securite : vide les champs lien a schema dangereux (javascript:, data:, vbscript:).
        # / Security: empty link fields with a dangerous scheme.
        for champ_url in CHAMPS_URL_A_NEUTRALISER:
            if url_a_schema_dangereux(getattr(bloc, champ_url, "")):
                setattr(bloc, champ_url, "")
        # Fichiers multipart (image, video, etc.) appliques avant le save unique.
        # / Multipart files (image, video, etc.) applied before the single save.
        _appliquer_fichiers_multipart(request, bloc)
        bloc.save()
        return Response(BlocSchemaSerializer(bloc).data)

    def destroy(self, request, uuid=None):
        bloc = get_object_or_404(Bloc, uuid=uuid)
        bloc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
