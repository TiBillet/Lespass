"""
Le lecteur de carte bancaire devient un objet a part : TPEBancaire.
/ The card reader becomes its own object: TPEBancaire.

Il etait jusqu'ici trois champs colles sur Terminal (registration_code, stripe_id, type).
Deux raisons de l'en sortir :

1. IL SE DEPLACE. On debranche un lecteur d'une caisse pour le brancher sur une borne.
   C'est un objet physique, il doit pouvoir changer d'appareil.
2. IL SERA TYPE. Aujourd'hui Stripe ; demain SumUp, Stancer.

L'ORDRE DES OPERATIONS COMPTE : on cree le modele, on recopie les donnees, ET SEULEMENT
APRES on supprime les champs. L'inverse perdrait les lecteurs deja enregistres.

Voir TECH_DOC/SESSIONS/IMPRESSION/CHANTIER-06-extraction-tpe.md
"""

from django.db import connection, migrations, models
import django.db.models.deletion
import uuid


def sortir_les_lecteurs_des_terminaux(apps, schema_editor):
    """
    Fabrique un TPEBancaire pour chaque terminal qui portait un lecteur.
    / Creates a TPEBancaire for every terminal that carried a reader.

    LOCALISATION : laboutik/migrations/0005_...

    Le lecteur reste branche sur son terminal : on ne debranche rien, on ne fait que sortir
    l'objet. `type == 'W'` etait l'ancienne valeur « Stripe WisePOS ».

    Les modeles viennent de apps.get_model() (l'etat historique), jamais d'un import direct :
    les methodes du modele d'aujourd'hui n'existent pas ici.
    """
    # Les tables de laboutik n'existent pas dans le schema public.
    # / laboutik tables do not exist in the public schema.
    if connection.schema_name == 'public':
        return

    Terminal = apps.get_model('laboutik', 'Terminal')
    TPEBancaire = apps.get_model('laboutik', 'TPEBancaire')

    terminaux_avec_un_lecteur = Terminal.objects.exclude(
        type='',
    ) | Terminal.objects.exclude(
        stripe_id__isnull=True,
    ).exclude(
        stripe_id='',
    )

    nombre_de_lecteurs_sortis = 0
    for terminal in terminaux_avec_un_lecteur.distinct():
        TPEBancaire.objects.create(
            name=terminal.name or "TPE",
            tpe_type='SW',
            registration_code=terminal.registration_code,
            stripe_id=terminal.stripe_id,
            terminal=terminal,
            active=True,
        )
        nombre_de_lecteurs_sortis += 1

    if nombre_de_lecteurs_sortis:
        print(
            f"  -> [{connection.schema_name}] "
            f"{nombre_de_lecteurs_sortis} lecteur(s) de carte sorti(s) du terminal"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('laboutik', '0004_alter_terminal_archived_and_more'),
    ]

    operations = [
        # 1. Le nouveau modele.
        # / 1. The new model.
        migrations.CreateModel(
            name='TPEBancaire',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(help_text='Nom du lecteur, par exemple « TPE du bar ».', max_length=200, verbose_name='Nom')),
                ('tpe_type', models.CharField(choices=[('SW', 'Stripe — BBPOS WisePOS E')], default='SW', max_length=2, verbose_name='Type de lecteur')),
                ('registration_code', models.CharField(blank=True, help_text='Code affiché par le lecteur Stripe à son premier démarrage.', max_length=200, null=True, verbose_name="Code d'enregistrement")),
                ('stripe_id', models.CharField(blank=True, max_length=21, null=True, unique=True, verbose_name='Identifiant Stripe')),
                ('active', models.BooleanField(default=True, help_text='Décochez pour mettre ce lecteur hors service.', verbose_name='Actif')),
                ('terminal', models.OneToOneField(blank=True, help_text="L'appareil sur lequel ce lecteur est branché. Laisser vide si le lecteur n'est branché nulle part.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tpe', to='laboutik.terminal', verbose_name='Branché sur le terminal')),
            ],
            options={
                'verbose_name': 'TPE bancaire',
                'verbose_name_plural': 'TPE bancaires',
                'ordering': ('name',),
            },
        ),

        # 2. On recopie les lecteurs AVANT de supprimer les champs.
        # / 2. Copy the readers BEFORE dropping the fields.
        migrations.RunPython(
            sortir_les_lecteurs_des_terminaux,
            reverse_code=migrations.RunPython.noop,
        ),

        # 3. Et seulement maintenant, on retire les champs du terminal.
        # / 3. And only now, drop the fields from the terminal.
        migrations.RemoveField(
            model_name='terminal',
            name='registration_code',
        ),
        migrations.RemoveField(
            model_name='terminal',
            name='stripe_id',
        ),
        migrations.RemoveField(
            model_name='terminal',
            name='type',
        ),
        migrations.AlterField(
            model_name='terminal',
            name='printer',
            field=models.ForeignKey(blank=True, help_text="Imprimante utilisée par ce terminal. Laisser vide si l'appareil n'imprime pas.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='terminaux', to='laboutik.printer', verbose_name='Imprimante'),
        ),
    ]
