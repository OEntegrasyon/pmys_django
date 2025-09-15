import os, json, pika, secrets, string
from datetime import timedelta, datetime, timezone
from typing import Any, Optional, Dict, Tuple, List

from django.db import transaction
from django.utils import timezone as djtz

from client.models import Client
from .models import LapsPolicy, LapsSecret, LapsSecretHistory, LapsAccessLog, LapsAssignment
from .utils import enc, dec

def resolve_policy_and_account_for_client(client: Client) -> Tuple[Optional[LapsPolicy], str]:
    """
    Öncelik: client assignment (ileride group/org eklenebilir)
    Dönüş: (policy or None, account_name string)
    """
    a = (LapsAssignment.objects
         .filter(enabled=True, target_type='client', target_id=client.uuid)
         .order_by('-id')
         .first())
    if a:
        pol = a.policy
        acc = a.account_name_override or pol.account_name or "Administrator"
        return pol, acc

    # fallback: eski mantık
    pol = resolve_policy_for_client(client)
    return pol, (pol.account_name if pol else "Administrator")

# -------- password generator (server-side) --------
def generate_password(length=16, use_upper=True, use_lower=True, use_digits=True, use_symbols=True) -> str:
    pools = []
    if use_upper:  pools.append(string.ascii_uppercase)
    if use_lower:  pools.append(string.ascii_lowercase)
    if use_digits: pools.append(string.digits)
    if use_symbols: pools.append("!@#$%^&*-_=+?")
    if not pools:  pools = [string.ascii_letters + string.digits]
    allchars = "".join(pools)
    parts = [secrets.choice(p) for p in pools]
    parts += [secrets.choice(allchars) for _ in range(max(0, length - len(parts)))]
    secrets.SystemRandom().shuffle(parts)
    return "".join(parts[:length])

def resolve_policy_for_client(client: Client) -> Optional[LapsPolicy]:
    return LapsPolicy.objects.filter(disabled=False).order_by("-id").first()

# -------- MQ publisher --------
def publish_laps_command(payload: Dict):
    """
    payload:
      action: "set_local_admin_password"
      uuid: "<client uuid>"
      account: "Administrator"
      new_password: "<opt>"
      expires_at: "UTC ISO Z"
      post_auth: {action, delay_minutes}
      rename: {enabled, new_name}
      policy: {...} # optional
    """
    host = os.environ.get('RABBITMQ_HOST')
    user = os.environ.get('RABBITMQ_USER')
    pw   = os.environ.get('RABBITMQ_PASS')
    if not (host and user and pw):
        return
    conn = pika.BlockingConnection(pika.ConnectionParameters(
        host=host, credentials=pika.PlainCredentials(user, pw)
    ))
    ch = conn.channel()
    ch.queue_declare(queue="laps_command", durable=True)
    ch.basic_publish(
        exchange="",
        routing_key="laps_command",
        body=json.dumps(payload).encode(),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )
    conn.close()

# -------- rotate: server generate + agent apply --------
@transaction.atomic
def rotate_now(client_id: int, by: str = "") -> Tuple[LapsSecret, str]:
    client = Client.objects.select_for_update().get(id=client_id)
    policy, account = resolve_policy_and_account_for_client(client)

    # mevcut secret ve history
    try:
        secret = LapsSecret.objects.select_for_update().get(client=client, account_name=account)
        if secret.password_encrypted:
            LapsSecretHistory.objects.create(
                client=client, account_name=secret.account_name,
                password_encrypted=secret.password_encrypted, version=secret.version
            )
        version = secret.version + 1
    except LapsSecret.DoesNotExist:
        secret = LapsSecret(client=client, account_name=account)
        version = 1

    # parola üret
    pwd = generate_password(
        length=(policy.length if policy else 16),
        use_upper=(policy.use_upper if policy else True),
        use_lower=(policy.use_lower if policy else True),
        use_digits=(policy.use_digits if policy else True),
        use_symbols=(policy.use_symbols if policy else True),
    )

    # kaydet (DB)
    secret.password_encrypted = enc(pwd)
    secret.version = version
    secret.last_rotated_at = djtz.now()
    secret.expires_at = djtz.now() + timedelta(days=(policy.rotation_days if policy else 30))
    secret.policy = policy
    secret.save()

    # history prune
    keep = (policy.history_keep if policy else 10)
    if keep >= 0:
        qs = LapsSecretHistory.objects.filter(client=client, account_name=account).order_by("-rotated_at", "-version")
        ids = list(qs.values_list("id", flat=True))
        if len(ids) > keep:
            LapsSecretHistory.objects.filter(id__in=ids[keep:]).delete()

    # ajana gönder
    publish_laps_command({
        "action": "set_local_admin_password",
        "uuid": client.uuid,
        "account": account,
        "new_password": pwd,
        "expires_at": secret.expires_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "post_auth": {
            "action": (policy.post_auth_action if policy else "none"),
            "delay_minutes": (policy.post_auth_delay_minutes if policy else 0),
        },
        "rename": {
            "enabled": bool(policy and policy.rename_admin and policy.rename_admin_to),
            "new_name": (policy.rename_admin_to if (policy and policy.rename_admin and policy.rename_admin_to) else ""),
        },
        # opsiyonel olarak policy'yi de ekliyoruz; ajan kendi üretmek isterse kullansın
        "policy": {
            "length": policy.length if policy else 16,
            "use_upper": policy.use_upper if policy else True,
            "use_lower": policy.use_lower if policy else True,
            "use_digits": policy.use_digits if policy else True,
            "use_symbols": policy.use_symbols if policy else True,
            "rotation_days": policy.rotation_days if policy else 30,
            "enforce_max_age": policy.enforce_max_age if policy else True,
        }
    })

    LapsAccessLog.objects.create(client=client, secret=secret, action="rotate", requested_by=by, result="ok")
    return secret, pwd

# -------- agent → server report path --------
def upsert_secret_from_agent(report: Dict):
    uuid = report.get("uuid")
    if not uuid:
        return
    try:
        client = Client.objects.get(uuid=uuid)
    except Client.DoesNotExist:
        return

    ok = report.get("ok", False)
    account = report.get("account") or "Administrator"
    pwd = (report.get("password") or "") if ok else ""
    expires_at = report.get("expires_at")
    expires_dt = None
    if expires_at:
        try:
            expires_dt = datetime.strptime(expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except Exception:
            expires_dt = None

    with transaction.atomic():
        try:
            secret = LapsSecret.objects.select_for_update().get(client=client, account_name=account)
            if secret.password_encrypted:
                LapsSecretHistory.objects.create(
                    client=client, account_name=secret.account_name,
                    password_encrypted=secret.password_encrypted, version=secret.version
                )
            secret.version += 1
        except LapsSecret.DoesNotExist:
            secret = LapsSecret(client=client, account_name=account, version=1)

        if pwd:
            secret.password_encrypted = enc(pwd)
        secret.last_rotated_at = djtz.now()
        if expires_dt:
            secret.expires_at = expires_dt
        secret.save()

    # policy'ye göre prune
    pol = resolve_policy_for_client(client)
    keep = (pol.history_keep if pol else 10)
    if keep >= 0:
        qs = LapsSecretHistory.objects.filter(client=client, account_name=account).order_by("-rotated_at", "-version")
        ids = list(qs.values_list("id", flat=True))
        if len(ids) > keep:
            LapsSecretHistory.objects.filter(id__in=ids[keep:]).delete()

    LapsAccessLog.objects.create(
        client=client, secret=secret, action=("report" if ok else "error"),
        result=("ok" if ok else (report.get("error") or "agent-error"))
    )

# -------- reads & helpers --------
def safe_account_for(client: Client) -> str:
    pol = resolve_policy_for_client(client)
    return pol.account_name if pol else "Administrator"

def get_secret_for_client(client_id: int, context: Optional[Dict[str, Any]] = None) -> Dict:
    context = context or {}
    client = Client.objects.get(id=client_id)
    policy, account = resolve_policy_and_account_for_client(client)

    try:
        s = LapsSecret.objects.get(client=client, account_name=account)
    except LapsSecret.DoesNotExist:
        raise ValueError("Bu makine için kayıtlı parola yok. Önce 'Döndür' yapın.")

    password = dec(s.password_encrypted) if s.password_encrypted else ""
    now = djtz.now()
    expires_in = int((s.expires_at - now).total_seconds()) if s.expires_at else None

    # LOG: view + zengin alanlar
    LapsAccessLog.objects.create(
        client=client,
        secret=s,
        action="view",
        requested_by=(context.get("actor") or ""),
        result="ok",
        reason=(context.get("reason") or ""),
        ticket=(context.get("ticket") or ""),
        ip=context.get("ip"),
        user_agent=(context.get("ua") or ""),
    )

    return {
        "client_id": client.id,
        "client_uuid": client.uuid,
        "account": s.account_name,
        "password": password,
        "version": s.version,
        "last_rotated_at": s.last_rotated_at,
        "expires_at": s.expires_at,
        "expires_in": expires_in,
        "view_ttl_seconds": (policy.view_ttl_seconds if policy else 15),
    }

def get_secret_for_machine_key(key: str, context: Optional[Dict[str, Any]] = None) -> dict:
    c = _get_client_by_key(key)
    return get_secret_for_client(c.pk, context=context)

def _get_client_by_key(key: str) -> Client:
    from django.core.exceptions import ObjectDoesNotExist
    try: return Client.objects.get(pk=int(key))
    except Exception: pass
    try: return Client.objects.get(uuid=key)
    except ObjectDoesNotExist: pass
    try: return Client.objects.get(hostname=key)
    except ObjectDoesNotExist:
        raise ValueError(f"Machine not found for key: {key}")

def rotate_now_for_machine_key(key: str) -> dict:
    c = _get_client_by_key(key)
    secret, _pwd = rotate_now(c.pk)
    return {"client_id": c.pk, "client_uuid": c.uuid, "version": secret.version, "expires_at": secret.expires_at}

def bulk_rotate_by_keys(keys: List[str], by: str = "") -> Tuple[bool, List[dict]]:
    errors = []
    for k in keys:
        try:
            c = _get_client_by_key(k); rotate_now(c.pk, by=by)
        except Exception as e:
            errors.append({"key": k, "error": str(e)})
    if keys:
        try:
            first = _get_client_by_key(keys[0])
            LapsAccessLog.objects.create(client=first, secret=None, action="bulk_rotate", requested_by=by, result=f"count={len(keys)}")
        except Exception:
            pass
    return (len(errors) == 0, errors)

def get_history_for_machine_key(key: str) -> List[Dict]:
    c = _get_client_by_key(key)
    items = (LapsSecretHistory.objects
             .filter(client=c)
             .order_by("-rotated_at", "-version")
             .values("account_name", "version", "rotated_at"))
    return list(items)
