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
            try:
                data = json.loads(body.decode())
                action = data.get("action", "")
                details = data.get("details", {})

                PolicyLog.objects.create(
                    action=action,
                    details=details
                )

            except Exception as e:
                print(f"POLICY LOG ERROR: Mesaj işlenirken hata oluştu: {e}")
            
            finally:
                try:
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except:
                    pass

        while True:
            try:
                connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host=os.environ.get('RABBITMQ_HOST'),
                        credentials=pika.PlainCredentials(os.environ.get('RABBITMQ_USER'), os.environ.get('RABBITMQ_PASS')),
                        heartbeat=600
                    )
                )
                channel = connection.channel()
                channel.queue_declare(queue='client_policy_log', durable=True)
                channel.basic_consume(queue='client_policy_log', on_message_callback=callback, auto_ack=False)
                
                print("Policy Log Listener başlatıldı ve dinliyor...")
                channel.start_consuming()
            
            except Exception as e:
                print(f"RabbitMQ Bağlantı Hatası (Log Listener): {e}. 5 saniye sonra tekrar denenecek...")
                import time
                time.sleep(5)