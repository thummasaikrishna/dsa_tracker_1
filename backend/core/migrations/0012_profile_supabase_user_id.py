from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("core", "0011_alter_notification_event")]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="supabase_user_id",
            field=models.CharField(blank=True, max_length=36, null=True, unique=True),
        ),
    ]
