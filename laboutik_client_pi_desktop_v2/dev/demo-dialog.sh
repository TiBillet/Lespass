#!/bin/bash

# Script de démonstration dialog pour LaBoutik
# Ce script est une simulation - aucune action réelle n'est effectuée

# Vérifier si dialog est installé
if ! command -v dialog &> /dev/null; then
    echo "Installation de dialog..."
    sudo apt-get update && sudo apt-get install -y dialog
fi

# Fonction pour afficher un message de simulation
simulate_action() {
    dialog --title "Simulation" --msgbox "Action simulée : $1\n\nAucune modification n'a été effectuée." 10 50
}

# Fonction pour le menu principal
show_main_menu() {
    while true; do
        CHOIX=$(dialog --clear --title "LaBoutik - Configuration" \
            --menu "Choisissez une option:" 15 60 6 \
            1 "Configurer NFC" \
            2 "Configurer écran" \
            3 "Activer/Désactiver debug" \
            4 "Vérifier l'état" \
            5 "Aide" \
            6 "Quitter" \
            3>&1 1>&2 2>&3)
        
        # Si l'utilisateur appuie sur Annuler ou Échap
        if [ $? -ne 0 ]; then
            clear
            echo "Opération annulée."
            exit 0
        fi
        
        case $CHOIX in
            1)
                show_nfc_menu
                ;;
            2)
                show_screen_menu
                ;;
            3)
                show_debug_menu
                ;;
            4)
                show_status
                ;;
            5)
                show_help
                ;;
            6)
                dialog --title "Quitter" --yesno "Voulez-vous vraiment quitter?" 7 50
                if [ $? -eq 0 ]; then
                    clear
                    echo "Au revoir!"
                    exit 0
                fi
                ;;
        esac
    done
}

# Menu NFC
show_nfc_menu() {
    NFC_CHOIX=$(dialog --clear --title "Configuration NFC" \
        --menu "Type de lecteur NFC:" 12 50 3 \
        1 "GPIO - RC522 (SoftSPI)" \
        2 "USB - ACR122U" \
        3 "Retour" \
        3>&1 1>&2 2>&3)
    
    if [ $? -ne 0 ]; then
        return
    fi
    
    case $NFC_CHOIX in
        1)
            dialog --title "Configuration GPIO" \
                --checklist "Options:" 12 50 2 \
                1 "Activer SPI" on \
                2 "Configurer droits" on \
                3>&1 1>&2 2>&3
            simulate_action "Configuration NFC GPIO"
            ;;
        2)
            dialog --title "Configuration USB" \
                --msgbox "Installation des drivers PC/SC...\n\n(Simulation)" 8 40
            simulate_action "Configuration NFC USB"
            ;;
        3)
            return
            ;;
    esac
}

# Menu Écran
show_screen_menu() {
    ROTATION=$(dialog --clear --title "Configuration Écran" \
        --radiolist "Rotation de l'écran:" 12 50 4 \
        0 "0° - Normal" off \
        1 "90°" off \
        2 "180°" off \
        3 "270° (défaut)" on \
        3>&1 1>&2 2>&3)
    
    if [ $? -ne 0 ]; then
        return
    fi
    
    dialog --title "Confirmation" \
        --yesno "Appliquer la rotation $ROTATION ?" 7 40
    
    if [ $? -eq 0 ]; then
        simulate_action "Rotation écran : $ROTATION°"
    fi
}

# Menu Debug
show_debug_menu() {
    DEBUG_CHOIX=$(dialog --clear --title "Mode Debug" \
        --menu "Gestion du débogage Chromium:" 12 50 3 \
        1 "Activer debug (port 9222)" \
        2 "Désactiver debug" \
        3 "Voir l'état" \
        3>&1 1>&2 2>&3)
    
    if [ $? -ne 0 ]; then
        return
    fi
    
    case $DEBUG_CHOIX in
        1)
            simulate_action "Activation du débogage distant sur le port 9222"
            dialog --title "Info" --msgbox "Après activation, redémarrez le Pi.\n\nPuis sur votre PC :\nssh -L 9222:localhost:9222 sysop@<ip>" 10 50
            ;;
        2)
            simulate_action "Désactivation du débogage distant"
            ;;
        3)
            dialog --title "État" --msgbox "État actuel : DÉSACTIVÉ\n\n(Simulation)" 8 40
            ;;
    esac
}

# Afficher l'état
show_status() {
    STATUS=$(cat <<EOF
=== ÉTAT DU SYSTÈME (Simulation) ===

Système : Raspberry Pi
Node.js : v24.15.0
NFC : GPIO (RC522)
Écran : 270°
Debug : Désactivé

Tous les services fonctionnent normalement.
EOF
)
    
    dialog --title "État du système" --msgbox "$STATUS" 15 50
}

# Afficher l'aide
show_help() {
    HELP=$(cat <<EOF
AIDE - LaBoutik Configuration

Ce script permet de configurer :
- Le lecteur NFC (GPIO ou USB)
- La rotation de l'écran
- Le mode débogage de Chromium

Navigation :
- Flèches haut/bas : se déplacer
- Entrée : sélectionner
- Échap : annuler

Pour plus d'informations, consultez le README.
EOF
)
    
    dialog --title "Aide" --msgbox "$HELP" 15 50
}

# Démarrage du script
clear
echo "Démarrage de l'interface de configuration LaBoutik..."
sleep 1

show_main_menu
