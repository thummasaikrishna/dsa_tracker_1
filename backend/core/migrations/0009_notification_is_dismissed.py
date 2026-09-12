from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_ai_generation_and_validators"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="is_dismissed",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                fields=["user", "is_dismissed", "-created_at"],
                name="core_notif_user_dismiss_idx",
            ),
        ),
    ]
