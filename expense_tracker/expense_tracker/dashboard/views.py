from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import Budget, Expense, Receipt, FamilyGroup, Alert, UserPreference, GroupExpense
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.db import models
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse, HttpResponse
from .nlp_utils import parse_expense_text
import requests
import json
import os
import re
import calendar
import csv
import io
import pandas as pd
from datetime import date, datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# Force disable experimental Paddle features to prevent "Unimplemented" crashes
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_new_ir_api"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"

from PIL import Image

from .ocr_engine import ReceiptOCR
from .ml_engine import FinancialAdvisor

# Global OCR engine instance (lazy loaded)
_ocr_engine = None

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = ReceiptOCR()
    return _ocr_engine

def check_budget_alerts(user):
    """Checks if user has exceeded or is close to budget and creates alerts."""
    budget_obj, created = Budget.objects.get_or_create(user=user, defaults={'amount': 0})
    if budget_obj.amount <= 0:
        return

    total_expenses = Expense.objects.filter(user=user).aggregate(Sum('amount'))['amount__sum'] or 0
    percent_used = (total_expenses / budget_obj.amount) * 100

    if percent_used >= 100:
        Alert.objects.get_or_create(
            user=user,
            title="Budget Exceeded!",
            type='budget_exceeded',
            defaults={'message': f"You have spent ₹{total_expenses:,.2f}, which exceeds your monthly budget of ₹{budget_obj.amount:,.2f}."}
        )
    elif percent_used >= 80:
        Alert.objects.get_or_create(
            user=user,
            title="Budget Warning (80%)",
            type='budget_warning',
            defaults={'message': f"You have used {percent_used:.1f}% of your monthly budget (₹{total_expenses:,.2f} of ₹{budget_obj.amount:,.2f})."}
        )

# Normalized Icon Map for consistency
NORMALIZED_ICON_MAP = {
    'Food': 'lunch_dining',
    'Transport': 'directions_car',
    'Shopping': 'shopping_bag',
    'Bills': 'receipt_long',
    'Health': 'health_and_safety',
    'Entertainment': 'theater_comedy',
    'Travel': 'flight',
    'Fuel': 'local_gas_station',
    'Salary': 'account_balance_wallet',
    'Groceries': 'shopping_cart',
    'Gifts': 'redeem',
    'Pets': 'pets',
    'Children': 'child_care',
    'Home': 'home',
    'Rent': 'apartment',
    'Utilities': 'bolt',
    'Insurance': 'shield',
    'Investments': 'show_chart',
    'Income': 'arrow_circle_down',
    'Education': 'school',
    'Others': 'more_horiz',
    'Uncategorized': 'inventory_2'
}

@login_required
def dashboard_view(request):
    # Check for alerts whenever dashboard is loaded
    check_budget_alerts(request.user)
    
    budget_obj, created = Budget.objects.get_or_create(user=request.user, defaults={'amount': 40000})
    
    user_expenses = Expense.objects.filter(user=request.user).order_by('-date')
    total_val = user_expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    
    if not user_expenses.exists():
        # Create some sample data if none exists
        today = timezone.now()
        Expense.objects.create(user=request.user, name="Domino's Pizza", category='Food', amount=520.00, icon='lunch_dining', date=today - timedelta(days=1))
        Expense.objects.create(user=request.user, name='Uber Ride', category='Transport', amount=315.00, icon='directions_car', date=today - timedelta(days=2))
        Expense.objects.create(user=request.user, name='Dmart', category='Shopping', amount=1240.00, icon='shopping_bag', date=today - timedelta(days=3))
        Expense.objects.create(user=request.user, name='Electricity Bill', category='Bills', amount=1150.00, icon='receipt_long', date=today - timedelta(days=4))
        user_expenses = Expense.objects.filter(user=request.user).order_by('-date')
        total_val = user_expenses.aggregate(Sum('amount'))['amount__sum'] or 0

    recent_list = []
    now_local = timezone.localtime(timezone.now())
    for exp in user_expenses[:4]:
        exp_local = timezone.localtime(exp.date)
        recent_list.append({
            'icon': exp.icon,
            'name': exp.name,
            'category': exp.category,
            'amount': f"{exp.amount:,.2f}",
            'time': exp_local.strftime("%d %b %Y") if exp_local.date() < now_local.date() else "Today, " + exp_local.strftime("%I:%M %p")
        })

    # Top Vendors
    vendor_data = {}
    for exp in user_expenses:
        vendor_data[exp.name] = vendor_data.get(exp.name, 0) + float(exp.amount)
    
    sorted_vendors = sorted(vendor_data.items(), key=lambda x: x[1], reverse=True)[:5]
    top_vendors_list = [{'name': name, 'amount': f"{amt:,.2f}"} for name, amt in sorted_vendors]

    # Expenses by Category (Donut Chart)
    category_totals = Expense.objects.filter(user=request.user).values('category').annotate(total=Sum('amount')).order_by('-total')
    cat_colors = ['#5470ff', '#4ade80', '#fbbf24', '#a78bfa', '#f87171', '#38bdf8', '#fb7185']
    
    cat_list = []
    for i, c in enumerate(category_totals):
        cat_list.append({
            'label': c['category'],
            'data': float(c['total']),
            'color': cat_colors[i % len(cat_colors)]
        })

    # Expenses Over Time (Line Chart - Last 7 Days)
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=6)
    
    daily_expenses = Expense.objects.filter(
        user=request.user, 
        date__date__range=[start_date, end_date]
    ).annotate(day=TruncDate('date')).values('day').annotate(total=Sum('amount')).order_by('day')

    # Create a complete list of last 7 days even if no expenses exist for some days
    daily_map = {d['day']: float(d['total']) for d in daily_expenses}
    time_labels = []
    time_data = []
    
    for i in range(7):
        curr_day = start_date + timedelta(days=i)
        time_labels.append(curr_day.strftime("%d %b"))
        time_data.append(daily_map.get(curr_day, 0.0))

    remaining_budget_raw = float(budget_obj.amount) - float(total_val)
    unread_alerts_count = Alert.objects.filter(user=request.user, is_read=False).count()

# ML Powered Insights - Triggering reload
    advisor = FinancialAdvisor(request.user)
    predicted_spending = advisor.get_spending_forecast()
    savings_recommendations = advisor.get_savings_recommendations()

    context = {
        'user_name': request.user.username,
        'total_expenses': f"{total_val:,.2f}",
        'expense_increase': '12.5%',
        'month_budget': f"{budget_obj.amount:,.2f}",
        'remaining_budget': f"{abs(remaining_budget_raw):,.2f}",
        'remaining_budget_raw': remaining_budget_raw,
        'budget_used_percent': int((float(total_val) / float(budget_obj.amount)) * 100) if budget_obj.amount > 0 else 0,
        'total_transactions': user_expenses.count(),
        'transactions_increase': 8,
        'budget_alerts': unread_alerts_count,
        'recent_expenses': recent_list,
        'top_vendors': top_vendors_list,
        'expenses_by_category': {
            'labels': [c['label'] for c in cat_list],
            'data': [c['data'] for c in cat_list],
            'colors': [c['color'] for c in cat_list],
            'items': cat_list
        },
        'expenses_over_time': {
            'labels': time_labels,
            'data': time_data
        },
        'predicted_spending': f"{predicted_spending:,.2f}" if predicted_spending else None,
        'savings_recommendations': savings_recommendations
    }
    return render(request, 'dashboard/index.html', context)

@login_required
def smart_parse_view(request):
    """API endpoint to parse natural language expense input."""
    if request.method == 'POST':
        import json
        text = request.POST.get('text')
        if not text:
            try:
                data = json.loads(request.body)
                text = data.get('text')
            except:
                pass
                
        if text:
            parsed = parse_expense_text(text)
            
            if parsed['amount'] > 0:
                Expense.objects.create(
                    user=request.user,
                    name=parsed['name'],
                    category=parsed['category'],
                    amount=parsed['amount'],
                    date=parsed['date'],
                    icon=NORMALIZED_ICON_MAP.get(parsed['category'], 'payments')
                )
                return JsonResponse({
                    'status': 'success',
                    'message': f"Added ₹{parsed['amount']} for {parsed['name']} in {parsed['category']}",
                    'data': parsed
                })
            else:
                return JsonResponse({'status': 'error', 'message': "Could not find an amount in your input."})
                
    return JsonResponse({'status': 'error', 'message': "Invalid request."})

@login_required
def ocr_upload_view(request):
    """Step 1: Upload and Extract. Returns JSON for user to review."""
    if request.method == 'POST' and request.FILES.get('receipt_image'):
        image_file = request.FILES['receipt_image']
        receipt = Receipt.objects.create(user=request.user, image=image_file)
        
        try:
            engine = get_ocr_engine()
            data = engine.process_image(receipt.image.path)
            
            if not data.raw_text:
                return JsonResponse({'status': 'error', 'message': "No text detected."})
            
            receipt.extracted_text = data.raw_text
            receipt.save()
            
            # Use data from the robust engine
            name = data.merchant or "Unknown Vendor"
            try:
                amount = float(data.total.replace(",", "")) if data.total else 0.0
            except:
                amount = 0.0
            
            # Smart Categorization: Use Merchant Name + Address for NLP focus
            context_text = f"{name} {data.address}"
            parsed = parse_expense_text(context_text if name != "Unknown Vendor" else data.raw_text)
            
            category = parsed['category'] if parsed['category'] != 'Others' else 'Uncategorized'
            
            # If OCR failed to find amount but NLP found something in text
            if amount == 0 and parsed['amount'] > 0:
                amount = parsed['amount']
            
            return JsonResponse({
                'status': 'success',
                'data': {
                    'receipt_id': receipt.id,
                    'merchant': name,
                    'amount': amount,
                    'category': category,
                    'date': data.date or timezone.now().strftime('%Y-%m-%d'),
                    'warnings': data.warnings,
                    'confidence': data.confidence_scores
                }
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

@login_required
def ocr_confirm_view(request):
    """Step 2: Confirm and Save the extracted data."""
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            receipt_id = data.get('receipt_id')
            name = data.get('merchant', 'Unknown Vendor')
            amount = data.get('amount', 0.0)
            category = data.get('category', 'Others')
            date_str = data.get('date')

            # Create the expense
            expense = Expense.objects.create(
                user=request.user,
                name=name,
                category=category,
                amount=amount,
                icon=NORMALIZED_ICON_MAP.get(category, 'document_scanner')
            )
            
            # If date is provided, update it (Expense.date is auto_now_add by default, 
            # might need to change model if we want to support past dates from receipts)
            if date_str:
                try:
                    # Try common formats
                    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d %b %Y'):
                        try:
                            expense.date = datetime.strptime(date_str, fmt)
                            expense.save()
                            break
                        except:
                            continue
                except:
                    pass

            return JsonResponse({'status': 'success', 'message': 'Expense saved successfully!'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
            
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

@login_required
def receipts_view(request):
    if request.method == 'POST' and request.FILES.get('receipt_image'):
        image_file = request.FILES['receipt_image']
        receipt = Receipt.objects.create(user=request.user, image=image_file)
        
        try:
            # Use the new robust ReceiptOCR engine
            engine = get_ocr_engine()
            data = engine.process_image(receipt.image.path)
            
            if not data.raw_text:
                messages.error(request, "OCR could not extract any text from the image. Please try a clearer photo.")
                return redirect('dashboard')
            
            receipt.extracted_text = data.raw_text
            receipt.save()
            
            # Use data from the robust engine
            name = data.merchant or "Unknown Vendor"
            
            # Try to convert total to float
            try:
                amount = float(data.total.replace(",", "")) if data.total else 0.0
            except (ValueError, AttributeError):
                amount = 0.0
            
            # Use NLP parsing as a secondary check for category and name fallback
            parsed = parse_expense_text(data.raw_text)
            
            if name == "Unknown Vendor" and parsed['name'] != "New Expense":
                name = parsed['name']
            
            if amount == 0 and parsed['amount'] > 0:
                amount = parsed['amount']
                
            category = parsed['category'] if parsed['category'] != 'Others' else 'Uncategorized'
            
            Expense.objects.create(
                user=request.user,
                name=name,
                category=category,
                amount=amount,
                icon=NORMALIZED_ICON_MAP.get(category, 'document_scanner')
            )
            
            if data.warnings:
                for warning in data.warnings:
                    messages.warning(request, f"OCR Warning: {warning}")

            messages.success(request, f"Receipt scanned! Vendor: {name}, Amount: ₹ {amount:,.2f}")
        except Exception as e:
            messages.error(request, f"OCR Processing failed: {str(e)}")
            import traceback
            traceback.print_exc()
            
        return redirect('dashboard')
    
    receipts = Receipt.objects.filter(user=request.user).order_by('-uploaded_at')
    return render(request, 'dashboard/receipts.html', {'receipts': receipts})

@login_required
def budgets_view(request):
    budget_obj, created = Budget.objects.get_or_create(user=request.user, defaults={'amount': 0})
    if request.method == 'POST':
        amount = request.POST.get('amount')
        if amount:
            budget_obj.amount = amount
            budget_obj.save()
            messages.success(request, f"Monthly budget updated to ₹ {float(amount):,.2f}")
            return redirect('dashboard')
    return render(request, 'dashboard/budgets.html', {'budget': budget_obj})

@login_required
def expenses_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        category = request.POST.get('category')
        amount = request.POST.get('amount')
        
        if name and category and amount:
            Expense.objects.create(
                user=request.user,
                name=name,
                category=category,
                amount=amount,
                icon=NORMALIZED_ICON_MAP.get(category, 'payments')
            )
            messages.success(request, f"Expense '{name}' added successfully!")
            return redirect('expenses')

    expenses = Expense.objects.filter(user=request.user).order_by('-date')
    return render(request, 'dashboard/expenses.html', {'expenses': expenses})

@login_required
def delete_expense(request, pk):
    if request.method == 'POST':
        expense = Expense.objects.filter(user=request.user, pk=pk).first()
        if expense:
            expense.delete()
            messages.success(request, "Expense deleted.")
    return redirect('expenses')

@login_required
def categories_view(request):
    # Aggregate expenses by category name only to avoid duplicates
    categories_qs = Expense.objects.filter(user=request.user).values('category').annotate(
        total_amount=Sum('amount'),
        transaction_count=Count('id')
    ).order_by('-total_amount')
    
    total_all = sum(c['total_amount'] for c in categories_qs) or 0
    
    categories_data = []
    for cat in categories_qs:
        name = cat['category']
        categories_data.append({
            'category': name,
            'icon': NORMALIZED_ICON_MAP.get(name, 'payments'),
            'total_amount': cat['total_amount'],
            'transaction_count': cat['transaction_count'],
            'percentage': int((cat['total_amount'] / total_all * 100)) if total_all > 0 else 0
        })

    context = {
        'categories': categories_data,
        'total_all': f"{total_all:,.2f}"
    }
    return render(request, 'dashboard/categories.html', context)

@login_required
def reports_view(request):
    # Date Filtering
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if start_date_str and end_date_str:
        from datetime import datetime
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    else:
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)

    expenses = Expense.objects.filter(user=request.user, date__range=[start_date, end_date])
    
    # Analytics
    total_spent = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    avg_daily = float(total_spent) / 30
    transaction_count = expenses.count()
    
    # Chart Data: Category Breakdown
    cat_breakdown = expenses.values('category').annotate(total=Sum('amount')).order_by('-total')
    
    # Chart Data: Daily Trend
    daily_trend = expenses.annotate(day=TruncDate('date')).values('day').annotate(total=Sum('amount')).order_by('day')
    
    # NEW: Day of Week Distribution
    # 1=Sunday, 2=Monday, ..., 7=Saturday in many DBs, but Django __week_day is similar
    dow_data = [0.0] * 7
    dow_labels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    for exp in expenses:
        # date.weekday() returns 0 for Monday, 6 for Sunday
        # Let's map it to Sun=0
        idx = (exp.date.weekday() + 1) % 7 
        dow_data[idx] += float(exp.amount)

    # NEW: Weekday vs Weekend
    weekday_spent = 0.0
    weekend_spent = 0.0
    for exp in expenses:
        if exp.date.weekday() < 5: # 0-4 is Mon-Fri
            weekday_spent += float(exp.amount)
        else:
            weekend_spent += float(exp.amount)

    # NEW: Financial Health Score Calculation
    budget_obj = Budget.objects.filter(user=request.user).first()
    score = 0
    
    # 1. Budget Adherence (Max 60 points)
    if budget_obj and budget_obj.amount > 0:
        percent_spent = (float(total_spent) / float(budget_obj.amount)) * 100
        if percent_spent <= 80:
            score += 60
        elif percent_spent <= 100:
            score += 40
        elif percent_spent <= 120:
            score += 20
        else:
            score += 5
    else:
        score += 30 # Neutral if no budget set
        
    # 2. Transaction Frequency (Max 20 points)
    if transaction_count >= 15:
        score += 20
    elif transaction_count >= 5:
        score += 10
    else:
        score += 5
        
    # 3. Category Diversity (Max 20 points)
    unique_categories = len(set([e['category'] for e in cat_breakdown]))
    if unique_categories >= 5:
        score += 20
    elif unique_categories >= 3:
        score += 10
    else:
        score += 5

    if score >= 80:
        health_status = "Excellent"
        health_color = "#10b981" # Green
    elif score >= 60:
        health_status = "Good"
        health_color = "#3b82f6" # Blue
    elif score >= 40:
        health_status = "Fair"
        health_color = "#fbbf24" # Yellow
    else:
        health_status = "Poor"
        health_color = "#ef4444" # Red

    context = {
        'total_spent': f"{total_spent:,.2f}",
        'avg_daily': f"{avg_daily:,.2f}",
        'transaction_count': transaction_count,
        'health_score': score,
        'health_status': health_status,
        'health_color': health_color,
        'cat_labels': [c['category'] for c in cat_breakdown],
        'cat_data': [float(c['total']) for c in cat_breakdown],
        'trend_labels': [d['day'].strftime('%d %b') for d in daily_trend],
        'trend_data': [float(d['total']) for d in daily_trend],
        'dow_labels': dow_labels,
        'dow_data': dow_data,
        'wv_labels': ['Weekday', 'Weekend'],
        'wv_data': [weekday_spent, weekend_spent],
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
    }
    return render(request, 'dashboard/reports.html', context)

@login_required
def alerts_view(request):
    if request.method == 'POST':
        Alert.objects.filter(user=request.user).update(is_read=True)
        messages.success(request, "All alerts marked as read.")
        return redirect('alerts')

    alerts = Alert.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'dashboard/alerts.html', {'alerts': alerts})

@login_required
def groups_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_group':
            group_name = request.POST.get('group_name')
            if group_name:
                new_group = FamilyGroup.objects.create(name=group_name, created_by=request.user)
                new_group.members.add(request.user)
                messages.success(request, f"Group '{group_name}' created successfully!")
        
        elif action == 'add_member':
            group_id = request.POST.get('group_id')
            username = request.POST.get('username')
            try:
                group = FamilyGroup.objects.get(id=group_id, members=request.user)
                user_to_add = User.objects.get(username=username)
                group.members.add(user_to_add)
                messages.success(request, f"User '{username}' added to group '{group.name}'!")
            except FamilyGroup.DoesNotExist:
                messages.error(request, "Group not found.")
            except User.DoesNotExist:
                messages.error(request, f"User '{username}' not found.")

        elif action == 'add_group_expense':
            group_id = request.POST.get('group_id')
            description = request.POST.get('description')
            amount = request.POST.get('amount')
            try:
                group = FamilyGroup.objects.get(id=group_id, members=request.user)
                GroupExpense.objects.create(
                    group=group,
                    paid_by=request.user,
                    description=description,
                    amount=amount
                )
                messages.success(request, f"Group expense '{description}' added!")
            except FamilyGroup.DoesNotExist:
                messages.error(request, "Error adding expense.")

        elif action == 'delete_group':
            group_id = request.POST.get('group_id')
            try:
                group = FamilyGroup.objects.get(id=group_id, created_by=request.user)
                group_name = group.name
                group.delete()
                messages.success(request, f"Group '{group_name}' has been deleted.")
            except FamilyGroup.DoesNotExist:
                messages.error(request, "Only the creator can delete the group.")

        return redirect('groups')

    user_groups = request.user.family_groups.all()
    groups_data = []
    
    for group in user_groups:
        members = group.members.all()
        n_members = members.count()
        group_expenses = group.expenses.all().order_by('-date')
        total_spent = group_expenses.aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Balance Logic
        # balance[user] = total_paid_by_user - (total_group_spent / n_members)
        balances = []
        share_per_person = float(total_spent) / n_members if n_members > 0 else 0
        
        for member in members:
            paid_by_member = group_expenses.filter(paid_by=member).aggregate(Sum('amount'))['amount__sum'] or 0
            net_balance = float(paid_by_member) - share_per_person
            balances.append({
                'username': member.username,
                'paid': paid_by_member,
                'balance': net_balance,
                'abs_balance': abs(net_balance),
                'is_user': member == request.user
            })
            
        groups_data.append({
            'id': group.id,
            'name': group.name,
            'total_expense': total_spent,
            'members': members,
            'expenses': group_expenses[:5], # Last 5 expenses
            'balances': balances,
            'is_creator': group.created_by == request.user
        })
        
    return render(request, 'dashboard/groups.html', {'groups': groups_data})

@login_required
def search_view(request):
    query = request.GET.get('q', '')
    results = []
    if query:
        results = Expense.objects.filter(
            Q(user=request.user) & (
                Q(name__icontains=query) | 
                Q(category__icontains=query) |
                Q(amount__icontains=query)
            )
        ).order_by('-date')
    
    return render(request, 'dashboard/search.html', {'query': query, 'results': results})

@login_required
def calendar_view(request):
    # Get year and month from query params or use current
    now = timezone.localtime(timezone.now())
    year = int(request.GET.get('year', now.year))
    month = int(request.GET.get('month', now.month))
    
    if month > 12:
        year += 1
        month = 1
    elif month < 1:
        year -= 1
        month = 12
        
    cal = calendar.monthcalendar(year, month)
    month_name = calendar.month_name[month]
    
    # Get expenses for this month
    start_date = timezone.make_aware(datetime(year, month, 1))
    if month == 12:
        end_date = timezone.make_aware(datetime(year + 1, 1, 1))
    else:
        end_date = timezone.make_aware(datetime(year, month + 1, 1))
        
    expenses = Expense.objects.filter(
        user=request.user,
        date__range=[start_date, end_date]
    )
    
    # Group expenses by day
    daily_expenses = {}
    for exp in expenses:
        day = timezone.localtime(exp.date).day
        if day not in daily_expenses:
            daily_expenses[day] = {'total': 0, 'items': []}
        daily_expenses[day]['total'] += float(exp.amount)
        daily_expenses[day]['items'].append({
            'name': exp.name,
            'amount': float(exp.amount),
            'category': exp.category
        })
    
    import json
    daily_expenses_json = json.dumps(daily_expenses)
        
    # Prev/Next month links
    prev_month = month - 1
    prev_year = year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
        
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year += 1

    context = {
        'year': year,
        'month': month,
        'month_name': month_name,
        'calendar': cal,
        'daily_expenses': daily_expenses,
        'daily_expenses_json': daily_expenses_json,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'today': now.day if now.year == year and now.month == month else 0,
        'title': 'Calendar',
        'icon': 'calendar_month'
    }
    return render(request, 'dashboard/calendar.html', context)

@login_required
def settings_view(request):
    preferences, created = UserPreference.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_profile':
            username = request.POST.get('username')
            email = request.POST.get('email')
            if username:
                request.user.username = username
                request.user.email = email
                request.user.save()
                messages.success(request, "Profile updated successfully!")
        
        elif action == 'update_preferences':
            currency = request.POST.get('currency', 'INR')
            notifications = request.POST.get('notifications') == 'on'
            dark_mode = request.POST.get('dark_mode') == 'on'
            voice_enabled = request.POST.get('voice_enabled') == 'on'
            voice_language = request.POST.get('voice_language', 'en-US')
            
            # Get multiple enabled languages
            enabled_langs = request.POST.getlist('enabled_langs')
            enabled_langs_str = ",".join(enabled_langs) if enabled_langs else 'en-US'

            symbols = {'INR': '₹', 'USD': '$', 'EUR': '€', 'GBP': '£'}

            preferences.currency = currency
            preferences.currency_symbol = symbols.get(currency, '₹')
            preferences.notifications_enabled = notifications
            preferences.dark_mode = dark_mode
            preferences.voice_assistant_enabled = voice_enabled
            preferences.voice_assistant_language = voice_language
            preferences.enabled_languages = enabled_langs_str
            preferences.save()
            messages.success(request, "App preferences updated!")
        elif action == 'reset_data':
            Expense.objects.filter(user=request.user).delete()
            Receipt.objects.filter(user=request.user).delete()
            Alert.objects.filter(user=request.user).delete()
            budget_obj = Budget.objects.filter(user=request.user).first()
            if budget_obj:
                budget_obj.amount = 0
                budget_obj.save()
            messages.success(request, "All expense data has been reset.")
        return redirect('settings')

    context = {
        'user': request.user,
        'preferences': preferences,
        'enabled_langs_list': preferences.enabled_languages.split(',') if preferences.enabled_languages else [],
        'available_languages': [
            {'code': 'en-US', 'name': 'English'},
            {'code': 'hi-IN', 'name': 'Hindi'},
            {'code': 'gu-IN', 'name': 'Gujarati'},
            {'code': 'mr-IN', 'name': 'Marathi'},
            {'code': 'es-ES', 'name': 'Spanish'},
            {'code': 'fr-FR', 'name': 'French'},
            {'code': 'de-DE', 'name': 'German'},
        ],
        'title': 'Settings',
        'icon': 'settings'
    }
    return render(request, 'dashboard/settings.html', context)

@login_required
def export_expenses(request):
    export_format = request.GET.get('format', 'csv')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    else:
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)

    # Use make_aware for consistent comparison
    if timezone.is_naive(start_date):
        start_date = timezone.make_aware(start_date)
    if timezone.is_naive(end_date):
        end_date = timezone.make_aware(end_date)

    expenses = Expense.objects.filter(user=request.user, date__range=[start_date, end_date]).order_by('-date')

    if export_format == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="expense_report_{start_date.date()}_{end_date.date()}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Date', 'Name', 'Category', 'Amount'])
        for exp in expenses:
            writer.writerow([exp.date.strftime('%Y-%m-%d'), exp.name, exp.category, exp.amount])
        return response

    elif export_format == 'pdf':
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="expense_report_{start_date.date()}_{end_date.date()}.pdf"'
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        # Title
        elements.append(Paragraph(f"Expense Report: {start_date.date()} to {end_date.date()}", styles['Title']))
        elements.append(Spacer(1, 12))

        # Table Data
        data = [['Date', 'Name', 'Category', 'Amount']]
        total = 0
        for exp in expenses:
            data.append([exp.date.strftime('%Y-%m-%d'), exp.name, exp.category, f"Rs. {exp.amount:,.2f}"])
            total += float(exp.amount)
        
        data.append(['', '', 'TOTAL', f"Rs. {total:,.2f}"])

        t = Table(data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(t)
        doc.build(elements)
        
        response.write(buffer.getvalue())
        buffer.close()
        return response

    elif export_format == 'ledger':
        # Using Excel as Ledger format
        data_list = list(expenses.values('date', 'name', 'category', 'amount'))
        df = pd.DataFrame(data_list)
        if not df.empty:
            # Convert timezone aware dates to naive for Excel
            if 'date' in df.columns:
                df['date'] = df['date'].apply(lambda x: x.replace(tzinfo=None) if hasattr(x, 'replace') else x)
        
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="expense_ledger_{start_date.date()}_{end_date.date()}.xlsx"'
        
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Expenses')
        return response

    return redirect('reports')

@login_required
def chatbot_api_view(request):
    """Backend AI endpoint strictly using Llama 3.1 via Ollama."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'})

    try:
        data = json.loads(request.body)
        prompt = data.get('prompt', '')
        context = data.get('context', '')
    except:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'})

    # Strictly Llama 3.1 via Ollama
    try:
        response = requests.post(
            'http://localhost:11434/api/chat',
            json={
                'model': 'llama3.1:8b',
                'messages': [
                    {'role': 'system', 'content': 'You are a helpful financial assistant for a personal expense tracker app. Use the provided context to answer questions about the user\'s spending.'},
                    {'role': 'user', 'content': f"{context}\n\nUser query: {prompt}"}
                ],
                'stream': False
            },
            timeout=60 # Llama can be slow on some hardware
        )
        
        if response.status_code == 200:
            res_data = response.json()
            return JsonResponse({'status': 'success', 'response': res_data['message']['content']})
        else:
            return JsonResponse({'status': 'error', 'message': f'Ollama returned error: {response.status_code}'})
            
    except requests.exceptions.ConnectionError:
        return JsonResponse({'status': 'error', 'message': 'Ollama is not running. Please start Ollama with "ollama run llama3.1:8b"'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
