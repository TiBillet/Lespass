import logging
from logging.handlers import RotatingFileHandler
from config.settings import LOG_DIR

def setup_logger(name: str = "tibeer") -> logging.Logger:
    """
    Configure et retourne un logger avec :
    - Rotation des fichiers (5Mo max, 3 backups)
    - Sortie console + fichier
    - Format standardisé
    """
    logger = logging.getLogger(name)
   # logger.setLevel(logging.INFO)  # Niveau par défaut
    logger.setLevel(logging.DEBUG)
    # Format des logs
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Handler pour fichier (rotation automatique)
    file_handler = RotatingFileHandler(
        LOG_DIR / "tibeer.log",
        maxBytes=5 * 1024 * 1024,  # 5 Mo
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    # Handler pour console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Ajout des handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# Logger global pour l'application
logger = setup_logger()
