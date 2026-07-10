# =============================================================================
#  Borne TiBillet sur Raspberry Pi — installation
#  / TiBillet kiosk device on Raspberry Pi — installer
# =============================================================================
#
#  Usage :
#     sudo apt-get update && sudo apt-get install -y make curl
#     curl -O https://raw.githubusercontent.com/TiBillet/Lespass/main-fedow-import/kiosk/Pi/Makefile
#     make conf              # ecrit tibillet.conf (valeurs par defaut)
#     make install           # clone + systeme + correctifs + ecran + node + service
#     sudo reboot            # la borne demarre sur la page d'appairage
#
#  `make` n'est pas dans l'image Raspberry Pi OS Lite : il faut l'installer
#  avant de recuperer ce fichier.
#  / `make` is not shipped with Raspberry Pi OS Lite: install it first.
#
#  Le code PIN n'est PAS ici : il se saisit sur l'ecran tactile de la borne.
#  / The pairing PIN is NOT here: it is typed on the device's touchscreen.
#
#  Ce Makefile n'installe rien lui-meme : il appelle le script officiel du
#  client LaBoutik (laboutik_client_pi_desktop_v2/install_pi/setup-laboutik-pi)
#  puis applique les correctifs necessaires. Le code du client n'est pas modifie.
#  / This Makefile installs nothing by itself: it calls the official LaBoutik
#  client script, then applies the required fixes. The client code is untouched.
#
#  Cibles / Targets :
#     conf     ecrit tibillet.conf s'il n'existe pas
#     install  tout, dans l'ordre (conf clone system fix screen node service)
#     status   ou en est-on ?
#     logs     journal du serveur NFC
# =============================================================================

# Le fichier de configuration est la source des valeurs. S'il n'existe pas,
# les defauts ci-dessous s'appliquent (et `make conf` l'ecrira).
# / The conf file is the source of truth. When missing, the defaults below apply.
-include tibillet.conf

# --- Valeurs par defaut / Defaults -------------------------------------------

# Adresse RACINE du serveur TiBillet (pas le sous-domaine du lieu).
# C'est elle qui repond a /api/discovery/claim/.
# / TiBillet server ROOT address (not the venue subdomain).
SERVER      ?= https://tibillet.coop

# Definition de l'ecran, en pixels. Waveshare 7"  : 1024 x 600
#                                   Waveshare 13" : 1920 x 1080 (defaut)
# / Screen definition, in pixels.
SCREEN_WIDTH  ?= 1920
SCREEN_HEIGHT ?= 1080

# Rotation de l'ecran : 0 = paysage (defaut), 1 = 90, 2 = 180, 3 = 270.
# Pilote aussi la matrice de calibration du tactile.
# / Screen rotation: 0 = landscape (default). Also drives touch calibration.
ROTATE      ?= 0

# Lecteur NFC : gpio (RC522 sur les broches) ou usb (ACR122U).
# / NFC reader: gpio (RC522 on the pins) or usb (ACR122U).
NFC         ?= gpio

GIT_REPO    ?= https://github.com/TiBillet/Lespass.git
GIT_BRANCH  ?= main-fedow-import

# --- Chemins calcules / Computed paths ---------------------------------------

SYSUSER   := $(shell id -un)
REPO_DIR  := $(HOME)/Lespass
CLIENT    := $(REPO_DIR)/laboutik_client_pi_desktop_v2
INSTALLER := $(CLIENT)/install_pi

# Emplacement de config.txt : /boot sur Bullseye, /boot/firmware sur Bookworm.
# / config.txt location: /boot on Bullseye, /boot/firmware on Bookworm.
BOOT_CONFIG := $(shell test -f /boot/firmware/config.txt && echo /boot/firmware/config.txt || echo /boot/config.txt)

# Faux `reboot` : le script setup-laboutik-pi se termine par un reboot en dur.
# On le neutralise pour enchainer les correctifs sans redemarrage intermediaire.
# Un seul reboot, a la fin, suffit (SPI + hdmi + autologin).
# / Fake `reboot`: setup-laboutik-pi ends with a hard reboot. We neutralise it to
# chain the fixes without an intermediate restart. One final reboot is enough.
SHIM_DIR := /tmp/tibillet-shim

.PHONY: conf clone system fix screen node service install status logs help

# =============================================================================
#  conf — ecrit tibillet.conf s'il n'existe pas
# =============================================================================
conf:
	@if [ -f tibillet.conf ]; then \
	    echo "tibillet.conf existe deja — rien a faire."; \
	else \
	    printf '%s\n' \
	    "# Configuration de la borne TiBillet. Editez, puis : make install" \
	    "# / TiBillet device configuration. Edit, then: make install" \
	    "" \
	    "# Adresse RACINE du serveur (pas le sous-domaine du lieu)." \
	    "# Le code PIN, lui, se saisit sur l'ecran tactile de la borne." \
	    "SERVER=$(SERVER)" \
	    "" \
	    "# Definition de l'ecran, en pixels." \
	    "#   Waveshare 7 pouces  : 1024 x 600" \
	    "#   Waveshare 13 pouces : 1920 x 1080  (valeur par defaut)" \
	    "SCREEN_WIDTH=$(SCREEN_WIDTH)" \
	    "SCREEN_HEIGHT=$(SCREEN_HEIGHT)" \
	    "" \
	    "# Rotation : 0 = paysage, 1 = 90, 2 = 180, 3 = 270." \
	    "# Pilote aussi la calibration du tactile." \
	    "ROTATE=$(ROTATE)" \
	    "" \
	    "# Lecteur NFC : gpio (RC522 sur les broches) ou usb (ACR122U)." \
	    "NFC=$(NFC)" \
	    "" \
	    "# Depot et branche a deployer sur la borne." \
	    "GIT_REPO=$(GIT_REPO)" \
	    "GIT_BRANCH=$(GIT_BRANCH)" \
	    > tibillet.conf; \
	    echo "tibillet.conf ecrit avec les valeurs par defaut."; \
	fi
	@echo ""
	@cat tibillet.conf

# =============================================================================
#  clone — recupere le depot (contient le client LaBoutik)
# =============================================================================
clone:
	@command -v git >/dev/null || { echo "Installation de git..."; sudo apt-get update -qq && sudo apt-get install -y git; }
	@if [ -d "$(REPO_DIR)/.git" ]; then \
	    echo "Depot deja present dans $(REPO_DIR)."; \
	else \
	    git clone --depth=1 -b "$(GIT_BRANCH)" "$(GIT_REPO)" "$(REPO_DIR)"; \
	fi

# =============================================================================
#  system — appelle le script officiel du client LaBoutik
#
#  « sudo env USER/HOME » : sudo impose USER=root et HOME=/root (env_reset).
#  Or le script fait `usermod -a -G gpio $USER` et ecrit `startx` dans
#  $HOME/.bashrc. Sans ce contournement, les droits GPIO vont a root et le
#  startx atterrit dans /root/.bashrc : X ne demarre jamais pour l'utilisateur.
#  / sudo forces USER=root and HOME=/root. The script relies on both.
# =============================================================================
system: clone
	@mkdir -p $(SHIM_DIR)
	@printf '#!/bin/sh\nexit 0\n' > $(SHIM_DIR)/reboot
	@chmod +x $(SHIM_DIR)/reboot
	@chmod +x $(INSTALLER)/setup-laboutik-pi
	cd $(INSTALLER) && sudo env PATH="$(SHIM_DIR):$$PATH" USER="$(SYSUSER)" HOME="$(HOME)" \
	    ./setup-laboutik-pi $(NFC) $(ROTATE)
	@rm -rf $(SHIM_DIR)

# =============================================================================
#  fix — deux correctifs, sans lesquels la borne ne demarre pas
#
#  1. fbturbo : le `apt upgrade` du script monte xorg-server dans une version
#     qui ne fournit plus le symbole `shadowUpdatePackedWeak` reclame par
#     fbturbo_drv.so. X meurt a l'ouverture du driver, donc ni Openbox ni
#     Chromium. Ce driver ne sert a rien : X fonctionne tres bien sur fbdev.
#  2. cache npm : le `npm install -g` du script tourne en root avec
#     HOME=/home/<user>, et laisse un ~/.npm appartenant a root.
# =============================================================================
fix:
	sudo apt-get purge -y xserver-xorg-video-fbturbo || true
	sudo rm -f /usr/share/X11/xorg.conf.d/99-fbturbo.conf
	sudo chown -R $(shell id -u):$(shell id -g) $(HOME)/.npm 2>/dev/null || true
	@echo "Correctifs appliques (fbturbo retire, cache npm rendu a $(SYSUSER))."

# =============================================================================
#  screen — definition de l'ecran
#
#  setup-laboutik-pi ecrit « hdmi_cvt 1024 600 » en dur, quelle que soit la
#  dalle. On reecrit la ligne selon tibillet.conf.
#  / setup-laboutik-pi hardcodes 1024x600. We rewrite it from tibillet.conf.
# =============================================================================
screen:
	sudo sed -i '/^hdmi_cvt /d' $(BOOT_CONFIG)
	echo "hdmi_cvt $(SCREEN_WIDTH) $(SCREEN_HEIGHT) 60 6 0 0 0" | sudo tee -a $(BOOT_CONFIG) > /dev/null
	@echo "Ecran regle sur $(SCREEN_WIDTH)x$(SCREEN_HEIGHT) (rotation $(ROTATE)) dans $(BOOT_CONFIG)."

# =============================================================================
#  node — modules du client + adresse du serveur
#
#  env.js est absent du depot (seul env-example.js y est), or
#  install-modules-nodejs fait un `sed -i ... env.js` : sans la copie, il
#  s'arrete net (set -e).
#  / env.js is absent from the repo; install-modules-nodejs would fail on it.
# =============================================================================
node:
	@test -f $(CLIENT)/env.js || cp $(CLIENT)/env-example.js $(CLIENT)/env.js
	@chmod +x $(CLIENT)/install-modules-nodejs
	cd $(CLIENT) && ./install-modules-nodejs pi
	cd $(CLIENT) && sed -i 's|server_pin_code: ".*"|server_pin_code: "$(SERVER)"|' env.js
	@echo "Serveur d'appairage : $(SERVER)"

# =============================================================================
#  service — nfcServer.js au demarrage
#
#  Rien ne lance nfcServer.js : `laboutik_launcher` n'est appele par personne, et
#  l'autostart d'Openbox ne lance que Chromium sur http://localhost:3000/, page
#  que rien ne sert. Le service demarre avant l'autologin, donc avant Chromium.
#  / Nothing starts nfcServer.js. This unit does, before Chromium.
# =============================================================================
service:
	printf '%s\n' \
	    "[Unit]" \
	    "Description=TiBillet NFC server (client LaBoutik)" \
	    "After=network-online.target" \
	    "Wants=network-online.target" \
	    "" \
	    "[Service]" \
	    "User=$(SYSUSER)" \
	    "WorkingDirectory=$(CLIENT)" \
	    "ExecStart=/usr/bin/node nfcServer.js" \
	    "Restart=always" \
	    "RestartSec=3" \
	    "" \
	    "[Install]" \
	    "WantedBy=multi-user.target" \
	    | sudo tee /etc/systemd/system/tibillet-nfc.service > /dev/null
	sudo systemctl daemon-reload
	sudo systemctl enable --now tibillet-nfc

# =============================================================================
#  install — tout, dans l'ordre
# =============================================================================
install: conf clone system fix screen node service
	@echo ""
	@echo "=== INSTALLATION TERMINEE ==="
	@echo "Serveur d'appairage : $(SERVER)"
	@echo "Ecran               : $(SCREEN_WIDTH)x$(SCREEN_HEIGHT), rotation $(ROTATE)"
	@echo "Lecteur NFC         : $(NFC)"
	@echo ""
	@echo "Redemarrez la borne :  sudo reboot"
	@echo "Elle affichera la page d'appairage. Saisissez-y le code PIN."

# =============================================================================
#  status / logs
# =============================================================================
status:
	@echo "--- machine"
	@echo "  arch     : $$(uname -m)  (aarch64 attendu)"
	@echo "  systeme  : $$(grep -oP '(?<=^PRETTY_NAME=").*(?=")' /etc/os-release)"
	@echo "  config   : $(BOOT_CONFIG)"
	@echo "--- installation"
	@test -d $(REPO_DIR)/.git && echo "  depot    : OK" || echo "  depot    : ABSENT (make clone)"
	@test -f $(CLIENT)/env.js && echo "  env.js   : OK" || echo "  env.js   : ABSENT (make node)"
	@test -f /usr/share/X11/xorg.conf.d/99-fbturbo.conf && echo "  fbturbo  : PRESENT — X ne demarrera pas (make fix)" || echo "  fbturbo  : retire, OK"
	@echo "  groupes  : $$(id -Gn | tr ' ' '\n' | grep -cE '^(gpio|spi)$$')/2 (gpio, spi)"
	@ls /dev/spidev0.0 >/dev/null 2>&1 && echo "  spi      : OK" || echo "  spi      : ABSENT (reboot ?)"
	@echo "--- services"
	@echo "  nfc      : $$(systemctl is-active tibillet-nfc 2>/dev/null)"
	@ss -lnt 2>/dev/null | grep -q ':3000' && echo "  port 3000: en ecoute" || echo "  port 3000: FERME"
	@echo "  X/chrome : Xorg=$$(pgrep -c Xorg) openbox=$$(pgrep -c openbox) chromium=$$(pgrep -c chromium)"

logs:
	journalctl -u tibillet-nfc -f

help:
	@echo "make conf     — ecrit tibillet.conf (valeurs par defaut) puis l'affiche"
	@echo "make install  — installation complete ; terminer par : sudo reboot"
	@echo "make status   — etat de la borne"
	@echo "make logs     — journal du serveur NFC"
	@echo ""
	@echo "Le code PIN d'appairage se saisit sur l'ecran tactile, pas ici."
