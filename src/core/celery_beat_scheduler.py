import os

from celery.beat import PersistentScheduler

HEARTBEAT_FILE = "/tmp/celerybeat-heartbeat"


class HeartbeatPersistentScheduler(PersistentScheduler):
    """PersistentScheduler that touches a heartbeat file on every tick.

    The shelve-backed schedule file is only written when beat mutates its
    state, so its mtime drifts well past our healthcheck threshold. Touching
    a dedicated file from inside the beat loop gives a direct liveness signal.
    """

    def tick(self, *args, **kwargs):
        try:
            with open(HEARTBEAT_FILE, "a"):
                os.utime(HEARTBEAT_FILE, None)
        except OSError:
            pass
        return super().tick(*args, **kwargs)
