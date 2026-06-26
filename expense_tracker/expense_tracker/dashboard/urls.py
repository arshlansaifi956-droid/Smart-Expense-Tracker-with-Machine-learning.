from django.urls import path
from .views import (
    dashboard_view, expenses_view, receipts_view, 
    categories_view, budgets_view, reports_view, export_expenses,
    alerts_view, groups_view, search_view, settings_view,
    delete_expense, smart_parse_view, calendar_view,
    ocr_upload_view, ocr_confirm_view, chatbot_api_view
)

urlpatterns = [
    path('', dashboard_view, name='dashboard'),
    path('expenses/', expenses_view, name='expenses'),
    path('expenses/delete/<int:pk>/', delete_expense, name='delete_expense'),
    path('receipts/', receipts_view, name='receipts'),
    path('ocr-upload/', ocr_upload_view, name='ocr_upload'),
    path('ocr-confirm/', ocr_confirm_view, name='ocr_confirm'),
    path('categories/', categories_view, name='categories'),
    path('budgets/', budgets_view, name='budgets'),
    path('reports/', reports_view, name='reports'),
    path('reports/export/', export_expenses, name='export_expenses'),
    path('alerts/', alerts_view, name='alerts'),
    path('groups/', groups_view, name='groups'),
    path('search/', search_view, name='search'),
    path('settings/', settings_view, name='settings'),
    path('calendar/', calendar_view, name='calendar'),
    path('smart-parse/', smart_parse_view, name='smart_parse'),
    path('chatbot-api/', chatbot_api_view, name='chatbot_api'),
]
