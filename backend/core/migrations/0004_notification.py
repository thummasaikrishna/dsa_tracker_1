# Generated manually for student in-app notifications

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0003_alter_assignment_linkedin_post_url"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event", models.CharField(choices=[("new_question", "New Question"), ("proof_validated", "Proof Validated")], db_index=True, max_length=32)),
                ("title", models.CharField(max_length=255)),
                ("message", models.TextField(blank=True)),
                ("is_read", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("assignment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="core.assignment")),
                ("question", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="core.question")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "is_read", "-created_at"], name="core_notifi_user_id_3a4e8a_idx"),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                condition=models.Q(("event", "new_question"), ("question__isnull", False)),
                fields=("user", "event", "question"),
                name="uniq_user_new_question_notification",
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                condition=models.Q(("event", "proof_validated"), ("assignment__isnull", False)),
                fields=("user", "event", "assignment"),
                name="uniq_user_validated_assignment_notification",
            ),
        ),
    ]
