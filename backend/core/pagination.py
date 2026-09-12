from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError


class FlexiblePagination(PageNumberPagination):
    """Allow clients to request a larger page via ?page_size= (capped)."""

    page_size_query_param = "page_size"
    max_page_size = 200

    def get_page_number(self, request, paginator):
        value = request.query_params.get(self.page_query_param)
        if value is not None and (not value.isdigit() or int(value) < 1):
            raise ValidationError({self.page_query_param: "Must be a positive integer."})
        return super().get_page_number(request, paginator)

    def get_page_size(self, request):
        value = request.query_params.get(self.page_size_query_param)
        if value is not None and (not value.isdigit() or not 1 <= int(value) <= self.max_page_size):
            raise ValidationError({self.page_size_query_param: f"Must be an integer between 1 and {self.max_page_size}."})
        return super().get_page_size(request)
