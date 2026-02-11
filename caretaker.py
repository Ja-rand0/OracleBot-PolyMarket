"""PBCareTaker — launches the visual dashboard and restarts it on crash."""
import logging
import subprocess
import sys
import time
from datetime import datetime

LOG_FILE = "caretaker.log"
RESTART_DELAY = 10
CRASH_LOOP_DELAY = 60
CRASH_LOOP_THRESHOLD = 30  # if bot dies within this many seconds, slow down

BOT_CMD = [sys.executable, "dashboard.py"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CARETAKER] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE)],
)
log = logging.getLogger("caretaker")


def run():
    restarts = 0

    while True:
        log.info("Starting dashboard (restart #%d)", restarts)
        start = datetime.now()

        try:
            proc = subprocess.Popen(BOT_CMD, stdout=sys.stdout, stderr=sys.stderr)
            exit_code = proc.wait()
        except KeyboardInterrupt:
            log.info("Caretaker stopped by user")
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            break
        except Exception as e:
            log.error("Failed to launch dashboard: %s", e)
            exit_code = -1

        elapsed = (datetime.now() - start).total_seconds()
        log.warning("Dashboard exited (code=%s) after %.0fs", exit_code, elapsed)

        delay = RESTART_DELAY if elapsed > CRASH_LOOP_THRESHOLD else CRASH_LOOP_DELAY
        log.info("Restarting in %ds...", delay)

        try:
            time.sleep(delay)
        except KeyboardInterrupt:
            log.info("Caretaker stopped during restart delay")
            break

        restarts += 1

    log.info("PBCareTaker shut down (total restarts: %d)", restarts)


if __name__ == "__main__":
    run()
