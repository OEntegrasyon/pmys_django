from django.apps import AppConfig
import os, threading, pika, json
import requests, time
from datetime import datetime
from django.utils.timezone import now
from django.contrib.auth import get_user_model
import uuid as uuidlib
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

class ClientConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'client'

    thread_started = False 

    def ready(self):
        Client = self.get_model('Client')
        m2m_changed.connect(log_client_policy_assignment, sender=Client.policies.through)
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

            self.publish_policies(user, client)

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

    def publish_policies(self, user, client): 
        from policy.models import Policy
        from .models import Client 

        user_policies = Policy.objects.none()
        
        if user and user.is_active:
            try:
 
                user_with_policies = user.__class__.objects.prefetch_related('policies__policy_type').get(id=user.id)
                user_policies = user_with_policies.policies.all()
            except user.__class__.DoesNotExist:
                pass 


        try:
            client_with_policies = Client.objects.prefetch_related('policies__policy_type').get(id=client.id)
            client_policies = client_with_policies.policies.all()
        except Client.DoesNotExist:
            client_policies = Policy.objects.none()

        def serialize_policies(policy_queryset):
            return list(policy_queryset.values(
                'policy_type__name', 
                'parameters',
                'policy_type__is_cis'
            ))

        message = {
            "username": user.username if user else None,
            "client_uuid": client.uuid,
            "policies": {
                "user": serialize_policies(user_policies),
                "client": serialize_policies(client_policies)
            }
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

def log_client_policy_assignment(sender, instance, action, pk_set, **kwargs):

    from .models import ClientLog, Client
    from policy.models import Policy

    if not isinstance(instance, Client):
        return

    if getattr(instance, '_m2m_signal_running', False):
        return
    
    setattr(instance, '_m2m_signal_running', True)

    try:
        if action == "post_add":
            policies = Policy.objects.filter(pk__in=pk_set)
            for policy in policies:
                ClientLog.objects.create(
                    client=instance, 
                    action="policy_assigned", 
                    details={
                        "policy_id": policy.id,
                        "policy_name": policy.name,
                        "policy_type": policy.policy_type.name,
                        "message": f"'{policy.name}' politikası istemciye atandı."
                    }
                )
        elif action == "post_remove":
            policies = Policy.objects.filter(pk__in=pk_set)
            for policy in policies:
                ClientLog.objects.create(
                    client=instance,
                    action="policy_removed", 
                    details={
                        "policy_id": policy.id,
                        "policy_name": policy.name,
                        "message": f"'{policy.name}' politikası istemciden kaldırıldı."
                    }
                )
    finally:
        delattr(instance, '_m2m_signal_running')