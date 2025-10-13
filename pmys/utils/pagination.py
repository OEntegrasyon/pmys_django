
from rest_framework.pagination import PageNumberPagination

class OptionalPagination(PageNumberPagination):
    """
    URL'de '?paginate=false' parametresi varsa sayfalama işlemini tamamen atlar,
    aksi halde normal sayfalama yapar.
    """
    page_size_query_param = 'page_size'

    def paginate_queryset(self, queryset, request, view=None):
        """
        Bu metod, veriyi dilimlemeden hemen önce çalışır.
        """
        # URL'de '?paginate=false' parametresi varsa, sayfalama yapma.
        # Bu durumda, DRF'e sayfalama işlemini atlamasını söylemek için 'None' döndürürüz.
        if request.query_params.get('paginate', 'true').lower() == 'false':
            return None

        # Aksi halde, normal sayfalama işlemini (veriyi dilimlemeyi) yap.
        return super().paginate_queryset(queryset, request, view)