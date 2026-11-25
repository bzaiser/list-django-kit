from django.urls import path

from . import views

app_name = "list_kit"

urlpatterns = [
    path("", views.collection_list_view, name="collection_list"),
    path("create/", views.collection_create_view, name="collection_create"),
    path("builder/", views.builder_list_view, name="builder_list"),
    path("builder/new/", views.builder_edit_view, name="builder_create"),
    path("builder/import/", views.builder_import_view, name="builder_import"),
    path("builder/<int:pk>/", views.builder_edit_view, name="builder_edit"),
    path("builder/<int:pk>/export/", views.builder_export_view, name="builder_export"),
    path("builder/<int:pk>/delete/", views.builder_delete_view, name="builder_delete"),
    path("<uuid:pk>/", views.collection_detail_view, name="collection_detail"),
    path("<uuid:pk>/pdf/", views.collection_pdf_view, name="collection_pdf"),
    path("<uuid:pk>/export.csv", views.collection_export_csv_view, name="collection_export_csv"),
    path("submit/<uuid:pk>/", views.public_submit_view, name="public_submit"),
    path("<uuid:pk>/delete/", views.collection_delete_view, name="collection_delete"),
    path("<uuid:pk>/entries/add/", views.entry_save_view, name="entry_add"),
    path("<uuid:pk>/entries/<int:entry_id>/edit/", views.entry_save_view, name="entry_edit"),
    path("<uuid:pk>/entries/<int:entry_id>/duplicate/", views.entry_duplicate_view, name="entry_duplicate"),
    path("<uuid:pk>/entries/<int:entry_id>/confirm/", views.entry_confirm_view, name="entry_confirm"),
    path("<uuid:pk>/entries/<int:entry_id>/create-person/", views.entry_create_person_view, name="entry_create_person"),
    path("<uuid:pk>/entries/<int:entry_id>/protocol.pdf", views.entry_protocol_pdf_view, name="entry_protocol_pdf"),
    path("<uuid:pk>/entries/<int:entry_id>/press.pdf", views.entry_press_pdf_view, name="entry_press_pdf"),
    path("<uuid:pk>/entries/<int:entry_id>/toggle/", views.entry_toggle_view, name="entry_toggle"),
    path("<uuid:pk>/entries/<int:entry_id>/images/<int:image_id>/toggle/", views.entry_image_toggle_view, name="entry_image_toggle"),
    path("<uuid:pk>/entries/<int:entry_id>/delete/", views.entry_delete_view, name="entry_delete"),
]
