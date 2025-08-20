from django.apps import AppConfig
import os, threading, pika, json
import requests, time
from datetime import datetime
from django.utils.timezone import now
from django.contrib.auth import get_user_model
import uuid as uuidlib

class ClientConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'client'

    thread_started = False 

    def ready(self):
        if os.environ.get("RUN_MAIN") == "true":
            if not self.thread_started:
                self.thread_started = True
                threading.Thread(target=self.consumer, daemon=True).start()
                threading.Thread(target=self.check_connections, daemon=True).start()


    def consumer(self):
        from client.models import Client, ClientLog
        from user.models import User

        def callback(ch, method, properties, body):
            action = "login"
            data = json.loads(body.decode())
            uuid = data.get("uuid")
            hostname = data.get("hostname", "")
            ip_address = data.get("ip_address", "")
            mac_address = data.get("mac_address", "")
            username = data.get("username", "unknown") 
            is_active = False

            if not uuid:
                uuid = str(uuidlib.uuid4())  

            try:
                user = User.objects.get(username=username)
                is_active = True
            except User.DoesNotExist:
                action = "connected"
                user = None

            try:
                client = Client.objects.get(uuid=uuid)
            except Client.DoesNotExist:
                action = "register"
                client = Client(
                    hostname=hostname,
                    uuid=uuid,
                    mac_address=mac_address,
                    ip_address=ip_address,
                    is_active=True
                )
                client.save()

            if client.ip_address != ip_address or client.mac_address != mac_address or client.hostname != hostname or client.is_active != is_active:
                client.ip_address = ip_address
                client.mac_address = mac_address
                client.hostname = hostname
                client.is_active = is_active
                client.save()

            if user and not client.users_logged_in.filter(id=user.id).exists():
                client.users_logged_in.add(user)

            ClientLog.objects.create(
                client=client,
                action=action,
                details={
                    "uuid": uuid,
                    "user": username,
                    "ip": ip_address,
                    "hostname": hostname,
                    "timestamp": now().isoformat()
                }
            )

            if properties.reply_to:
                response = json.dumps({"uuid": uuid})
                ch.basic_publish(
                    exchange='',
                    routing_key=properties.reply_to,
                    properties=pika.BasicProperties(
                        correlation_id=properties.correlation_id
                    ),
                    body=response
                )

            self.publish_user_policies(user)

        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=os.environ.get('RABBITMQ_HOST'),
                credentials=pika.PlainCredentials(os.environ.get('RABBITMQ_USER'), os.environ.get('RABBITMQ_PASS'))
            )
        )
        channel = connection.channel()
        channel.queue_declare(queue='client_status', durable=True)
        channel.basic_consume(queue='client_status', on_message_callback=callback, auto_ack=True)
        channel.start_consuming()

    def check_connections(self):
        from client.models import Client, ClientLog
        while True:
            rabbitmq_server_ip = os.environ.get('RABBITMQ_HOST')
            RABBITMQ_API_URL = f"http://{rabbitmq_server_ip}:{os.environ.get('RABBITMQ_PORT')}/api/connections"

            response = requests.get(RABBITMQ_API_URL, auth=(os.environ.get('RABBITMQ_USER'), os.environ.get('RABBITMQ_PASS')))
            response.raise_for_status()
            connections = response.json()

            agent_connections = [
                conn.get("peer_host") for conn in connections
                if conn.get("peer_host") != rabbitmq_server_ip
            ]
            clients = Client.objects.all()
            for client in clients:
                if client.ip_address not in agent_connections and client.is_active:
                    ClientLog.objects.create(
                        client=client,
                        action="disconnected",
                        details={
                            "uuid": client.uuid,
                            "ip": client.ip_address,
                            "hostname": client.hostname,
                            "timestamp": now().isoformat()
                        }
                    )
                    client.is_active = False
                    client.save()
                if client.ip_address in agent_connections and not client.is_active:
                    ClientLog.objects.create(
                        client=client,
                        action="connected",
                        details={
                            "uuid": client.uuid,
                            "ip": client.ip_address,
                            "hostname": client.hostname,
                            "timestamp": now().isoformat()
                        }
                    )
                    client.is_active = True
                    client.save()
            time.sleep(5)

    def publish_user_policies(self, user):
        from user.models import User
        from policy.models import Policy

        if user and user.is_active:
            user_policies = User.objects.filter(id=user.id).values_list('policies__id', flat=True)
            if user_policies:
                user_policies = Policy.objects.filter(id__in=user_policies)
            else:
                user_policies = Policy.objects.none()
            
            message = {
                "username": user.username,
                "policies": list(user_policies.values('policy_type__name', 'parameters'))
            }

            conn_params = pika.ConnectionParameters(
                host=os.environ.get('RABBITMQ_HOST'),
                credentials=pika.PlainCredentials(os.environ.get('RABBITMQ_USER'), os.environ.get('RABBITMQ_PASS'))
            )
            connection = pika.BlockingConnection(conn_params)
            channel = connection.channel()
            channel.queue_declare(queue='user_policy_queue', durable=True)
            
            channel.basic_publish(
                exchange='',
                routing_key='user_policy_queue',
                body=json.dumps(message),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            connection.close()