import os
import sys
import time

SCHEDULE_PATH = "/tmp/celerybeat-schedule"
MAX_AGE_SECONDS = 120

try:
    if time.time() - os.path.getmtime(SCHEDULE_PATH) > MAX_AGE_SECONDS:
        sys.exit(1)
except OSError:
    sys.exit(1)

sys.exit(0)
