from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("list_kit", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="entry",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="entry",
            name="slug",
            field=models.SlugField(blank=True, default="", max_length=260),
        ),
    ]
