from django.apps import AppConfig

class DirectoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'directory'
    label = 'ldap'
    verbose_name = 'LDAP Directory'
