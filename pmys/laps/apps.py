import os, json, threading, pika
from django.apps import AppConfig

class LapsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'laps'
    _threads_started = False

    def ready(self):
        if os.environ.get("RUN_MAIN") != "true":
            return
        if self._threads_started:
            return
        self._threads_started = True

        t = threading.Thread(target=self.consume_secret_reports, daemon=True)
        t.start()

    def consume_secret_reports(self):
        try:
            from laps.services import upsert_secret_from_agent
        except Exception:
            return

        host = os.environ.get('RABBITMQ_HOST')
        user = os.environ.get('RABBITMQ_USER')
        pw   = os.environ.get('RABBITMQ_PASS')
        if not (host and user and pw):
            return

        try:
            conn = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=host,
                    credentials=pika.PlainCredentials(user, pw)
                )
            )
            ch = conn.channel()
            ch.queue_declare(queue='laps_secret_reports', durable=True)

            def cb(chx, method, props, body):
                try:
                    payload = json.loads(body.decode() if isinstance(body, (bytes, bytearray)) else body)
                    upsert_secret_from_agent(payload)
                except Exception:
                    pass

            ch.basic_consume(queue='laps_secret_reports', on_message_callback=cb, auto_ack=True)
            ch.start_consuming()
        except Exception:
            return
