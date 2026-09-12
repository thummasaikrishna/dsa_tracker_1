import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0006_deadline_and_leaderboard_points"),
    ]

    operations = [
        migrations.CreateModel(
            name="TestCase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("input_data", models.TextField(blank=True)),
                ("expected_output", models.TextField()),
                ("is_hidden", models.BooleanField(db_index=True, default=False)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="test_cases",
                        to="core.question",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="testcase",
            index=models.Index(fields=["question", "is_hidden", "order"], name="core_testca_questio_hidden_idx"),
        ),
        migrations.CreateModel(
            name="CodeSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "language",
                    models.CharField(
                        choices=[("python", "Python"), ("java", "Java"), ("cpp", "C++")],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("source_code", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("accepted", "Accepted"),
                            ("wrong_answer", "Wrong Answer"),
                            ("compilation_error", "Compilation Error"),
                            ("runtime_error", "Runtime Error"),
                            ("time_limit_exceeded", "Time Limit Exceeded"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=24,
                    ),
                ),
                ("tests_passed", models.PositiveIntegerField(default=0)),
                ("total_tests", models.PositiveIntegerField(default=0)),
                ("execution_time", models.FloatField(blank=True, help_text="Seconds", null=True)),
                ("memory_used", models.FloatField(blank=True, help_text="KB if reported", null=True)),
                ("compile_output", models.TextField(blank=True)),
                ("public_results", models.JSONField(blank=True, default=list)),
                ("potential_points", models.PositiveSmallIntegerField(default=0)),
                ("points_awarded", models.PositiveSmallIntegerField(default=0)),
                ("submitted_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="code_submissions",
                        to="core.question",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="code_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-submitted_at"]},
        ),
        migrations.AddIndex(
            model_name="codesubmission",
            index=models.Index(fields=["user", "question", "-submitted_at"], name="core_codesu_user_q_sub_idx"),
        ),
        migrations.AddIndex(
            model_name="codesubmission",
            index=models.Index(fields=["status", "-submitted_at"], name="core_codesu_status_sub_idx"),
        ),
        migrations.AddIndex(
            model_name="codesubmission",
            index=models.Index(fields=["language"], name="core_codesu_language_idx"),
        ),
        migrations.AddField(
            model_name="notification",
            name="code_submission",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notifications",
                to="core.codesubmission",
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
                    ("code_submitted", "Code Submitted"),
                    ("code_result", "Code Result"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                condition=models.Q(("code_submission__isnull", False), ("event", "code_submitted")),
                fields=("user", "event", "code_submission"),
                name="uniq_admin_code_submitted_notification",
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                condition=models.Q(("code_submission__isnull", False), ("event", "code_result")),
                fields=("user", "event", "code_submission"),
                name="uniq_student_code_result_notification",
            ),
        ),
    ]
