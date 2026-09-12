from django.db import migrations, models


def normalize_existing_emails(apps, schema_editor):
    """Backfill safely; refuse to guess how an operator wants duplicates fixed."""
    User = apps.get_model("auth", "User")
    Profile = apps.get_model("core", "Profile")
    seen = set()

    for user in User.objects.exclude(email="").order_by("id"):
        email = user.email.strip().lower()
        if email in seen:
            raise RuntimeError(
                "Duplicate normalized email addresses exist. Resolve them manually "
                "before applying core.0015_profile_normalized_email."
            )
        seen.add(email)
        Profile.objects.filter(user_id=user.id).update(normalized_email=email)


class Migration(migrations.Migration):

    dependencies = [("core", "0014_question_reference_solution")]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="normalized_email",
            field=models.CharField(blank=True, max_length=254, null=True, unique=True),
        ),
        migrations.RunPython(normalize_existing_emails, migrations.RunPython.noop),
    ]
