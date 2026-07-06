"""
Commande : démarrer un nouveau skin en copiant le socle classic.
/ Command: start a new skin by copying the classic base.

LOCALISATION : pages/management/commands/demarrer_skin.py

Usage :
    python manage.py demarrer_skin mon-skin

La commande copie pages/templates/pages/classic/ vers
pages/templates/pages/<nom>/ puis affiche la marche à suivre (FALC).
Elle REFUSE d'écraser un skin existant.
Le contrat complet (blocs, ids, variables) est documenté dans
TECH_DOC/SESSIONS/SKINS/CONTRAT-DE-SKIN.md.
/ Copies the classic base to a new skin folder, refuses to overwrite,
then prints the next steps. Full contract in CONTRAT-DE-SKIN.md.
"""
import re
import shutil
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Crée un nouveau skin en copiant le socle pages/classic/ (zéro code Python)."

    def add_arguments(self, parser):
        parser.add_argument(
            "nom_du_skin",
            help="Nom du nouveau skin (minuscules, chiffres, tirets). Ex : mon-skin",
        )

    def handle(self, *args, **options):
        nom_du_skin = options["nom_du_skin"]

        # Le nom doit être utilisable dans un chemin de template et dans le
        # champ ConfigurationSite.skin (max 50 caractères).
        # / The name must be path-safe and fit the skin CharField (max 50).
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", nom_du_skin):
            raise CommandError(
                "Nom de skin invalide. Utiliser uniquement des minuscules, "
                "chiffres, tirets ou underscores (50 caractères max). "
                "Exemple : mon-skin"
            )
        if nom_du_skin in ("classic", "reunion"):
            raise CommandError(
                f"'{nom_du_skin}' est réservé : 'classic' est le socle, "
                "'reunion' est le skin par défaut (qui utilise classic)."
            )

        dossier_pages = Path(__file__).resolve().parent.parent.parent / "templates" / "pages"
        dossier_classic = dossier_pages / "classic"
        dossier_nouveau = dossier_pages / nom_du_skin

        if not dossier_classic.is_dir():
            raise CommandError(f"Socle introuvable : {dossier_classic}")
        if dossier_nouveau.exists():
            raise CommandError(
                f"Le skin '{nom_du_skin}' existe déjà ({dossier_nouveau}). "
                "Cette commande ne remplace JAMAIS un skin existant."
            )

        shutil.copytree(dossier_classic, dossier_nouveau)
        nombre_de_fichiers = sum(1 for f in dossier_nouveau.rglob("*") if f.is_file())

        self.stdout.write(self.style.SUCCESS(
            f"Skin '{nom_du_skin}' créé : {nombre_de_fichiers} gabarits copiés "
            f"dans {dossier_nouveau}"
        ))
        self.stdout.write(
            "\nLa suite, pas à pas :\n"
            "  1. Supprime dans ce dossier tous les fichiers que tu ne veux PAS\n"
            "     personnaliser : ils retomberont automatiquement sur classic.\n"
            "  2. Restyle shell.html (CSS, polices) et partials/navbar.html,\n"
            "     footer.html, carte_evenement.html.\n"
            "  3. Le contrat complet (blocs, ids à ne pas toucher, variables) :\n"
            "     TECH_DOC/SESSIONS/SKINS/CONTRAT-DE-SKIN.md\n"
            "  4. Pour activer le skin, ajoute la choice dans\n"
            "     pages/models.py (ConfigurationSite.skin) puis sélectionne le\n"
            "     thème dans l'admin du tenant (décision mainteneur).\n"
        )
