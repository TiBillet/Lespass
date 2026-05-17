import time
import pigpio
import os
from utils.logger import logger
from utils.exceptions import FlowMeterError


class FlowMeter:
    """
    Gestion du débitmètre via pigpio (interruptions précises).
    Calcule le volume total et le débit instantané.
    """

    def __init__(self, calibration_factor: float = None):
        # Configuration depuis variables d'env
        self.gpio_pin = int(os.getenv("GPIO_FLOW_SENSOR", "23"))
        if calibration_factor is not None:
            self.calibration_factor = float(calibration_factor)
        else:
            try:
                self.calibration_factor = float(os.getenv("FLOW_CALIBRATION_FACTOR", "6.5"))
            except ValueError:
                self.calibration_factor = 6.5

        self.pi = pigpio.pi()
        if not self.pi.connected:
            logger.error("Pigpio non connecté ! Le débitmètre ne fonctionnera pas.")
            logger.error("Avez-vous lancé 'sudo pigpiod' ?")
            raise FlowMeterError(
                "Pigpio non connecté : impossible d'initialiser le débitmètre"
            )

        # Config GPIO
        self.pi.set_mode(self.gpio_pin, pigpio.INPUT)
        self.pi.set_pull_up_down(self.gpio_pin, pigpio.PUD_UP)

        # Variables internes
        self.flow_count = 0
        self.total_pulses = 0
        self.volume_total_ml = 0.0
        self.last_time = time.time()
        self.current_flow_rate = 0.0  # L/min

        # Filtre anti-parasite : ignore les impulsions plus courtes que GLITCH_FILTER_US.
        # Le relais génère ~7 impulsions parasites au moment de sa commutation (back-EMF
        # de la bobine injectée par couplage sur le GPIO débitmètre). Ces parasites durent
        # quelques µs, alors que les impulsions légitimes du YF-S201 durent plusieurs ms.
        # 5000 µs = 5 ms : largement au-dessus du bruit relais, bien en dessous du signal réel.
        # / Glitch filter: ignore pulses shorter than GLITCH_FILTER_US.
        # The relay generates ~7 spurious pulses when switching (back-EMF from coil
        # injected via coupling onto the flow meter GPIO). These last a few µs, while
        # legitimate YF-S201 pulses last several ms.
        GLITCH_FILTER_US = 5000  # 5 ms
        self.pi.set_glitch_filter(self.gpio_pin, GLITCH_FILTER_US)

        # Callback (Interruption)
        self.cb = self.pi.callback(self.gpio_pin, pigpio.FALLING_EDGE, self._callback)
        logger.info(f"Débitmètre initialisé sur GPIO {self.gpio_pin} (filtre parasite: {GLITCH_FILTER_US}µs)")

    def _callback(self, gpio, level, tick):
        """Appelé à chaque impulsion du capteur."""
        self.flow_count += 1
        self.total_pulses += 1

    def update(self):
        """
        À appeler régulièrement (ex: toutes les secondes) pour mettre à jour
        le débit instantané (L/min) et le volume cumulé.
        """
        now = time.time()
        delta_t = now - self.last_time

        # On met à jour si plus de 0.5s s'est écoulé pour lisser
        if delta_t > 0.5:
            # Fréquence en Hz
            freq = self.flow_count / delta_t

            # Calcul débit L/min = (Hz / facteur) * 60
            self.current_flow_rate = (
                (freq / self.calibration_factor) * 60 if freq > 0 else 0
            )

            # Ajout au volume total (L) converti en ml
            # Volume ce cycle = (Débit L/min / 60) * delta_t_sec * 1000
            vol_added = (self.current_flow_rate / 60) * delta_t * 1000
            self.volume_total_ml += vol_added

            # Reset compteurs intermédiaires
            self.flow_count = 0
            self.last_time = now

            return self.current_flow_rate
        return self.current_flow_rate

    def volume_l(self):
        """
        Fonction requise par TibeerController.
        Retourne le volume total en Litres.
        Formule: 1 L = (Facteur * 60) impulsions.
        """
        pulses_per_liter = self.calibration_factor * 60
        if pulses_per_liter == 0:
            return 0.0
        return self.total_pulses / pulses_per_liter

    def get_volume_ml(self):
        return self.volume_total_ml

    def get_flow_rate(self):
        """Retourne le débit en L/min (usage interne)."""
        return self.current_flow_rate

    def get_flow_rate_cl(self):
        """Retourne le débit en cl/min."""
        return self.current_flow_rate * 100

    def set_calibration_factor(self, factor: float):
        """Met à jour le facteur de calibration reçu depuis le backend Django."""
        self.calibration_factor = float(factor)
        logger.info(f"Débitmètre : facteur de calibration mis à jour → {self.calibration_factor}")

    def reset(self):
        self.flow_count = 0
        self.total_pulses = 0
        self.current_flow_rate = 0.0
        self.last_time = time.time()

    def cleanup(self):
        if self.cb:
            self.cb.cancel()
        # Note: on ne stop pas self.pi ici car partagé avec Valve si besoin,
