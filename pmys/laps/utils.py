import os
from cryptography.fernet import Fernet

_F = None

def get_fernet() -> Fernet:
    global _F
    if _F:
        return _F
    key = os.environ.get("LAPS_FERNET_KEY")
    if not key:
        raise RuntimeError(
            "LAPS_FERNET_KEY env eksik. "
            "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' "
            "ile üretip environment'a ekleyin."
        )
    _F = Fernet(key.encode() if not key.startswith("gAAAA") else key)
    return _F

def enc(text: str) -> str:
    return get_fernet().encrypt(text.encode()).decode()

def dec(token: str) -> str:
    return get_fernet().decrypt(token.encode()).decode()
