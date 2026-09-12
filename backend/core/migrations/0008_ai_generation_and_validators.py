from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_code_submissions_and_test_cases"),
    ]

    operations = [
        migrations.AddField(
            model_name="testcase",
            name="validation_type",
            field=models.CharField(
                choices=[("EXACT_MATCH", "Exact match"), ("CUSTOM_VALIDATOR", "Custom validator")],
                db_index=True,
                default="EXACT_MATCH",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="testcase",
            name="validator_type",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AlterField(
            model_name="testcase",
            name="expected_output",
            field=models.TextField(blank=True),
        ),
        migrations.CreateModel(
            name="AIQuestionGenerationCache",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("input_hash", models.CharField(db_index=True, max_length=64, unique=True)),
                ("problem_title", models.CharField(max_length=255)),
                ("problem_statement", models.TextField()),
                ("generated_response", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
    ]
