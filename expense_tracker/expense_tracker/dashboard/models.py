from django.db import models
from django.contrib.auth.models import User

class Budget(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    month = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s Budget - {self.amount}"

class Expense(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    icon = models.CharField(max_length=50, default='receipt')

    def __str__(self):
        return f"{self.name} - {self.amount}"

class Receipt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='receipts/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    extracted_text = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Receipt {self.id} for {self.user.username}"

class FamilyGroup(models.Model):
    name = models.CharField(max_length=255)
    members = models.ManyToManyField(User, related_name='family_groups')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_groups')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class GroupExpense(models.Model):
    group = models.ForeignKey(FamilyGroup, on_delete=models.CASCADE, related_name='expenses')
    paid_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='paid_group_expenses')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.description} in {self.group.name}"

class Alert(models.Model):
    ALERT_TYPES = (
        ('budget_warning', 'Budget Warning'),
        ('budget_exceeded', 'Budget Exceeded'),
        ('info', 'Information'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    message = models.TextField()
    type = models.CharField(max_length=20, choices=ALERT_TYPES, default='info')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} for {self.user.username}"

class UserPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    currency = models.CharField(max_length=10, default='INR')
    currency_symbol = models.CharField(max_length=5, default='₹')
    notifications_enabled = models.BooleanField(default=True)
    dark_mode = models.BooleanField(default=False)
    
    # Voice Assistant Settings
    voice_assistant_enabled = models.BooleanField(default=True)
    voice_assistant_language = models.CharField(max_length=10, default='en-US')
    enabled_languages = models.TextField(default='en-US,hi-IN')

    def __str__(self):
        return f"Preferences for {self.user.username}"
