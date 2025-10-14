from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.utils.dateparse import parse_datetime
from django.utils import timezone as djtz
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated,AllowAny
from django.http import HttpResponseBadRequest, Http404
from django.db.models import Q
from django.db import transaction
from utils.pagination import OptionalPagination

from client.models import Client
from .serializers import (
    ClientLiteSerializer, LapsAccessLogSerializer, LapsPolicySerializer,
    LapsAssignmentSerializer
)
from .models import LapsAccessGrant, LapsAccessLog, LapsPolicy, LapsAssignment
from . import services as svc

# -------- Clients (liste) --------
class ClientsListView(APIView):
    def get(self, request):
        qs = Client.objects.all().order_by("hostname")
        data = ClientLiteSerializer(qs, many=True).data
        return Response(data)

# -------- Secret (tekli) --------
class ClientSecretByKeyView(APIView):
    def get(self, request, key: str):
        autogen = request.query_params.get("autogen")
        grant_token = request.query_params.get("grant")

        ctx = {}
        if grant_token:
            try:
                # === FIX: transaction içinde FOR UPDATE kilidi al ===
                with transaction.atomic():
                    g = (LapsAccessGrant.objects
                         .select_for_update()
                         .select_related("client")
                         .get(token=grant_token))

                    if not g.is_valid():
                        return Response({"detail": "Grant geçersiz veya süresi dolmuş."}, status=403)

                    c = svc._get_client_by_key(key)
                    if c.id != g.client_id:
                        return Response({"detail": "Grant bu istemci için değil."}, status=403)

                    # Tek-kullanımlık işaretle (aynı tx içinde)
                    g.used_at = djtz.now()
                    g.save(update_fields=["used_at"])

                    # Log context'i topla
                    ctx = {
                        "actor": g.actor, "reason": g.reason, "ticket": g.ticket,
                        "ip": g.ip, "ua": g.user_agent,
                    }

            except LapsAccessGrant.DoesNotExist:
                return Response({"detail": "Grant bulunamadı."}, status=403)

        try:
            data = svc.get_secret_for_machine_key(
                key,
                context=ctx if grant_token else {
                    "actor": request.user.get_username() if getattr(request, "user", None) and request.user.is_authenticated else (request.headers.get("X-Actor") or ""),
                    "ip": request.META.get("REMOTE_ADDR"),
                    "ua": request.META.get("HTTP_USER_AGENT", ""),
                }
            )
            return Response(data)
        except Exception as e:
            if autogen:
                try:
                    svc.rotate_now_for_machine_key(key)
                    data = svc.get_secret_for_machine_key(key, context=ctx)
                    return Response(data)
                except Exception as e2:
                    return Response({"detail": str(e2)}, status=400)
            return Response({"detail": str(e)}, status=404)


# -------- Rotate (tekli) --------
class ClientRotateByKeyView(APIView):
    def post(self, request, key: str):
        user = request.user.username if getattr(request.user, "is_authenticated", False) else ""
        try:
            meta = svc.rotate_now_for_machine_key(key)
            return Response({"ok": True, "meta": meta})
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

# -------- Bulk rotate --------
class ClientsBulkRotateView(APIView):
    """
    POST body: { "keys": [...] }
    """
    def post(self, request):
        keys = request.data.get("keys") or request.data.get("uuids") or request.data.get("ids") or request.data.get("clientIds")
        if not isinstance(keys, list) or not keys:
            return Response({"detail": "keys (list) gerekli"}, status=400)
        user = request.user.username if getattr(request.user, "is_authenticated", False) else ""
        ok, errors = svc.bulk_rotate_by_keys(keys, by=user)
        return Response({"ok": ok, "errors": errors}, status=200 if ok else 400)

# -------- History (yalın) --------
class ClientHistoryByKeyView(APIView):
    def get(self, request, key: str):
        try:
            return Response(svc.get_history_for_machine_key(key))
        except Exception as e:
            return Response({"detail": str(e)}, status=404)

# -------- Policies CRUD --------
class PolicyViewSet(viewsets.ModelViewSet):
    queryset = LapsPolicy.objects.all().order_by("name")
    serializer_class = LapsPolicySerializer
    pagination_class = OptionalPagination



# -------- Extra: accounts/effective-policy/assignments --------
@api_view(["GET"])
@permission_classes([AllowAny])   # <— önce IsAuthenticated idi
def client_accounts(request, key: str):
    try:
        c = svc._get_client_by_key(key)
        uuid = c.uuid
    except Exception:
        return Response([], status=200)

    qs = LapsAssignment.objects.filter(enabled=True).filter(
        Q(target_type="client", target_id=uuid)
        # ileride group/org eklenir
    )

    names = []
    for a in qs:
        names.append(a.account_name_override or a.policy.account_name or "Administrator")

    out, seen = [], set()
    for n in names:
        if n not in seen:
            out.append({"account_name": n}); seen.add(n)
    if not out:
        out = [{"account_name":"Administrator"}]
    return Response(out)

@api_view(["GET"])
@permission_classes([AllowAny])   # <— yeni uç
def client_effective_policy(request, key: str):
    try:
        c = svc._get_client_by_key(key)
    except Exception:
        return Response({"source": None, "policy": None}, status=200)

    pol = svc.resolve_policy_for_client(c)
    if pol:
        return Response({"source": None, "policy": LapsPolicySerializer(pol).data})
    return Response({"source": None, "policy": None})

@api_view(["POST"])
@permission_classes([AllowAny])   # <— önce IsAuthenticated idi
def create_assignment(request):
    ser = LapsAssignmentSerializer(data=request.data)
    if not ser.is_valid():
        return HttpResponseBadRequest(ser.errors)
    obj = ser.save()
    return Response(LapsAssignmentSerializer(obj).data, status=201)

@api_view(["GET"])
@permission_classes([AllowAny])   # <— yeni uç
def list_assignments(request):
    qs = LapsAssignment.objects.all().order_by("-id")
    return Response(LapsAssignmentSerializer(qs, many=True).data)

@api_view(["DELETE"])
@permission_classes([AllowAny])
def delete_assignment(request, pk: int):
    try:
        LapsAssignment.objects.get(pk=pk).delete()
        return Response({"ok": True})
    except LapsAssignment.DoesNotExist:
        raise Http404

class LogsListView(APIView):
    permission_classes = [AllowAny]  # prod'da IsAuthenticated

    def get(self, request):
        qs = (LapsAccessLog.objects
              .select_related("client", "secret")
              .order_by("-created_at"))

        # --- Filtreler ---
        q = request.query_params.get("q")               # hostname/uuid/requested_by/result/account
        action = request.query_params.get("action")     # rotate/view/report/bulk_rotate/error
        client = request.query_params.get("client")     # id | uuid | hostname
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        if q:
            qs = qs.filter(
                Q(client__hostname__icontains=q) |
                Q(client__uuid__icontains=q) |
                Q(requested_by__icontains=q) |
                Q(result__icontains=q) |
                Q(secret__account_name__icontains=q)
            )

        if action:
            qs = qs.filter(action=action)

        if client:
            # client=id
            try:
                qs = qs.filter(client_id=int(client))
            except ValueError:
                # uuid veya hostname
                qs = qs.filter(Q(client__uuid=client) | Q(client__hostname__iexact=client))

        # tarih aralığı (ISO 8601 veya "YYYY-MM-DD")
        def _to_dt(s):
            if not s: return None
            dt = parse_datetime(s)
            if dt: return dt if dt.tzinfo else djtz.make_aware(dt)
            try:
                from datetime import datetime
                dt = datetime.strptime(s, "%Y-%m-%d")
                return djtz.make_aware(dt)
            except Exception:
                return None

        dt_from = _to_dt(date_from)
        dt_to = _to_dt(date_to)
        if dt_from:
            qs = qs.filter(created_at__gte=dt_from)
        if dt_to:
            qs = qs.filter(created_at__lte=dt_to)

        # --- Sayfalama ---
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError:
            page = 1
        try:
            page_size = min(500, max(1, int(request.query_params.get("page_size", 50))))
        except ValueError:
            page_size = 50

        total = qs.count()
        start = (page - 1) * page_size
        end = start + page_size
        data = LapsAccessLogSerializer(qs[start:end], many=True).data

        return Response({
            "items": data,
            "total": total,
            "page": page,
            "page_size": page_size,
        })
    
class GrantCreateView(APIView):
    permission_classes = [AllowAny]  # prod: IsAuthenticated

    def post(self, request):
        key = request.data.get("client")  # id | uuid | hostname
        reason = (request.data.get("reason") or "").strip()
        ticket = (request.data.get("ticket") or "").strip()
        ttl = int(request.data.get("ttl") or 60)  # saniye

        if len(reason) < 8:
            return Response({"detail":"Gerekçe en az 8 karakter olmalı."}, status=400)

        try:
            c = svc._get_client_by_key(key)
        except Exception as e:
            return Response({"detail": str(e)}, status=404)

        actor = request.user.get_username() if getattr(request, "user", None) and request.user.is_authenticated else (request.headers.get("X-Actor") or "")
        ip = request.META.get("REMOTE_ADDR")
        ua = request.META.get("HTTP_USER_AGENT", "")

        g = LapsAccessGrant.objects.create(
            client=c,
            actor=actor,
            reason=reason,
            ticket=ticket,
            ip=ip,
            user_agent=ua,
            expires_at=djtz.now() + djtz.timedelta(seconds=max(10, min(ttl, 300))),
        )
        return Response({"grant": g.token, "expires_in": (g.expires_at - djtz.now()).seconds}, status=201)