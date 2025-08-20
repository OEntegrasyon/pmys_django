from django.apps import AppConfig
import os
import threading
import pika
import json



class PolicyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'policy'

    thread_started = False 

    def ready(self):
        if os.environ.get("RUN_MAIN") == "true":
            if not self.thread_started:
                self.thread_started = True
                threading.Thread(target=self.policy_log_listener, daemon=True).start()

    def policy_log_listener(self):
        from policy.models import PolicyLog

        def callback(ch, method, properties, body):
            data = json.loads(body.decode())
            action = data.get("action", "")
            details = data.get("details", {})

            PolicyLog.objects.create(
                action=action,
                details=details
            )

        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=os.environ.get('RABBITMQ_HOST'),
                credentials=pika.PlainCredentials(os.environ.get('RABBITMQ_USER'), os.environ.get('RABBITMQ_PASS'))
            )
        )
        channel = connection.channel()
        channel.queue_declare(queue='client_policy_log', durable=True)
        channel.basic_consume(queue='client_policy_log', on_message_callback=callback, auto_ack=True)
        channel.start_consuming()