from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ListTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=140, unique=True)),
                ("icon", models.CharField(default="bi-card-checklist", max_length=40)),
                ("description", models.TextField(blank=True, default="")),
                ("content_type", models.CharField(choices=[("list", "Liste"), ("news", "News / Beitrag"), ("faq", "FAQ"), ("form_inbox", "Formular-Eingang")], default="list", max_length=20)),
                ("use_notes", models.BooleanField(default=True)),
                ("use_status", models.BooleanField(default=True)),
                ("use_start_date", models.BooleanField(default=False)),
                ("use_end_date", models.BooleanField(default=False)),
                ("use_reminder", models.BooleanField(default=False)),
                ("use_amount", models.BooleanField(default=False)),
                ("use_price", models.BooleanField(default=False)),
                ("use_rating", models.BooleanField(default=False)),
                ("use_url", models.BooleanField(default=False)),
                ("use_image", models.BooleanField(default=False)),
                ("use_location", models.BooleanField(default=False)),
                ("custom_fields_json", models.JSONField(blank=True, default=list)),
                ("allowed_statuses_json", models.JSONField(blank=True, default=list)),
                ("ui_style_json", models.JSONField(blank=True, default=dict)),
                ("summary_rule_json", models.JSONField(blank=True, default=dict)),
                ("is_system", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Collection",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=200)),
                ("slug", models.SlugField(blank=True, max_length=220)),
                ("description", models.TextField(blank=True, default="")),
                ("is_public", models.BooleanField(default=False)),
                ("allow_public_submit", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="list_kit_collections", to=settings.AUTH_USER_MODEL)),
                ("shared_with", models.ManyToManyField(blank=True, related_name="list_kit_shared_collections", to=settings.AUTH_USER_MODEL)),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="collections", to="list_kit.listtemplate")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Entry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("notes", models.TextField(blank=True, default="")),
                ("status", models.CharField(default="open", max_length=40)),
                ("is_completed", models.BooleanField(default=False)),
                ("visibility", models.CharField(choices=[("draft", "Entwurf"), ("internal", "Intern"), ("public", "Öffentlich"), ("archived", "Archiviert")], default="internal", max_length=20)),
                ("is_pinned", models.BooleanField(default=False)),
                ("publish_at", models.DateTimeField(blank=True, null=True)),
                ("start_date", models.DateTimeField(blank=True, null=True)),
                ("end_date", models.DateTimeField(blank=True, null=True)),
                ("reminder_at", models.DateTimeField(blank=True, null=True)),
                ("amount_value", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("amount_unit", models.CharField(blank=True, default="", max_length=30)),
                ("price", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("rating", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("url", models.URLField(blank=True, default="")),
                ("location", models.CharField(blank=True, default="", max_length=160)),
                ("image_url", models.URLField(blank=True, default="")),
                ("custom_data_json", models.JSONField(blank=True, default=dict)),
                ("position", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("collection", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="list_kit.collection")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="list_kit_entries", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-is_pinned", "is_completed", "position", "-created_at"]},
        ),
    ]
