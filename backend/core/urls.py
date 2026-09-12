from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .ai_views import GenerateQuestionDataView
from .code_views import CodeRunView, CodeSubmissionViewSet, CodeSubmitView
from .views import (
    AssignmentViewSet,
    ContactAdminView,
    LeaderboardView,
    MeView,
    MyActivityView,
    NotificationListView,
    NotificationReadAllView,
    NotificationReadView,
    NotificationDismissView,
    OverviewStatsView,
    PendingProofsView,
    QuestionViewSet,
    RegisterView,
    RemoveStudentView,
    SupabaseGoogleLoginView,
    StudentActivityView,
    StudentListView,
    TrackerTokenObtainPairView,
)

router = DefaultRouter()
router.register("questions", QuestionViewSet, basename="question")
router.register("assignments", AssignmentViewSet, basename="assignment")
router.register("code/submissions", CodeSubmissionViewSet, basename="code-submission")

urlpatterns = [
    # Auth
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", TrackerTokenObtainPairView.as_view(), name="login"),
    path("auth/supabase/google/", SupabaseGoogleLoginView.as_view(), name="supabase-google-login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("auth/me/", MeView.as_view(), name="me"),
    # Analytics
    path("analytics/my-activity/", MyActivityView.as_view(), name="my-activity"),
    path("analytics/student/<int:user_id>/", StudentActivityView.as_view(), name="student-activity"),
    path("analytics/students/", StudentListView.as_view(), name="student-list"),
    path("analytics/students/<int:user_id>/remove/", RemoveStudentView.as_view(), name="remove-student"),
    path("contact-admin/", ContactAdminView.as_view(), name="contact-admin"),
    path("analytics/overview/", OverviewStatsView.as_view(), name="overview-stats"),
    path("analytics/leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("analytics/pending-proofs/", PendingProofsView.as_view(), name="pending-proofs"),
    path("notifications/", NotificationListView.as_view(), name="notifications"),
    path("notifications/<int:pk>/read/", NotificationReadView.as_view(), name="notification-read"),
    path("notifications/<int:pk>/dismiss/", NotificationDismissView.as_view(), name="notification-dismiss"),
    path("notifications/read-all/", NotificationReadAllView.as_view(), name="notifications-read-all"),
    path("code/run/", CodeRunView.as_view(), name="code-run"),
    path("code/submit/", CodeSubmitView.as_view(), name="code-submit"),
    path(
        "admin/ai/generate-question-data/",
        GenerateQuestionDataView.as_view(),
        name="ai-generate-question-data",
    ),
    # CRUD routers
    path("", include(router.urls)),
]
