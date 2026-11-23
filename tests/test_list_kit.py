import json
import os
import sys

import django
from django.conf import settings
from django.core.management import call_command
from django.test import Client, TestCase

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS_DIR = os.path.join(os.path.dirname(BASE_DIR), "django-design-studio")
for p in (BASE_DIR, DS_DIR):
    if p not in sys.path and os.path.isdir(p):
        sys.path.insert(0, p)

if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY="test-list-kit",
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
            "django.contrib.messages",
            "django.contrib.staticfiles",
            "design_studio",
            "list_kit",
        ],
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
        ],
        ROOT_URLCONF="tests.test_list_kit",
        TEMPLATES=[{
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "APP_DIRS": True,
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                    "design_studio.context_processors.theme_context",
                ],
            },
        }],
        STATIC_URL="/static/",
        USE_TZ=True,
        TIME_ZONE="Europe/Berlin",
    )
    django.setup()

from django.contrib.auth import get_user_model
from django.urls import include, path, reverse
from list_kit.models import Collection, Entry, ListTemplate
from list_kit.services import seed_default_templates

urlpatterns = [
    path("lists/", include("list_kit.urls")),
    path("design/", include("design_studio.urls")),
]


class ListKitTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="member", password="pw")
        self.staff = User.objects.create_user(username="staff", password="pw", is_staff=True)
        self.client = Client()

    def test_no_missing_migrations(self):
        call_command("makemigrations", "list_kit", check=True, dry_run=True, verbosity=0)

    def test_seed_default_templates(self):
        tpls = seed_default_templates()
        self.assertGreaterEqual(len(tpls), 3)
        slugs = set(ListTemplate.objects.values_list("slug", flat=True))
        self.assertTrue({"aufgabenliste", "news-aktuelles", "faq"}.issubset(slugs))

    def test_builder_create_edit_export_import_delete(self):
        self.client.force_login(self.staff)
        card_layout = {
            "header": ["use_status"],
            "body": ["cf:autor"],
            "footer": ["use_price"],
            "hidden": ["cf:intern"],
        }
        resp = self.client.post(reverse("list_kit:builder_create"), {
            "name": "Vereins-News",
            "content_type": "news",
            "icon": "bi-newspaper",
            "use_notes": "on",
            "use_status": "on",
            "use_price": "on",
            "cf_key": ["autor", "intern"],
            "cf_label": ["Autor", "Interne Notiz"],
            "cf_type": ["text", "text"],
            "cf_options": ["", ""],
            "cf_zone": ["body", "hidden"],
            "cf_show_card": ["1", "0"],
            "ui_layout_mode": "cards",
            "ui_card_width": "1/2",
            "ui_density": "compact",
            "ui_genre": "scifi",
            "ui_show_creator": "on",
            "ui_card_layout_json": json.dumps(card_layout),
        })
        self.assertRedirects(resp, reverse("list_kit:builder_list"))
        tpl = ListTemplate.objects.get(name="Vereins-News")
        self.assertEqual(tpl.content_type, "news")
        self.assertEqual(tpl.get_ui_style()["genre"], "scifi")
        self.assertEqual(tpl.get_ui_style()["card_layout"], card_layout)
        self.assertFalse(tpl.custom_fields_json[1]["show_on_card"])

        exp = self.client.get(reverse("list_kit:builder_export", args=[tpl.id]))
        self.assertEqual(exp.status_code, 200)
        imp = self.client.post(reverse("list_kit:builder_import"), {
            "json_payload": exp.content.decode("utf-8").replace("Vereins-News", "Vereins-News Kopie"),
        })
        self.assertEqual(imp.status_code, 302)
        kopie = ListTemplate.objects.get(name="Vereins-News Kopie")

        del_resp = self.client.post(reverse("list_kit:builder_delete", args=[kopie.id]))
        self.assertRedirects(del_resp, reverse("list_kit:builder_list"))
        self.assertFalse(ListTemplate.objects.filter(pk=kopie.id).exists())

    def test_collection_and_entry_crud_with_card_layout_and_genre(self):
        tpl = ListTemplate.objects.create(
            name="Bücher",
            slug="buecher",
            use_price=True,
            custom_fields_json=[
                {"key": "autor", "label": "Autor", "type": "text", "zone": "body", "show_on_card": True},
                {"key": "intern", "label": "Intern", "type": "text", "zone": "hidden", "show_on_card": False},
            ],
            ui_style_json={
                "layout_mode": "cards",
                "genre": "scifi",
                "card_layout": {"header": [], "body": ["cf:autor"], "footer": ["use_price"], "hidden": ["cf:intern"]},
            },
        )
        self.client.force_login(self.user)
        col_resp = self.client.post(reverse("list_kit:collection_create"), {
            "template_id": tpl.id,
            "title": "Vereinsbibliothek",
        })
        col = Collection.objects.get(title="Vereinsbibliothek")
        self.assertRedirects(col_resp, reverse("list_kit:collection_detail", args=[col.id]))

        add_resp = self.client.post(reverse("list_kit:entry_add", args=[col.id]), {
            "title": "Der Schwarm",
            "price": "14.90",
            "custom_autor": "Frank Schätzing",
            "custom_intern": "Geheim123",
        })
        self.assertRedirects(add_resp, reverse("list_kit:collection_detail", args=[col.id]))

        detail = self.client.get(reverse("list_kit:collection_detail", args=[col.id]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'data-genre="scifi"')
        self.assertContains(detail, "Frank Schätzing")
        self.assertNotContains(detail, "Geheim123")

    def test_markdown_publishing_window_and_public_submit(self):
        from datetime import timedelta
        from django.utils import timezone
        from list_kit.services import get_published_entries, render_safe_markdown

        html = render_safe_markdown("## Titel\n**Fett** <script>alert(1)</script>\n- Punkt 1\n[Link](https://example.com)")
        self.assertIn("<h4", html)
        self.assertIn("<strong>Fett</strong>", html)
        self.assertNotIn("<script>", html)
        self.assertIn("https://example.com", html)

        tpls = seed_default_templates()
        self.assertIn("kontakt-anfragen", {t.slug for t in tpls})

        news_tpl = ListTemplate.objects.get(slug="news-aktuelles")
        news_col = Collection.objects.create(title="News", template=news_tpl, owner=self.staff, is_public=True)
        now = timezone.now()
        pub = Entry.objects.create(collection=news_col, title="Aktiv", visibility="public", publish_at=now - timedelta(hours=1))
        Entry.objects.create(collection=news_col, title="Zukunft", visibility="public", publish_at=now + timedelta(days=1))
        Entry.objects.create(collection=news_col, title="Abgelaufen", visibility="public", expires_at=now - timedelta(minutes=5))
        Entry.objects.create(collection=news_col, title="Entwurf", visibility="draft")

        published = get_published_entries(content_type="news")
        self.assertEqual([e.id for e in published], [pub.id])
        self.assertTrue(pub.slug)

        form_tpl = ListTemplate.objects.get(slug="kontakt-anfragen")
        form_col = Collection.objects.create(title="Kontakt", template=form_tpl, owner=self.staff, is_public=True, allow_public_submit=True)
        anon = Client()
        sub_resp = anon.post(reverse("list_kit:public_submit", args=[form_col.id]), {
            "title": "Mitgliedsanfrage",
            "notes": "Ich möchte beitreten.",
            "custom_absender_name": "Max",
            "custom_absender_email": "max@example.com",
            "next": "/lists/",
        })
        self.assertEqual(sub_resp.status_code, 302)
        created = Entry.objects.get(collection=form_col, title="Mitgliedsanfrage")
        self.assertEqual(created.visibility, "draft")
        self.assertEqual(created.custom_data_json.get("absender_name"), "Max")

    def test_multi_photo_captions_checkoff_pdf_and_ai_import(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from list_kit.models import EntryImage

        self.client.force_login(self.staff)
        # 1. JSON paste import (with markdown fence + use_image_checklist + pdf config)
        imp_resp = self.client.post(reverse("list_kit:builder_import"), {
            "template_json": """```json
{
  "name": "Verleih-Fotos",
  "content_type": "list",
  "flags": {"use_image": true, "use_image_checklist": true, "use_price": true},
  "ui_style_json": {
    "layout_mode": "row",
    "pdf": {"orientation": "landscape", "filter": "all", "include_summary": true, "include_photos": true, "footer_text": "Verleih"}
  }
}
```"""
        })
        self.assertEqual(imp_resp.status_code, 302)
        tpl = ListTemplate.objects.get(name="Verleih-Fotos")
        self.assertTrue(tpl.use_image)
        self.assertTrue(tpl.use_image_checklist)

        col = Collection.objects.create(title="Werkzeugverleih", template=tpl, owner=self.staff)
        tiny_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        f1 = SimpleUploadedFile("p1.png", tiny_png, content_type="image/png")
        f2 = SimpleUploadedFile("p2.png", tiny_png, content_type="image/png")
        add_resp = self.client.post(reverse("list_kit:entry_add", args=[col.id]), {
            "title": "Koffer 1",
            "price": "25.00",
            "images": [f1, f2],
            "new_image_captions": ["Bohrer", "Akku"],
        })
        self.assertEqual(add_resp.status_code, 302)

        entry = Entry.objects.get(collection=col, title="Koffer 1")
        imgs = list(entry.images.order_by("id"))
        self.assertEqual(len(imgs), 2)
        self.assertEqual(imgs[0].caption, "Bohrer")
        self.assertEqual(imgs[1].caption, "Akku")

        # Toggle photo 1 checked
        tog = self.client.post(reverse("list_kit:entry_image_toggle", args=[col.id, entry.id, imgs[0].id]))
        self.assertEqual(tog.status_code, 302)
        imgs[0].refresh_from_db()
        self.assertTrue(imgs[0].is_checked)

        # Detail page renders carousel & lightbox
        det = self.client.get(reverse("list_kit:collection_detail", args=[col.id]))
        self.assertEqual(det.status_code, 200)
        self.assertContains(det, "carousel")
        self.assertContains(det, "openLkPhotoLightboxFromEl")
        self.assertContains(det, "Fotos abhaken")

        # PDF/Print view renders cleanly
        pdf_resp = self.client.get(reverse("list_kit:collection_pdf", args=[col.id]))
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertTrue(
            pdf_resp["Content-Type"].startswith("application/pdf")
            or b"Werkzeugverleih" in pdf_resp.content
        )

        for img in EntryImage.objects.filter(entry=entry):
            img.image.delete(save=False)


if __name__ == "__main__":
    import unittest
    from django.test.utils import setup_test_environment, teardown_test_environment

    setup_test_environment()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ListKitTests)
    old_config = django.db.connections.databases["default"].copy()
    from django.test.runner import DiscoverRunner
    runner = DiscoverRunner(verbosity=2)
    old = runner.setup_databases()
    result = runner.run_suite(suite)
    runner.teardown_databases(old)
    teardown_test_environment()
    sys.exit(0 if result.wasSuccessful() else 1)
