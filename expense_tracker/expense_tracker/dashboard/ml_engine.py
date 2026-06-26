import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from django.db import models
from django.db.models import Sum
from .models import Expense, Budget
from sklearn.ensemble import RandomForestRegressor
from django.utils import timezone

class FinancialAdvisor:
    """ML-powered advisor for expense prediction and savings recommendations."""
    
    def __init__(self, user):
        self.user = user

    def get_spending_forecast(self):
        """Predicts spending for the next 7 days based on historical trends using Random Forest."""
        expenses = Expense.objects.filter(user=self.user).order_by('date')
        if not expenses.exists() or expenses.count() < 10:
            return None

        # Prepare data for Random Forest
        data = []
        for exp in expenses:
            data.append({
                'date': exp.date.date(),
                'amount': float(exp.amount)
            })
        
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        
        # Group by date to get daily totals
        daily_df = df.groupby('date')['amount'].sum().reset_index()
        
        # FEATURE ENGINEERING: Extract time patterns
        daily_df['day_of_week'] = daily_df['date'].dt.dayofweek
        daily_df['day_of_month'] = daily_df['date'].dt.day
        daily_df['is_weekend'] = daily_df['day_of_week'].apply(lambda x: 1 if x >= 5 else 0)
        
        # Use features that capture patterns, not just a linear trend
        X = daily_df[['day_of_week', 'day_of_month', 'is_weekend']].values
        y = daily_df['amount'].values
        
        # Initialize and train Random Forest Regressor
        # n_estimators=100 is a good default, random_state for consistency
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X, y)
        
        # Predict for the next 7 days (Upcoming Week)
        last_date = daily_df['date'].max()
        
        total_predicted = 0
        for i in range(1, 8): # Next 7 days
            future_date = last_date + timedelta(days=i)
            # Create features for the future date
            future_features = [
                future_date.weekday(), 
                future_date.day, 
                1 if future_date.weekday() >= 5 else 0
            ]
            prediction = model.predict([future_features])[0]
            total_predicted += max(0, prediction) 
            
        return round(total_predicted, 2)

    def get_savings_recommendations(self):
        """Generates actionable savings tips based on spending patterns."""
        recommendations = []
        
        # Get data for last 30 days vs previous 30 days
        now = timezone.now()
        last_30_start = now - timedelta(days=30)
        prev_30_start = now - timedelta(days=60)
        
        current_expenses = Expense.objects.filter(
            user=self.user, 
            date__range=[last_30_start, now]
        ).values('category').annotate(total=Sum('amount'))
        
        previous_expenses = Expense.objects.filter(
            user=self.user, 
            date__range=[prev_30_start, last_30_start]
        ).values('category').annotate(total=Sum('amount'))
        
        prev_map = {item['category']: float(item['total']) for item in previous_expenses}
        
        for item in current_expenses:
            cat = item['category']
            current_total = float(item['total'])
            prev_total = prev_map.get(cat, 0)
            
            if prev_total > 0:
                increase_pct = ((current_total - prev_total) / prev_total) * 100
                if increase_pct > 20:
                    recommendations.append({
                        'category': cat,
                        'message': f"Your spending in '{cat}' increased by {increase_pct:.1f}% compared to last month. Consider reviewing these costs.",
                        'priority': 'High' if increase_pct > 50 else 'Medium'
                    })
        
        # Budget adherence tip
        budget_obj = Budget.objects.filter(user=self.user).first()
        if budget_obj and budget_obj.amount > 0:
            total_this_month = Expense.objects.filter(
                user=self.user, 
                date__month=now.month, 
                date__year=now.year
            ).aggregate(Sum('amount'))['amount__sum'] or 0
            
            if float(total_this_month) > float(budget_obj.amount) * 0.9:
                recommendations.append({
                    'category': 'General',
                    'message': "You've used over 90% of your budget. Focus on essential spending only for the rest of the month.",
                    'priority': 'Critical'
                })
        
        # Frequency analysis
        top_category = Expense.objects.filter(user=self.user).values('category').annotate(
            count=models.Count('id')
        ).order_by('-count').first()
        
        if top_category and top_category['count'] > 10:
            recommendations.append({
                'category': top_category['category'],
                'message': f"You make frequent transactions in '{top_category['category']}'. Try bulk purchasing or planning to reduce costs.",
                'priority': 'Low'
            })

        return recommendations[:3] # Return top 3 tips
