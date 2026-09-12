from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone


def backfill_deadlines_and_points(apps, schema_editor):
    Question = apps.get_model("core", "Question")
    for question in Question.objects.all():
        if question.deadline is None:
            created = question.created_at or timezone.now()
            question.deadline = created + timedelta(hours=72)
            question.save(update_fields=["deadline"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_removed_and_extra_notifications"),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="deadline",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(backfill_deadlines_and_points, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="question",
            name="deadline",
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AddField(
            model_name="assignment",
            name="potential_points",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="assignment",
            name="points_awarded",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="assignment",
            name="proof_status",
            field=models.CharField(
                choices=[
                    ("none", "Not Submitted"),
                    ("pending", "Pending Review"),
                    ("validated", "Validated"),
                    ("rejected", "Rejected"),
                ],
                db_index=True,
                default="none",
                max_length=15,
            ),
        ),
        migrations.AlterField(
            model_name="notification",
            name="event",
            field=models.CharField(
                choices=[
                    ("new_question", "New Question"),
                    ("proof_validated", "Proof Validated"),
                    ("proof_rejected", "Proof Rejected"),
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
                condition=models.Q(("assignment__isnull", False), ("event", "proof_rejected")),
                fields=("user", "event", "assignment"),
                name="uniq_user_rejected_assignment_notification",
            ),
        ),
    ]
