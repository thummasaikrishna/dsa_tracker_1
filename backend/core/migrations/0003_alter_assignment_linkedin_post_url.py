# Generated manually for longer LinkedIn share URLs

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_question_examples_and_linkedin_proof"),
    ]

    operations = [
        migrations.AlterField(
            model_name="assignment",
            name="linkedin_post_url",
            field=models.URLField(blank=True, max_length=500),
        ),
    ]
