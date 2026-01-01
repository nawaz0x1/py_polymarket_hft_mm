import os
import psutil
import logging

logger = logging.getLogger(__name__)


def set_cpu_affinity():
    try:
        process = psutil.Process()
        cpu_count = os.cpu_count()
        logger.info(f"System has {cpu_count} CPU cores")
        if cpu_count >= 4:
            affinity_cores = [cpu_count - 2, cpu_count - 1]
        elif cpu_count >= 2:
            affinity_cores = [cpu_count - 1]
        else:
            affinity_cores = [0]

        process.cpu_affinity(affinity_cores)
        logger.info(f"CPU affinity set to cores: {affinity_cores}")

        if os.name == "nt":  # Windows
            process.nice(psutil.HIGH_PRIORITY_CLASS)
            logger.info("Process priority set to HIGH")
        else:  # Linux/Unix
            process.nice(-10)  # Higher priority (lower nice value)
            logger.info("Process nice value set to -10 (high priority)")

    except Exception as e:
        logger.warning(f"Failed to set CPU affinity: {e}")
