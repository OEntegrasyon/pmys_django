import base64
from typing import Optional
from ldap3 import SUBTREE, LEVEL, MODIFY_REPLACE, MODIFY_ADD, MODIFY_DELETE

def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode()

def b64d(s: str) -> str:
    try:
        pad = '=' * (-len(s) % 4)
        decoded = base64.urlsafe_b64decode((s + pad).encode('ascii')).decode('utf-8')
        return decoded
    except Exception:
        return s

SUBTREE_SCOPE = SUBTREE
LEVEL_SCOPE = LEVEL
ADD = MODIFY_ADD
DELETE = MODIFY_DELETE
REPLACE = MODIFY_REPLACE