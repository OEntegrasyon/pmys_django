from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from .utils import b64, b64d
from . import services as svc

# Küçük yardımcı: None veya non-string -> "" (stringe çevir)
def _str_or_empty(v):
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)

class TreeView(APIView):
    def get(self, request):
        return Response(svc.load_tree())

# ------------ Organizations ------------
class OrganizationsView(APIView):
    def post(self, request):
        name = request.data.get("name")
        if not name: return Response({"detail":"name gerekli"}, status=400)
        desc = _str_or_empty(request.data.get("description", ""))
        dn = svc.create_organization(name, desc)
        return Response({"dn": dn}, status=201)

class OrganizationDetailView(APIView):
    def put(self, request, b64dn: str):
        name = request.data.get("name")  # name'i boş bırakmak 'dokunma' semantiği için None kalabilir
        desc = _str_or_empty(request.data.get("description", ""))
        svc.update_organization(b64d(b64dn), name, desc)
        return Response({"ok": True})
    def delete(self, request, b64dn: str):
        svc.delete_organization(b64d(b64dn))
        return Response(status=204)

# ------------ Groups ------------
class GroupsView(APIView):
    def post(self, request):
        org_dn = request.data.get("organizationDn")
        name = request.data.get("name")
        if not org_dn or not name:
            return Response({"detail":"organizationDn ve name gerekli"}, status=400)
        desc = _str_or_empty(request.data.get("description", ""))
        dn = svc.create_group(org_dn, name, desc)
        return Response({"dn": dn}, status=201)

class GroupDetailView(APIView):
    def put(self, request, b64dn: str):
        name = request.data.get("name")
        desc = _str_or_empty(request.data.get("description", ""))
        svc.update_group(b64d(b64dn), name, desc)
        return Response({"ok": True})
    def delete(self, request, b64dn: str):
        svc.delete_group(b64d(b64dn))
        return Response(status=204)

# ------------ Users ------------
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
        if not to_group_dn: return Response({"detail":"toGroupDn gerekli"}, status=400)
        svc.move_user(b64d(b64dn), to_group_dn)
        return Response({"ok": True})

class UserActiveView(APIView):
    def post(self, request, b64dn: str):
        active = bool(request.data.get("active", True))
        method = request.data.get("method")  # ppolicy|shadow|None
        svc.set_user_active(b64d(b64dn), active, method=method)
        return Response({"ok": True})

# ------------ Export / Import ------------
class ExportView(APIView):
    def get(self, request):
        kind = request.GET.get("kind","domain")
        dn = request.GET.get("dn_b64")
        dn = b64d(dn) if dn else None

        tree = svc.load_tree()
        if kind == "domain": return Response(tree)

        for o in tree["organizations"]:
            if kind == "organization" and o["dn"] == dn: return Response(o)
            if kind == "group":
                for g in o["groups"]:
                    if g["dn"] == dn: return Response({"domain": tree["domain"],"organizationDn":o["dn"],"group":g})
            if kind == "user":
                for u in o["users"]:
                    if u["dn"] == dn: return Response({"domain": tree["domain"],"organizationDn":o["dn"],"user":u})
        return Response({"detail":"bulunamadı"}, status=404)

class ImportValidateView(APIView):
    def post(self, request):
        data = request.data
        plan, errors = _build_import_plan(data)
        return Response({"ok": len(errors)==0, "plan": plan, "errors": errors}, status=200)

class ImportApplyView(APIView):
    def post(self, request):
        data = request.data
        plan, errors = _build_import_plan(data)
        results = []
        if errors:
            return Response({"ok": False, "errors": errors}, status=400)
        for step in plan:
            try:
                if step["op"] == "create_org":
                    svc.create_organization(step["name"], _str_or_empty(step.get("description","")))
                elif step["op"] == "create_group":
                    svc.create_group(step["orgDn"], step["name"], _str_or_empty(step.get("description","")))
                elif step["op"] == "create_user":
                    svc.create_user(step["orgDn"], step["user"], primary_group_dn=step.get("groupDn"))
                results.append({"step": step, "ok": True})
            except Exception as e:
                results.append({"step": step, "ok": False, "error": str(e)})
        ok = all(r["ok"] for r in results)
        return Response({"ok": ok, "results": results}, status=200 if ok else 400)

def _build_import_plan(data):
    plan = []
    errors = []

    def err(msg): errors.append(msg)
    def req(obj, key, ctx): 
        if key not in obj: err(f"{ctx}: '{key}' zorunlu")

    if "organizations" in data:
        for org in data["organizations"]:
            if "name" not in org: err("org: 'name' zorunlu"); continue
            plan.append({"op":"create_org","name":org["name"],"description":_str_or_empty(org.get("description",""))})
            o_dn = org.get("dn") or org_dn(org["name"])
            for g in org.get("groups", []):
                if "name" not in g: err(f"group @{org['name']}: 'name' zorunlu"); continue
                plan.append({"op":"create_group","orgDn":o_dn,"name":g["name"],"description":_str_or_empty(g.get("description",""))})
            for u in org.get("users", []):
                if "uid" not in u: err(f"user @{org['name']}: 'uid' zorunlu"); continue
                plan.append({"op":"create_user","orgDn":o_dn,"groupDn":u.get("primaryGroupDn"),"user":u})
        return plan, errors

    if "group" in data and "organizationDn" in data:
        g = data["group"]
        req(g,"name","group")
        if not errors:
            plan.append({"op":"create_group","orgDn":data["organizationDn"],"name":g["name"],"description":_str_or_empty(g.get("description",""))})
        return plan, errors

    if "user" in data and "organizationDn" in data:
        u = data["user"]
        req(u,"uid","user")
        if not errors:
            plan.append({"op":"create_user","orgDn":data["organizationDn"],"groupDn":data.get("groupDn"),"user":u})
        return plan, errors

    err("desteklenmeyen import biçimi")
    return plan, errors

def org_dn(name: str) -> str:
    base = settings.LDAP["BASE_DN"]
    org_root = settings.LDAP.get("ORG_BASE_OU") or ""
    if org_root:
        return f"ou={name},{org_root},{base}"
    return f"ou={name},{base}"

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
