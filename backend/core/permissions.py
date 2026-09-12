"""
Role-Based Access Control (RBAC) permission classes.

DRF permission classes are the standard "guard clause" mechanism: each
request is checked against `has_permission` (object-independent) and
`has_object_permission` (object-specific) *before* the view method runs.
We compose small, single-purpose classes rather than branching inside
every view — this keeps authorization logic declarative and testable in
isolation from business logic.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdmin(BasePermission):
    """Allows access only to users whose profile.role == 'admin'."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, "profile")
            and request.user.profile.is_admin
        )


class IsAdminOrReadOnly(BasePermission):
    """Anyone authenticated can read (GET/HEAD/OPTIONS); only Admins can write."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return hasattr(request.user, "profile") and request.user.profile.is_admin


class IsOwnerOrAdmin(BasePermission):
    """
    Object-level check: a user may read/modify their OWN assignment.
    Admins may view any assignment (SAFE_METHODS) and may run admin-only
    actions such as validate_proof (checked on the action itself).
    """

    def has_object_permission(self, request, view, obj):
        if obj.user_id == request.user.id:
            return True
        if hasattr(request.user, "profile") and request.user.profile.is_admin:
            if getattr(view, "action", None) in {"validate_proof"}:
                return True
            return request.method in SAFE_METHODS
        return False
