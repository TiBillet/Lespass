# Ajout des deux affichages du bloc LIEU : VERTICAL (le rendu historique) et
# HORIZONTAL (carte en bandeau, infos en rangee — maquette DA v1).
# Changement de CHOICES uniquement : aucune colonne touchee, aucun SQL de donnees.
# Django l'applique malgre tout schema par schema en multi-tenant :
#   docker exec lespass_django poetry run python manage.py migrate_schemas
# Les blocs LIEU deja enregistres gardent un `affichage` VIDE, et c'est voulu :
# le rendu retombe sur `bloc_lieu.html`, donc leur aspect ne change pas. Aucune
# migration de donnees n'est necessaire.
# / Adds the LIEU block's two layouts. CHOICES-only change, applied schema by
# schema in multi-tenant. Existing LIEU blocks keep an EMPTY affichage on
# purpose: rendering falls back to `bloc_lieu.html`, so they look unchanged.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0003_alter_bloc_affichage'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bloc',
            name='affichage',
            field=models.CharField(blank=True, choices=[('BANNIERE', "Bannière d'ouverture"), ('TEXTE_IMAGE_GAUCHE', 'Texte avec image à gauche'), ('TEXTE_IMAGE_DROITE', 'Texte avec image à droite'), ('TEXTE_VIDEO', 'Texte avec vidéo (fichier déposé)'), ('MEDIA_ET_CARTES', 'Média + texte + sous-cartes (section composée)'), ('CARTE', 'Carte (se range en grille avec les cartes voisines)'), ('APPEL_ACTION', "Appel à l'action (boutons mis en avant)"), ('CITATION', 'Citation / témoignage signé'), ('EQUIPE', 'Équipe (personnes et rôles)'), ('FRISE', 'Frise chronologique (dates et étapes)'), ('RESSOURCES', 'Ressources (documents et liens)'), ('PLEINE_LARGEUR', 'Photo pleine largeur'), ('VIGNETTE_TITRE', 'Vignette centrée (image-titre dessinée)'), ('GRILLE', 'Galerie en grille'), ('BANDE_LOGOS', 'Bande de logos cliquables'), ('VIDEO', 'Vidéo en ligne (YouTube / Vimeo / PeerTube)'), ('WIDGET', 'Formulaire ou widget (hôte autorisé par le ROOT)'), ('NEWSLETTER', 'Inscription newsletter (Ghost)'), ('VERTICAL', 'Infos à gauche, carte à droite (deux colonnes)'), ('HORIZONTAL', 'Carte en bandeau, infos en rangée dessous')], max_length=20, verbose_name='Affichage'),
        ),
    ]
