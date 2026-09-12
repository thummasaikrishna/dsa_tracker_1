# Soft-remove students + question-update / inactivity notifications

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0004_notification"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="is_removed",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="profile",
            name="removed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="profile",
            index=models.Index(fields=["is_removed", "role"], name="core_profil_is_remo_role_idx"),
        ),
        migrations.AddField(
            model_name="notification",
            name="about_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notifications_about",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="notification",
            name="event",
            field=models.CharField(
                choices=[
                    ("new_question", "New Question"),
                    ("proof_validated", "Proof Validated"),
                    ("question_updated", "Question Updated"),
                    ("student_inactive", "Student Inactivity"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                condition=models.Q(("event", "question_updated"), ("question__isnull", False)),
                fields=("user", "event", "question"),
                name="uniq_user_question_updated_notification",
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                condition=models.Q(("event", "student_inactive"), ("about_user__isnull", False)),
                fields=("user", "event", "about_user"),
                name="uniq_admin_student_inactive_notification",
            ),
        ),
    ]
