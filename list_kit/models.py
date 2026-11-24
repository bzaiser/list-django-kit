import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class ListTemplate(models.Model):
    CONTENT_TYPE_CHOICES = [
        ("list", "Liste"),
        ("news", "News / Beitrag"),
        ("faq", "FAQ"),
        ("form_inbox", "Formular-Eingang"),
    ]

    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, max_length=140)
    icon = models.CharField(max_length=40, default="bi-card-checklist")
    description = models.TextField(blank=True, default="")
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, default="list")

    use_notes = models.BooleanField(default=True)
    use_status = models.BooleanField(default=True)
    use_start_date = models.BooleanField(default=False)
    use_end_date = models.BooleanField(default=False)
    use_reminder = models.BooleanField(default=False)
    use_amount = models.BooleanField(default=False)
    use_price = models.BooleanField(default=False)
    use_rating = models.BooleanField(default=False)
    use_url = models.BooleanField(default=False)
    use_image = models.BooleanField(default=False)
    use_image_checklist = models.BooleanField(default=False)
    use_location = models.BooleanField(default=False)
    use_category = models.BooleanField(default=False)
    use_master_status = models.BooleanField(default=False)
    use_person = models.BooleanField(default=False)
    use_document = models.BooleanField(default=False)

    custom_fields_json = models.JSONField(default=list, blank=True)
    allowed_statuses_json = models.JSONField(default=list, blank=True)
    ui_style_json = models.JSONField(default=dict, blank=True)
    summary_rule_json = models.JSONField(default=dict, blank=True)

    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "template"
            cand = base
            idx = 2
            while ListTemplate.objects.filter(slug=cand).exclude(pk=self.pk).exists():
                cand = f"{base}-{idx}"
                idx += 1
            self.slug = cand
        super().save(*args, **kwargs)

    def get_ui_style(self) -> dict:
        defaults = {
            "layout_mode": "row",
            "card_width": "1/3",
            "density": "normal",
            "show_creator": True,
            "genre": "",
            "card_layout": None,
        }
        if isinstance(self.ui_style_json, dict):
            defaults.update(self.ui_style_json)
        return defaults

    def get_effective_statuses(self) -> list[dict]:
        if isinstance(self.allowed_statuses_json, list) and self.allowed_statuses_json:
            return self.allowed_statuses_json
        return [
            {"key": "open", "label": "Offen", "completes": False},
            {"key": "done", "label": "Erledigt", "completes": True},
        ]

    def __str__(self):
        return self.name


class Collection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    slug = models.SlugField(blank=True, max_length=220)
    template = models.ForeignKey(ListTemplate, on_delete=models.PROTECT, related_name="collections")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="list_kit_collections",
    )
    responsible_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="list_kit_responsible_collections",
    )
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="list_kit_shared_collections",
    )
    description = models.TextField(blank=True, default="")
    is_public = models.BooleanField(default=False)
    allow_public_submit = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:200] or str(self.id)[:8]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Entry(models.Model):
    VISIBILITY_CHOICES = [
        ("draft", "Entwurf"),
        ("internal", "Intern"),
        ("public", "Öffentlich"),
        ("archived", "Archiviert"),
    ]

    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="entries")
    title = models.CharField(max_length=255)
    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=40, default="open")
    is_completed = models.BooleanField(default=False)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default="internal")
    slug = models.SlugField(max_length=260, blank=True, default="")
    is_pinned = models.BooleanField(default=False)
    publish_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    reminder_at = models.DateTimeField(null=True, blank=True)
    amount_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    amount_unit = models.CharField(max_length=30, blank=True, default="")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    url = models.URLField(blank=True, default="")
    location = models.CharField(max_length=160, blank=True, default="")
    image_url = models.URLField(blank=True, default="")
    category_id = models.PositiveIntegerField(null=True, blank=True)
    category_label = models.CharField(max_length=120, blank=True, default="")
    master_status_id = models.PositiveIntegerField(null=True, blank=True)
    master_status_label = models.CharField(max_length=120, blank=True, default="")
    person_id = models.PositiveIntegerField(null=True, blank=True)
    person_label = models.CharField(max_length=160, blank=True, default="")
    linked_document_id = models.PositiveIntegerField(null=True, blank=True)

    custom_data_json = models.JSONField(default=dict, blank=True)
    position = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="list_kit_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "is_completed", "position", "-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:240] or "entry"
            cand = base
            idx = 2
            while Entry.objects.filter(collection=self.collection, slug=cand).exclude(pk=self.pk).exists():
                cand = f"{base[:230]}-{idx}"
                idx += 1
            self.slug = cand
        super().save(*args, **kwargs)

    def is_currently_published(self) -> bool:
        if self.visibility != "public":
            return False
        from django.utils import timezone
        now = timezone.now()
        if self.publish_at and self.publish_at > now:
            return False
        if self.expires_at and self.expires_at <= now:
            return False
        return True

    def get_custom_field_display(self) -> list[dict]:
        fields = getattr(self.collection.template, "custom_fields_json", None) or []
        data = self.custom_data_json if isinstance(self.custom_data_json, dict) else {}
        result = []
        for f in fields:
            key = f.get("key")
            if not key or key not in data:
                continue
            val = data.get(key)
            if val is None or val == "" or val is False:
                continue
            if f.get("type") == "checkbox":
                val = "Ja"
            elif f.get("type") == "currency":
                curr = (f.get("options") or "€").strip() or "€"
                val = f"{val} {curr}"
            elif f.get("type") == "multiselect" and isinstance(val, list):
                if not val:
                    continue
                val = ", ".join(str(v) for v in val)
            result.append({
                "key": key,
                "label": f.get("label", key),
                "type": f.get("type", "text"),
                "value": val,
                "show_on_card": f.get("show_on_card", True),
                "zone": f.get("zone", "body"),
            })
        return result

    def get_all_photos(self) -> list[dict]:
        photos = []
        if self.image_url:
            photos.append({
                "id": None,
                "url": self.image_url,
                "caption": "",
                "is_checked": False,
                "is_legacy": True,
            })
        for img in self.images.all():
            photos.append({
                "id": img.id,
                "url": img.image.url,
                "caption": img.caption or "",
                "is_checked": img.is_checked,
                "is_legacy": False,
            })
        return photos

    def photo_checklist_summary(self):
        imgs = list(self.images.all())
        if not imgs:
            return None
        done = sum(1 for img in imgs if img.is_checked)
        return {"done": done, "total": len(imgs)}

    def __str__(self):
        return self.title


class EntryImage(models.Model):
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="images")
    image = models.FileField(upload_to="list_kit_photos/")
    caption = models.CharField(max_length=200, blank=True, default="")
    is_checked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Foto für {self.entry.title}"


class EntryDocument(models.Model):
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField(upload_to="list_kit_docs/")
    title = models.CharField(max_length=200, blank=True, default="")
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    @property
    def filename(self) -> str:
        name = (self.file.name or "").rsplit("/", 1)[-1]
        return self.title or name or "Dokument"

    def __str__(self):
        return self.filename
