from typing import Dict, List, Optional
from django.conf import settings
from ldap3 import BASE, SUBTREE as LDAP_SUBTREE, LEVEL as LDAP_LEVEL
from ldap3.core.exceptions import LDAPAttributeError
from .ldap_client import ldap_conn
from .utils import ADD, DELETE, REPLACE
import base64, os, hashlib

CFG = settings.LDAP_API
BASE_DN = CFG["BASE_DN"]
ORG_BASE_OU = CFG.get("ORG_BASE_OU") or ""
GROUP_SCHEMA = CFG["GROUP_SCHEMA"]          # "groupOfNames" | "posixGroup" | "both"
LOCK_METHOD = CFG["LOCK_METHOD"]            # "ppolicy" | "shadow"
SEED_MEMBER_DN = CFG.get("BIND_DN")

# ---------------- DN helpers ----------------
def domain_base() -> str:
    return BASE_DN

def org_container_base() -> str:
    return f"{ORG_BASE_OU},{BASE_DN}" if ORG_BASE_OU else BASE_DN

def org_dn(org_name: str) -> str:
    return f"ou={org_name},{org_container_base()}"

def group_dn(group_cn: str, org_dn_str: str) -> str:
    return f"cn={group_cn},{org_dn_str}"

def user_dn(uid: str, group_dn_str: str) -> str:
    return f"uid={uid},{group_dn_str}"

def _opt_str(v: Optional[str]) -> Optional[str]:
    if v is None: return None
    s = str(v).strip()
    return s if s else None

def _attr(entry, key, default=None):
    try:
        v = entry[key].value
        return v if v is not None else default
    except Exception:
        return default

# ---------------- Tree loader ----------------
def load_tree() -> Dict:
    from ldap3.utils.dn import parse_dn
    with ldap_conn() as c:
        c.search(
            search_base=org_container_base(),
            search_scope=LDAP_LEVEL,
            search_filter="(objectClass=organizationalUnit)",
            attributes=["ou","description"],
        )
        orgs = []
        for o in c.entries:
            o_dn = o.entry_dn
            o_name = _attr(o, "ou", "")
            o_desc = _attr(o, "description", "")

            if GROUP_SCHEMA == "both":
                group_filter = "(|(objectClass=groupOfNames)(objectClass=posixGroup))"
            elif GROUP_SCHEMA == "groupOfNames":
                group_filter = "(objectClass=groupOfNames)"
            else:
                group_filter = "(objectClass=posixGroup)"

            c.search(
                search_base=o_dn,
                search_scope=LDAP_LEVEL,
                search_filter=group_filter,
                attributes=["cn", "description", "member", "memberUid", "gidNumber"],
            )
            groups = []
            for g in c.entries:
                g_dn = g.entry_dn
                g_name = _attr(g, "cn", "")
                g_desc = _attr(g, "description", "")
                members = g.entry_attributes_as_dict.get("member", []) or []
                member_uids = g.entry_attributes_as_dict.get("memberUid", []) or []
                groups.append({
                    "dn": g_dn,
                    "name": g_name,
                    "description": g_desc,
                    "members": members,
                    "memberUids": member_uids
                })

            base_attrs = [
                "uid","givenName","sn","mail","telephoneNumber","userPassword",
                "uidNumber","gidNumber","homeDirectory"
            ]
            lock_attr = "shadowExpire" if LOCK_METHOD == "shadow" else "pwdAccountLockedTime"

            def _search_users(attrs):
                c.search(
                    search_base=o_dn,
                    search_scope=LDAP_SUBTREE,
                    search_filter="(&(objectClass=inetOrgPerson)(objectClass=posixAccount))",
                    attributes=attrs,
                )

            try:
                _search_users(base_attrs + [lock_attr])
            except LDAPAttributeError:
                _search_users(base_attrs)

            users = []
            for u in c.entries:
                user_groups = []
                for g in groups:
                    if u.entry_dn in (g["members"] or []):
                        user_groups.append(g["name"])
                    elif _attr(u, "uid") and _attr(u, "uid") in (g["memberUids"] or []):
                        user_groups.append(g["name"])

                users.append({
                    "dn": u.entry_dn,
                    "uid": _attr(u, "uid", ""),
                    "givenName": _attr(u, "givenName", ""),
                    "sn": _attr(u, "sn", ""),
                    "mail": _attr(u, "mail", ""),
                    "phone": _attr(u, "telephoneNumber", ""),
                    "userPassword": _attr(u, "userPassword", ""),
                    "uidNumber": _attr(u, "uidNumber"),
                    "gidNumber": _attr(u, "gidNumber"),
                    "homeDirectory": _attr(u, "homeDirectory", ""),
                    "isActive": not _is_locked(u),
                    "groups": user_groups,
                })

            orgs.append({
                "dn": o_dn,
                "name": o_name,
                "description": o_desc,
                "groups": groups,
                "users": users
            })

        return {"domain": BASE_DN, "organizations": orgs}

def _is_locked(user_entry) -> bool:
    try:
        locked = user_entry["pwdAccountLockedTime"].value
        if locked: return True
    except Exception:
        pass
    try:
        shadow = user_entry["shadowExpire"].value
        if shadow and int(shadow) <= 1:
            return True
    except Exception:
        pass
    return False

# ---------------- Org CRUD ----------------
def create_organization(name: str, description: str="") -> str:
    dn = org_dn(name)
    with ldap_conn() as c:
        attrs = {"objectClass": ["top","organizationalUnit"], "ou": name}
        if description:
            attrs["description"] = description
        if not c.add(dn, attributes=attrs):
            raise ValueError(c.result)
    return dn

def update_organization(dn: str, name: Optional[str]=None, description: Optional[str]=None):
    with ldap_conn() as c:
        changes = {}
        if description is not None:
            if description.strip():
                changes["description"] = [(REPLACE, [description.strip()])]
            else:
                changes["description"] = [(DELETE, [])]
        if changes and not c.modify(dn, changes):
            raise ValueError(c.result)
        if name:
            new_rdn = f"ou={name}"
            if not c.modify_dn(dn, new_rdn, True):
                raise ValueError(c.result)

def delete_organization(dn: str):
    with ldap_conn() as c:
        if not c.delete(dn):
            raise ValueError(c.result)

# ---------------- Group CRUD ----------------
def _next_number(attr_name: str, base: str) -> int:
    with ldap_conn() as c:
        if attr_name == "uidNumber":
            filt = "(&(objectClass=posixAccount)(uidNumber=*))"; attrs = ["uidNumber"]
        elif attr_name == "gidNumber":
            filt = "(&(|(objectClass=posixAccount)(objectClass=posixGroup))(gidNumber=*))"; attrs = ["gidNumber"]
        else:
            filt = f"({attr_name}=*)"; attrs = [attr_name]

        c.search(search_base=base, search_scope=LDAP_SUBTREE, search_filter=filt, attributes=attrs)

        mx = 10000
        for e in c.entries:
            try:
                val = getattr(e, attr_name, None)
                if val is None:
                    val = e.entry_attributes_as_dict.get(attr_name)
                if val is not None:
                    if hasattr(val, "value"):
                        val = val.value
                    if isinstance(val, list):
                        for v in val:
                            mx = max(mx, int(v))
                    else:
                        mx = max(mx, int(val))
            except Exception:
                pass
        return mx + 1

def create_group(org_dn: str, cn: str, description: Optional[str] = None):
    gdn = f"cn={cn},{org_dn}"
    desc = _opt_str(description)

    ocs = ["top"]
    attrs = {"cn": cn}

    if GROUP_SCHEMA in ("groupOfNames", "both"):
        ocs.append("groupOfNames")
        org_part = org_dn
        placeholder = SEED_MEMBER_DN or f"cn=placeholder,{org_part}"
        attrs["member"] = [placeholder]

    if GROUP_SCHEMA in ("posixGroup", "both"):
        ocs.append("posixGroup")
        gid = _next_number("gidNumber", org_dn)
        attrs["gidNumber"] = str(gid)

    if desc is not None:
        attrs["description"] = desc

    attrs["objectClass"] = ocs

    with ldap_conn() as c:
        if not c.add(gdn, attributes=attrs):
            raise ValueError(c.result)
    return gdn

def update_group(dn: str, name: Optional[str]=None, description: Optional[str]=None):
    with ldap_conn() as c:
        changes = {}
        if description is not None:
            desc = _opt_str(description)
            if desc is None:
                changes["description"] = [(DELETE, [])]
            else:
                changes["description"] = [(REPLACE, [desc])]
        if changes and not c.modify(dn, changes):
            raise ValueError(c.result)

        if name:
            new_rdn = f"cn={name}"
            if not c.modify_dn(dn, new_rdn, True):
                raise ValueError(c.result)

def delete_group(dn: str):
    with ldap_conn() as c:
        if not c.delete(dn):
            raise ValueError(c.result)

# ---------------- Membership ----------------
def _group_state(group_dn_str):
    with ldap_conn() as c:
        ok = c.search(
            search_base=group_dn_str,
            search_scope=BASE,
            search_filter="(objectClass=*)",
            attributes=["objectClass", "member", "memberUid", "gidNumber"],
        )
        if not ok or not c.entries:
            raise ValueError(f"Group not found: {group_dn_str}")

        e = c.entries[0]
        try:
            ocs = set(oc.lower() for oc in e["objectClass"].values)
        except Exception:
            ocs = set()

        members = e.entry_attributes_as_dict.get("member", []) or []
        member_uids = e.entry_attributes_as_dict.get("memberUid", []) or []
        return e, ocs, members, member_uids

def add_membership(user_dn_str: str, group_dn_str: str, uid: Optional[str]=None):
    with ldap_conn() as c:
        e, ocs, members, member_uids = _group_state(group_dn_str)

        if "groupofnames" in ocs:
            ops = {"member": [(ADD, [user_dn_str])]}
            ok = c.modify(group_dn_str, ops)
            if not ok:
                raise ValueError(c.result)

            if SEED_MEMBER_DN and SEED_MEMBER_DN in (members or []):
                # seed cleanup
                e2, _, members2, _ = _group_state(group_dn_str)
                mems = set(members2 or [])
                if len(mems) >= 2 and SEED_MEMBER_DN in mems:
                    c.modify(group_dn_str, {"member": [(DELETE, [SEED_MEMBER_DN])]})

        if "posixgroup" in ocs and uid:
            ok = c.modify(group_dn_str, {"memberUid": [(ADD, [uid])]})
            if not ok:
                raise ValueError(c.result)
            
def remove_membership(user_dn_str: str, group_dn_str: str, uid: Optional[str]=None):
    with ldap_conn() as c:
        e, ocs, members, member_uids = _group_state(group_dn_str)

        if "groupofnames" in ocs:
            mems = set(members or [])
            if user_dn_str in mems:
                if len(mems) <= 1:
                    print(f"[WARN] {group_dn_str} son member olduğu için silinemedi")
                else:
                    c.modify(group_dn_str, {"member": [(DELETE, [user_dn_str])]})

        if "posixgroup" in ocs and uid:
            if uid in (member_uids or []):
                c.modify(group_dn_str, {"memberUid": [(DELETE, [uid])]})

# ---------------- Users ----------------
def suggest_ids(org_dn_str: str, group_dn_str: Optional[str] = None) -> Dict[str, int]:
    uid_next = _next_number("uidNumber", org_dn_str)

    gid_next: Optional[int] = None
    if group_dn_str:
        with ldap_conn() as c:
            c.search(
                search_base=group_dn_str,
                search_scope=BASE,
                search_filter="(objectClass=*)",
                attributes=["objectClass", "gidNumber"],
            )
            if c.entries:
                e = c.entries[0]
                try:
                    ocs = set(oc.lower() for oc in e["objectClass"].values)
                except Exception:
                    ocs = set()
                if "posixgroup" in ocs:
                    try:
                        g = e["gidNumber"].value
                        if g is not None:
                            gid_next = int(g)
                    except Exception:
                        pass

    if gid_next is None:
        gid_next = _next_number("gidNumber", org_dn_str)

    return {"uidNumber": int(uid_next), "gidNumber": int(gid_next)}

def _hash_ssha(password: str) -> str:
    salt = os.urandom(4)
    sha = hashlib.sha1(password.encode('utf-8'))
    sha.update(salt)
    digest = sha.digest() + salt
    return '{SSHA}' + base64.b64encode(digest).decode('utf-8')

def create_user(org_dn_str: str, data: Dict, primary_group_dn: Optional[str]) -> str:
    if not primary_group_dn:
        raise ValueError("groupDn zorunlu")

    uid = data["uid"]
    given = data.get("givenName","")
    sn = data.get("sn","")
    cn = (given + " " + sn).strip() or uid
    mail = data.get("mail")
    phone = data.get("phone")
    userPassword = data.get("userPassword")

    uidNumber = data.get("uidNumber") or _next_number("uidNumber", org_dn_str)
    gidNumber = data.get("gidNumber")
    if gidNumber is None:
        with ldap_conn() as c:
            c.search(primary_group_dn, BASE, "(objectClass=posixGroup)", attributes=["gidNumber"])
            if c.entries and c.entries[0]["gidNumber"].value:
                gidNumber = int(c.entries[0]["gidNumber"].value)
            else:
                gidNumber = _next_number("gidNumber", org_dn_str)

    home = data.get("homeDirectory") or f"/home/{uid}"
    shell = data.get("loginShell") or "/bin/bash"

    dn = f"uid={uid},{primary_group_dn}"
    attrs = {
        "objectClass": ["top","inetOrgPerson","posixAccount","shadowAccount"],
        "uid": uid, "cn": cn, "givenName": given, "sn": sn,
        "uidNumber": str(uidNumber), "gidNumber": str(gidNumber),
        "homeDirectory": home, "loginShell": shell,
    }
    if mail:  attrs["mail"] = mail
    if phone: attrs["telephoneNumber"] = phone
    if userPassword:
        attrs["userPassword"] = _hash_ssha(userPassword)

    with ldap_conn() as c:
        if not c.add(dn, attributes=attrs):
            raise ValueError(c.result)

    add_membership(dn, primary_group_dn, uid=uid)
    return dn

def create_user_at_dn(dn: str, data: Dict, org_dn_str: Optional[str] = None) -> str:
    if "uid=" not in dn:
        raise ValueError("dn, 'uid=' ile başlamalı")

    uid = data.get("uid") or dn.split(",", 1)[0].split("=", 1)[1]
    given = data.get("givenName", "")
    sn = data.get("sn", "")
    cn = (given + " " + sn).strip() or uid

    base_dn = ",".join(dn.split(",")[1:])
    org_base = org_dn_str or base_dn
    if base_dn.lower().startswith("cn="):
        org_base = ",".join(base_dn.split(",")[1:])

    uidNumber = data.get("uidNumber") or _next_number("uidNumber", org_base)
    gidNumber = data.get("gidNumber") or _next_number("gidNumber", org_base)
    home = data.get("homeDirectory") or f"/home/{uid}"
    shell = data.get("loginShell") or "/bin/bash"

    attrs = {
        "objectClass": ["top", "inetOrgPerson", "posixAccount", "shadowAccount"],
        "uid": uid, "cn": cn, "givenName": given, "sn": sn,
        "uidNumber": str(uidNumber), "gidNumber": str(gidNumber),
        "homeDirectory": home, "loginShell": shell,
    }
    mail = data.get("mail"); phone = data.get("phone")
    if mail:  attrs["mail"] = mail
    if phone: attrs["telephoneNumber"] = phone

    userPassword = data.get("userPassword")
    if userPassword:
        attrs["userPassword"] = _hash_ssha(userPassword)

    with ldap_conn() as c:
        if not c.add(dn, attributes=attrs):
            raise ValueError(c.result)
    return dn

def update_user(dn: str, data: Dict):
    changes = {}
    def put(attr, val):
        if val is not None:
            changes[attr] = [(REPLACE, [val])]
    put("givenName", data.get("givenName"))
    put("sn", data.get("sn"))
    cn = (f"{data.get('givenName','')} {data.get('sn','')}".strip() or None)
    if cn: put("cn", cn)
    put("mail", data.get("mail"))
    put("telephoneNumber", data.get("phone"))
    user_password = data.get("userPassword")
    if user_password:
        put("userPassword", _hash_ssha(user_password))
    if data.get("uidNumber") is not None: put("uidNumber", str(data["uidNumber"]))
    if data.get("gidNumber") is not None: put("gidNumber", str(data["gidNumber"]))
    put("homeDirectory", data.get("homeDirectory"))
    put("loginShell", data.get("loginShell"))

    if changes:
        with ldap_conn() as c:
            if not c.modify(dn, changes):
                raise ValueError(c.result)

def delete_user(dn: str):
    with ldap_conn() as c:
        if not c.delete(dn):
            raise ValueError(c.result)

def move_user(user_dn_str: str, to_group_dn: str):
    current_rdn = user_dn_str.split(',')[0]
    current_parent_dn = ','.join(user_dn_str.split(',')[1:])
    new_superior = to_group_dn

    if current_parent_dn == new_superior:
        return user_dn_str

    with ldap_conn() as c:
        ok = c.modify_dn(user_dn_str, current_rdn, True, new_superior)
        if not ok:
            raise ValueError(c.result)

    new_dn = f"{current_rdn},{new_superior}"

    try:
        remove_membership(user_dn_str, current_parent_dn, uid=current_rdn.split("=")[1])
    except Exception as e:
        print(f"[WARN] eski grup üyelik silinemedi: {e}")

    try:
        add_membership(new_dn, to_group_dn, uid=current_rdn.split("=")[1])
    except Exception as e:
        print(f"[WARN] yeni gruba üyelik eklenemedi: {e}")

    return new_dn

def set_user_active(dn: str, active: bool, method: Optional[str]=None):
    method = (method or LOCK_METHOD)
    with ldap_conn() as c:
        if method == "ppolicy":
            if active:
                c.modify(dn, {"pwdAccountLockedTime": [(DELETE, [])]})
            else:
                c.modify(dn, {"pwdAccountLockedTime": [(REPLACE, ["000001010000Z"])]})
        else:
            if active:
                c.modify(dn, {"shadowExpire": [(DELETE, [])]})
            else:
                c.modify(dn, {"shadowExpire": [(REPLACE, ["1"])]})
