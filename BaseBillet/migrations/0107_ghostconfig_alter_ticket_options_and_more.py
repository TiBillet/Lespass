# Generated by Django 4.2.17 on 2025-01-28 14:50

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import stdimage.models
import stdimage.validators
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('rest_framework_api_key', '0005_auto_20220110_1102'),
        ('Customers', '0002_alter_client_categorie'),
        ('BaseBillet', '0106_tag_slug_alter_tag_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='GhostConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ghost_url', models.URLField(blank=True, null=True)),
                ('ghost_key', models.CharField(blank=True, max_length=200, null=True)),
                ('ghost_last_log', models.TextField(blank=True, null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AlterModelOptions(
            name='ticket',
            options={'verbose_name': 'Billet', 'verbose_name_plural': 'Billets'},
        ),
        migrations.RemoveField(
            model_name='configuration',
            name='ghost_key',
        ),
        migrations.RemoveField(
            model_name='configuration',
            name='ghost_last_log',
        ),
        migrations.RemoveField(
            model_name='configuration',
            name='ghost_url',
        ),
        migrations.RemoveField(
            model_name='event',
            name='recurrent',
        ),
        migrations.RemoveField(
            model_name='externalapikey',
            name='artist',
        ),
        migrations.RemoveField(
            model_name='externalapikey',
            name='place',
        ),
        migrations.RemoveField(
            model_name='externalapikey',
            name='revoquer_apikey',
        ),
        migrations.RemoveField(
            model_name='product',
            name='send_to_cashless',
        ),
        migrations.AddField(
            model_name='event',
            name='end_datetime',
            field=models.DateTimeField(blank=True, help_text='Non obligatoire', null=True, verbose_name='Date de fin'),
        ),
        migrations.AddField(
            model_name='externalapikey',
            name='wallet',
            field=models.BooleanField(default=False, verbose_name='Wallets'),
        ),
        migrations.AddField(
            model_name='lignearticle',
            name='amount',
            field=models.IntegerField(default=0, verbose_name='Montant'),
        ),
        migrations.AddField(
            model_name='lignearticle',
            name='membership',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='lignearticles', to='BaseBillet.membership', verbose_name='Adhésion associée'),
        ),
        migrations.AddField(
            model_name='lignearticle',
            name='payment_method',
            field=models.CharField(blank=True, choices=[('NA', 'Aucun : offert'), ('CC', 'Carte bancaire : TPE'), ('CA', 'Espèce'), ('CH', 'Cheque bancaire'), ('SF', 'En ligne : Stripe fédéré'), ('SN', 'En ligne : Stripe account'), ('SR', 'Paiement récurent : Stripe account')], max_length=2, null=True, verbose_name='Moyen de paiement'),
        ),
        migrations.AddField(
            model_name='membership',
            name='deadline',
            field=models.DateTimeField(blank=True, null=True, verbose_name="Fin d'adhésion"),
        ),
        migrations.AddField(
            model_name='membership',
            name='payment_method',
            field=models.CharField(blank=True, choices=[('NA', 'Aucun : offert'), ('CC', 'Carte bancaire : TPE'), ('CA', 'Espèce'), ('CH', 'Cheque bancaire'), ('SF', 'En ligne : Stripe fédéré'), ('SN', 'En ligne : Stripe account'), ('SR', 'Paiement récurent : Stripe account')], max_length=2, null=True, verbose_name='Moyen de paiement'),
        ),
        migrations.AddField(
            model_name='membership',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.AddField(
            model_name='ticket',
            name='payment_method',
            field=models.CharField(blank=True, choices=[('NA', 'Aucun : offert'), ('CC', 'Carte bancaire : TPE'), ('CA', 'Espèce'), ('CH', 'Cheque bancaire'), ('SF', 'En ligne : Stripe fédéré'), ('SN', 'En ligne : Stripe account'), ('SR', 'Paiement récurent : Stripe account')], max_length=2, null=True, verbose_name='Moyen de paiement'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='sale_origin',
            field=models.CharField(choices=[('LP', 'En ligne'), ('LB', 'Caisse'), ('AD', 'Administration'), ('EX', 'Extérieur')], default='LP', max_length=2, verbose_name='Origine du paiement'),
        ),
        migrations.AlterField(
            model_name='configuration',
            name='federated_with',
            field=models.ManyToManyField(blank=True, help_text='Affiche les évènements et les adhésions des structures fédérées.', related_name='federated_with', to='Customers.client', verbose_name='Fédéré avec'),
        ),
        migrations.AlterField(
            model_name='event',
            name='datetime',
            field=models.DateTimeField(verbose_name='Date de début'),
        ),
        migrations.AlterField(
            model_name='event',
            name='img',
            field=stdimage.models.StdImageField(blank=True, force_min_size=False, null=True, upload_to='images/', validators=[stdimage.validators.MaxSizeValidator(1920, 1920)], variations={'crop': (480, 270, True), 'crop_hdr': (960, 540, True), 'fhd': (1920, 1920), 'hdr': (1280, 1280), 'med': (480, 480), 'thumbnail': (150, 90)}, verbose_name='Image'),
        ),
        migrations.AlterField(
            model_name='event',
            name='long_description',
            field=models.TextField(blank=True, null=True, verbose_name='Description longue'),
        ),
        migrations.AlterField(
            model_name='event',
            name='max_per_user',
            field=models.PositiveSmallIntegerField(default=10, help_text='ex : Un même email peut réserver plusieurs billets.', verbose_name='Nombre de reservation maximales par utilisateur.ices'),
        ),
        migrations.AlterField(
            model_name='event',
            name='name',
            field=models.CharField(max_length=200, verbose_name="Nom de l'évènement"),
        ),
        migrations.AlterField(
            model_name='event',
            name='products',
            field=models.ManyToManyField(blank=True, to='BaseBillet.product', verbose_name='Produits'),
        ),
        migrations.AlterField(
            model_name='event',
            name='short_description',
            field=models.CharField(blank=True, max_length=250, null=True, verbose_name='Description courte'),
        ),
        migrations.AlterField(
            model_name='event',
            name='tag',
            field=models.ManyToManyField(blank=True, related_name='events', to='BaseBillet.tag', verbose_name='Tags'),
        ),
        migrations.AlterField(
            model_name='externalapikey',
            name='event',
            field=models.BooleanField(default=False, verbose_name='Évènements'),
        ),
        migrations.AlterField(
            model_name='externalapikey',
            name='ip',
            field=models.GenericIPAddressField(blank=True, help_text="Si non renseignée, la clé api fonctionnera depuis n'importe quelle ip.", null=True, verbose_name='Ip source'),
        ),
        migrations.AlterField(
            model_name='externalapikey',
            name='key',
            field=models.OneToOneField(blank=True, help_text="Validez l'enregistrement pour faire apparaitre la clé. Elle n'apparaitra qu'à la création.", null=True, on_delete=django.db.models.deletion.CASCADE, related_name='api_key', to='rest_framework_api_key.apikey'),
        ),
        migrations.AlterField(
            model_name='externalapikey',
            name='product',
            field=models.BooleanField(default=False, verbose_name='Produits'),
        ),
        migrations.AlterField(
            model_name='externalapikey',
            name='reservation',
            field=models.BooleanField(default=False, verbose_name='Reservations'),
        ),
        migrations.AlterField(
            model_name='externalapikey',
            name='ticket',
            field=models.BooleanField(default=False, verbose_name='Billets'),
        ),
        migrations.AlterField(
            model_name='externalapikey',
            name='user',
            field=models.ForeignKey(blank=True, help_text='Utilisateur qui a créé cette clé.', null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='lignearticle',
            name='datetime',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='lignearticle',
            name='pricesold',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='BaseBillet.pricesold', verbose_name='Article vendu'),
        ),
        migrations.AlterField(
            model_name='lignearticle',
            name='status',
            field=models.CharField(choices=[('C', 'Annulée'), ('O', 'Non envoyé en paiement'), ('U', 'Non payée'), ('F', 'Reservation gratuite'), ('P', 'Payée & non validée'), ('V', 'Validée')], default='O', max_length=3, verbose_name='Status de ligne article'),
        ),
        migrations.AlterField(
            model_name='lignearticle',
            name='vat',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=4, verbose_name='TVA'),
        ),
        migrations.AlterField(
            model_name='membership',
            name='contribution_value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name='Contribution'),
        ),
        migrations.AlterField(
            model_name='membership',
            name='first_contribution',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='membership',
            name='last_contribution',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Date'),
        ),
        migrations.AlterField(
            model_name='membership',
            name='price',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='membership', to='BaseBillet.price', verbose_name='Produit/Prix'),
        ),
        migrations.AlterField(
            model_name='membership',
            name='status',
            field=models.CharField(choices=[('D', "Enregistré via l'administration"), ('O', 'Paiement unique en ligne'), ('A', 'Renouvellement automatique'), ('C', 'Annulée')], default='O', max_length=1, verbose_name='Origine'),
        ),
        migrations.AlterField(
            model_name='optiongenerale',
            name='poids',
            field=models.PositiveIntegerField(db_index=True, default=0, verbose_name='Poids'),
        ),
        migrations.AlterField(
            model_name='price',
            name='adhesion_obligatoire',
            field=models.ForeignKey(blank=True, help_text="Ce tarif n'est possible que si l'utilisateur.ices est adhérant.e à ", null=True, on_delete=django.db.models.deletion.PROTECT, related_name='adhesion_obligatoire', to='BaseBillet.product', verbose_name='Adhésion obligatoire'),
        ),
        migrations.AlterField(
            model_name='price',
            name='prix',
            field=models.DecimalField(decimal_places=2, max_digits=6, verbose_name='Prix'),
        ),
        migrations.AlterField(
            model_name='price',
            name='product',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='prices', to='BaseBillet.product', verbose_name='Produit'),
        ),
        migrations.AlterField(
            model_name='price',
            name='publish',
            field=models.BooleanField(default=True, verbose_name='Publier'),
        ),
        migrations.AlterField(
            model_name='pricesold',
            name='productsold',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='BaseBillet.productsold', verbose_name='Produit'),
        ),
        migrations.AlterField(
            model_name='product',
            name='archive',
            field=models.BooleanField(default=False, verbose_name='Archiver'),
        ),
        migrations.AlterField(
            model_name='product',
            name='categorie_article',
            field=models.CharField(choices=[('N', 'Selectionnez une catégorie'), ('B', 'Billet pour reservation payante'), ('A', 'Abonnement et/ou adhésion associative'), ('G', 'Badgeuse'), ('F', 'Reservation gratuite')], default='N', max_length=3, verbose_name='Type de produit'),
        ),
        migrations.AlterField(
            model_name='product',
            name='legal_link',
            field=models.URLField(blank=True, help_text='Non obligatoire', null=True, verbose_name='Lien vers mentions légales'),
        ),
        migrations.AlterField(
            model_name='product',
            name='nominative',
            field=models.BooleanField(default=False, help_text='Nom/Prenom obligatoire par billet si plusieurs réservation.', verbose_name='Nominatif'),
        ),
        migrations.AlterField(
            model_name='product',
            name='option_generale_checkbox',
            field=models.ManyToManyField(blank=True, help_text='Peux choisir plusieurs options selectionnés.', related_name='produits_checkbox', to='BaseBillet.optiongenerale', verbose_name='Option choix multiple'),
        ),
        migrations.AlterField(
            model_name='product',
            name='option_generale_radio',
            field=models.ManyToManyField(blank=True, help_text='Peux choisir entre une seule des options selectionnés.', related_name='produits_radio', to='BaseBillet.optiongenerale', verbose_name='Option choix unique'),
        ),
        migrations.AlterField(
            model_name='product',
            name='publish',
            field=models.BooleanField(default=True, verbose_name='Publier'),
        ),
        migrations.AlterField(
            model_name='productsold',
            name='categorie_article',
            field=models.CharField(choices=[('N', 'Selectionnez une catégorie'), ('B', 'Billet pour reservation payante'), ('A', 'Abonnement et/ou adhésion associative'), ('G', 'Badgeuse'), ('F', 'Reservation gratuite')], default='N', max_length=3, verbose_name='Type de produit'),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='first_name',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='last_name',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='webhook',
            name='event',
            field=models.CharField(choices=[('MV', 'Adhésion validée'), ('RV', 'Réservation validée')], default='RV', max_length=2, verbose_name='Évènement'),
        ),
    ]
