# ldap/ldap_client.py
from contextlib import contextmanager
from django.conf import settings
from ldap3 import Server, Connection, ALL

@contextmanager
def ldap_conn(auto_bind=True):
    server = Server(settings.AUTH_LDAP_SERVER_URI, get_info=ALL)
    conn = Connection(
        server,
        user=settings.AUTH_LDAP_BIND_DN,
        password=settings.AUTH_LDAP_BIND_PASSWORD,
        auto_bind=auto_bind,
    )
    try:
        yield conn
    finally:
        try:
            conn.unbind()
        except Exception:
            pass
