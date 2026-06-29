class TiBeerError(Exception):
    """Exception de base pour TiBeer."""
    pass

class RFIDError(TiBeerError):
    """Erreurs liées au lecteur RFID."""
    pass

class RFIDInitError(RFIDError):
    """Erreur d'initialisation du RFID."""
    pass

class RFIDReadError(RFIDError):
    """Erreur de lecture du RFID."""
    pass

class ValveError(TiBeerError):
    """Erreurs liées à la vanne."""
    pass

class FlowMeterError(TiBeerError):
    """Erreurs liées au débitmètre."""
    pass

class BackendError(TiBeerError):
    """Erreurs de communication avec le backend."""
    pass
