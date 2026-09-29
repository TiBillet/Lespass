"""
Section « Stock » dans la fiche d'un produit de caisse ou d'un fût.
/ "Stock" section in the POS product and keg product admin pages.

LOCALISATION : Administration/admin/stock_fiche_produit.py

But : gérer le stock sans quitter la fiche produit.
La section a deux parties :
- les RÉGLAGES (unité, seuil d'alerte, vente hors stock).
  Ils s'enregistrent avec le bouton Enregistrer du produit.
- les OPÉRATIONS (réception, ajustement, offert, perte).
  Elles partent tout de suite, en HTMX, sans enregistrer le produit.
  Elles réutilisent stock_action_view (inventaire/views.py).

Utilisé par POSProductAdmin et FutProductAdmin (Administration/admin/products.py).

Tout est défini au niveau du module, pas dans les ModelAdmin :
Unfold wrappe les méthodes des ModelAdmin (voir le skill unfold).
/ Everything is module-level: Unfold wraps ModelAdmin methods.
"""

from django import forms
from django.contrib import admin
from django.db import transaction
from django.db.models import F, Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.decorators import display
from unfold.widgets import (
    UnfoldAdminIntegerFieldWidget,
    UnfoldAdminSelectWidget,
    UnfoldBooleanSwitchWidget,
)

from inventaire.models import MouvementStock, Stock, TypeMouvement, UniteStock

# Id HTML de la section Stock. Sert d'ancre : /admin/.../change/#section-stock
# La colonne Stock de la liste des produits (option B) pointe dessus.
# / HTML id of the Stock section, used as an anchor by the list column.
ANCRE_SECTION_STOCK = "section-stock"


# ---------------------------------------------------------------------------
# Lecture du stock d'un produit
# / Reading a product's stock
# ---------------------------------------------------------------------------


def stock_du_produit_ou_none(produit):
    """
    Renvoie le Stock du produit, ou None s'il n'en a pas.
    / Returns the product's Stock, or None.

    produit.stock_inventaire lève une exception quand il n'y a pas de stock.
    Cette fonction évite de répéter le try/except partout.
    """
    if produit is None or produit.pk is None:
        return None
    try:
        return produit.stock_inventaire
    except Stock.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# Formulaire : champs de la section Stock
# / Form: Stock section fields
# ---------------------------------------------------------------------------


class ChampsStockFicheProduitMixin(forms.Form):
    """
    Ajoute les champs de la section Stock au formulaire d'un produit.
    / Adds the Stock section fields to a product form.

    LOCALISATION : Administration/admin/stock_fiche_produit.py

    Ces champs ne sont PAS des champs du modèle Product.
    Ils sont lus par enregistrer_section_stock() après la sauvegarde du produit.
    / These are NOT Product model fields. Read by enregistrer_section_stock().

    Utilisation : class POSProductForm(ChampsStockFicheProduitMixin, ProductAdminCustomForm)
    Un fût met unite_stock_par_defaut = UniteStock.CL.
    """

    # Unité proposée quand le produit n'a pas encore de stock
    # / Unit suggested when the product has no stock yet
    unite_stock_par_defaut = UniteStock.UN

    stock_suivi = forms.BooleanField(
        required=False,
        label=_("Suivre le stock"),
        help_text=_(
            "Cochez pour compter le stock de cet article. "
            "La caisse affichera le stock restant sur la tuile."
        ),
        widget=UnfoldBooleanSwitchWidget(),
    )

    stock_quantite_initiale = forms.IntegerField(
        required=False,
        min_value=0,
        label=_("Quantité de départ"),
        help_text=_(
            "En unité de stock (pièces, centilitres ou grammes). "
            "Elle est tracée dans le journal comme une réception « Stock initial »."
        ),
        widget=UnfoldAdminIntegerFieldWidget(),
    )

    stock_unite = forms.ChoiceField(
        required=False,
        choices=UniteStock.choices,
        label=_("Unité"),
        help_text=_("Unité de mesure du stock"),
        widget=UnfoldAdminSelectWidget(),
    )

    stock_seuil_alerte = forms.IntegerField(
        required=False,
        min_value=0,
        label=_("Seuil d'alerte"),
        help_text=_(
            "Alerte quand le stock descend sous ce seuil (vide = pas d'alerte)"
        ),
        widget=UnfoldAdminIntegerFieldWidget(),
    )

    stock_vente_hors_stock = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Autoriser vente hors stock"),
        help_text=_("Si coché, la vente reste possible même en rupture de stock"),
        widget=UnfoldBooleanSwitchWidget(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Préremplit les réglages depuis le stock existant du produit
        # / Prefills settings from the product's existing stock
        stock_existant = stock_du_produit_ou_none(self.instance)
        if stock_existant is None:
            self.fields["stock_unite"].initial = self.unite_stock_par_defaut
            return

        self.fields["stock_suivi"].initial = True
        self.fields["stock_unite"].initial = stock_existant.unite
        self.fields["stock_seuil_alerte"].initial = stock_existant.seuil_alerte
        self.fields[
            "stock_vente_hors_stock"
        ].initial = stock_existant.autoriser_vente_hors_stock


# ---------------------------------------------------------------------------
# Fieldset et champs en lecture seule
# / Fieldset and read-only fields
# ---------------------------------------------------------------------------


@display(description=_("Opérations"))
def panneau_operations_stock(produit):
    """
    Affiche le panneau d'opérations de stock (4 boutons HTMX + derniers mouvements).
    / Displays the stock operations panel (4 HTMX buttons + recent movements).

    LOCALISATION : Administration/admin/stock_fiche_produit.py

    Champ en lecture seule de la section Stock (mode modification seulement).
    Rend admin/inventaire/stock_actions.html, le même panneau que la fiche Stock.
    Les boutons postent vers stock_action_view (inventaire/views.py),
    qui renvoie stock_actions_partial.html dans #stock-actions-container.

    Le jeton CSRF n'est pas disponible ici (pas de request).
    htmx envoie les champs du formulaire produit qui entoure le panneau,
    dont csrfmiddlewaretoken : Django l'accepte.
    / No request here: the CSRF token comes from the enclosing product form.
    """
    stock = stock_du_produit_ou_none(produit)
    if stock is None:
        return "—"

    derniers_mouvements = (
        MouvementStock.objects.filter(stock=stock)
        .exclude(type_mouvement__in=[TypeMouvement.VE, TypeMouvement.DM])
        .select_related("cree_par")
        .order_by("-cree_le")[:5]
    )

    contexte = {
        "original": produit,
        "stock": stock,
        "product_name": produit.name,
        "derniers_mouvements": derniers_mouvements,
        "stock_action_url": reverse(
            "staff_admin:inventaire_stock_action", args=[stock.pk]
        ),
    }
    html_du_panneau = render_to_string("admin/inventaire/stock_actions.html", contexte)
    return mark_safe(html_du_panneau)


def fieldset_section_stock(produit):
    """
    Construit le fieldset « Stock » à ajouter à la fin des fieldsets du produit.
    / Builds the "Stock" fieldset appended to the product fieldsets.

    Trois cas :
    - produit sans stock (création ou modification) : case « Suivre le stock »,
      quantité de départ et réglages ;
    - produit avec stock : réglages + panneau d'opérations.
      La case et la quantité de départ disparaissent :
      le stock se modifie par des mouvements tracés, pas par un champ.
    / Without stock: tracking switch + starting quantity + settings.
    With stock: settings + operations panel.
    """
    # La description porte l'ancre et la règle à retenir
    # / The description carries the anchor and the rule to remember
    description_de_la_section = format_html(
        '<p id="{}" data-testid="product-section-stock">{}</p>',
        ANCRE_SECTION_STOCK,
        _(
            "Les réglages s'enregistrent avec le bouton Enregistrer du produit. "
            "Les opérations (réception, perte…) sont enregistrées tout de suite."
        ),
    )

    stock_existant = stock_du_produit_ou_none(produit)
    if stock_existant is None:
        champs_de_la_section = (
            "stock_suivi",
            "stock_quantite_initiale",
            "stock_unite",
            "stock_seuil_alerte",
            "stock_vente_hors_stock",
        )
    else:
        champs_de_la_section = (
            "stock_unite",
            "stock_seuil_alerte",
            "stock_vente_hors_stock",
            panneau_operations_stock,
        )

    return (
        _("Stock"),
        {
            "fields": champs_de_la_section,
            "description": description_de_la_section,
        },
    )


# ---------------------------------------------------------------------------
# Sauvegarde
# / Saving
# ---------------------------------------------------------------------------


def enregistrer_section_stock(request, produit, donnees_validees):
    """
    Applique la section Stock après la sauvegarde du produit.
    / Applies the Stock section after the product is saved.

    LOCALISATION : Administration/admin/stock_fiche_produit.py

    Appelée par POSProductAdmin.save_model et FutProductAdmin.save_model.

    - Pas de stock et « Suivre le stock » coché :
      StockService.creer_stock_initial (stock + mouvement « Stock initial »).
    - Stock existant : met à jour les 3 réglages s'ils ont changé,
      puis prévient les caisses (la tuile peut se débloquer).
      Aucun mouvement : la quantité ne change jamais ici.
    - Pas de stock et case décochée : rien.

    :param request: HttpRequest (pour l'utilisateur)
    :param produit: Product déjà enregistré
    :param donnees_validees: form.cleaned_data
    """
    from inventaire.services import StockService
    from wsocket.broadcast import broadcast_etat_stock

    unite_choisie = donnees_validees.get("stock_unite") or UniteStock.UN
    seuil_choisi = donnees_validees.get("stock_seuil_alerte")
    vente_hors_stock_choisie = bool(donnees_validees.get("stock_vente_hors_stock"))

    stock_existant = stock_du_produit_ou_none(produit)

    # --- Pas encore de stock ---
    if stock_existant is None:
        suivi_demande = bool(donnees_validees.get("stock_suivi"))
        if not suivi_demande:
            return

        quantite_de_depart = donnees_validees.get("stock_quantite_initiale") or 0
        StockService.creer_stock_initial(
            product=produit,
            unite=unite_choisie,
            quantite_initiale=quantite_de_depart,
            seuil_alerte=seuil_choisi,
            autoriser_vente_hors_stock=vente_hors_stock_choisie,
            utilisateur=request.user,
        )
        return

    # --- Stock existant : mise à jour des réglages seulement ---
    reglages_modifies = []
    if stock_existant.unite != unite_choisie:
        stock_existant.unite = unite_choisie
        reglages_modifies.append("unite")
    if stock_existant.seuil_alerte != seuil_choisi:
        stock_existant.seuil_alerte = seuil_choisi
        reglages_modifies.append("seuil_alerte")
    if stock_existant.autoriser_vente_hors_stock != vente_hors_stock_choisie:
        stock_existant.autoriser_vente_hors_stock = vente_hors_stock_choisie
        reglages_modifies.append("autoriser_vente_hors_stock")

    if not reglages_modifies:
        return

    # update_fields : on ne réécrit jamais la quantité.
    # Une vente a pu la changer depuis l'ouverture de la page.
    # / Never rewrite the quantity: a sale may have changed it meanwhile.
    stock_existant.save(update_fields=reglages_modifies)
    transaction.on_commit(lambda: broadcast_etat_stock(stock_existant))


# ---------------------------------------------------------------------------
# Option B — colonne « Stock » et filtre « État du stock » dans la liste
# / Option B — "Stock" column and "Stock state" filter in the list
# ---------------------------------------------------------------------------

# Couleurs des badges, en styles inline (règle Unfold : pas de classes Tailwind custom)
# / Badge colors, inline styles (Unfold rule: no custom Tailwind classes)
STYLE_BADGE_PAR_ETAT = {
    "rupture": "background-color: #fef2f2; color: #991b1b;",
    "alerte": "background-color: #fffbeb; color: #92400e;",
    "ok": "background-color: #dcfce7; color: #166534;",
}


def etat_du_stock(stock):
    """
    Renvoie l'état d'un stock : "rupture", "alerte" ou "ok".
    / Returns a stock state: "rupture", "alerte" or "ok".

    Réutilise les méthodes du modèle (inventaire/models.py).
    """
    if stock.est_en_rupture():
        return "rupture"
    if stock.est_en_alerte():
        return "alerte"
    return "ok"


def html_badge_stock_avec_lien(produit, nom_url_fiche_produit):
    """
    Construit le badge de stock de la liste, avec un lien vers la section Stock.
    / Builds the list stock badge, linking to the product Stock section.

    LOCALISATION : Administration/admin/stock_fiche_produit.py

    - Pas de stock suivi : « — », pas de lien.
    - Sinon : quantité lisible (ex : « 1.5 L ») dans un badge coloré.
      Rouge = épuisé, orange = sous le seuil, vert = ok.
      Le clic ouvre la fiche produit, sur l'ancre #section-stock.

    La liste ne modifie jamais la quantité : chaque changement doit rester
    un mouvement tracé. On agit dans la section Stock de la fiche.
    / The list never edits quantity: every change stays a traced movement.

    :param produit: Product (avec stock_inventaire en select_related)
    :param nom_url_fiche_produit: ex "staff_admin:BaseBillet_posproduct_change"
    """
    from Administration.admin.inventaire import _formater_quantite_lisible

    stock = stock_du_produit_ou_none(produit)
    if stock is None:
        return "—"

    etat = etat_du_stock(stock)
    if etat == "rupture":
        texte_du_badge = _("Épuisé")
        texte_pour_lecteur_ecran = _("Stock épuisé")
    else:
        texte_du_badge = _formater_quantite_lisible(stock.quantite, stock.unite)
        if etat == "alerte":
            texte_pour_lecteur_ecran = _("Stock bas")
        else:
            texte_pour_lecteur_ecran = _("Stock")

    url_section_stock = (
        reverse(nom_url_fiche_produit, args=[produit.pk]) + "#" + ANCRE_SECTION_STOCK
    )

    return format_html(
        '<a href="{}" title="{}" aria-label="{} : {}" data-testid="product-list-stock-{}" '
        'style="text-decoration: none;">'
        '<span style="display: inline-block; padding: 2px 10px; border-radius: 999px; '
        'font-size: 12px; font-weight: 600; white-space: nowrap; {}">{}</span>'
        "</a>",
        url_section_stock,
        _("Gérer le stock"),
        texte_pour_lecteur_ecran,
        texte_du_badge,
        produit.pk,
        STYLE_BADGE_PAR_ETAT[etat],
        texte_du_badge,
    )


@display(description=_("Stock"), ordering="stock_inventaire__quantite")
def display_stock_produit_caisse(produit):
    return html_badge_stock_avec_lien(
        produit, "staff_admin:BaseBillet_posproduct_change"
    )


@display(description=_("Stock"), ordering="stock_inventaire__quantite")
def display_stock_fut(produit):
    return html_badge_stock_avec_lien(
        produit, "staff_admin:BaseBillet_futproduct_change"
    )


class EtatStockFilter(admin.SimpleListFilter):
    """
    Filtre « État du stock » de la liste des produits.
    Répond à la question : « qu'est-ce que je dois commander ? »
    / "Stock state" filter: answers "what do I need to order?"

    LOCALISATION : Administration/admin/stock_fiche_produit.py

    Mêmes règles que Stock.est_en_rupture() et Stock.est_en_alerte(),
    écrites en requête pour filtrer en base.
    / Same rules as the model methods, written as queries.
    """

    title = _("État du stock")
    parameter_name = "etat_stock"

    def lookups(self, request, model_admin):
        return [
            ("rupture", _("Épuisé")),
            ("alerte", _("Stock bas")),
            ("ok", _("OK")),
            ("non_suivi", _("Non suivi")),
        ]

    def queryset(self, request, queryset):
        valeur_choisie = self.value()

        # Rupture : quantité à 0 ou négative
        # / Out of stock: quantity 0 or less
        if valeur_choisie == "rupture":
            return queryset.filter(stock_inventaire__quantite__lte=0)

        # Alerte : un seuil existe, et 0 < quantité <= seuil
        # / Alert: a threshold exists, and 0 < quantity <= threshold
        condition_alerte = Q(
            stock_inventaire__seuil_alerte__isnull=False,
            stock_inventaire__quantite__gt=0,
            stock_inventaire__quantite__lte=F("stock_inventaire__seuil_alerte"),
        )
        if valeur_choisie == "alerte":
            return queryset.filter(condition_alerte)

        # OK : un stock existe, pas en rupture, pas en alerte
        # / OK: stock exists, not out, not in alert
        if valeur_choisie == "ok":
            return queryset.filter(
                stock_inventaire__isnull=False,
                stock_inventaire__quantite__gt=0,
            ).exclude(condition_alerte)

        # Non suivi : le produit n'a pas de stock
        # / Not tracked: the product has no stock
        if valeur_choisie == "non_suivi":
            return queryset.filter(stock_inventaire__isnull=True)

        return queryset
