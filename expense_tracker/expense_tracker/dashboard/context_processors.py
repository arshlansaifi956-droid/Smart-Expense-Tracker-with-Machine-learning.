from .models import UserPreference, Alert
from django.utils import timezone
import calendar
import holidays
from datetime import datetime, timedelta

def user_preferences(request):
    if request.user.is_authenticated:
        preferences, created = UserPreference.objects.get_or_create(user=request.user)
        unread_alerts_count = Alert.objects.filter(user=request.user, is_read=False).count()
        
        # Current time data
        now = timezone.localtime(timezone.now())
        today = now.date()
        year = today.year
        month = today.month
        
        # Use python-holidays for India (includes state specific if needed, here we use generic)
        in_holidays = holidays.India(years=year)
        
        # Generate Calendar Grid (Weeks and Days)
        cal = calendar.Calendar(firstweekday=6) # Sunday start like the image
        month_days_it = cal.monthdayscalendar(year, month)
        
        calendar_grid = []
        upcoming_festivals = []
        four_days_later = today + timedelta(days=4)
        
        for week in month_days_it:
            week_data = []
            for d in week:
                if d == 0:
                    week_data.append({'day': '', 'is_today': False, 'holiday': None})
                else:
                    date_obj = datetime(year, month, d).date()
                    h_name = in_holidays.get(date_obj)
                    
                    day_info = {
                        'day': d,
                        'is_today': date_obj == today,
                        'holiday': h_name,
                        'is_past': date_obj < today
                    }
                    week_data.append(day_info)
                    
                    # Notification check
                    if h_name and today <= date_obj <= four_days_later:
                        upcoming_festivals.append({
                            'name': h_name,
                            'date': date_obj.strftime('%d %b'),
                            'days_left': (date_obj - today).days
                        })
            calendar_grid.append(week_data)
        
        return {
            'user_prefs': preferences,
            'unread_alerts_count': unread_alerts_count,
            'calendar_grid': calendar_grid,
            'upcoming_festivals': upcoming_festivals,
            'current_month_name': now.strftime('%B'),
            'current_year': year,
            'today_date': today.strftime('%d %b %Y')
        }
    return {
        'user_prefs': None, 
        'unread_alerts_count': 0,
        'calendar_grid': [],
        'upcoming_festivals': [],
        'current_month_name': '',
        'current_year': '',
        'today_date': ''
    }
