from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    if dictionary:
        return dictionary.get(key)
    return None

@register.filter
def split(value, arg):
    return value.split(arg)

@register.filter
def category_icon_class(category):
    if not category:
        return 'icon-other'
    category = str(category).lower()
    if 'food' in category or 'dining' in category or 'restaurant' in category:
        return 'icon-food'
    elif 'transport' in category or 'car' in category or 'taxi' in category:
        return 'icon-transport'
    elif 'shopping' in category or 'mall' in category:
        return 'icon-shopping'
    elif 'bill' in category or 'invoice' in category:
        return 'icon-bills'
    elif 'entertainment' in category or 'movie' in category or 'party' in category:
        return 'icon-entertainment'
    elif 'health' in category or 'medical' in category or 'doctor' in category:
        return 'icon-health'
    elif 'education' in category or 'school' in category or 'book' in category:
        return 'icon-education'
    elif 'travel' in category or 'flight' in category or 'hotel' in category:
        return 'icon-travel'
    elif 'fuel' in category or 'gas' in category or 'petrol' in category:
        return 'icon-fuel'
    elif 'salary' in category or 'bonus' in category:
        return 'icon-salary'
    elif 'groceries' in category or 'market' in category or 'mart' in category:
        return 'icon-groceries'
    elif 'gift' in category or 'present' in category:
        return 'icon-gifts'
    elif 'pet' in category or 'dog' in category or 'cat' in category:
        return 'icon-pets'
    elif 'child' in category or 'baby' in category or 'kid' in category:
        return 'icon-children'
    elif 'home' in category or 'house' in category:
        return 'icon-home'
    elif 'rent' in category or 'apartment' in category:
        return 'icon-rent'
    elif 'utilities' in category or 'electricity' in category or 'water' in category:
        return 'icon-utilities'
    elif 'insurance' in category:
        return 'icon-insurance'
    elif 'invest' in category or 'stock' in category or 'saving' in category:
        return 'icon-investments'
    elif 'income' in category or 'profit' in category:
        return 'icon-income'
    return 'icon-other'
