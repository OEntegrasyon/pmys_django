# ldap_api/exporters.py (YENİ DOSYA)

import io
from django.conf import settings
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# ===================================================================
# --- LDIF Generation
# ===================================================================
# Not: Bu fonksiyonlar services.py'deki create_* fonksiyonlarındaki
# objectClass tanımlarına dayanarak sentetik bir LDIF oluşturur.

def _user_to_ldif(user_data):
    """load_tree'den gelen bir user dict'ini LDIF metnine çevirir."""
    dn = user_data.get("dn")
    if not dn: return ""
    
    lines = [f"dn: {dn}"]
    lines.append("objectClass: top")
    lines.append("objectClass: inetOrgPerson")
    lines.append("objectClass: posixAccount")
    lines.append("objectClass: shadowAccount") # services.py create_user'dan alınmıştır
    
    # Frontend key'lerini LDAP attribute'lerine map'le
    mapping = {
        "uid": "uid", "givenName": "givenName", "sn": "sn",
        "mail": "mail", "phone": "telephoneNumber",
        "uidNumber": "uidNumber", "gidNumber": "gidNumber",
        "homeDirectory": "homeDirectory"
    }
    for key, attr in mapping.items():
        val = user_data.get(key)
        # Sadece None olmayan ve boş olmayan değerleri yaz
        if val is not None and str(val):
            lines.append(f"{attr}: {val}")
    
    # cn, ad ve soyaddan türetilir
    cn = (f"{user_data.get('givenName','')} {user_data.get('sn','')}").strip() or user_data.get('uid')
    if cn:
        lines.append(f"cn: {cn}")
    
    # Parola güvenlik nedeniyle dışa aktarılmaz
    # 'isActive' türetilmiş bir alandır, LDAP'da direkt karşılığı yok (ppolicy/shadow hariç)
    
    return "\n".join(lines)

def _group_to_ldif(group_data, schema_type):
    """load_tree'den gelen bir group dict'ini LDIF metnine çevirir."""
    dn = group_data.get("dn")
    if not dn: return ""
    
    lines = [f"dn: {dn}"]
    lines.append("objectClass: top")
    
    if schema_type in ("groupOfNames", "both"):
        lines.append("objectClass: groupOfNames")
    if schema_type in ("posixGroup", "both"):
        lines.append("objectClass: posixGroup")

    if group_data.get("name"):
        lines.append(f"cn: {group_data['name']}")
    if group_data.get("description"):
        lines.append(f"description: {group_data['description']}")
        
    # posixGroup özelliği
    if schema_type in ("posixGroup", "both") and group_data.get('gidNumber'):
         lines.append(f"gidNumber: {group_data['gidNumber']}")
        
    # groupOfNames özelliği
    if schema_type in ("groupOfNames", "both"):
        for member_dn in group_data.get("members", []):
            lines.append(f"member: {member_dn}")
        
    # posixGroup özelliği
    if schema_type in ("posixGroup", "both"):
        for member_uid in group_data.get("memberUids", []):
            lines.append(f"memberUid: {member_uid}")
        
    return "\n".join(lines)

def _org_to_ldif(org_data, schema_type):
    """Bir organizasyonu, gruplarını ve kullanıcılarını LDIF metnine çevirir."""
    dn = org_data.get("dn")
    if not dn: return ""
    
    ldif_parts = []
    
    # 1. Organizasyonun kendisi
    org_lines = [f"dn: {dn}"]
    org_lines.append("objectClass: top")
    org_lines.append("objectClass: organizationalUnit")
    org_lines.append(f"ou: {org_data.get('name')}")
    if org_data.get("description"):
        org_lines.append(f"description: {org_data['description']}")
    ldif_parts.append("\n".join(org_lines))
    
    # 2. Gruplar
    for group in org_data.get("groups", []):
        ldif_parts.append(_group_to_ldif(group, schema_type))
        
    # 3. Kullanıcılar
    # load_tree tüm kullanıcıları organizasyon altına yerleştirir, bu bizim için uygundur.
    for user in org_data.get("users", []):
        ldif_parts.append(_user_to_ldif(user))
        
    return "\n\n".join(filter(None, ldif_parts)) # Aralara boşluk ekle

def generate_ldif(data, kind, schema_type):
    """LDIF üretimi için ana giriş noktası."""
    
    if kind == "domain":
        parts = []
        # Domain'in kendisini (dc=example,dc=org) oluşturmuyoruz,
        # sadece altındaki organizasyonları alıyoruz.
        for org in data.get("organizations", []):
            parts.append(_org_to_ldif(org, schema_type))
        return "\n\n".join(filter(None, parts))
        
    elif kind == "organization":
        return _org_to_ldif(data, schema_type)
        
    elif kind == "group":
        # data = {"group": g, ...}
        return _group_to_ldif(data.get("group", {}), schema_type)
        
    elif kind == "user":
        # data = {"user": u, ...}
        return _user_to_ldif(data.get("user", {}))
        
    return f"# Hata: Desteklenmeyen dışa aktarma türü: {kind}"

# ===================================================================
# --- PDF Generation
# ===================================================================

def _setup_pdf_doc(buffer):
    """Temel ReportLab dokümanını ve stillerini hazırlar.
       - Unicode için TTF font register eder (örn. DejaVuSans).
       - Gerekli stil isimlerini garanti eder (Title, Body, Heading1, Heading2, Code).
    """
    # 1) register a Unicode TTF font (try project static path, then system path, fallback)
    # Adjust these paths according to where you put the TTF file.
    ttfont_candidates = [
        # Project-local font (put DejaVuSans.ttf into <project>/static/fonts/)
        os.path.join(settings.BASE_DIR, "static", "fonts", "DejaVuSans.ttf"),
        # Common system path on Debian/Ubuntu
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        # Another common location
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]

    registered_font_name = None
    for path in ttfont_candidates:
        try:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont("DejaVuSans", path))
                registered_font_name = "DejaVuSans"
                break
        except Exception:
            # ignore and try next
            registered_font_name = None

    # If registration failed, try to use a built-in font name (may not support Turkish)
    if not registered_font_name:
        # As fallback, try to register any available font via ReportLab search
        # But if no TTF is available, we still proceed — user will see missing chars.
        try:
            # Try system font lookup (best effort)
            pdfmetrics.registerFont(TTFont("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
            registered_font_name = "DejaVuSans"
        except Exception:
            registered_font_name = None

    # 2) Doc and stylesheet
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    styles = getSampleStyleSheet()

    # helper: add or update style by name (idempotent)
    def ensure_style(name, **kwargs):
        try:
            if name in styles:
                # update only provided attributes
                st = styles[name]
                for k, v in kwargs.items():
                    setattr(st, k, v)
            else:
                styles.add(ParagraphStyle(name=name, **kwargs))
        except Exception:
            # if any unexpected error, fallback quietly
            try:
                styles.add(ParagraphStyle(name=name, **kwargs))
            except Exception:
                pass

    base_font = registered_font_name or "Helvetica"  # fallback

    ensure_style('Title',
                 fontName=base_font,
                 fontSize=18,
                 alignment=TA_CENTER,
                 spaceAfter=20)

    ensure_style('Heading1',
                 fontName=base_font,
                 fontSize=14,
                 alignment=TA_LEFT,
                 spaceAfter=12,
                 spaceBefore=10)

    ensure_style('Heading2',
                 fontName=base_font,
                 fontSize=12,
                 alignment=TA_LEFT,
                 spaceAfter=8,
                 spaceBefore=8,
                 leftIndent=10)

    ensure_style('Body',
                 fontName=base_font,
                 fontSize=10,
                 alignment=TA_LEFT,
                 leading=12,
                 leftIndent=10)

    ensure_style('Code',
                 fontName=base_font,
                 fontSize=9,
                 alignment=TA_LEFT,
                 leading=11,
                 leftIndent=20,
                 spaceAfter=2)

    return doc, styles

def _user_to_pdf_flow(user_data, styles):
    """Bir kullanıcıyı PDF akış objelerine (Paragraph, Spacer) çevirir."""
    flow = []
    if not user_data: return flow
    
    flow.append(Paragraph(f"Kullanıcı: {user_data.get('uid')}", styles['Heading2']))
    
    details = [
        f"<b>DN:</b> {user_data.get('dn')}",
        f"<b>İsim:</b> {user_data.get('givenName')} {user_data.get('sn')}",
        f"<b>E-posta:</b> {user_data.get('mail') or '-'}",
        f"<b>Telefon:</b> {user_data.get('phone') or '-'}",
        f"<b>uidNumber:</b> {user_data.get('uidNumber')}",
        f"<b>gidNumber:</b> {user_data.get('gidNumber')}",
        f"<b>Ev Dizini:</b> {user_data.get('homeDirectory')}",
        f"<b>Durum:</b> {'Aktif' if user_data.get('isActive') else 'Pasif'}",
        f"<b>Gruplar (Bilgi):</b> {', '.join(user_data.get('groups', [])) or '-'}"
    ]
    for detail in details:
        flow.append(Paragraph(detail, styles['Body']))
    flow.append(Spacer(1, 12))
    return flow
    
def _group_to_pdf_flow(group_data, styles, users_list=None):
    """Bir grubu PDF akış objelerine çevirir."""
    flow = []
    if not group_data: return flow
    
    flow.append(Paragraph(f"Grup: {group_data.get('name')}", styles['Heading2']))
    
    details = [
        f"<b>DN:</b> {group_data.get('dn')}",
        f"<b>Açıklama:</b> {group_data.get('description') or '-'}",
    ]
    for detail in details:
        flow.append(Paragraph(detail, styles['Body']))

    # Üyeleri bul
    if users_list is not None:
         # Org veya Domain kapsamındaysak, üye DN'lerini kullanıcı listesiyle eşleştiririz
        member_dns = group_data.get('members', [])
        members = [u for u in users_list if u['dn'] in member_dns]
        flow.append(Paragraph(f"<b>Üyeler ({len(members)}):</b>", styles['Body']))
        for user in members:
            flow.append(Paragraph(f"- {user['uid']} ({user['givenName']} {user['sn']})", styles['Code']))
    else:
         # Sadece grup kapsamındaysak, elimizde kullanıcı listesi olmaz
        flow.append(Paragraph(f"<b>Üye DN'leri ({len(group_data.get('members', []))}):</b>", styles['Body']))
        for dn in group_data.get('members', []):
            flow.append(Paragraph(dn, styles['Code']))
            
    flow.append(Spacer(1, 12))
    return flow

def _org_to_pdf_flow(org_data, styles):
    """Bir organizasyonu PDF akış objelerine çevirir."""
    flow = []
    if not org_data: return flow
    
    flow.append(Paragraph(f"Organizasyon: {org_data.get('name')}", styles['Heading1']))
    flow.append(Paragraph(f"<b>DN:</b> {org_data.get('dn')}", styles['Body']))
    flow.append(Paragraph(f"<b>Açıklama:</b> {org_data.get('description') or '-'}", styles['Body']))
    flow.append(Spacer(1, 20))
    
    users = org_data.get('users', [])
    groups = org_data.get('groups', [])
    
    flow.append(Paragraph(f"Gruplar ({len(groups)})", styles['Heading1']))
    for group in groups:
        # Üye isimlerini çözebilmek için kullanıcı listesini de gönder
        flow.extend(_group_to_pdf_flow(group, styles, users_list=users))
        
    flow.append(Paragraph(f"Kullanıcılar ({len(users)})", styles['Heading1']))
    for user in users:
        flow.extend(_user_to_pdf_flow(user, styles))
        
    return flow

def generate_pdf(data, kind):
    """PDF üretimi için ana giriş noktası."""
    buffer = io.BytesIO()
    doc, styles = _setup_pdf_doc(buffer)
    flow = []

    if kind == "domain":
        flow.append(Paragraph(f"LDAP Domain Dışa Aktarma: {data.get('domain')}", styles['Title']))
        for org in data.get("organizations", []):
            flow.extend(_org_to_pdf_flow(org, styles))
            flow.append(PageBreak())
            
    elif kind == "organization":
        flow.append(Paragraph(f"LDAP Organizasyon Dışa Aktarma", styles['Title']))
        flow.extend(_org_to_pdf_flow(data, styles))
        
    elif kind == "group":
        # data = {"group": g, "organization": o, ...}
        flow.append(Paragraph(f"LDAP Grup Dışa Aktarma", styles['Title']))
        flow.extend(_group_to_pdf_flow(data.get("group"), styles))
        
    elif kind == "user":
        # data = {"user": u, ...}
        flow.append(Paragraph(f"LDAP Kullanıcı Dışa Aktarma", styles['Title']))
        flow.extend(_user_to_pdf_flow(data.get("user"), styles))
    
    else:
        flow.append(Paragraph(f"Hata: Desteklenmeyen Tür: {kind}", styles['Title']))

    doc.build(flow)
    buffer.seek(0)
    return buffer