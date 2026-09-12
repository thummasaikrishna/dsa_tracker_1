from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("core", "0010_proof_submitted_notification")]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="event",
            field=models.CharField(
                choices=[
                    ("new_question", "New Question"),
                    ("proof_validated", "Proof Validated"),
                    ("proof_rejected", "Proof Rejected"),
                    ("proof_submitted", "Proof Submitted"),
                    ("question_updated", "Question Updated"),
                    ("student_inactive", "Student Inactivity"),
                    ("code_submitted", "Code Submitted"),
                    ("code_result", "Code Result"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
    ]
