from rest_framework.pagination import PageNumberPagination


class FlexiblePagination(PageNumberPagination):
    """Allow clients to request a larger page via ?page_size= (capped)."""

    page_size_query_param = "page_size"
    max_page_size = 200
