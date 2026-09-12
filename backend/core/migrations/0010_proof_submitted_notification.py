from django.db import migrations, models


def create_pending_proof_notifications(apps, schema_editor):
    Profile = apps.get_model("core", "Profile")
    Assignment = apps.get_model("core", "Assignment")
    Notification = apps.get_model("core", "Notification")
    admin = Profile.objects.filter(role="admin", is_removed=False).first()
    if not admin:
        return
    for assignment in Assignment.objects.filter(proof_status="pending").select_related("question", "user"):
        Notification.objects.get_or_create(
            user_id=admin.user_id,
            event="proof_submitted",
            assignment_id=assignment.id,
            defaults={
                "title": "NEW PROOF SUBMISSION",
                "message": f"{assignment.user.username} submitted a LinkedIn proof for {assignment.question.title}.",
                "question_id": assignment.question_id,
                "about_user_id": assignment.user_id,
            },
        )


class Migration(migrations.Migration):

    dependencies = [("core", "0009_notification_is_dismissed")]

    operations = [
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                fields=("user", "event", "assignment"),
                condition=models.Q(assignment__isnull=False, event="proof_submitted"),
                name="uniq_admin_submitted_proof_notification",
            ),
        ),
        migrations.RunPython(create_pending_proof_notifications, migrations.RunPython.noop),
    ]
