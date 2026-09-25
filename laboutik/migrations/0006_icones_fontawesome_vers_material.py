"""
Migration de donnees : icones FontAwesome → Material Symbols
/ Data migration: FontAwesome icons → Material Symbols

LOCALISATION : laboutik/migrations/0006_icones_fontawesome_vers_material.py

POURQUOI :
La caisse n'utilise plus FontAwesome. Elle affiche les icones avec la police
Material Symbols locale (fournie par django-unfold) :
    <span class="material-symbols-outlined">sports_bar</span>
Le selecteur d'icones de l'admin (ICON_POS, Administration/admin/products.py)
propose maintenant des noms Material. Les noms FontAwesome deja enregistres
(« fa-beer »...) sont convertis ici, une seule fois.
/ The POS no longer uses FontAwesome. Stored "fa-..." names are converted
  once to the matching Material Symbols names.

CHAMPS CONVERTIS :
- BaseBillet.CategorieProduct.icon
- BaseBillet.Product.icon_pos
- laboutik.PointDeVente.icon
- laboutik.CategorieTable.icon

REGLES :
- nom FontAwesome (dernier mot commencant par « fa- ») dans CORRESPONDANCE
  → sa valeur Material ;
- autre nom FontAwesome → ICONE_DE_REPLI ;
- nom Material ou vide → inchange.
ATTENTION : on teste « fa- » avec le tiret, pas « fa » seul. Des noms Material
commencent aussi par « fa » (fastfood, favorite...) et ne doivent pas bouger.
/ Detection uses "fa-" (with the dash): some Material names start with "fa".
La correspondance reprend celle qui a servi a reecrire ICON_POS : un nom
FontAwesome choisi dans l'ancien selecteur reste selectionne dans le nouveau.

MULTI-TENANT : les tables sont des TENANT_APPS. Rien a faire dans le schema public.
/ Tenant tables: nothing to do in the public schema.
"""

from django.db import connection, migrations


ICONE_DE_REPLI = "category"

CORRESPONDANCE = {
    # --- Anciennes entrees du selecteur ICON_POS / Former ICON_POS entries ---
    "fa-beer": "sports_bar",
    "fa-wine-glass-alt": "wine_bar",
    "fa-wine-glass": "glass_cup",
    "fa-wine-bottle": "liquor",
    "fa-cocktail": "local_bar",
    "fa-glass-whiskey": "local_drink",
    "fa-glass-cheers": "celebration",
    "fa-glass-martini-alt": "nightlife",
    "fa-coffee": "coffee",
    "fa-mug-hot": "emoji_food_beverage",
    "fa-tint": "water_drop",
    "fa-lemon": "water_full",
    "fa-blender": "blender",
    "fa-flask": "science",
    "fa-prescription-bottle": "medication_liquid",
    "fa-water": "water",
    "fa-utensils": "restaurant",
    "fa-pizza-slice": "local_pizza",
    "fa-hamburger": "lunch_dining",
    "fa-hotdog": "fastfood",
    "fa-bread-slice": "bakery_dining",
    "fa-cheese": "tapas",
    "fa-egg": "egg",
    "fa-apple-alt": "nutrition",
    "fa-leaf": "eco",
    "fa-seedling": "potted_plant",
    "fa-cookie": "cookie",
    "fa-cookie-bite": "donut_small",
    "fa-ice-cream": "icecream",
    "fa-drumstick-bite": "outdoor_grill",
    "fa-fish": "set_meal",
    "fa-carrot": "grass",
    "fa-pepper-hot": "whatshot",
    "fa-candy-cane": "donut_large",
    "fa-stroopwafel": "breakfast_dining",
    "fa-bacon": "kebab_dining",
    "fa-birthday-cake": "cake",
    "fa-coins": "toll",
    "fa-wallet": "account_balance_wallet",
    "fa-money-bill-wave": "payments",
    "fa-credit-card": "credit_card",
    "fa-money-check": "checkbook",
    "fa-euro-sign": "euro",
    "fa-dollar-sign": "attach_money",
    "fa-pound-sign": "currency_pound",
    "fa-ruble-sign": "currency_ruble",
    "fa-lira-sign": "currency_lira",
    "fa-rupee-sign": "currency_rupee",
    "fa-yen-sign": "currency_yen",
    "fa-shekel-sign": "universal_currency_alt",
    "fa-won-sign": "currency_exchange",
    "fa-gift": "redeem",
    "fa-gem": "diamond",
    "fa-clock": "schedule",
    "fa-id-card": "badge",
    "fa-user-plus": "person_add",
    "fa-users": "group",
    "fa-handshake": "handshake",
    "fa-heart": "favorite",
    "fa-star": "star",
    "fa-ticket-alt": "confirmation_number",
    "fa-music": "music_note",
    "fa-guitar": "queue_music",
    "fa-microphone-alt": "mic",
    "fa-theater-masks": "theater_comedy",
    "fa-campground": "camping",
    "fa-bus": "directions_bus",
    "fa-tshirt": "apparel",
    "fa-hat-wizard": "auto_fix_high",
    "fa-socks": "checkroom",
    "fa-shopping-bag": "shopping_bag",
    "fa-book": "menu_book",
    "fa-compact-disc": "album",
    "fa-palette": "palette",
    "fa-pen-fancy": "stylus_fountain_pen",
    "fa-box-open": "inventory_2",
    "fa-tag": "sell",
    "fa-umbrella-beach": "beach_access",
    "fa-store": "store",
    "fa-store-alt": "storefront",
    "fa-door-open": "door_open",
    "fa-map-marker-alt": "location_on",
    "fa-home": "home",
    "fa-warehouse": "warehouse",
    "fa-truck": "local_shipping",
    "fa-shuttle-van": "airport_shuttle",
    "fa-caravan": "rv_hookup",
    "fa-tree": "park",
    "fa-fire": "local_fire_department",
    "fa-sun": "sunny",
    "fa-exclamation-triangle": "warning",
    "fa-trash-alt": "delete",
    "fa-undo-alt": "undo",
    "fa-exchange-alt": "swap_horiz",
    "fa-recycle": "recycling",
    "fa-ban": "block",
    "fa-lock": "lock",
    "fa-check-circle": "check_circle",
    # --- Noms ecrits par les donnees de demo (create_test_pos_data) ---
    # / Names written by the demo data command
    "fa-eraser": "ink_eraser",
    "fa-rotate-left": "undo",
    "fa-image": "image",
    "fa-trash": "delete",
    "fa-cash-register": "point_of_sale",
    "fa-calendar-alt": "calendar_month",
    "fa-th": "apps",
}


def nom_material(nom_stocke):
    """
    Renvoie le nom Material a enregistrer, ou None si rien ne change.
    / Returns the Material name to store, or None if nothing changes.
    """
    if not nom_stocke or not nom_stocke.strip():
        return None
    # « fas fa-beer » / « fa-solid fa-beer » : le dernier morceau est le nom
    # / Last token is the icon name
    dernier_morceau = nom_stocke.strip().split()[-1]
    # Un nom FontAwesome commence par « fa- ». Un nom Material n'a pas de tiret
    # (fastfood, favorite commencent par « fa » mais restent intacts).
    # / A FontAwesome name starts with "fa-"; Material names have no dash.
    est_un_nom_fontawesome = dernier_morceau.startswith("fa-")
    if not est_un_nom_fontawesome:
        return None
    return CORRESPONDANCE.get(dernier_morceau, ICONE_DE_REPLI)


def convertir_un_champ(modele, nom_du_champ):
    """
    Convertit les icones FontAwesome d'un champ, ligne par ligne.
    / Converts the FontAwesome icons of one field, row by row.
    :return: nombre de lignes modifiees
    """
    nombre_de_lignes_modifiees = 0
    # Pre-filtre large (« fa- » n'importe ou) ; nom_material() tranche.
    # / Broad pre-filter; nom_material() decides.
    filtre_fontawesome = {f"{nom_du_champ}__contains": "fa-"}
    for objet in modele.objects.filter(**filtre_fontawesome):
        nouveau_nom = nom_material(getattr(objet, nom_du_champ))
        if nouveau_nom is None:
            continue
        setattr(objet, nom_du_champ, nouveau_nom)
        objet.save(update_fields=[nom_du_champ])
        nombre_de_lignes_modifiees += 1
    return nombre_de_lignes_modifiees


def convertir_les_icones(apps, schema_editor):
    """
    Convertit toutes les icones FontAwesome stockees en noms Material.
    / Converts every stored FontAwesome icon to a Material name.

    IMPORTANT : TENANT_APPS. Les tables n'existent pas dans le schema public :
    on sort tout de suite si on y est.
    / IMPORTANT: TENANT_APPS. Return immediately in the public schema.
    """
    schema_courant = connection.schema_name
    schema_est_public = schema_courant == "public"
    if schema_est_public:
        return

    champs_a_convertir = [
        (apps.get_model("BaseBillet", "CategorieProduct"), "icon"),
        (apps.get_model("BaseBillet", "Product"), "icon_pos"),
        (apps.get_model("laboutik", "PointDeVente"), "icon"),
        (apps.get_model("laboutik", "CategorieTable"), "icon"),
    ]

    total_modifie = 0
    for modele, nom_du_champ in champs_a_convertir:
        total_modifie += convertir_un_champ(modele, nom_du_champ)

    if total_modifie:
        print(f"  -> [{schema_courant}] {total_modifie} icone(s) FontAwesome convertie(s) en Material")


class Migration(migrations.Migration):

    dependencies = [
        ("laboutik", "0005_alter_terminal_name"),
        ("BaseBillet", "0228_alter_brevoconfig_last_log_and_more"),
    ]

    operations = [
        migrations.RunPython(
            convertir_les_icones,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
