# Guide d'utilisation de Dialog pour LaBoutik

## Introduction

`dialog` est un outil en ligne de commande qui permet de créer des interfaces utilisateur (UI) en mode texte (TUI - Text User Interface). Il est idéal pour les scripts d'installation et de configuration sur Raspberry Pi.

## Installation

```bash
sudo apt-get update
sudo apt-get install dialog
```

## Types de widgets disponibles

### 1. Boîte de message (msgbox)

Affiche un message avec un bouton OK.

```bash
dialog --title "Titre" --msgbox "Votre message ici" 10 50
```

**Paramètres :**
- `10` : hauteur (nombre de lignes)
- `50` : largeur (nombre de caractères)

### 2. Boîte de confirmation (yesno)

Demande une confirmation Oui/Non.

```bash
dialog --title "Confirmation" --yesno "Voulez-vous continuer ?" 7 60
if [ $? -eq 0 ]; then
    echo "Oui"
else
    echo "Non"
fi
```

**Codes de retour :**
- `0` : Oui (OK)
- `1` : Non (Cancel)
- `255` : Échap

### 3. Menu (menu)

Affiche une liste d'options sélectionnables.

```bash
CHOIX=$(dialog --clear --title "Menu" \
    --menu "Choisissez une option:" 15 50 4 \
    1 "Option 1" \
    2 "Option 2" \
    3 "Option 3" \
    4 "Quitter" \
    3>&1 1>&2 2>&3)
```

**Paramètres :**
- `15` : hauteur totale de la boîte
- `50` : largeur totale
- `4` : nombre d'éléments affichés (les autres sont scrollables)

**Redirections (obligatoires) :**
```bash
3>&1 1>&2 2>&3
```
Cela permet de capturer la sortie dans une variable.

### 4. Liste à choix unique (radiolist)

Permet de sélectionner une seule option.

```bash
RESULTAT=$(dialog --title "Choix" \
    --radiolist "Sélectionnez :" 12 50 3 \
    1 "Option A" on \
    2 "Option B" off \
    3 "Option C" off \
    3>&1 1>&2 2>&3)
```

**Note :** `on` = sélectionné par défaut, `off` = non sélectionné

### 5. Liste à choix multiples (checklist)

Permet de sélectionner plusieurs options.

```bash
OPTIONS=$(dialog --title "Options" \
    --checklist "Cochez les options :" 12 50 3 \
    1 "Option 1" on \
    2 "Option 2" off \
    3 "Option 3" on \
    3>&1 1>&2 2>&3)
```

**Note :** Le résultat contient les numéros sélectionnés séparés par des espaces.

### 6. Saisie de texte (inputbox)

Demande à l'utilisateur de saisir du texte.

```bash
TEXTE=$(dialog --title "Saisie" \
    --inputbox "Entrez votre nom :" 8 40 \
    3>&1 1>&2 2>&3)
```

### 7. Barre de progression (gauge)

Affiche une barre de progression.

```bash
(
    for i in $(seq 0 10 100); do
        echo $i
        sleep 1
    done
) | dialog --title "Progression" --gauge "Chargement..." 7 50 0
```

### 8. Boîte d'informations (infobox)

Affiche un message sans attendre (non bloquant).

```bash
dialog --title "Info" --infobox "Traitement en cours..." 5 30
sleep 2
```

### 9. Boîte de mot de passe (passwordbox)

Saisie masquée (comme un mot de passe).

```bash
PASS=$(dialog --title "Mot de passe" \
    --passwordbox "Entrez le mot de passe :" 8 40 \
    3>&1 1>&2 2>&3)
```

## Gestion des codes de retour

```bash
dialog --yesno "Question ?" 7 50
CODE=$?

case $CODE in
    0)
        echo "L'utilisateur a cliqué sur Oui"
        ;;
    1)
        echo "L'utilisateur a cliqué sur Non"
        ;;
    255)
        echo "L'utilisateur a appuyé sur Échap"
        ;;
esac
```

## Astuces et bonnes pratiques

### 1. Effacer l'écran après dialog

```bash
dialog --clear --title "Titre" --msgbox "Message" 10 50
clear
```

### 2. Couleurs personnalisées

```bash
dialog --colors --title "\Z1Titre en rouge\Zn" \
    --msgbox "\Z2Texte en vert\Zn" 10 50
```

**Codes couleurs :**
- `\Z0` : Noir
- `\Z1` : Rouge
- `\Z2` : Vert
- `\Z3` : Jaune
- `\Z4` : Bleu
- `\Z5` : Magenta
- `\Z6` : Cyan
- `\Z7` : Blanc
- `\Zn` : Retour à la couleur par défaut

### 3. Sauvegarder et restaurer l'écran

```bash
# Sauvegarder l'écran
dialog --keep-tite --title "Titre" --msgbox "Message" 10 50
```

### 4. Utiliser des fichiers temporaires pour les résultats complexes

```bash
FICHIER_TEMP=$(mktemp)
dialog --checklist "Options" 12 50 3 \
    1 "Opt1" on \
    2 "Opt2" off \
    3 "Opt3" off \
    2>$FICHIER_TEMP

RESULTAT=$(cat $FICHIER_TEMP)
rm $FICHIER_TEMP
```

### 5. Créer un menu avec sous-menus

```bash
#!/bin/bash

show_submenu() {
    local CHOIX=$(dialog --clear --title "Sous-menu" \
        --menu "Options:" 10 40 2 \
        1 "Action 1" \
        2 "Retour" \
        3>&1 1>&2 2>&3)
    
    case $CHOIX in
        1) echo "Action 1" ;;
        2) return ;;
    esac
}

while true; do
    CHOIX=$(dialog --clear --title "Menu Principal" \
        --menu "Choisissez :" 12 50 3 \
        1 "Sous-menu" \
        2 "Info" \
        3 "Quitter" \
        3>&1 1>&2 2>&3)
    
    [ $? -ne 0 ] && break
    
    case $CHOIX in
        1) show_submenu ;;
        2) dialog --msgbox "Information" 8 30 ;;
        3) break ;;
    esac
done

clear
```

## Exemple complet : Script d'installation

```bash
#!/bin/bash

# Installation de dialog si nécessaire
if ! command -v dialog &> /dev/null; then
    sudo apt-get update && sudo apt-get install -y dialog
fi

# Variables
NFC_TYPE=""
SCREEN_ROTATION=""
DEBUG_MODE=""

# Étape 1 : Configuration NFC
NFC_CHOIX=$(dialog --clear --title "Étape 1/3 - NFC" \
    --radiolist "Type de lecteur NFC :" 12 50 2 \
    gpio "GPIO (RC522)" on \
    usb "USB (ACR122U)" off \
    3>&1 1>&2 2>&3)

[ $? -ne 0 ] && exit 1
NFC_TYPE=$NFC_CHOIX

# Étape 2 : Rotation écran
ROTATION=$(dialog --clear --title "Étape 2/3 - Écran" \
    --radiolist "Rotation :" 12 50 4 \
    0 "0° (Normal)" off \
    1 "90°" off \
    2 "180°" off \
    3 "270°" on \
    3>&1 1>&2 2>&3)

[ $? -ne 0 ] && exit 1
SCREEN_ROTATION=$ROTATION

# Étape 3 : Debug
DEBUG=$(dialog --clear --title "Étape 3/3 - Debug" \
    --yesno "Activer le mode debug Chromium ?" 7 50 \
    3>&1 1>&2 2>&3)

if [ $? -eq 0 ]; then
    DEBUG_MODE="oui"
else
    DEBUG_MODE="non"
fi

# Récapitulatif
dialog --title "Récapitulatif" --msgbox \
"Configuration choisie :\n\n\
NFC : $NFC_TYPE\n\
Rotation : $SCREEN_ROTATION°\n\
Debug : $DEBUG_MODE\n\n\
Cliquez sur OK pour appliquer." 12 50

# Ici, vous ajouteriez les commandes réelles d'installation
# Exemple :
# sudo ./install_pi/setup-laboutik-pi $NFC_TYPE $SCREEN_ROTATION

dialog --title "Terminé" --msgbox "Installation terminée !" 8 30
clear

echo "Configuration appliquée :"
echo "  NFC : $NFC_TYPE"
echo "  Rotation : $SCREEN_ROTATION°"
echo "  Debug : $DEBUG_MODE"
```

## Ressources

- **Manuel officiel :** `man dialog`
- **Aide intégrée :** `dialog --help`
- **Documentation complète :** `/usr/share/doc/dialog/`

## Notes importantes

1. **Toujours utiliser les redirections** `3>&1 1>&2 2>&3` pour capturer la sortie
2. **Vérifier le code de retour** `$?` après chaque dialog
3. **Utiliser `--clear`** pour nettoyer l'écran après utilisation
4. **Tester les dimensions** (hauteur/largeur) sur l'écran cible
5. **Gérer la touche Échap** (code retour 255) pour éviter les blocages
