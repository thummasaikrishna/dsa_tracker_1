from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0012_profile_supabase_user_id")]

    operations = [
        migrations.AddField(
            model_name="testcase",
            name="verification_status",
            field=models.CharField(
                choices=[("GENERATED", "Generated"), ("VERIFIED", "Verified"), ("REQUIRES_REVIEW", "Requires review"), ("INVALID", "Invalid")],
                db_index=True, default="GENERATED", max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="testcase",
            name="verification_reason",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
