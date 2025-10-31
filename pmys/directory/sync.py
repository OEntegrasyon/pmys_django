# directory/sync.py
import logging
from typing import Dict, Tuple
from django.db import transaction
from .ldap_client import ldap_conn
from .models import LdapOrganization, LdapGroup, LdapUser
from user.models import User,Group,Organization
from .services import load_tree  # yukarıdaki load_tree fonksiyonun bulunduğu modül

logger = logging.getLogger(__name__)

# ------------------ Sync fonksiyonları ------------------

@transaction.atomic
def sync_organizations() -> Tuple[int,int]:
    tree = load_tree()
    created = updated = 0
    existing = {o.name: o for o in Organization.objects.all()}

    for org_data in tree["organizations"]:
        name = org_data["name"]
        desc = org_data.get("description", "")
        if name in existing:
            org = existing[name]
            if org.description != desc:
                org.description = desc
                org.save()
                updated += 1
        else:
            Organization.objects.create(name=name, description=desc)
            created += 1

    logger.info("sync_organizations: created=%d updated=%d", created, updated)
    return created, updated

@transaction.atomic
def sync_groups() -> Tuple[int,int]:
    tree = load_tree()
    created = updated = 0
    existing = {g.name: g for g in Group.objects.select_related("organization").all()}
    orgs = {o.name: o for o in Organization.objects.all()}

    inserted_names = set()  # <--- yeni eklendi

    for org_data in tree["organizations"]:
        org = orgs.get(org_data["name"])
        for g in org_data["groups"]:
            name = g["name"]
            if name in inserted_names:
                logger.debug("Skipping duplicate group in sync: %s", name)
                continue
            desc = g.get("description", "")

            if name in existing:
                group = existing[name]
                changed = False
                if group.description != desc:
                    group.description = desc
                    changed = True
                if group.organization != org:
                    group.organization = org
                    changed = True
                if changed:
                    group.save()
                    updated += 1
            else:
                Group.objects.create(name=name, description=desc, organization=org)
                created += 1
                inserted_names.add(name)  # <--- ekle

    logger.info("sync_groups: created=%d updated=%d", created, updated)
    return created, updated


@transaction.atomic
def sync_users() -> Tuple[int,int,int]:
    tree = load_tree()
    created = updated = linked = 0
    existing_users = {u.username: u for u in User.objects.all()}
    groups_map = {g.name: g for g in Group.objects.all()}

    for org_data in tree["organizations"]:
        for u in org_data["users"]:
            uname = u["uid"]
            if not uname:
                continue

            email = u.get("mail") or f"{uname}@example.invalid"
            first_name = u.get("givenName") or ""
            last_name = u.get("sn") or ""
            is_active = u.get("isActive", True)
            user_groups = u.get("groups", [])

            if uname in existing_users:
                user = existing_users[uname]
                changed = False
                if user.email != email:
                    user.email = email
                    changed = True
                if user.first_name != first_name:
                    user.first_name = first_name
                    changed = True
                if user.last_name != last_name:
                    user.last_name = last_name
                    changed = True
                if user.is_active != is_active:
                    user.is_active = is_active
                    changed = True
                if changed:
                    user.save()
                    updated += 1
            else:
                user = User.objects.create(
                    username=uname,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=is_active
                )
                created += 1

            # Grup üyeliği
            for gname, gobj in groups_map.items():
                if gname in user_groups:
                    if not gobj.users.filter(id=user.id).exists():
                        gobj.users.add(user)
                        linked += 1
                else:
                    if gobj.users.filter(id=user.id).exists():
                        gobj.users.remove(user)

    logger.info("sync_users: created=%d updated=%d linked=%d", created, updated, linked)
    return created, updated, linked

# ------------------ Full sync ------------------

def full_sync() -> Dict[str, Tuple[int,int,int]]:
    r = {}
    r["orgs"] = sync_organizations()
    r["groups"] = sync_groups()
    r["users"] = sync_users()
    return r
