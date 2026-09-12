from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0013_testcase_verification_status")]

    operations = [
        migrations.AddField(
            model_name="question",
            name="reference_solution",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="question",
            name="reference_solution_language",
            field=models.CharField(default="python", max_length=16),
        ),
        migrations.AddField(
            model_name="question",
            name="reference_solution_status",
            field=models.CharField(
                choices=[("DRAFT", "Draft"), ("VERIFIED", "Verified"), ("FAILED", "Failed")],
                db_index=True,
                default="DRAFT",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="question",
            name="reference_solution_error",
            field=models.TextField(blank=True),
        ),
    ]
