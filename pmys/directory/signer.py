from django.core import signing

_SALT = "ldap-import-plan"

def sign_plan(plan: dict) -> str:
    return signing.dumps(plan, salt=_SALT)

def unsign_plan(token: str) -> dict:
    return signing.loads(token, salt=_SALT)