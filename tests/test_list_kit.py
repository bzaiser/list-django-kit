import atexit
import json
import os
import shutil
import sys
import tempfile

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
    _TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="list_kit_test_media_")
    atexit.register(shutil.rmtree, _TEST_MEDIA_ROOT, ignore_errors=True)
    settings.configure(
        DEBUG=True,
        MEDIA_ROOT=_TEST_MEDIA_ROOT,
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

    def test_form_inbox_status_workflow_and_paid_flag(self):
        self.client.force_login(self.staff)
        seed_default_templates()
        tpl = ListTemplate.objects.get(slug="kurs-anmeldung")
        col = Collection.objects.create(title="Kursanmeldungen", template=tpl, owner=self.staff)
        e1 = Entry.objects.create(collection=col, title="Max Mustermann", status="Offen")
        e2 = Entry.objects.create(collection=col, title="Erika Alt", status="Abgelehnt")

        # Confirm -> Bestätigt, is_completed remains False
        r = self.client.post(reverse("list_kit:entry_confirm", args=[col.id, e1.id]), {"decision": "confirm"})
        self.assertEqual(r.status_code, 302)
        e1.refresh_from_db()
        self.assertEqual(e1.status, "Bestätigt")
        self.assertFalse(e1.is_completed)

        # Paid -> separate flag is_paid=True, status stays Bestätigt
        r = self.client.post(reverse("list_kit:entry_confirm", args=[col.id, e1.id]), {"decision": "paid"})
        self.assertEqual(r.status_code, 302)
        e1.refresh_from_db()
        self.assertEqual(e1.status, "Bestätigt")
        self.assertTrue(e1.custom_data_json.get("is_paid"))
        self.assertFalse(e1.is_completed)

        det_paid = self.client.get(reverse("list_kit:collection_detail", args=[col.id]) + "?status=bezahlt")
        self.assertContains(det_paid, "Max Mustermann")
        self.assertContains(det_paid, "Bezahlt")
        self.assertNotContains(det_paid, "text-decoration-line-through")
        self.assertNotContains(det_paid, "Erika Alt")

        # Attended -> Teilgenommen, is_completed remains False
        self.client.post(reverse("list_kit:entry_confirm", args=[col.id, e1.id]), {"decision": "attended"})
        e1.refresh_from_db()
        self.assertEqual(e1.status, "Teilgenommen")
        self.assertFalse(e1.is_completed)

        # Reject -> Abgesagt, appears with Abgelehnt in ?status=abgesagt
        self.client.post(reverse("list_kit:entry_confirm", args=[col.id, e1.id]), {"decision": "reject"})
        e1.refresh_from_db()
        self.assertEqual(e1.status, "Abgesagt")
        self.assertFalse(e1.is_completed)

        det_cancel = self.client.get(reverse("list_kit:collection_detail", args=[col.id]) + "?status=abgesagt")
        self.assertContains(det_cancel, "Max Mustermann")
        self.assertContains(det_cancel, "Erika Alt")

    def test_news_edit_expires_at_and_archive_helper(self):
        from datetime import timedelta
        from django.utils import timezone
        from list_kit.services import get_archived_entries, get_published_entries

        self.client.force_login(self.staff)
        seed_default_templates()
        tpl = ListTemplate.objects.filter(content_type="news").first()
        col = Collection.objects.create(title="Vereins-News", template=tpl, owner=self.staff, is_public=True)
        future = (timezone.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")

        r_add = self.client.post(reverse("list_kit:entry_add", args=[col.id]), {
            "title": "Aktuelle Meldung",
            "notes": "Inhalt",
            "visibility": "public",
            "expires_at": future,
        })
        self.assertEqual(r_add.status_code, 302)
        entry = Entry.objects.get(collection=col, title="Aktuelle Meldung")
        self.assertEqual(len(get_published_entries(content_type="news")), 1)
        self.assertEqual(len(get_archived_entries(content_type="news")), 0)

        # Edit and archive immediately
        r_edit = self.client.post(reverse("list_kit:entry_edit", args=[col.id, entry.id]), {
            "title": "Geänderte Meldung",
            "notes": "Neu",
            "visibility": "public",
            "archive_now": "1",
        })
        self.assertEqual(r_edit.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.title, "Geänderte Meldung")
        self.assertEqual(len(get_published_entries(content_type="news")), 0)
        self.assertEqual(len(get_archived_entries(content_type="news")), 1)

    def test_protocol_and_press_pdf_views(self):
        from list_kit.services import seed_default_templates
        self.client.force_login(self.user)
        tpl_map = {t.slug: t for t in seed_default_templates()}
        col_news = Collection.objects.create(title="Presse", template=tpl_map["news-aktuelles"], owner=self.user)
        e_news = Entry.objects.create(collection=col_news, title="Ausstellungseröffnung", notes="Text", created_by=self.user)
        r_press = self.client.get(reverse("list_kit:entry_press_pdf", args=[col_news.id, e_news.id]))
        self.assertEqual(r_press.status_code, 200)

        col_prot = Collection.objects.create(title="Protokolle", template=tpl_map["protokoll"], owner=self.user)
        e_prot = Entry.objects.create(collection=col_prot, title="Sitzung 1", notes="TOP 1", created_by=self.user)
        r_prot = self.client.get(reverse("list_kit:entry_protocol_pdf", args=[col_prot.id, e_prot.id]))
        self.assertEqual(r_prot.status_code, 200)

        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group
        Group.objects.get_or_create(name="Mitglied / Portal")
        normal = get_user_model().objects.create_user(username="member_plain", password="pw", is_staff=False)
        self.client.force_login(normal)
        r_create = self.client.get(reverse("list_kit:collection_create"))
        self.assertEqual(r_create.status_code, 403)

    def test_mitgliedsantrag_optional_portal_login(self):
        from list_kit.services import seed_default_templates
        self.client.force_login(self.user)
        tpl_map = {t.slug: t for t in seed_default_templates()}
        col = Collection.objects.create(title="Anträge", template=tpl_map["mitgliedsantrag"], owner=self.user)
        e1 = Entry.objects.create(
            collection=col,
            title="Ohne Login",
            custom_data_json={
                "vorname": "Erika",
                "nachname": "Ohne",
                "portal_zugang": "Nein",
                "einzugsermaechtigung": True,
                "satzung_akzeptiert": True,
            },
            created_by=self.user,
        )
        r1 = self.client.post(reverse("list_kit:entry_create_person", args=[col.id, e1.id]))
        self.assertEqual(r1.status_code, 302)

        col_staff = Collection.objects.create(
            title="Anträge Web",
            slug="mitgliedsantrag-test",
            template=tpl_map["mitgliedsantrag"],
            owner=self.staff,
            allow_public_submit=True,
        )
        self.client.force_login(self.staff)
        r_det = self.client.get(reverse("list_kit:collection_detail", args=[col_staff.id]))
        self.assertContains(r_det, reverse("list_kit:builder_edit", args=[tpl_map["mitgliedsantrag"].id]))
        self.assertContains(r_det, f"/formular/{col_staff.slug}/")

    def test_generic_forms_and_inbox_lists_workflow(self):
        self.client.force_login(self.staff)
        # 1. Create a brand-new generic form template WITH automatic inbox creation
        r_new = self.client.post(reverse("list_kit:builder_create"), {
            "name": "Feedback-Formular",
            "content_type": "form_inbox",
            "create_inbox": "1",
            "cf_label": ["Bewertung", "Kommentar"],
            "cf_type": ["text", "textarea"],
            "cf_zone": ["body", "body"],
            "cf_show_card": ["1", "1"],
        })
        self.assertEqual(r_new.status_code, 302)
        tpl = ListTemplate.objects.get(name="Feedback-Formular")
        col = Collection.objects.get(template=tpl)
        self.assertTrue(col.is_public)
        self.assertTrue(col.allow_public_submit)

        # 2. Create another form template WITHOUT inbox, then create inbox via 1-click button
        tpl2 = ListTemplate.objects.create(name="Schadensmeldung", content_type="form_inbox")
        r_list = self.client.get(reverse("list_kit:collection_list"))
        self.assertContains(r_list, "Formulare & Eingangslisten")
        self.assertContains(r_list, "Listen, News, Galerien & FAQs")
        self.assertContains(r_list, "Eingangsliste jetzt erstellen")
        self.assertContains(r_list, f"/formular/{col.slug}/")

        r_ci = self.client.post(reverse("list_kit:builder_create_inbox", args=[tpl2.id]))
        self.assertEqual(r_ci.status_code, 302)
        col2 = Collection.objects.get(template=tpl2)
        self.assertTrue(col2.allow_public_submit)

    def test_public_submit_handles_ja_checkbox_and_radio_values(self):
        tpl = ListTemplate.objects.create(
            name="Mitgliedsantrag Submit",
            slug="mitgliedsantrag-submit-tpl",
            content_type="form_inbox",
            custom_fields_json=[
                {"key": "mitgliedsart", "label": "Mitgliedschaft", "type": "radio", "options": "Aktives Mitglied (62 Euro), Fördermitglied (31 Euro)", "zone": "body", "show_on_card": True},
                {"key": "einzugsermaechtigung", "label": "SEPA", "type": "checkbox", "options": "", "zone": "body", "show_on_card": False},
                {"key": "satzung_akzeptiert", "label": "Satzung", "type": "checkbox", "options": "", "zone": "body", "show_on_card": False},
                {"key": "portal_zugang", "label": "Portal", "type": "select", "options": "Ja, Nein", "zone": "body", "show_on_card": True},
            ],
        )
        col = Collection.objects.create(
            title="Mitgliedsantrag",
            slug="mitgliedsantrag-submit",
            template=tpl,
            owner=self.staff,
            is_public=True,
            allow_public_submit=True,
        )
        r = self.client.post(reverse("list_kit:public_submit", args=[col.id]), {
            "title": "Antrag Test",
            "custom_mitgliedsart": "Aktives Mitglied (62 Euro)",
            "custom_einzugsermaechtigung": "Ja",
            "custom_satzung_akzeptiert": "Ja",
            "custom_portal_zugang": "Ja",
        })
        self.assertEqual(r.status_code, 302)
        entry = Entry.objects.get(collection=col, title="Antrag Test")
        self.assertEqual(entry.custom_data_json["mitgliedsart"], "Aktives Mitglied (62 Euro)")
        self.assertTrue(entry.custom_data_json["einzugsermaechtigung"])
        self.assertTrue(entry.custom_data_json["satzung_akzeptiert"])
        self.assertEqual(entry.custom_data_json["portal_zugang"], "Ja")

    def test_builder_import_update_existing_by_slug_and_preserves_width_section(self):
        self.client.force_login(self.staff)
        tpl = ListTemplate.objects.create(
            name="Alt",
            slug="mein-antrag",
            content_type="form_inbox",
            custom_fields_json=[],
        )
        payload = json.dumps({
            "name": "Neu",
            "slug": "mein-antrag",
            "content_type": "form_inbox",
            "custom_fields_json": [
                {"key": "nachname", "label": "Name", "type": "text", "options": "", "zone": "body", "show_on_card": True, "width": "half", "section": "Person"},
            ],
        })
        r = self.client.post(reverse("list_kit:builder_import"), {
            "json_payload": payload,
            "update_existing": "1",
        })
        self.assertEqual(r.status_code, 302)
        tpl.refresh_from_db()
        self.assertEqual(tpl.name, "Neu")
        self.assertEqual(tpl.custom_fields_json[0]["width"], "half")
        self.assertEqual(tpl.custom_fields_json[0]["section"], "Person")

    def test_collection_and_system_template_delete(self):
        from django.contrib.auth import get_user_model
        other = get_user_model().objects.create_user(username="other_owner", password="x")
        self.client.force_login(self.staff)
        tpl = ListTemplate.objects.create(name="SysTpl", slug="sys-del-tpl", content_type="form_inbox", is_system=True)
        col = Collection.objects.create(title="SysCol", slug="sys-del-col", template=tpl, owner=other, is_public=True)
        # Cannot delete template while collection exists
        r_blk = self.client.post(reverse("list_kit:builder_delete", args=[tpl.id]))
        self.assertEqual(r_blk.status_code, 302)
        self.assertTrue(ListTemplate.objects.filter(id=tpl.id).exists())
        # Staff can delete collection even if owned by another user
        r_col = self.client.post(reverse("list_kit:collection_delete", args=[col.id]))
        self.assertEqual(r_col.status_code, 302)
        self.assertFalse(Collection.objects.filter(id=col.id).exists())
        # Now template (even is_system=True) can be deleted
        r_tpl = self.client.post(reverse("list_kit:builder_delete", args=[tpl.id]))
        self.assertEqual(r_tpl.status_code, 302)
        self.assertFalse(ListTemplate.objects.filter(id=tpl.id).exists())

    def test_collection_create_from_form_inbox_enables_public_submit(self):
        self.client.force_login(self.staff)
        tpl = ListTemplate.objects.create(name="Umfrage", slug="umfrage-tpl", content_type="form_inbox")
        r = self.client.post(reverse("list_kit:collection_create"), {
            "template_id": tpl.id,
            "title": "Mitglieder-Umfrage",
        })
        self.assertEqual(r.status_code, 302)
        col = Collection.objects.get(title="Mitglieder-Umfrage")
        self.assertTrue(col.is_public)
        self.assertTrue(col.allow_public_submit)

    def test_builder_edit_exposes_and_saves_width_and_section(self):
        self.client.force_login(self.staff)
        tpl = ListTemplate.objects.create(name="FormTest", slug="form-width-sec", content_type="form_inbox")
        r_get = self.client.get(reverse("list_kit:builder_edit", args=[tpl.id]))
        self.assertContains(r_get, 'name="cf_width"')
        self.assertContains(r_get, 'name="cf_section"')
        self.assertContains(r_get, "Live-Vorschau (Öffentliches Formular)")
        self.assertNotContains(r_get, "Baustein-Palette")
        r_post = self.client.post(reverse("list_kit:builder_edit", args=[tpl.id]), {
            "form_editor_mode": "1",
            "name": "FormTest",
            "content_type": "form_inbox",
            "cf_label": ["Name", "IBAN"],
            "cf_key": ["nachname", "iban"],
            "cf_type": ["text", "text"],
            "cf_options": ["", ""],
            "cf_zone": ["body", "body"],
            "cf_show_card": ["1", "0"],
            "cf_width": ["half", "half"],
            "cf_section": ["Persönliche Daten", ""],
        })
        self.assertEqual(r_post.status_code, 302)
        tpl.refresh_from_db()
        self.assertEqual(tpl.custom_fields_json[0]["width"], "half")
        self.assertEqual(tpl.custom_fields_json[0]["section"], "Persönliche Daten")
        self.assertTrue(tpl.custom_fields_json[0]["show_on_card"])
        self.assertFalse(tpl.custom_fields_json[1]["show_on_card"])
        self.assertEqual(tpl.custom_fields_json[1]["zone"], "body")

    def test_pressewart_cannot_access_unassigned_form_inbox_collections(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group

        User = get_user_model()

        g_presse, _ = Group.objects.get_or_create(name="Pressewart")
        g_vorstand, _ = Group.objects.get_or_create(name="Leitung / Vorstand")
        u_presse = User.objects.create_user(username="presse_list", password="pw")
        u_presse.groups.add(g_presse)
        u_vorstand = User.objects.create_user(username="vorstand_list", password="pw")
        u_vorstand.groups.add(g_vorstand)

        tpl_inbox = ListTemplate.objects.create(name="Mitgliedsantrag", slug="mitgliedsantrag-t", content_type="form_inbox")
        col_inbox = Collection.objects.create(title="Mitgliedsantrag", slug="mitgliedsantrag-c", template=tpl_inbox, owner=self.staff, is_public=True)
        tpl_news = ListTemplate.objects.create(name="News", slug="news-t", content_type="news")
        col_news = Collection.objects.create(title="Aktuelles & News", slug="news-c", template=tpl_news, owner=self.staff, is_public=True)

        # Pressewart sees public news, NOT form_inbox
        self.client.force_login(u_presse)
        r_list = self.client.get("/lists/")
        self.assertEqual(r_list.status_code, 200)
        self.assertContains(r_list, "Aktuelles &amp; News")
        self.assertNotContains(r_list, "Mitgliedsantrag")
        self.assertEqual(self.client.get(f"/lists/{col_inbox.id}/").status_code, 403)
        self.assertEqual(self.client.get(f"/lists/{col_news.id}/").status_code, 200)

        # Leitung / Vorstand sees form_inbox
        self.client.force_login(u_vorstand)
        r_vlist = self.client.get("/lists/")
        self.assertContains(r_vlist, "Mitgliedsantrag")
        self.assertEqual(self.client.get(f"/lists/{col_inbox.id}/").status_code, 200)


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
