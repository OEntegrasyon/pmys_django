from dataclasses import dataclass
import re
from typing import List, Dict, Optional, Literal, Tuple, Set

from .serializers import ImportPayloadSerializer
from . import services as svc

ChangeAction = Literal["create","update","delete","move","membership_add","membership_remove","lock","unlock"]
ChangeKind = Literal["organization","group","user"]

@dataclass
class Change:
    kind: ChangeKind
    action: ChangeAction
    dn: Optional[str] = None
    targetDn: Optional[str] = None
    before: Optional[dict] = None
    after: Optional[dict] = None
    diff: Optional[dict] = None
    reasons: Optional[List[str]] = None
    warnings: Optional[List[str]] = None
    blockers: Optional[List[str]] = None
    preconditions: Optional[dict] = None

def _norm(s: str | None) -> str:
    return (s or "").strip().lower()

def _is_dn(s: str | None) -> bool:
    return isinstance(s, str) and bool(re.search(r"(^|,)cn=", s or "", flags=re.IGNORECASE))

def _parse_cn_from_dn(dn: str | None) -> str | None:
    if not isinstance(dn, str):
        return None
    m = re.match(r"\s*cn\s*=\s*([^,]+)", dn, flags=re.IGNORECASE)
    return m.group(1) if m else None

def _cn_from_cn_or_dn(val: Optional[str]) -> Optional[str]:
    """CN ise doğrudan döndür; DN ise cn=... kısmını soyup CN olarak döndür."""
    if not val:
        return None
    s = str(val).strip()
    if _is_dn(s):
        cn = _parse_cn_from_dn(s)
        return cn or s
    return s

def _index_tree(tree: dict):
    org_by_name: Dict[str, dict] = {}
    group_by_key: Dict[Tuple[str, str], dict] = {}   # (orgName, groupCN)
    user_by_uid: Dict[Tuple[str, str], dict] = {}    # (orgName, uid)

    for o in tree.get("organizations", []):
        on = o.get("name")
        if not on:
            continue
        org_by_name[on] = o
        for g in (o.get("groups") or []):
            gcn = g.get("name")
            if gcn:
                group_by_key[(on, gcn)] = g
        for u in (o.get("users") or []):
            uid = u.get("uid")
            if uid:
                user_by_uid[(on, uid)] = u
    return org_by_name, group_by_key, user_by_uid

def _org_dn(name: str) -> str:
    return svc.org_dn(name)

def _group_dn(cn: str, orgdn: str) -> str:
    return svc.group_dn(cn, orgdn)

def _user_dn(uid: str, parent_dn: str) -> str:
    return svc.user_dn(uid, parent_dn)

def _cn_from_cn_or_dn(val: Optional[str]) -> Optional[str]:
    if not val: return None
    s = str(val)
    if "," in s and "=" in s:
        try:
            head = s.split(",", 1)[0]
            k, v = head.split("=", 1)
            return v if k.lower().strip() == "cn" else s
        except Exception:
            return s
    return s

def _first(lst: List[dict], key: str) -> Optional[str]:
    if not lst: return None
    v = lst[0].get(key)
    return str(v) if v is not None else None

def _parent_dn_from_user(u: dict, orgdn: str) -> Optional[str]:
    u_dn = u.get("dn")
    if isinstance(u_dn, str) and "," in u_dn:
        return ",".join(u_dn.split(",", 1)[1:])
    grs = u.get("groups") or []
    if grs:
        gcn = _cn_from_cn_or_dn(grs[0])
        if gcn:
            return _group_dn(gcn, orgdn)
    pg = u.get("primaryGroup")
    if isinstance(pg, str) and pg:
        if "cn=" in pg.lower():
            return ",".join(pg.split(",",1)[1:])  
        return _group_dn(pg, orgdn)
    return None

def compute_plan(payload: dict, options: dict | None = None):
    """
    - primaryGroup: CN veya DN destekli; yoksa user.groups[0] -> org/payload ilk grup fallback
    - DN koruma: payload'taki 'dn' varsa create sırasında birebir kullanılır (create_user_at_dn)
    - autoCreateMissingGroups ile eksik parent grup otomatik eklenebilir
    """
    options = options or {}
    auto_create_missing_groups = bool(options.get("autoCreateMissingGroups", False))

    current = svc.load_tree()
    org_idx, grp_idx, usr_idx = _index_tree(current)

    changes: List[Change] = []
    blockers: List[dict] = []
    warnings: List[dict] = []

    stats = {
        "organizations":{"create":0,"update":0,"delete":0,"skip":0},
        "groups":{"create":0,"update":0,"delete":0,"skip":0},
        "users":{"create":0,"update":0,"move":0,"delete":0,"skip":0},
        "memberships":{"add":0,"remove":0}
    }

    ImportPayloadSerializer(data=payload).is_valid(raise_exception=True)

    for org in payload.get("organizations", []) or []:
        oname: str = org["name"]
        odesc: str = org.get("description","") or ""
        orgdn: str = _org_dn(oname)

        existing_org = org_idx.get(oname)
        if not existing_org:
            changes.append(Change(kind="organization", action="create",
                                  targetDn=orgdn, after={"name":oname,"description":odesc},
                                  reasons=["organizasyon mevcut değil"]))
            stats["organizations"]["create"] += 1
        else:
            old_desc = existing_org.get("description","") or ""
            if old_desc != odesc:
                changes.append(Change(kind="organization", action="update",
                                      dn=existing_org["dn"],
                                      before={"description":old_desc},
                                      after={"description":odesc},
                                      reasons=["description farkı"]))
                stats["organizations"]["update"] += 1

        payload_group_cns: Set[str] = { (g.get("cn") or g.get("name")) for g in (org.get("groups") or []) if (g.get("cn") or g.get("name")) }

        for g in (org.get("groups") or []):
            gcn = g.get("cn") or g.get("name")
            if not gcn:
                continue
            exp_dn = _group_dn(gcn, orgdn)
            exists = (oname, gcn) in grp_idx
            if not exists:
                changes.append(Change(kind="group", action="create",
                                      targetDn=exp_dn,
                                      after={"cn": gcn, "description": g.get("description","")},
                                      reasons=["grup mevcut değil"]))
                stats["groups"]["create"] += 1
            else:
                eg = grp_idx[(oname, gcn)]
                old_d = (eg.get("description","") or "")
                new_d = (g.get("description","") or "")
                if old_d != new_d:
                    changes.append(Change(kind="group", action="update",
                                          dn=eg["dn"],
                                          before={"description":old_d},
                                          after={"description":new_d},
                                          reasons=["description farkı"]))
                    stats["groups"]["update"] += 1

        first_payload_group_cn = _first(org.get("groups") or [], "cn")
        first_existing_group_cn = None
        if existing_org:
            ex_groups = existing_org.get("groups") or []
            first_existing_group_cn = _first(ex_groups, "name")

        for u in (org.get("users") or []):
            uid = u["uid"]

            primary_in = u.get("primaryGroup")
            primary_cn = _cn_from_cn_or_dn(primary_in) if primary_in else None

            if not primary_cn:
                ugrs = u.get("groups") or []
                if ugrs:
                    primary_cn = _cn_from_cn_or_dn(ugrs[0])
                    if primary_cn:
                        warnings.append({"kind":"user","uid":uid,"reason":f"primaryGroup yok; groups[0] ({primary_cn}) atandı"})
                if not primary_cn and first_payload_group_cn:
                    primary_cn = first_payload_group_cn
                    warnings.append({"kind":"user","uid":uid,"reason":f"primaryGroup yok; payload ilk grup ({primary_cn}) atandı"})
                if not primary_cn and first_existing_group_cn:
                    primary_cn = first_existing_group_cn
                    warnings.append({"kind":"user","uid":uid,"reason":f"primaryGroup yok; mevcut ağaç ilk grup ({primary_cn}) atandı"})

            if primary_cn:
                parent_dn = _group_dn(primary_cn, orgdn)
            else:
                parent_dn = _parent_dn_from_user(u, orgdn)

            if not parent_dn:
                blockers.append({"kind":"user","uid":uid,"reason":"ebeveyn belirlenemedi (grup yok)"})
                continue

            if parent_dn.lower().startswith("cn="):
                gcn = _cn_from_cn_or_dn(parent_dn.split(",",1)[0])
                group_exists_now = (oname, gcn) in grp_idx if gcn else False
                will_be_created = gcn in payload_group_cns if gcn else False
                if not group_exists_now and not will_be_created:
                    if auto_create_missing_groups:
                        changes.append(Change(kind="group", action="create",
                                              targetDn=parent_dn,
                                              after={"cn": gcn, "description": ""},
                                              reasons=["ebeveyn grup yok; otomatik oluştur"]))
                        stats["groups"]["create"] += 1
                    else:
                        blockers.append({"kind":"user","uid":uid,"reason":f"ebeveyn grup yok: {parent_dn}"})
                        continue

            expected_user_dn = u.get("dn") or _user_dn(uid, parent_dn)
            user_exists = (oname, uid) in usr_idx

            if not user_exists:
                after = {
                    "uid": uid,
                    "givenName": u.get("givenName",""),
                    "sn": u.get("sn",""),
                    "mail": u.get("mail",""),
                    "phone": u.get("phone",""),
                    "groups": u.get("groups") or [],
                    "isActive": u.get("isActive", True),
                    "userPassword": u.get("userPassword"),
                    "dn": u.get("dn"),
                    "uidNumber": u.get("uidNumber"),
                    "gidNumber": u.get("gidNumber"),
                    "homeDirectory": u.get("homeDirectory"),
                    "loginShell": u.get("loginShell"),
                }
                changes.append(Change(kind="user", action="create",
                                      targetDn=expected_user_dn, after=after,
                                      reasons=["kullanıcı mevcut değil"],
                                      preconditions={"notExists": expected_user_dn}))
                stats["users"]["create"] += 1
            else:
                ex = usr_idx[(oname, uid)]
                ex_parent_dn = ex["dn"].split(",",1)[1]
                if ex_parent_dn != parent_dn:
                    changes.append(Change(kind="user", action="move",
                                          dn=ex["dn"], targetDn=parent_dn,
                                          reasons=[f"primaryGroup/DN uyumu"]))
                    stats["users"]["move"] += 1

                diffs = {}
                def _pick(key_src, key_tree, alias=None):
                    old = ex.get(key_tree, "")
                    new = u.get(key_src, "")
                    if (old or "") != (new or ""):
                        diffs[(alias or key_tree)] = {"from": old, "to": new}
                _pick("mail","mail")
                _pick("givenName","givenName")
                _pick("sn","sn")
                _pick("phone","phone","phone")

                if diffs:
                    changes.append(Change(kind="user", action="update",
                                          dn=ex["dn"], diff=diffs,
                                          reasons=["alan farkı"],
                                          preconditions={"exists": True}))
                    stats["users"]["update"] += 1

                if "isActive" in u:
                    want_active = bool(u["isActive"])
                    if bool(ex.get("isActive", True)) != want_active:
                        changes.append(Change(kind="user",
                                              action=("unlock" if want_active else "lock"),
                                              dn=ex["dn"], reasons=["aktiflik farkı"]))

                have_groups = set(ex.get("groups") or [])
                want_groups = set(u.get("groups") or [])
                for add in sorted(want_groups - have_groups):
                    changes.append(Change(kind="user", action="membership_add",
                                          dn=ex["dn"], targetDn=_group_dn(add, orgdn)))
                    stats["memberships"]["add"] += 1
                for rem in sorted(have_groups - want_groups):
                    changes.append(Change(kind="user", action="membership_remove",
                                          dn=ex["dn"], targetDn=_group_dn(rem, orgdn)))
                    stats["memberships"]["remove"] += 1

    return changes, stats, blockers, warnings

def _diff_to_update_kwargs(diff: dict) -> dict:
    data = {}
    for k, ch in (diff or {}).items():
        data[k] = ch.get("to")
    return data

def _normalize_error(e: Exception) -> dict:
    try:
        if hasattr(e, "args") and e.args and isinstance(e.args[0], dict) and "description" in e.args[0]:
            res = e.args[0]
            return {"code": res.get("description"), "detail": res}
        return {"code": e.__class__.__name__, "detail": str(e)}
    except Exception:
        return {"code": "UnknownError", "detail": str(e)}

def apply_plan(changes: List[Change], options: dict | None = None):
    options = options or {}
    atomic = bool(options.get("atomic", False))
    cont = bool(options.get("continueOnError", True))

    results = []
    success = failed = skipped = 0

    def pick(kind: str, actions: List[str]):
        return [c for c in changes if c.kind == kind and c.action in actions]

    ordered = (
        pick("organization", ["create"]) +
        pick("group", ["create"]) +
        pick("user", ["create","move"]) +
        pick("organization", ["update"]) +
        pick("group", ["update"]) +
        pick("user", ["update"]) +
        pick("user", ["membership_add","membership_remove"]) +
        pick("user", ["lock","unlock"])
    )

    for ch in ordered:
        try:
            if ch.kind == "organization":
                if ch.action == "create":
                    svc.create_organization(ch.after["name"], ch.after.get("description",""))
                elif ch.action == "update":
                    svc.update_organization(ch.dn, description=ch.after.get("description"))

            elif ch.kind == "group":
                if ch.action == "create":
                    orgdn = ",".join(ch.targetDn.split(",")[1:])
                    svc.create_group(org_dn=orgdn, cn=ch.after["cn"], description=ch.after.get("description"))
                elif ch.action == "update":
                    svc.update_group(ch.dn, description=ch.after.get("description"))

            elif ch.kind == "user":
                if ch.action == "create":
                    uid = ch.after["uid"]
                    dn_for_create = ch.after.get("dn") or ch.targetDn
                    parent_dn = ",".join(dn_for_create.split(",")[1:])
                    orgdn = ",".join(parent_dn.split(",")[1:]) if parent_dn.lower().startswith("cn=") else parent_dn

                    data = {
                        "uid": uid,
                        "givenName": ch.after.get("givenName",""),
                        "sn": ch.after.get("sn",""),
                        "mail": ch.after.get("mail"),
                        "phone": ch.after.get("phone"),
                        "userPassword": ch.after.get("userPassword"),
                        "isActive": ch.after.get("isActive", True),
                        "uidNumber": ch.after.get("uidNumber"),
                        "gidNumber": ch.after.get("gidNumber"),
                        "homeDirectory": ch.after.get("homeDirectory"),
                        "loginShell": ch.after.get("loginShell"),
                    }

                    new_dn = svc.create_user_at_dn(dn_for_create, data, org_dn_str=orgdn)

                    for g in ch.after.get("groups") or []:
                        g_dn = svc.group_dn(_cn_from_cn_or_dn(g), orgdn) if "cn=" not in str(g).lower() else g
                        try:
                            svc.add_membership(new_dn, g_dn, uid=uid)
                        except Exception as e:
                            print(f"[WARN] grup üyeliği eklenemedi: {e}")

                    if "isActive" in ch.after and not ch.after["isActive"]:
                        svc.set_user_active(new_dn, False)

                elif ch.action == "move":
                    svc.move_user(ch.dn, ch.targetDn)

                elif ch.action == "update":
                    svc.update_user(ch.dn, data=_diff_to_update_kwargs(ch.diff))

                elif ch.action == "membership_add":
                    uid = ch.dn.split(",")[0].split("=")[1]
                    svc.add_membership(ch.dn, ch.targetDn, uid=uid)

                elif ch.action == "membership_remove":
                    uid = ch.dn.split(",")[0].split("=")[1]
                    svc.remove_membership(ch.dn, ch.targetDn, uid=uid)

                elif ch.action in ("lock","unlock"):
                    svc.set_user_active(ch.dn, active=(ch.action=="unlock"))

            results.append({"kind": ch.kind, "action": ch.action, "dn": ch.dn, "targetDn": ch.targetDn, "ok": True})
            success += 1
        except Exception as e:
            results.append({"kind": ch.kind, "action": ch.action, "dn": ch.dn, "targetDn": ch.targetDn,
                            "ok": False, "error": _normalize_error(e)})
            failed += 1
            if atomic or not cont:
                break

    summary = {"succeeded": success, "failed": failed, "skipped": skipped}
    status_code = 200 if failed == 0 else 207
    return results, summary, status_code
