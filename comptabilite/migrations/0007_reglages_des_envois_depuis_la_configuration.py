"""
Migration de données : crée les réglages des envois de chaque lieu à partir des
anciens champs `Configuration.rapport_periodicite` et `Configuration.rapport_emails`.
/ Data migration: creates each venue's mail settings from the old Configuration fields.

LOCALISATION : comptabilite/migrations/0007_reglages_des_envois_depuis_la_configuration.py

Spécification : TECH_DOC/SESSIONS/RECAP_QUOTIDIEN/CHANTIER-02-recap-allege.md §5.5.

La migration suivante de BaseBillet (0238) supprime ces deux champs : elle dépend de
celle-ci, qui doit les lire avant.
/ BaseBillet 0238 removes both fields: it depends on this one, which reads them first.
"""

from django.db import connection, migrations

# Les valeurs de l'ancien champ `rapport_periodicite`, écrites en dur : les constantes
# `Configuration.PERIODICITE_*` n'existent plus dans le code.
# / The old field's values, hard-coded: the constants are gone from the code.
ANCIENNE_PERIODICITE_AUCUNE = "NONE"
ANCIENNE_PERIODICITE_JOURNALIERE = "J"

# Le type « humain » de TibilletUser (`TibilletUser.TYPE_HUM`).
# / TibilletUser's "human" type.
ESPECE_HUMAINE = "HU"


def creer_les_reglages_des_envois(apps, schema_editor):
    """
    Crée le singleton `ConfigurationDesRapports` du lieu courant.
    / Creates the current venue's ConfigurationDesRapports singleton.

    FLUX :
    1. schéma public, ou lieu sans Configuration : rien à faire ;
    2. les booléens : ancienne périodicité « aucune » (le défaut, presque tous les
       lieux) → tout coché ; périodicité X → le récap du matin (J) et X cochés, le
       reste décoché ;
    3. la liste des destinataires : AUCUN admin (décision du mainteneur, « plus
       safe ») ; seulement les users du lieu dont l'e-mail était dans `rapport_emails` ;
    4. les e-mails de `rapport_emails` sans user du lieu sont perdus : on les écrit
       dans la sortie de la migration, avec le schéma.
    """
    schema_courant = connection.schema_name
    schema_est_public = schema_courant == "public"
    if schema_est_public:
        return

    # Modèles historiques : pas de get_solo() (le modèle abstrait de django-solo est
    # aplati), et le manager de HumanUser ne filtre rien ici : on filtre à la main.
    # / Historical models: no get_solo(), and HumanUser's manager filters nothing.
    Configuration = apps.get_model("BaseBillet", "Configuration")
    ConfigurationDesRapports = apps.get_model("comptabilite", "ConfigurationDesRapports")
    HumanUser = apps.get_model("AuthBillet", "HumanUser")

    configuration_du_lieu = Configuration.objects.first()
    if configuration_du_lieu is None:
        return

    # 2. Les booléens.
    # / 2. The booleans.
    ancienne_periodicite = configuration_du_lieu.rapport_periodicite
    if ancienne_periodicite == ANCIENNE_PERIODICITE_AUCUNE:
        cases_cochees = {
            "envoyer_le_recap_quotidien": True,
            "envoyer_le_rapport_hebdomadaire": True,
            "envoyer_le_rapport_mensuel": True,
            "envoyer_le_rapport_annuel": True,
        }
    else:
        # Le récap du matin partait déjà aux admins : il reste coché.
        # / The morning recap was already sent: it stays ticked.
        cases_cochees = {
            "envoyer_le_recap_quotidien": True,
            "envoyer_le_rapport_hebdomadaire": ancienne_periodicite == "H",
            "envoyer_le_rapport_mensuel": ancienne_periodicite == "M",
            "envoyer_le_rapport_annuel": ancienne_periodicite == "A",
        }

    # Le singleton de django-solo a l'id 1.
    # / The django-solo singleton has id 1.
    reglages_des_envois, _cree = ConfigurationDesRapports.objects.update_or_create(
        id=1, defaults=cases_cochees
    )

    # 3. Les destinataires venus de `rapport_emails`. HumanUser.save met les e-mails
    # en minuscules : on compare en minuscules.
    # / 3. Recipients from rapport_emails, compared in lowercase.
    adresses_saisies = []
    for adresse_saisie in (configuration_du_lieu.rapport_emails or "").split(","):
        adresse = adresse_saisie.strip().lower()
        if adresse and adresse not in adresses_saisies:
            adresses_saisies.append(adresse)
    if not adresses_saisies:
        return

    # Les users du lieu : `client_achat` filtré par le nom du schéma, jamais par
    # `connection.tenant` (un schéma de test modèle n'a pas de Client).
    # / The venue's users: filtered by schema name, never by connection.tenant.
    users_du_lieu = HumanUser.objects.filter(
        espece=ESPECE_HUMAINE,
        client_achat__schema_name=schema_courant,
        email__in=adresses_saisies,
    ).distinct()

    adresses_trouvees = []
    identifiants_trouves = []
    for user in users_du_lieu:
        adresses_trouvees.append(user.email.lower())
        identifiants_trouves.append(user.pk)
    if identifiants_trouves:
        reglages_des_envois.destinataires.add(*identifiants_trouves)
        print(
            f"  -> [{schema_courant}] {len(identifiants_trouves)} destinataire(s) "
            f"repris de rapport_emails"
        )

    # 4. Les adresses perdues, pour que le mainteneur les relève.
    # / 4. Lost addresses, printed for the maintainer.
    for adresse in adresses_saisies:
        if adresse not in adresses_trouvees:
            print(
                f"  -> [{schema_courant}] ADRESSE PERDUE (aucun user du lieu) : {adresse}"
            )


class Migration(migrations.Migration):
    dependencies = [
        ("comptabilite", "0006_reglages_des_envois"),
        ("BaseBillet", "0237_event_panier_desactive"),
    ]

    operations = [
        migrations.RunPython(
            creer_les_reglages_des_envois,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
