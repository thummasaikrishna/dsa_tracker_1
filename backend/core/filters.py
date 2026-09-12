"""
Declarative filtering using django-filter.

Rather than hand-parsing `request.GET` in every view, FilterSet classes
translate query params (?difficulty=easy&status=completed) directly into
ORM `.filter()` calls. This is the same "filter by difficulty" and
"filter by time period" behaviour the PRD calls for in section 15, just
expressed as reusable, composable filter classes instead of ad-hoc
if/else chains.
"""

import django_filters
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from django_filters.rest_framework import DjangoFilterBackend

from .models import Assignment, Question


class StrictDjangoFilterBackend(DjangoFilterBackend):
    """Make invalid declared filter values a clear client error."""

    def filter_queryset(self, request, queryset, view):
        filterset = self.get_filterset(request, queryset, view)
        if filterset is None:
            return queryset
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)
        return filterset.qs


class StrictOrderingFilter(OrderingFilter):
    """Reject unknown ordering keys instead of silently ignoring them."""

    def get_ordering(self, request, queryset, view):
        raw = request.query_params.get(self.ordering_param)
        if raw:
            fields = getattr(view, "ordering_fields", ())
            if fields != "__all__":
                allowed = {field[0] if isinstance(field, tuple) else field for field in fields}
                if any(item.lstrip("-") not in allowed for item in raw.split(",")):
                    raise ValidationError({self.ordering_param: "Contains an unsupported ordering field."})
        return super().get_ordering(request, queryset, view)


class BoundedSearchFilter(SearchFilter):
    max_search_length = 100

    def filter_queryset(self, request, queryset, view):
        if len(request.query_params.get(self.search_param, "")) > self.max_search_length:
            raise ValidationError({self.search_param: f"Must not exceed {self.max_search_length} characters."})
        return super().filter_queryset(request, queryset, view)


class QuestionFilter(django_filters.FilterSet):
    difficulty = django_filters.ChoiceFilter(choices=Question.DIFFICULTY_CHOICES)
    search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")

    class Meta:
        model = Question
        fields = ["difficulty"]


class AssignmentFilter(django_filters.FilterSet):
    difficulty = django_filters.ChoiceFilter(
        field_name="question__difficulty", choices=Question.DIFFICULTY_CHOICES
    )
    status = django_filters.ChoiceFilter(choices=Assignment.STATUS_CHOICES)
    proof_status = django_filters.ChoiceFilter(choices=Assignment.PROOF_STATUS_CHOICES)

    class Meta:
        model = Assignment
        fields = ["difficulty", "status", "proof_status"]
