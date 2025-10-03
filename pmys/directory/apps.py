# directory/apps.py
from django.apps import AppConfig
import os
import threading
import time
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class DirectoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = "directory"     # python package/module adı (klasör adı)
    label = "ldap"         # <- burada migration'ların beklediği app label'i veriyoruz
    verbose_name = "LDAP sync"
    thread_started = False

    def ready(self):
        if os.environ.get("RUN_MAIN") != "true":
            return
        if not self.thread_started:
            self.thread_started = True
            interval = int(getattr(settings, "LDAP_SYNC_INTERVAL", 300))
            t = threading.Thread(target=self._periodic_sync, args=(interval,), daemon=True)
            t.start()
            logger.info("LDAP sync thread started with interval %s seconds", interval)

    def _periodic_sync(self, interval: int):
        from .sync import full_sync
        while True:
            try:
                logger.info("Starting LDAP full sync")
                res = full_sync()
                logger.info("LDAP sync finished: %s", res)
            except Exception:
                logger.exception("LDAP sync failed")
            time.sleep(interval)
