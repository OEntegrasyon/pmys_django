# api_views.py

from dataclasses import asdict, is_dataclass
import json
import traceback
from typing import Dict, List, Tuple, Any

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from . import exporters
from . import services as svc
from .serializers import (
    ValidateRequestSerializer,
    ApplyRequestSerializer,
    ImportPayloadSerializer,
)
from .services_import import compute_plan, apply_plan, Change
from .signer import sign_plan, unsign_plan
from .utils import b64d  # utils.b64d

# ======================================================================
# Upload/Validate/Apply için cache anahtarı
# ======================================================================
CACHE_KEY = "ldap_import:{job_id}"

# ======================================================================
# Yardımcılar
# ======================================================================
def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    try:
        if is_dataclass(obj):
            return asdict(obj)
    except Exception:
        pass
    if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
        try:
            return obj.to_dict()
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return {"repr": repr(obj)}

_UI_STATS_KEYS = [
    "orgCreate","orgUpdate",
    "groupCreate","groupUpdate",
    "userCreate","userMove","userUpdate",
    "mshipAdd","mshipRemove",
]

def _map_stats_for_ui(raw_stats: Dict[str, Any], changes_list: List[Dict[str, Any]]) -> Dict[str, int]:
    raw_stats = raw_stats or {}
    mapping = {
        "org_create":"orgCreate", "orgCreate":"orgCreate",
        "org_update":"orgUpdate", "orgUpdate":"orgUpdate",
        "group_create":"groupCreate", "groupCreate":"groupCreate",
        "group_update":"groupUpdate", "groupUpdate":"groupUpdate",
        "user_create":"userCreate", "userCreate":"userCreate",
        "user_move":"userMove", "userMove":"userMove",
        "user_update":"userUpdate", "userUpdate":"userUpdate",
        "membership_add":"mshipAdd", "mship_add":"mshipAdd", "mshipAdd":"mshipAdd",
        "membership_remove":"mshipRemove","mship_remove":"mshipRemove","mshipRemove":"mshipRemove",
    }
    ui = {k: 0 for k in _UI_STATS_KEYS}
    for k,v in raw_stats.items():
        ui_key = mapping.get(k)
        if ui_key:
            try: ui[ui_key] = int(v)
            except: ui[ui_key] = 0
    if sum(ui.values()) > 0:
        return ui

    # raw boşsa changes'tan çıkar
    op_to_ui = {
        "create_org":"orgCreate","update_org":"orgUpdate",
        "create_group":"groupCreate","update_group":"groupUpdate",
        "create_user":"userCreate","move_user":"userMove","update_user":"userUpdate",
        "add_membership":"mshipAdd","remove_membership":"mshipRemove",
    }
    for ch in changes_list or []:
        op = (ch.get("op") or ch.get("type") or ch.get("action") or "").lower()
        ui_key = op_to_ui.get(op)
        if ui_key: ui[ui_key] += 1
    return ui

def _find_scope(tree_data: dict, kind: str, dn: str | None) -> Tuple[dict | None, str | None]:
    if kind == "domain" or not dn:
        scope_name = tree_data.get("domain", "export")
        try:
            scope_short = scope_name.split(",")[0].split("=")[1]
        except Exception:
            scope_short = scope_name
        return tree_data, scope_short

    for o in tree_data.get("organizations", []):
        if kind == "organization" and o.get("dn") == dn:
            return o, o.get("name", "org")
        if kind == "group":
            for g in o.get("groups", []):
                if g.get("dn") == dn:
                    return {"group": g, "organization": o, "domain": tree_data.get("domain")}, g.get("name", "group")
        if kind == "user":
            for u in o.get("users", []):
                if u.get("dn") == dn:
                    return {"user": u, "organization": o, "domain": tree_data.get("domain")}, u.get("uid", "user")
    return None, None

# ======================================================================
# Tree
# ======================================================================
class TreeView(APIView):
    def get(self, request):
        return Response(svc.load_tree())

# ======================================================================
# Organizations
# ======================================================================
class OrganizationsView(APIView):
    def post(self, request):
        name = request.data.get("name")
        if not name:
            return Response({"detail":"name gerekli"}, status=400)
        desc = (request.data.get("description") or "").strip()
        dn = svc.create_organization(name, desc)
        return Response({"dn": dn}, status=201)

class OrganizationDetailView(APIView):
    def put(self, request, b64dn: str):
        name = request.data.get("name")
        desc = (request.data.get("description") or "").strip()
        svc.update_organization(b64d(b64dn), name, desc)
        return Response({"ok": True})

    def delete(self, request, b64dn: str):
        svc.delete_organization(b64d(b64dn))
        return Response(status=204)

# ======================================================================
# Groups
# ======================================================================
class GroupsView(APIView):
    def post(self, request):
        org_dn = request.data.get("organizationDn")
        name = request.data.get("name")
        if not org_dn or not name:
            return Response({"detail":"organizationDn ve name gerekli"}, status=400)
        desc = (request.data.get("description") or "").strip()
        dn = svc.create_group(org_dn, name, desc)
        return Response({"dn": dn}, status=201)

class GroupDetailView(APIView):
    def put(self, request, b64dn: str):
        name = request.data.get("name")
        desc = (request.data.get("description") or "").strip()
        svc.update_group(b64d(b64dn), name, desc)
        return Response({"ok": True})

    def delete(self, request, b64dn: str):
        svc.delete_group(b64d(b64dn))
        return Response(status=204)

# ======================================================================
# Users
# ======================================================================
class UsersView(APIView):
    def post(self, request):
        org_dn = request.data.get("organizationDn")
        group_dn = request.data.get("groupDn")
        user = request.data.get("user") or {}
        if not org_dn or not user.get("uid"):
            return Response({"detail":"organizationDn ve user.uid gerekli"}, status=400)
        if not group_dn:
            return Response({"detail":"groupDn zorunlu"}, status=400)
        dn = svc.create_user(org_dn, user, primary_group_dn=group_dn)
        return Response({"dn": dn}, status=201)

class UserDetailView(APIView):
    def put(self, request, b64dn: str):
        svc.update_user(b64d(b64dn), request.data or {})
        return Response({"ok": True})

    def delete(self, request, b64dn: str):
        svc.delete_user(b64d(b64dn))
        return Response(status=204)

class UserMoveView(APIView):
    def post(self, request, b64dn: str):
        to_group_dn = request.data.get("toGroupDn")
        if not to_group_dn:
            return Response({"detail":"toGroupDn gerekli"}, status=400)
        svc.move_user(b64d(b64dn), to_group_dn)
        return Response({"ok": True})

class UserActiveView(APIView):
    def post(self, request, b64dn: str):
        active = bool(request.data.get("active", True))
        method = request.data.get("method")
        svc.set_user_active(b64d(b64dn), active, method=method)
        return Response({"ok": True})

# ======================================================================
# Export
# ======================================================================
class ExportView(APIView):
    renderer_classes = (JSONRenderer,)

    def _detect_format(self, request, kwargs):
        for key in ("file_format","fmt","format"):
            v = request.GET.get(key)
            if v: return v.lower()
        fmt_kw = kwargs.get("format") if kwargs and isinstance(kwargs, dict) else None
        if fmt_kw: return str(fmt_kw).lower()
        return request.GET.get("format", "json").lower()

    def get(self, request, *args, **kwargs):
        fmt = self._detect_format(request, kwargs)
        kind = request.GET.get("kind", request.query_params.get("kind", "domain"))
        dn_b64 = request.GET.get("dn_b64") or request.query_params.get("dn_b64")
        dn = b64d(dn_b64) if dn_b64 else None

        try:
            tree_data = svc.load_tree()
        except Exception as e:
            traceback.print_exc()
            return Response({"detail": f"LDAP ağacı yüklenemedi: {e}"}, status=500)

        scope_data, scope_name = _find_scope(tree_data, kind, dn)
        if scope_data is None:
            return Response(
                {"detail":"Kapsam bulunamadı","requested":{"kind":kind,"dn_b64":dn_b64,"dn_decoded":dn}},
                status=404
            )

        safe_name = "".join(c for c in str(scope_name) if c.isalnum() or c in ("-","_")).strip() or "export"
        filename_base = f"ldap_export_{kind}_{safe_name}"

        try:
            if fmt == "json":
                return Response(scope_data)
            elif fmt == "ldif":
                schema_type = getattr(settings, "LDAP_API", {}).get("GROUP_SCHEMA", "both") if hasattr(settings, "LDAP_API") else "both"
                ldif_content = exporters.generate_ldif(scope_data, kind, schema_type)
                ldif_bytes = ldif_content.encode("utf-8") if isinstance(ldif_content, str) else bytes(ldif_content)
                resp = HttpResponse(ldif_bytes, content_type="text/ldif; charset=utf-8")
                resp["Content-Disposition"] = f'attachment; filename="{filename_base}.ldif"'
                resp["Access-Control-Expose-Headers"] = "Content-Disposition"
                return resp
            elif fmt == "pdf":
                pdf_buf = exporters.generate_pdf(scope_data, kind)
                pdf_bytes = pdf_buf.getvalue() if hasattr(pdf_buf, "getvalue") else bytes(pdf_buf)
                resp = HttpResponse(pdf_bytes, content_type="application/pdf")
                resp["Content-Disposition"] = f'attachment; filename="{filename_base}.pdf"'
                resp["Access-Control-Expose-Headers"] = "Content-Disposition"
                return resp
            return Response({"detail":"Geçersiz format. json/ldif/pdf"}, status=400)
        except Exception as e:
            traceback.print_exc()
            return Response({"detail": f"Dosya oluşturulurken sunucu hatası: {e}"}, status=500)

# ======================================================================
# Import — Upload / Validate / Apply
# ======================================================================
class ImportUploadView(APIView):
    """
    JSON payload'ı (gövde 'payload' ya da 'file') cache’e koyar ve jobId döner.
    """
    def post(self, request):
        payload = request.data.get("payload")
        if not payload and "file" in request.FILES:
            try:
                payload = json.loads(request.FILES["file"].read().decode("utf-8"))
            except Exception as e:
                return Response({"error": f"invalid json file: {e}"}, status=400)
        if payload is None:
            return Response({"error": "payload or file required"}, status=400)

        job_id = request.data.get("jobId")
        if not job_id:
            from uuid import uuid4
            job_id = str(uuid4())

        cache.set(CACHE_KEY.format(job_id=job_id), payload, timeout=3600)
        return Response({"jobId": job_id}, status=201)

def _is_export_tree(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("organizations"), list) and "domain" in payload

def _build_live_org_group_index(current_tree: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """
    canlı ağaçtan org_dn -> (cn_lower -> gerçek group_dn)
    """
    idx: Dict[str, Dict[str, str]] = {}
    if not isinstance(current_tree, dict):
        return idx
    for org in current_tree.get("organizations", []) or []:
        org_dn = (org.get("dn") or "").strip().lower()
        if not org_dn:
            continue
        cn_map: Dict[str, str] = {}
        for g in org.get("groups", []) or []:
            cn = (g.get("name") or "").strip()
            gdn = g.get("dn")
            if cn and isinstance(gdn, str) and gdn:
                cn_map[cn.lower()] = gdn
        if cn_map:
            idx[org_dn] = cn_map
    return idx

def _parse_cn_from_dn(dn: str | None) -> str | None:
    if not isinstance(dn, str):
        return None
    import re
    m = re.match(r"\s*cn\s*=\s*([^,]+)", dn, flags=re.IGNORECASE)
    return m.group(1) if m else None

def _norm(s: str | None) -> str:
    return (s or "").strip().lower()

def _guess_group_suffix_from_groups(groups, org_dn):
    suffixes = []
    for g in groups or []:
        gdn = g.get("dn")
        if isinstance(gdn, str) and "cn=" in gdn.lower():
            head, _, tail = gdn.partition(",")
            if tail: suffixes.append(tail.strip())
    if suffixes:
        first = suffixes[0]
        if all(_norm(x) == _norm(first) for x in suffixes):
            return first
    return org_dn

def _build_group_dn(base_dn: str | None, cn: str | None, fallback: str | None = None) -> str | None:
    if fallback: return fallback
    return f"cn={cn},{base_dn}" if base_dn and cn else None

def _export_tree_to_import_payload(tree: Dict[str, Any]) -> Dict[str, Any]:
    try:
        current_tree = svc.load_tree()
    except Exception:
        current_tree = {}
    live_idx = _build_live_org_group_index(current_tree)

    orgs_out: List[Dict[str, Any]] = []
    for org in tree.get("organizations", []) or []:
        org_dn: str | None = org.get("dn")
        org_dn_key = _norm(org_dn)
        org_name: str = (org.get("name") or "").strip()
        org_desc: str = (org.get("description") or "").strip()

        groups_src = org.get("groups", []) or []
        guessed_suffix = _guess_group_suffix_from_groups(groups_src, org_dn)

        groups_out: List[Dict[str, Any]] = []
        group_list_dns: List[str] = []
        group_cn_to_dn: Dict[str, str] = {}

        live_cn_map = live_idx.get(org_dn_key, {})

        for g in groups_src:
            cn = (g.get("cn") or g.get("name") or _parse_cn_from_dn(g.get("dn")) or "").strip()
            if not cn:
                continue
            real_dn = live_cn_map.get(cn.lower())
            g_dn = real_dn or _build_group_dn(guessed_suffix, cn, fallback=g.get("dn"))
            groups_out.append({
                "cn": cn,
                "description": (g.get("description") or "").strip(),
                "members": g.get("members") or [],
                "dn": g_dn,
            })
            if isinstance(g_dn, str) and g_dn:
                group_list_dns.append(g_dn)
                group_cn_to_dn[cn.lower()] = g_dn

        user_to_groups = {}
        for g in groups_out:
            gdn = g.get("dn")
            for m in g.get("members") or []:
                if isinstance(m, str) and m:
                    user_to_groups.setdefault(m, []).append(gdn)

        users_src = org.get("users", []) or []
        users_out: List[Dict[str, Any]] = []
        first_group_dn = group_list_dns[0] if group_list_dns else None

        for u in users_src:
            uid = (u.get("uid") or "").strip()
            if not uid:
                continue
            user_dn = u.get("dn")
            preferred = None

            ugroups = u.get("groups")
            if isinstance(ugroups, list) and ugroups:
                raw = ugroups[0]
                if isinstance(raw, str) and raw.strip():
                    if "cn=" in raw.lower():
                        raw_cn = _parse_cn_from_dn(raw)
                        preferred = live_cn_map.get(raw_cn.lower()) if raw_cn else raw
                        if not preferred: preferred = raw
                    else:
                        preferred = live_cn_map.get(raw.lower()) or group_cn_to_dn.get(raw.lower()) or _build_group_dn(guessed_suffix, raw)

            if not preferred and user_dn and user_dn in user_to_groups:
                preferred = user_to_groups[user_dn][0]
            if not preferred and first_group_dn:
                preferred = first_group_dn

            user_payload = {
                "uid": uid,
                "givenName": (u.get("givenName") or "").strip(),
                "sn": (u.get("sn") or "").strip(),
                "mail": (u.get("mail") or "").strip(),
                "phone": (u.get("phone") or "").strip(),
                "userPassword": u.get("userPassword"),
                "uidNumber": u.get("uidNumber"),
                "gidNumber": u.get("gidNumber"),
                "homeDirectory": (u.get("homeDirectory") or f"/home/{uid}"),
                "isActive": bool(u.get("isActive", True)),
            }

            if isinstance(user_dn, str) and user_dn:
                user_payload["dn"] = user_dn
                user_payload["targetDn"] = user_dn

            if isinstance(preferred, str) and preferred:
                if "cn=" not in preferred.lower():
                    preferred = live_cn_map.get(preferred.lower()) or group_cn_to_dn.get(preferred.lower()) or preferred
                user_payload["primaryGroup"] = preferred

            users_out.append(user_payload)

        orgs_out.append({
            "name": org_name,
            "description": org_desc,
            "groups": groups_out,
            "users": users_out,
        })
    return {"organizations": orgs_out}

class ImportValidateView(APIView):
    def post(self, request):
        s = ValidateRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        payload = s.validated_data.get("payload")
        job_id = s.validated_data.get("jobId")

        if payload is None and job_id:
            payload = cache.get(CACHE_KEY.format(job_id=job_id))
        if payload is None:
            return Response({"error": "payload not provided (jobId not found)"}, status=400)

        try:
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode("utf-8", "ignore")
            if isinstance(payload, str):
                payload = json.loads(payload)
        except Exception as e:
            return Response({"error": f"invalid json payload: {e}"}, status=400)

        is_export = _is_export_tree(payload)
        if is_export:
            try:
                payload = _export_tree_to_import_payload(payload)
            except Exception as e:
                return Response({"error": f"export tree convert failed: {e}"}, status=400)

        ps = ImportPayloadSerializer(data=payload)
        ps.is_valid(raise_exception=True)
        payload = ps.validated_data

        options = s.validated_data.get("options") or {}
        if is_export:
            options.setdefault("preserveExistingDn", True)

        changes, stats, blockers, warnings = compute_plan(payload, options=options)
        changes_list = [_obj_to_dict(c) for c in (changes or [])]
        ui_stats = _map_stats_for_ui(stats or {}, changes_list)

        plan_dict = {
            "payload": payload,
            "changes": changes_list,
            "stats": ui_stats,
            "blockers": blockers or [],
            "warnings": warnings or [],
        }
        token = sign_plan(plan_dict)

        return Response({
            "stats": ui_stats,
            "blockers": plan_dict["blockers"],
            "warnings": plan_dict["warnings"],
            "changes": changes_list,
            "applyToken": token,
            "canApply": len(plan_dict["blockers"]) == 0,
        }, status=200)

class ImportApplyView(APIView):
    def post(self, request):
        s = ApplyRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        try:
            plan = unsign_plan(s.validated_data["applyToken"])
        except Exception:
            return Response({"error":"invalid applyToken"}, status=400)

        if plan.get("blockers"):
            return Response(
                {"error":"blockers present, cannot apply", "blockers": plan["blockers"]},
                status=422,
            )

        options = s.validated_data.get("options") or {}
        changes_payload = plan.get("changes") or []
        try:
            changes_obj = [Change(**c) for c in changes_payload]
        except Exception as e:
            return Response({"error": f"invalid changes payload: {e}"}, status=400)

        results, summary, code = apply_plan(changes_obj, options=options)
        return Response({"results": results, "summary": summary}, status=code)

# ======================================================================
# Next IDs
# ======================================================================
class NextIdsView(APIView):
    def get(self, request):
        org_dn = request.query_params.get("orgDn")
        group_dn = request.query_params.get("groupDn")
        if not org_dn:
            return Response({"detail": "orgDn zorunlu"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            data = svc.suggest_ids(org_dn, group_dn or None)
            return Response(data)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
