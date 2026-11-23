from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("list_kit", "0002_entry_slug_and_expires"),
    ]

    operations = [
        migrations.AddField(
            model_name="listtemplate",
            name="use_image_checklist",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="EntryImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.FileField(upload_to="list_kit_photos/")),
                ("caption", models.CharField(blank=True, default="", max_length=200)),
                ("is_checked", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="list_kit.entry")),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
