SYSUSER    := sysop
REPO_DIR   := /home/$(SYSUSER)/tibeer
TARGET_DIR := $(REPO_DIR)/controlvanne/Pi
VENV       := $(TARGET_DIR)/.venv
CONFIG     := $(TARGET_DIR)/config

DEFAULT_SERVER := https://devtib.fr
DEFAULT_REPO   := https://github.com/TiBillet/Lespass.git
DEFAULT_BRANCH := V2
DEFAULT_RFID   := RC522

.PHONY: all claim install deploy start update logs status test-rfid test-hardware clean help

# Installation complète
# Usage : make all PIN=123456 [SERVER=https://...] [RFID=RC522]
all: claim install deploy start
	@echo "Installation terminee — redemarrez le Pi : sudo reboot"

# Appairage : recupere les credentials et genere .env
# Usage : make claim PIN=123456 [SERVER=https://devtib.fr] [RFID=RC522]
claim:
	@[ -n "$(PIN)" ] || { echo "Usage: make claim PIN=123456 [SERVER=...] [RFID=RC522]"; exit 1; }
	bash $(CONFIG)/claim.sh \
	    "$(PIN)" \
	    "$(or $(SERVER),$(DEFAULT_SERVER))" \
	    "$(or $(RFID),$(DEFAULT_RFID))" \
	    "$(or $(REPO),$(DEFAULT_REPO))" \
	    "$(or $(BRANCH),$(DEFAULT_BRANCH))"

# Dependances systeme + virtualenv Python
install:
	sudo apt-get update
	sudo apt-get install -y --no-install-recommends \
	    git nano locales fontconfig curl ca-certificates \
	    python3 python3-venv python3-pip python3-dev \
	    pigpio python3-pigpio \
	    xserver-xorg xinit openbox unclutter x11-apps \
	    chromium-browser chromium-chromedriver \
	    fonts-dejavu-core xfonts-base \
	    upower xserver-xorg-input-libinput
	sudo sed -i 's/^# *fr_FR.UTF-8 UTF-8/fr_FR.UTF-8 UTF-8/' /etc/locale.gen
	sudo locale-gen || true
	sudo raspi-config nonint do_spi 0 || true
	sudo usermod -aG sudo,video,input,render,gpio,spi,dialout,tty $(SYSUSER)
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r $(TARGET_DIR)/requirements.txt
	@if [ "$(or $(RFID),$(DEFAULT_RFID))" = "ACR122U" ]; then \
	    sudo apt-get install -y --no-install-recommends pcscd libpcsclite-dev swig; \
	    $(VENV)/bin/pip install pyscard; \
	fi

# Deploiement des fichiers de configuration vers leurs destinations systeme
deploy:
	sudo cp $(CONFIG)/kiosk.service  /etc/systemd/system/kiosk.service
	sudo cp $(CONFIG)/tibeer.service /etc/systemd/system/tibeer.service
	cp  $(CONFIG)/xinitrc.bash /home/$(SYSUSER)/.xinitrc
	chmod +x /home/$(SYSUSER)/.xinitrc
	chown $(SYSUSER):$(SYSUSER) /home/$(SYSUSER)/.xinitrc
	sudo mkdir -p /etc/X11/xorg.conf.d
	sudo cp $(CONFIG)/dpms.conf /etc/X11/xorg.conf.d/10-dpms.conf
	sudo cp $(CONFIG)/xwrapper.conf /etc/X11/Xwrapper.config
	$(eval CFG := $(shell [ -d /boot/firmware ] && echo /boot/firmware/config.txt || echo /boot/config.txt))
	sudo sed -i '/^dtoverlay=vc4/d;/^hdmi_force_hotplug=/d' $(CFG)
	echo "dtoverlay=vc4-fkms-v3d" | sudo tee -a $(CFG) > /dev/null
	echo "hdmi_force_hotplug=1"   | sudo tee -a $(CFG) > /dev/null

# Activation et demarrage des services
start:
	sudo systemctl enable pigpiod
	sudo systemctl start  pigpiod
	@if [ "$(or $(RFID),$(DEFAULT_RFID))" = "ACR122U" ]; then \
	    sudo systemctl enable pcscd; sudo systemctl start pcscd; \
	fi
	sudo systemctl daemon-reload
	sudo systemctl enable kiosk tibeer
	sudo systemctl disable --now getty@tty1.service || true

# Mise a jour depuis git + redemarrage
update:
	git -C $(REPO_DIR) pull
	$(VENV)/bin/pip install -r $(TARGET_DIR)/requirements.txt
	sudo systemctl restart tibeer

# Diagnostic
logs:
	journalctl -u tibeer -f

status:
	systemctl status tibeer kiosk --no-pager

test-rfid:
	$(eval RFID := $(shell grep '^RFID_TYPE=' $(TARGET_DIR)/.env 2>/dev/null | cut -d= -f2 | tr '[:upper:]' '[:lower:]'))
	$(VENV)/bin/python $(TARGET_DIR)/tests/test_rfid_$(or $(RFID),rc522).py

test-hardware:
	$(VENV)/bin/python $(TARGET_DIR)/tests/check_hardware.py

# Nettoyage complet
clean:
	sudo systemctl disable --now tibeer kiosk || true
	sudo rm -f /etc/systemd/system/tibeer.service /etc/systemd/system/kiosk.service
	sudo systemctl daemon-reload
	rm -rf $(VENV)

help:
	@echo ""
	@echo "TiBeer Pi — commandes disponibles"
	@echo "----------------------------------"
	@echo "  Installation"
	@echo "    make all     PIN=123456 [SERVER=https://...] [RFID=RC522]"
	@echo "                 Installation complete (claim + install + deploy + start)"
	@echo "    make claim   PIN=123456 [SERVER=...] [RFID=RC522] [REPO=...] [BRANCH=...]"
	@echo "                 Appairage : recupere les credentials et genere .env"
	@echo "    make install [RFID=RC522]"
	@echo "                 Dependances systeme + virtualenv Python"
	@echo "    make deploy  Deploie les services et fichiers de config systeme"
	@echo "    make start   Active et demarre tibeer + kiosk"
	@echo ""
	@echo "  Maintenance"
	@echo "    make update  git pull + pip install + redemarrage tibeer"
	@echo "    make clean   Desactive les services et supprime le virtualenv"
	@echo ""
	@echo "  Diagnostic"
	@echo "    make logs          Logs en direct (journalctl -u tibeer -f)"
	@echo "    make status        Etat des services tibeer et kiosk"
	@echo "    make test-rfid     Lance le test du lecteur defini dans .env (RC522/VMA405/ACR122U)"
	@echo "    make test-hardware Diagnostic global du materiel"
	@echo ""
	@echo "  Lecteurs RFID supportes : RC522 (defaut), VMA405, ACR122U"
	@echo ""
