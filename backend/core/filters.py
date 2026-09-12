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

from .models import Assignment, Question


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
