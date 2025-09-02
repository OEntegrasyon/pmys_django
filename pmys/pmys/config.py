import os
import ssl
from decouple import Config, RepositoryEnv
import pika

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(BASE_DIR, '.env')
config = Config(RepositoryEnv(env_path))

RABBITMQ = {
    'URL': config("RABBITMQ_URL"),
    'HOST': config("RABBITMQ_HOST"),
    'PORT': int(config("RABBITMQ_PORT")),
    'USER': config("RABBITMQ_USER"),
    'PASS': config("RABBITMQ_PASS"),
}

DB = {
    'NAME': config("DB_NAME"),
    'USER': config("DB_USER"),
    'PASSWORD': config("DB_PASSWORD"),
    'HOST': config("DB_HOST"),
    'PORT': config("DB_PORT"),
}

LDAP = {
    'SERVER': config("LDAP_SERVER"),
    'USER_DN': config("LDAP_USER_DN"),
    'PASSWORD': config("LDAP_PASSWORD"),
    'BASE_DN': config("LDAP_BASE_DN"),
}

LDAP_DJANGO = {
    'AUTH_LDAP_SERVER_URI': config("LDAP_SERVER"),
    'AUTH_LDAP_BIND_DN': config("LDAP_USER_DN"),
    'AUTH_LDAP_BIND_PASSWORD': config("LDAP_PASSWORD"),
    'AUTH_LDAP_USER_SEARCH_BASE': config("LDAP_BASE_DN"),
    'AUTH_LDAP_USER_PLACEMENT': config("LDAP_USER_PLACEMENT"),
    'AUTH_GROUP_SCHEMA': config("LDAP_GROUP_SCHEMA"),
    'AUTH_LOCK_METHOD': config("LDAP_AUTH_LOCK_METHOD"),
}