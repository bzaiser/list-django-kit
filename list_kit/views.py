from decimal import Decimal, InvalidOperation
from io import BytesIO
import json

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .models import Collection, Entry, EntryDocument, EntryImage, ListTemplate
from .services import (
    FIELD_DEFS,
    get_domain_masterdata_choices,
    get_linked_domain_document,
    get_site_page_choices,
    notify_staff_submission,
    sanitize_rich_html,
    seed_default_templates,
)


def _user_can_access_collection(user, collection: Collection, write: bool = False) -> bool:
    if user and user.is_authenticated:
        if user.is_superuser or collection.owner_id == user.id or collection.responsible_user_id == user.id:
            return True
        if collection.shared_with.filter(pk=user.pk).exists():
            return True
        if collection.is_public and user.groups.filter(name__in=("Redakteur", "Leitung / Vorstand", "Vorstand")).exists():
            return True
    if not write and collection.is_public:
        return True
    return False


def _user_allowed_collections(user):
    if user.is_superuser:
        return Collection.objects.all()
    q = Q(owner=user) | Q(responsible_user=user) | Q(shared_with=user)
    if user.groups.filter(name__in=("Redakteur", "Leitung / Vorstand", "Vorstand")).exists():
        q |= Q(is_public=True)
    return Collection.objects.filter(q).distinct()


def _can_manage_collections(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    from django.contrib.auth.models import Group
    if not Group.objects.exists():
        return True
    return user.groups.filter(
        name__in=("Leitung / Vorstand", "Vorstand", "Schriftführer", "Redakteur", "Pressewart", "Mitarbeiter")
    ).exists()


@login_required
def collection_list_view(request):
    seed_default_templates()
    qs = (
        _user_allowed_collections(request.user)
        .select_related("template", "owner")
        .annotate(
            open_count=Count("entries", filter=Q(entries__is_completed=False)),
            done_count=Count("entries", filter=Q(entries__is_completed=True)),
        )
    )
    return render(request, "list_kit/collection_list.html", {
        "collections": qs,
        "can_create_collection": _can_manage_collections(request.user),
    })


@login_required
def collection_create_view(request):
    if not _can_manage_collections(request.user):
        return HttpResponseForbidden("Keine Berechtigung zum Erstellen neuer Sammlungen.")
    seed_default_templates()
    templates = ListTemplate.objects.all()
    if request.method == "POST":
        tpl_id = request.POST.get("template_id")
        title = (request.POST.get("title") or "").strip()
        if not tpl_id or not title:
            messages.error(request, "Bitte Vorlage und Titel angeben.")
            return redirect("list_kit:collection_create")
        tpl = get_object_or_404(ListTemplate, pk=tpl_id)
        col = Collection.objects.create(
            title=title[:200],
            template=tpl,
            owner=request.user,
            is_public=request.POST.get("is_public") == "on",
        )
        messages.success(request, f"Sammlung „{col.title}“ erstellt.")
        return redirect("list_kit:collection_detail", pk=col.id)
    return render(request, "list_kit/collection_create.html", {"templates": templates})


def collection_detail_view(request, pk):
    col = get_object_or_404(Collection.objects.select_related("template", "owner"), pk=pk)
    if not _user_can_access_collection(request.user, col, write=False):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        return HttpResponseForbidden("Kein Zugriff auf diese Sammlung.")

    can_edit = _user_can_access_collection(request.user, col, write=True)
    entries_qs = col.entries.select_related("created_by").prefetch_related("images", "documents").all()
    if not can_edit:
        entries_qs = entries_qs.filter(visibility="public")

    all_entries = list(entries_qs)
    ui = col.template.get_ui_style()
    status_filter = (request.GET.get("status") or "all").strip().lower()
    inbox_tabs = []

    if col.template.content_type == "form_inbox":
        def _status_bucket(entry_obj):
            st = (entry_obj.status or "Offen").strip().lower()
            if st in ("abgesagt", "abgelehnt"):
                return "abgesagt"
            if st == "bestätigt":
                return "bestaetigt"
            if st == "teilgenommen":
                return "teilgenommen"
            return "offen"

        counts = {
            "all": len(all_entries),
            "offen": sum(1 for e in all_entries if _status_bucket(e) == "offen"),
            "bestaetigt": sum(1 for e in all_entries if _status_bucket(e) == "bestaetigt"),
            "bezahlt": sum(1 for e in all_entries if bool((e.custom_data_json or {}).get("is_paid"))),
            "teilgenommen": sum(1 for e in all_entries if _status_bucket(e) == "teilgenommen"),
            "abgesagt": sum(1 for e in all_entries if _status_bucket(e) == "abgesagt"),
        }
        inbox_tabs = [
            {"key": "all", "label": "Alle", "count": counts["all"]},
            {"key": "offen", "label": "Offen", "count": counts["offen"]},
            {"key": "bestaetigt", "label": "Bestätigt", "count": counts["bestaetigt"]},
        ]
        if col.template.slug in ("kurs-anmeldung", "mitgliedsantrag") or col.template.use_price:
            inbox_tabs.append({"key": "bezahlt", "label": "Bezahlt", "count": counts["bezahlt"]})
        if col.template.slug == "kurs-anmeldung":
            inbox_tabs.append({"key": "teilgenommen", "label": "Teilgenommen", "count": counts["teilgenommen"]})
        inbox_tabs.append({"key": "abgesagt", "label": "Abgesagt", "count": counts["abgesagt"]})

        if status_filter == "bezahlt":
            active_entries = [e for e in all_entries if bool((e.custom_data_json or {}).get("is_paid"))]
        elif status_filter in ("offen", "bestaetigt", "teilgenommen", "abgesagt"):
            active_entries = [e for e in all_entries if _status_bucket(e) == status_filter]
        else:
            status_filter = "all"
            active_entries = all_entries
        completed_entries = []
    elif col.template.content_type == "news":
        now = timezone.now()
        news_view_mode = (request.GET.get("view") or "active").strip().lower()
        if news_view_mode not in ("active", "archive"):
            news_view_mode = "active"
        active_news = [e for e in all_entries if not e.expires_at or e.expires_at > now]
        archived_news = [e for e in all_entries if e.expires_at and e.expires_at <= now]
        active_entries = archived_news if news_view_mode == "archive" else active_news
        completed_entries = []
    else:
        active_entries = [e for e in all_entries if not e.is_completed]
        completed_entries = [e for e in all_entries if e.is_completed]

    custom_fields = col.template.custom_fields_json or []
    masterdata = get_domain_masterdata_choices(col.template.content_type, public_only=col.is_public)
    prepared_custom_fields = []
    for cf in custom_fields:
        if not isinstance(cf, dict) or not cf.get("key"):
            continue
        raw_opts = cf.get("options") or ""
        opts_list = [o.strip() for o in str(raw_opts).split(",") if o.strip()]
        prepared_custom_fields.append({
            "key": cf.get("key"),
            "label": cf.get("label") or cf.get("key"),
            "type": cf.get("type", "text"),
            "options": raw_opts,
            "options_list": opts_list,
            "zone": cf.get("zone", "body"),
        })

    for entry in active_entries:
        cdata = entry.custom_data_json if isinstance(entry.custom_data_json, dict) else {}
        entry.edit_custom_fields = [
            {
                "key": cf["key"],
                "label": cf["label"],
                "type": cf["type"],
                "options_list": cf["options_list"],
                "value": cdata.get(cf["key"], ""),
            }
            for cf in prepared_custom_fields
            if cf["zone"] != "hidden"
        ]
        entry.linked_document_info = (
            get_linked_domain_document(entry.linked_document_id, require_public=col.is_public)
            if col.template.use_document and entry.linked_document_id
            else None
        )

    ctx = {
        "collection": col,
        "template": col.template,
        "can_edit": can_edit,
        "active_entries": active_entries,
        "completed_entries": completed_entries,
        "status_filter": status_filter,
        "inbox_tabs": inbox_tabs,
        "news_view_mode": locals().get("news_view_mode", "active"),
        "news_active_count": len(locals().get("active_news", [])),
        "news_archive_count": len(locals().get("archived_news", [])),
        "now": timezone.now(),
        "ui": ui,
        "statuses": col.template.get_effective_statuses(),
        "custom_fields": prepared_custom_fields,
        "masterdata": masterdata,
        "site_pages": get_site_page_choices(),
        "visibility_choices": Entry.VISIBILITY_CHOICES,
    }
    if ui.get("genre"):
        try:
            from design_studio.genres import get_genre_definition
            genre_def = get_genre_definition(ui["genre"])
            if genre_def:
                ctx["active_genre"] = genre_def
        except Exception:
            pass
    return render(request, "list_kit/collection_detail.html", ctx)


@login_required
@require_POST
def collection_delete_view(request, pk):
    col = get_object_or_404(Collection, pk=pk)
    if (col.owner_id != request.user.id or not _can_manage_collections(request.user)) and not request.user.is_superuser:
        return HttpResponseForbidden()
    title = col.title
    col.delete()
    messages.success(request, f"Sammlung „{title}“ gelöscht.")
    return redirect("list_kit:collection_list")


def _parse_decimal(raw: str):
    raw = (raw or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


@login_required
@require_POST
def entry_save_view(request, pk, entry_id=None):
    col = get_object_or_404(Collection.objects.select_related("template"), pk=pk)
    if not _user_can_access_collection(request.user, col, write=True):
        return HttpResponseForbidden()

    if entry_id is not None:
        entry = get_object_or_404(Entry, pk=entry_id, collection=col)
    else:
        entry = Entry(collection=col, created_by=request.user)

    title = (request.POST.get("title") or "").strip()
    if not title:
        messages.error(request, "Titel darf nicht leer sein.")
        return redirect("list_kit:collection_detail", pk=col.id)

    tpl = col.template
    entry.title = title[:255]
    raw_notes = (request.POST.get("notes") or "").strip()
    entry.notes = sanitize_rich_html(raw_notes) if tpl.use_rich_notes else raw_notes

    statuses = tpl.get_effective_statuses()
    status_map = {s["key"]: s for s in statuses if isinstance(s, dict) and s.get("key")}
    posted_status = (request.POST.get("status") or "").strip()
    if posted_status in status_map:
        entry.status = posted_status
        entry.is_completed = bool(status_map[posted_status].get("completes"))

    vis = (request.POST.get("visibility") or entry.visibility or "internal").strip()
    if vis in dict(Entry.VISIBILITY_CHOICES):
        entry.visibility = vis
    entry.is_pinned = request.POST.get("is_pinned") == "on"

    for dt_field in ("start_date", "end_date", "reminder_at", "publish_at", "expires_at"):
        raw_dt = (request.POST.get(dt_field) or "").strip()
        if raw_dt:
            parsed = parse_datetime(raw_dt)
            if parsed is not None:
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed)
                setattr(entry, dt_field, parsed)
        elif dt_field in request.POST:
            setattr(entry, dt_field, None)
    if request.POST.get("archive_now") == "1":
        entry.expires_at = timezone.now()

    if tpl.use_amount:
        entry.amount_value = _parse_decimal(request.POST.get("amount_value", ""))
        entry.amount_unit = (request.POST.get("amount_unit") or "").strip()[:30]
    if tpl.use_price:
        entry.price = _parse_decimal(request.POST.get("price", ""))
    if tpl.use_rating:
        raw_r = (request.POST.get("rating") or "").strip()
        entry.rating = max(1, min(5, int(raw_r))) if raw_r.isdigit() else None
    if tpl.use_url:
        entry.url = (request.POST.get("url") or "").strip()[:300]
        entry.url_label = (request.POST.get("url_label") or "").strip()[:120]
    if tpl.use_location:
        entry.location = (request.POST.get("location") or "").strip()[:160]
    if tpl.use_image:
        entry.image_url = (request.POST.get("image_url") or "").strip()[:200]
    if tpl.use_cover_image:
        if request.POST.get("remove_cover_image") == "1" and entry.cover_image:
            entry.cover_image.delete(save=False)
            entry.cover_image = None
        if "cover_image" in request.FILES:
            entry.cover_image = request.FILES["cover_image"]
    if tpl.use_category or tpl.use_master_status or tpl.use_person or tpl.use_document:
        md = get_domain_masterdata_choices(tpl.content_type, public_only=col.is_public)
        if tpl.use_category:
            cid = (request.POST.get("category_id") or "").strip()
            if cid.isdigit():
                entry.category_id = int(cid)
                match = next((c for c in md["categories"] if c["id"] == entry.category_id), None)
                entry.category_label = match["name"] if match else ""
            else:
                entry.category_id = None
                entry.category_label = (request.POST.get("category_label") or "").strip()[:120]
        if tpl.use_master_status:
            sid = (request.POST.get("master_status_id") or "").strip()
            if sid.isdigit():
                entry.master_status_id = int(sid)
                match = next((s for s in md["statuses"] if s["id"] == entry.master_status_id), None)
                entry.master_status_label = match["name"] if match else ""
            else:
                entry.master_status_id = None
                entry.master_status_label = (request.POST.get("master_status_label") or "").strip()[:120]
        if tpl.use_person:
            pid = (request.POST.get("person_id") or "").strip()
            if pid.isdigit():
                entry.person_id = int(pid)
                match = next((p for p in md["persons"] if p["id"] == entry.person_id), None)
                entry.person_label = match["name"] if match else ""
            else:
                entry.person_id = None
                entry.person_label = (request.POST.get("person_label") or "").strip()[:160]
        if tpl.use_document:
            did = (request.POST.get("linked_document_id") or "").strip()
            if did.isdigit():
                doc_info = get_linked_domain_document(int(did), require_public=col.is_public)
                entry.linked_document_id = doc_info["id"] if doc_info else None
            else:
                entry.linked_document_id = None

    custom_data = dict(entry.custom_data_json or {})
    for cf in (tpl.custom_fields_json or []):
        key = cf.get("key")
        if not key:
            continue
        ftype = cf.get("type", "text")
        form_key = f"custom_{key}"
        if ftype == "checkbox":
            custom_data[key] = request.POST.get(form_key) == "on"
        elif ftype == "multiselect":
            custom_data[key] = [v.strip() for v in request.POST.getlist(form_key) if v.strip()]
        elif ftype == "wysiwyg":
            custom_data[key] = sanitize_rich_html((request.POST.get(form_key) or "").strip())
        else:
            custom_data[key] = (request.POST.get(form_key) or "").strip()
    entry.custom_data_json = custom_data
    entry.save()

    if tpl.use_image:
        new_captions = request.POST.getlist("new_image_captions")
        for idx, img_file in enumerate(request.FILES.getlist("images")):
            cap = (new_captions[idx] if idx < len(new_captions) else "").strip()[:200]
            EntryImage.objects.create(entry=entry, image=img_file, caption=cap)

        delete_ids = [int(i) for i in request.POST.getlist("delete_image_ids") if str(i).isdigit()]
        if delete_ids:
            entry.images.filter(id__in=delete_ids).delete()

        for img in entry.images.all():
            cap_key = f"existing_image_caption_{img.id}"
            if cap_key in request.POST:
                new_cap = (request.POST.get(cap_key) or "").strip()[:200]
                if img.caption != new_cap:
                    img.caption = new_cap
                    img.save(update_fields=["caption"])

    if tpl.use_document:
        doc_titles = request.POST.getlist("new_document_titles")
        doc_public = request.POST.get("new_documents_public", "1") != "0"
        for idx, doc_file in enumerate(request.FILES.getlist("documents")):
            d_title = (doc_titles[idx] if idx < len(doc_titles) else "").strip()[:200]
            EntryDocument.objects.create(entry=entry, file=doc_file, title=d_title, is_public=doc_public)

        del_doc_ids = [int(i) for i in request.POST.getlist("delete_document_ids") if str(i).isdigit()]
        if del_doc_ids:
            entry.documents.filter(id__in=del_doc_ids).delete()

        for doc in entry.documents.all():
            pub_key = f"existing_document_public_{doc.id}"
            if f"existing_document_present_{doc.id}" in request.POST:
                new_pub = request.POST.get(pub_key) == "on"
                if doc.is_public != new_pub:
                    doc.is_public = new_pub
                    doc.save(update_fields=["is_public"])

    messages.success(request, "Eintrag gespeichert.")
    return redirect("list_kit:collection_detail", pk=col.id)


@login_required
@require_POST
def entry_image_toggle_view(request, pk, entry_id, image_id):
    col = get_object_or_404(Collection, pk=pk)
    if not _user_can_access_collection(request.user, col, write=True):
        return HttpResponseForbidden()
    entry = get_object_or_404(Entry, pk=entry_id, collection=col)
    img = get_object_or_404(EntryImage, pk=image_id, entry=entry)
    img.is_checked = not img.is_checked
    img.save(update_fields=["is_checked"])
    return redirect("list_kit:collection_detail", pk=col.id)


def collection_pdf_view(request, pk):
    col = get_object_or_404(Collection.objects.select_related("template", "owner"), pk=pk)
    if not _user_can_access_collection(request.user, col, write=False):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        return HttpResponseForbidden("Kein Zugriff auf diese Sammlung.")

    can_edit = _user_can_access_collection(request.user, col, write=True)
    tpl = col.template
    raw_pdf = (tpl.get_ui_style().get("pdf") or {})
    pdf_cfg = {
        "orientation": raw_pdf.get("orientation") if raw_pdf.get("orientation") in ("portrait", "landscape") else "portrait",
        "filter": request.GET.get("filter") or raw_pdf.get("filter") or "all",
        "include_summary": raw_pdf.get("include_summary", True),
        "include_notes": raw_pdf.get("include_notes", True),
        "include_photos": raw_pdf.get("include_photos", True),
        "include_custom_fields": raw_pdf.get("include_custom_fields", True),
        "include_dates": raw_pdf.get("include_dates", True),
        "footer_text": raw_pdf.get("footer_text", ""),
    }

    qs = col.entries.select_related("created_by").prefetch_related("images").all()
    if not can_edit:
        qs = qs.filter(visibility="public")
    all_entries = list(qs)
    total_count = len(all_entries)
    done_count = sum(1 for e in all_entries if e.is_completed)
    open_count = total_count - done_count

    if pdf_cfg["filter"] == "open":
        entries = [e for e in all_entries if not e.is_completed]
    elif pdf_cfg["filter"] == "done":
        entries = [e for e in all_entries if e.is_completed]
    else:
        entries = all_entries

    total_price = sum(float(e.price) for e in entries if e.price is not None) if tpl.use_price else None
    ctx = {
        "collection": col,
        "template": tpl,
        "entries": entries,
        "pdf_cfg": pdf_cfg,
        "total_count": total_count,
        "open_count": open_count,
        "done_count": done_count,
        "total_price": total_price,
    }
    html = get_template("list_kit/pdf_export.html").render(ctx)
    try:
        from xhtml2pdf import pisa
        result = BytesIO()
        pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
        if not pdf.err:
            resp = HttpResponse(result.getvalue(), content_type="application/pdf")
            resp["Content-Disposition"] = f'inline; filename="{col.slug or col.id}.pdf"'
            return resp
    except ImportError:
        pass
    return HttpResponse(html)


@login_required
@require_POST
def entry_toggle_view(request, pk, entry_id):
    col = get_object_or_404(Collection.objects.select_related("template"), pk=pk)
    if not _user_can_access_collection(request.user, col, write=True):
        return HttpResponseForbidden()
    entry = get_object_or_404(Entry, pk=entry_id, collection=col)
    entry.is_completed = not entry.is_completed
    statuses = col.template.get_effective_statuses()
    target = next((s for s in statuses if bool(s.get("completes")) == entry.is_completed), None)
    if target and target.get("key"):
        entry.status = target["key"]
    entry.save(update_fields=["is_completed", "status", "updated_at"])
    return redirect("list_kit:collection_detail", pk=col.id)


@login_required
@require_POST
def entry_delete_view(request, pk, entry_id):
    col = get_object_or_404(Collection, pk=pk)
    if not _user_can_access_collection(request.user, col, write=True):
        return HttpResponseForbidden()
    entry = get_object_or_404(Entry, pk=entry_id, collection=col)
    entry.delete()
    messages.success(request, "Eintrag gelöscht.")
    return redirect("list_kit:collection_detail", pk=col.id)


@login_required
@require_POST
def entry_duplicate_view(request, pk, entry_id):
    col = get_object_or_404(Collection.objects.select_related("template"), pk=pk)
    if not _user_can_access_collection(request.user, col, write=True):
        return HttpResponseForbidden()
    src = get_object_or_404(Entry, pk=entry_id, collection=col)
    is_news = col.template.content_type == "news"
    dup = Entry.objects.create(
        collection=col,
        title=f"{src.title[:247]} - Kopie",
        notes=src.notes,
        status=src.status,
        is_completed=False,
        visibility="draft" if is_news else src.visibility,
        is_pinned=False,
        start_date=src.start_date,
        end_date=src.end_date,
        reminder_at=src.reminder_at,
        amount_value=src.amount_value,
        amount_unit=src.amount_unit,
        price=src.price,
        rating=src.rating,
        url=src.url,
        url_label=src.url_label,
        location=src.location,
        image_url=src.image_url,
        category_id=src.category_id,
        category_label=src.category_label,
        master_status_id=src.master_status_id,
        master_status_label=src.master_status_label,
        person_id=src.person_id,
        person_label=src.person_label,
        linked_document_id=src.linked_document_id,
        custom_data_json=dict(src.custom_data_json or {}),
        position=src.position,
        created_by=request.user,
    )
    if src.cover_image:
        try:
            with src.cover_image.open("rb") as fh:
                name = (src.cover_image.name or "cover.jpg").rsplit("/", 1)[-1]
                dup.cover_image.save(name, ContentFile(fh.read()), save=True)
        except Exception:
            pass
    for img in src.images.all():
        try:
            with img.image.open("rb") as fh:
                name = (img.image.name or "photo.jpg").rsplit("/", 1)[-1]
                EntryImage.objects.create(
                    entry=dup,
                    image=ContentFile(fh.read(), name=name),
                    caption=img.caption,
                    is_checked=False,
                )
        except Exception:
            pass
    for doc in src.documents.all():
        try:
            with doc.file.open("rb") as fh:
                name = (doc.file.name or "doc.bin").rsplit("/", 1)[-1]
                EntryDocument.objects.create(
                    entry=dup,
                    file=ContentFile(fh.read(), name=name),
                    title=doc.title,
                    is_public=doc.is_public,
                )
        except Exception:
            pass
    messages.success(request, f"Kopie „{dup.title}“ angelegt.")
    return redirect(f"{reverse('list_kit:collection_detail', args=[col.id])}?edit={dup.id}")


@require_POST
def public_submit_view(request, pk):
    col = get_object_or_404(Collection.objects.select_related("template", "owner"), pk=pk)
    if not (col.is_public and col.allow_public_submit):
        return HttpResponseForbidden("Öffentliche Einreichung nicht aktiviert.")

    title = (request.POST.get("title") or "").strip()
    if not title:
        messages.error(request, "Bitte einen Betreff / Titel angeben.")
        next_url = (request.POST.get("next") or "").strip()
        return redirect(next_url or "list_kit:collection_detail", pk=col.id) if not next_url else redirect(next_url)

    custom_data = {}
    for cf in (col.template.custom_fields_json or []):
        key = cf.get("key")
        if not key:
            continue
        ftype = cf.get("type", "text")
        form_key = f"custom_{key}"
        if ftype == "checkbox":
            custom_data[key] = request.POST.get(form_key) == "on"
        elif ftype == "multiselect":
            custom_data[key] = [v.strip() for v in request.POST.getlist(form_key) if v.strip()]
        elif ftype == "wysiwyg":
            custom_data[key] = sanitize_rich_html((request.POST.get(form_key) or "").strip())
        else:
            custom_data[key] = (request.POST.get(form_key) or "").strip()

    event_id = (request.POST.get("event_id") or "").strip()
    if event_id.isdigit():
        custom_data["event_id"] = event_id

    entry = Entry.objects.create(
        collection=col,
        title=title[:255],
        notes=(request.POST.get("notes") or "").strip(),
        status="open",
        visibility="draft",
        custom_data_json=custom_data,
        created_by=request.user if request.user.is_authenticated else None,
    )
    notify_staff_submission(col, entry)
    messages.success(request, "Vielen Dank! Deine Anfrage wurde übermittelt.")
    next_url = (request.POST.get("next") or "").strip()
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect("list_kit:collection_detail", pk=col.id)


@login_required
@require_POST
def entry_confirm_view(request, pk, entry_id):
    col = get_object_or_404(Collection, pk=pk)
    if not _user_can_access_collection(request.user, col, write=True):
        return HttpResponseForbidden()
    entry = get_object_or_404(Entry, pk=entry_id, collection=col)
    decision = (request.POST.get("decision") or "confirm").strip().lower()
    note = (request.POST.get("confirm_note") or "").strip()
    now_str = timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M")
    username = request.user.get_username()

    data = dict(entry.custom_data_json or {})
    if note:
        data["confirm_note"] = note

    send_decision_mail = False
    subj_state = ""

    if decision == "paid":
        is_paid = not bool(data.get("is_paid"))
        data["is_paid"] = is_paid
        if is_paid:
            data["paid_by"] = username
            data["paid_at"] = now_str
        else:
            data.pop("paid_by", None)
            data.pop("paid_at", None)
        entry.is_completed = False
        msg = f"Eintrag „{entry.title}“ als {'Bezahlt' if is_paid else 'Nicht bezahlt'} markiert."
    elif decision == "payment_update":
        raw_paid = (request.POST.get("paid_amount") or "").strip().replace(",", ".")
        raw_cancel = (request.POST.get("cancellation_fee") or "").strip().replace(",", ".")
        if raw_paid:
            data["paid_amount"] = raw_paid
            try:
                data["is_paid"] = float(raw_paid) > 0
            except ValueError:
                pass
        else:
            data.pop("paid_amount", None)
        if raw_cancel:
            data["cancellation_fee"] = raw_cancel
        else:
            data.pop("cancellation_fee", None)
        entry.is_completed = False
        msg = f"Zahlungs-/Stornodaten für „{entry.title}“ aktualisiert."
    elif decision == "attended":
        data["attended_by"] = username
        data["attended_at"] = now_str
        entry.status = "Teilgenommen"
        entry.is_completed = False
        msg = f"Eintrag „{entry.title}“ als {entry.status} markiert."
    elif decision == "reject":
        data["confirmed_by"] = username
        data["confirmed_at"] = now_str
        entry.status = "Abgesagt"
        entry.is_completed = False
        send_decision_mail = True
        subj_state = "abgesagt"
        msg = f"Eintrag „{entry.title}“ als {entry.status} markiert."
    else:
        data["confirmed_by"] = username
        data["confirmed_at"] = now_str
        entry.status = "Bestätigt"
        entry.is_completed = False
        send_decision_mail = True
        subj_state = "bestätigt"
        msg = f"Eintrag „{entry.title}“ als {entry.status} markiert."

    entry.custom_data_json = data
    entry.save(update_fields=["custom_data_json", "status", "is_completed", "updated_at"])

    recipient_email = (data.get("absender_email") or data.get("email") or "").strip()
    if send_decision_mail and recipient_email and "@" in recipient_email:
        try:
            from django.conf import settings as django_settings
            from django.core.mail import send_mail

            body = (
                f"Hallo,\n\nIhre Anfrage „{entry.title}“ ({col.title}) wurde {subj_state}."
                + (f"\n\nHinweis: {note}" if note else "")
                + "\n"
            )
            send_mail(
                subject=f"{col.title}: {entry.title} ({subj_state})",
                message=body,
                from_email=getattr(django_settings, "DEFAULT_FROM_EMAIL", None) or "noreply@localhost",
                recipient_list=[recipient_email],
                fail_silently=True,
            )
        except Exception:
            pass

    messages.success(request, msg)
    next_url = (request.POST.get("next") or "").strip()
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect("list_kit:collection_detail", pk=col.id)


@login_required
@require_POST
def entry_create_person_view(request, pk, entry_id):
    col = get_object_or_404(Collection, pk=pk)
    if not _user_can_access_collection(request.user, col, write=True):
        return HttpResponseForbidden()
    entry = get_object_or_404(Entry, pk=entry_id, collection=col)
    try:
        from domain_kit.models import Address, Person
    except Exception:
        messages.error(request, "domain_kit ist nicht installiert.")
        return redirect("list_kit:collection_detail", pk=col.id)

    data = dict(entry.custom_data_json or {})
    first = (data.get("vorname") or "").strip()
    last = (data.get("nachname") or "").strip()
    if not first and data.get("absender_name"):
        parts = str(data["absender_name"]).strip().split(" ", 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""
    first = (first or entry.title or "Neu")[:80]
    email = (data.get("absender_email") or data.get("email") or "").strip()[:140]
    phone = (data.get("telefon") or "").strip()[:60]
    person = Person.objects.create(
        first_name=first,
        last_name=last[:80],
        display_name=f"{first} {last}".strip()[:140],
        email=email,
        phone=phone,
        notes=f"Übernommen aus {col.title}: {entry.title}",
    )
    street = (data.get("strasse") or "").strip()[:140]
    plz_ort = (data.get("plz_ort") or "").strip()
    if street or plz_ort:
        plz, city = "", plz_ort
        parts = plz_ort.split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            plz, city = parts[0][:24], parts[1][:80]
        Address.objects.create(
            person=person,
            label="Hauptadresse",
            street=street,
            postal_code=plz,
            city=city[:80],
            is_primary=True,
        )
    data["created_person_id"] = person.id
    entry.custom_data_json = data
    entry.save(update_fields=["custom_data_json", "updated_at"])
    messages.success(request, f"Person „{person.full_name}“ in domain_kit angelegt.")
    return redirect("list_kit:collection_detail", pk=col.id)


@login_required
def collection_export_csv_view(request, pk):
    import csv

    col = get_object_or_404(Collection.objects.select_related("template"), pk=pk)
    if not _user_can_access_collection(request.user, col, write=False):
        return HttpResponseForbidden()
    qs = col.entries.all().order_by("-created_at")
    status_filter = (request.GET.get("status") or "").strip()
    if status_filter:
        qs = qs.filter(status__iexact=status_filter)

    cf_keys = [cf.get("key") for cf in (col.template.custom_fields_json or []) if cf.get("key")]
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{col.slug or col.id}.csv"'
    resp.write("\ufeff")
    writer = csv.writer(resp, delimiter=";")
    writer.writerow(["Titel", "Status", "Erstellt"] + cf_keys + ["Notizen"])
    for e in qs:
        data = e.custom_data_json if isinstance(e.custom_data_json, dict) else {}
        writer.writerow(
            [e.title, e.status, e.created_at.strftime("%Y-%m-%d %H:%M")]
            + [data.get(k, "") for k in cf_keys]
            + [e.notes]
        )
    return resp


@staff_member_required
def builder_list_view(request):
    seed_default_templates()
    templates = ListTemplate.objects.annotate(collection_count=Count("collections")).order_by("name")
    return render(request, "list_kit/builder_list.html", {"templates": templates})


@staff_member_required
def builder_edit_view(request, pk=None):
    tpl = get_object_or_404(ListTemplate, pk=pk) if pk is not None else None
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, "Bitte einen Vorlagen-Namen angeben.")
            return redirect(request.path)

        if tpl is None:
            tpl = ListTemplate(name=name[:120])
        else:
            tpl.name = name[:120]

        tpl.icon = (request.POST.get("icon") or "bi-card-checklist").strip()[:40] or "bi-card-checklist"
        tpl.description = (request.POST.get("description") or "").strip()
        ctype = (request.POST.get("content_type") or "list").strip()
        if ctype in dict(ListTemplate.CONTENT_TYPE_CHOICES):
            tpl.content_type = ctype

        for fdef in FIELD_DEFS:
            setattr(tpl, fdef["key"], request.POST.get(fdef["key"]) == "on")

        # Statuses
        s_keys = request.POST.getlist("status_key")
        s_labels = request.POST.getlist("status_label")
        s_completes = request.POST.getlist("status_completes")
        statuses = []
        for idx, lbl in enumerate(s_labels):
            lbl_clean = lbl.strip()
            if not lbl_clean:
                continue
            raw_k = s_keys[idx] if idx < len(s_keys) else ""
            k_clean = slugify(raw_k or lbl_clean).replace("-", "_")[:24] or f"status_{idx}"
            comp = (s_completes[idx] == "1") if idx < len(s_completes) else False
            statuses.append({"key": k_clean, "label": lbl_clean, "completes": comp})
        tpl.allowed_statuses_json = statuses

        # Custom fields
        cf_keys = request.POST.getlist("cf_key")
        cf_labels = request.POST.getlist("cf_label")
        cf_types = request.POST.getlist("cf_type")
        cf_options = request.POST.getlist("cf_options")
        cf_zones = request.POST.getlist("cf_zone")
        cf_show_cards = request.POST.getlist("cf_show_card")
        allowed_cf_types = (
            "text", "textarea", "markdown", "wysiwyg", "number", "currency", "date", "url", "page_link",
            "image", "select", "radio", "multiselect", "checkbox", "rating", "color",
        )
        custom_fields = []
        for idx, lbl in enumerate(cf_labels):
            lbl_clean = lbl.strip()
            if not lbl_clean:
                continue
            raw_k = cf_keys[idx] if idx < len(cf_keys) else ""
            k_clean = slugify(raw_k or lbl_clean).replace("-", "_")[:30] or f"field_{idx}"
            ftype = cf_types[idx] if idx < len(cf_types) and cf_types[idx] in allowed_cf_types else "text"
            opts = cf_options[idx].strip() if idx < len(cf_options) else ""
            zone = cf_zones[idx].strip() if idx < len(cf_zones) and cf_zones[idx].strip() in ("header", "body", "footer", "hidden") else "body"
            show_on_card = (cf_show_cards[idx] != "0") if idx < len(cf_show_cards) else (zone != "hidden")
            if not show_on_card:
                zone = "hidden"
            custom_fields.append({
                "key": k_clean,
                "label": lbl_clean,
                "type": ftype,
                "options": opts,
                "zone": zone,
                "show_on_card": show_on_card,
            })
        tpl.custom_fields_json = custom_fields

        layout_mode = request.POST.get("ui_layout_mode", "row")
        if layout_mode not in ("row", "cards", "stacked"):
            layout_mode = "row"
        card_width = request.POST.get("ui_card_width", "1/3")
        if card_width not in ("1/4", "1/3", "1/2", "3/4", "hero"):
            card_width = "1/3"
        density = request.POST.get("ui_density", "normal")
        if density not in ("normal", "compact"):
            density = "normal"

        genre = (request.POST.get("ui_genre") or "").strip()
        try:
            from design_studio.genres import is_valid_genre
            if not is_valid_genre(genre):
                genre = ""
        except Exception:
            pass

        card_layout = None
        raw_layout = (request.POST.get("ui_card_layout_json") or "").strip()
        if raw_layout:
            try:
                parsed = json.loads(raw_layout)
                if isinstance(parsed, dict):
                    card_layout = {
                        z: [str(x).strip() for x in (parsed.get(z) or []) if str(x).strip()]
                        for z in ("header", "body", "footer", "hidden")
                    }
            except (ValueError, TypeError):
                card_layout = None

        pdf_orientation = request.POST.get("pdf_orientation", "portrait")
        if pdf_orientation not in ("portrait", "landscape"):
            pdf_orientation = "portrait"
        pdf_filter = request.POST.get("pdf_filter", "all")
        if pdf_filter not in ("all", "open", "done"):
            pdf_filter = "all"
        pdf_cfg = {
            "orientation": pdf_orientation,
            "filter": pdf_filter,
            "include_summary": request.POST.get("pdf_include_summary") == "on",
            "include_notes": request.POST.get("pdf_include_notes") == "on",
            "include_photos": request.POST.get("pdf_include_photos") == "on",
            "include_custom_fields": request.POST.get("pdf_include_custom_fields") == "on",
            "include_dates": request.POST.get("pdf_include_dates") == "on",
            "footer_text": (request.POST.get("pdf_footer_text") or "").strip()[:160],
        }

        c_pos = request.POST.get("ui_cover_position", "left")
        c_shape = request.POST.get("ui_cover_shape", "rounded")
        c_aspect = request.POST.get("ui_cover_aspect", "auto")
        c_size = request.POST.get("ui_cover_size", "md")
        cover_cfg = {
            "position": c_pos if c_pos in ("left", "right", "top", "bottom") else "left",
            "shape": c_shape if c_shape in ("rounded", "square", "circle") else "rounded",
            "aspect": c_aspect if c_aspect in ("auto", "landscape", "portrait", "square") else "auto",
            "size": c_size if c_size in ("sm", "md", "lg") else "md",
        }

        tpl.ui_style_json = {
            "layout_mode": layout_mode,
            "card_width": card_width,
            "cover_image": cover_cfg,
            "density": density,
            "show_creator": request.POST.get("ui_show_creator") == "on",
            "genre": genre,
            "card_layout": card_layout,
            "pdf": pdf_cfg,
        }
        tpl.save()
        messages.success(request, f"Vorlage „{tpl.name}“ gespeichert.")
        return redirect("list_kit:builder_list")

    active_keys = [f["key"] for f in FIELD_DEFS if (getattr(tpl, f["key"], False) if tpl else f["key"] in ("use_notes", "use_status"))]
    ui_style = tpl.get_ui_style() if tpl else {
        "layout_mode": "row",
        "card_width": "1/3",
        "density": "normal",
        "show_creator": True,
        "genre": "",
        "card_layout": None,
    }
    statuses = tpl.get_effective_statuses() if tpl else [
        {"key": "open", "label": "Offen", "completes": False},
        {"key": "done", "label": "Erledigt", "completes": True},
    ]
    custom_fields = tpl.custom_fields_json if (tpl and isinstance(tpl.custom_fields_json, list)) else []
    return render(request, "list_kit/builder_edit.html", {
        "tpl": tpl,
        "field_defs_json": json.dumps(FIELD_DEFS),
        "active_keys_json": json.dumps(active_keys),
        "custom_fields_json": json.dumps(custom_fields),
        "statuses_json": json.dumps(statuses),
        "ui_style": ui_style,
        "ui_style_json": json.dumps(ui_style),
        "content_type_choices": ListTemplate.CONTENT_TYPE_CHOICES,
    })


@staff_member_required
def builder_export_view(request, pk):
    tpl = get_object_or_404(ListTemplate, pk=pk)
    payload = {
        "name": tpl.name,
        "slug": tpl.slug,
        "icon": tpl.icon,
        "description": tpl.description,
        "content_type": tpl.content_type,
        "flags": {f["key"]: bool(getattr(tpl, f["key"], False)) for f in FIELD_DEFS},
        "custom_fields_json": tpl.custom_fields_json,
        "allowed_statuses_json": tpl.allowed_statuses_json,
        "ui_style_json": tpl.ui_style_json,
        "summary_rule_json": tpl.summary_rule_json,
    }
    resp = JsonResponse(payload, json_dumps_params={"indent": 2, "ensure_ascii": False})
    resp["Content-Disposition"] = f'attachment; filename="{tpl.slug}.json"'
    return resp


@staff_member_required
@require_POST
def builder_import_view(request):
    raw = (request.POST.get("json_payload") or request.POST.get("template_json") or "").strip()
    if not raw and request.FILES.get("json_file"):
        raw = request.FILES["json_file"].read().decode("utf-8", errors="replace").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or not data.get("name"):
            raise ValueError("Ungültiges Vorlagen-JSON.")
    except Exception as exc:
        messages.error(request, f"Import fehlgeschlagen: {exc}")
        return redirect("list_kit:builder_list")

    ctype = data.get("content_type", "list")
    if ctype not in dict(ListTemplate.CONTENT_TYPE_CHOICES):
        ctype = "list"

    ui_style = data.get("ui_style_json") or {}
    if isinstance(ui_style, dict) and ui_style.get("genre"):
        try:
            from design_studio.genres import is_valid_genre
            if not is_valid_genre(ui_style["genre"]):
                ui_style = {**ui_style, "genre": ""}
        except Exception:
            pass

    tpl = ListTemplate(
        name=str(data["name"])[:120],
        icon=str(data.get("icon") or "bi-card-checklist")[:40],
        description=str(data.get("description") or ""),
        content_type=ctype,
        custom_fields_json=data.get("custom_fields_json") or [],
        allowed_statuses_json=data.get("allowed_statuses_json") or [],
        ui_style_json=ui_style,
        summary_rule_json=data.get("summary_rule_json") or {},
    )
    flags = data.get("flags") or {}
    for f in FIELD_DEFS:
        if f["key"] in flags:
            setattr(tpl, f["key"], bool(flags[f["key"]]))
    tpl.save()
    messages.success(request, f"Vorlage „{tpl.name}“ importiert.")
    return redirect("list_kit:builder_edit", pk=tpl.id)


@staff_member_required
@require_POST
def builder_delete_view(request, pk):
    tpl = get_object_or_404(ListTemplate, pk=pk)
    if tpl.is_system:
        messages.warning(request, "System-Vorlagen können nicht gelöscht werden.")
        return redirect("list_kit:builder_list")
    if tpl.collections.exists():
        messages.warning(request, "Vorlage wird noch von Sammlungen verwendet.")
        return redirect("list_kit:builder_list")
    name = tpl.name
    tpl.delete()
    messages.success(request, f"Vorlage „{name}“ gelöscht.")
    return redirect("list_kit:builder_list")


def _render_entry_pdf(template_name: str, ctx: dict, filename: str) -> HttpResponse:
    from django.template.loader import render_to_string
    html = render_to_string(template_name, ctx)
    try:
        from io import BytesIO
        from xhtml2pdf import pisa
        buf = BytesIO()
        status = pisa.CreatePDF(html, dest=buf, encoding="utf-8")
        if not status.err:
            resp = HttpResponse(buf.getvalue(), content_type="application/pdf")
            resp["Content-Disposition"] = f'inline; filename="{filename}"'
            return resp
    except Exception:
        pass
    return HttpResponse(html)


@login_required
def entry_protocol_pdf_view(request, pk, entry_id):
    col = get_object_or_404(Collection, pk=pk)
    if not _user_can_access_collection(request.user, col):
        return HttpResponseForbidden()
    entry = get_object_or_404(Entry, pk=entry_id, collection=col)
    return _render_entry_pdf(
        "list_kit/protocol_pdf.html",
        {"collection": col, "entry": entry, "data": entry.custom_data_json or {}},
        f"protokoll-{entry.id}.pdf",
    )


@login_required
def entry_press_pdf_view(request, pk, entry_id):
    col = get_object_or_404(Collection, pk=pk)
    if not _user_can_access_collection(request.user, col):
        return HttpResponseForbidden()
    entry = get_object_or_404(Entry, pk=entry_id, collection=col)
    from django.conf import settings as django_settings
    org_name = getattr(django_settings, "DESIGN_STUDIO_APP_NAME", "Kunstverein")
    contact_email = ""
    from django.apps import apps
    if apps.is_installed("site_kit"):
        try:
            from site_kit.models import SiteConfig
            cfg = SiteConfig.get_solo()
            org_name = cfg.site_name or org_name
            contact_email = cfg.contact_email
        except Exception:
            pass
    return _render_entry_pdf(
        "list_kit/press_pdf.html",
        {"collection": col, "entry": entry, "org_name": org_name, "contact_email": contact_email},
        f"pressemitteilung-{entry.id}.pdf",
    )
