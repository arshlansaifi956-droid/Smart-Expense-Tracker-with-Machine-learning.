import spacy
from transformers import pipeline
import re
from datetime import datetime, timedelta

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except:
    # Fallback if model not found
    nlp = None

# Initialize transformers pipeline for zero-shot classification
classifier = None

def get_classifier():
    global classifier
    if classifier is None:
        # This will download the model on first use (~300MB)
        classifier = pipeline("zero-shot-classification", model="typeform/distilbert-base-uncased-mnli")
    return classifier

def parse_expense_text(text):
    """
    Parses natural language text to extract expense details.
    Example: "Yesterday I spent 300 on groceries"
    """
    result = {
        'amount': 0.0,
        'category': 'Others',
        'name': 'New Expense',
        'date': datetime.now(),
        'success': False
    }
    
    if not text:
        return result

    # 1. Extract Amount using Regex
    amount_match = re.search(r'(\d+(?:\.\d{1,2})?)', text)
    if amount_match:
        result['amount'] = float(amount_match.group(1))

    # 2. Extract Date using spaCy or simple logic
    doc = nlp(text) if nlp else None
    if doc:
        for ent in doc.ents:
            if ent.label_ == "DATE":
                date_text = ent.text.lower()
                if "yesterday" in date_text or "कल" in date_text:
                    result['date'] = datetime.now() - timedelta(days=1)
                elif "today" in date_text or "आज" in date_text:
                    result['date'] = datetime.now()
                break
    else:
        # Fallback for Hindi if spaCy fails
        if "कल" in text:
            result['date'] = datetime.now() - timedelta(days=1)
        elif "आज" in text:
            result['date'] = datetime.now()

    # 3. Categorization using Transformers
    categories = [
        'Food', 'Transport', 'Shopping', 'Bills', 'Entertainment', 
        'Health', 'Education', 'Travel', 'Fuel', 'Salary', 
        'Groceries', 'Gifts', 'Pets', 'Children', 'Home', 
        'Rent', 'Utilities', 'Insurance', 'Investments', 'Income', 'Others'
    ]
    
    # Handle Hindi text translation/mapping for classifier focus
    hindi_mappings = {
        'किराना': 'groceries', 'सब्जी': 'vegetables', 'किराया': 'rent',
        'बस': 'bus', 'खाना': 'food', 'दवा': 'medicine', 'बिजली': 'electricity'
    }
    
    clean_text = text
    for hi, en in hindi_mappings.items():
        if hi in text:
            clean_text += f" {en}"

    if amount_match:
        clean_text = clean_text.replace(amount_match.group(0), "")

    try:
        clf = get_classifier()
        classification = clf(clean_text, candidate_labels=categories)
        result['category'] = classification['labels'][0]
        
        # 4. Extract Name (the "what")
        result['name'] = text.strip()[:50]
        result['success'] = True
    except Exception as e:
        print(f"NLP Error: {e}")
        # Simple keyword fallback
        lower_text = text.lower()
        if any(kw in lower_text for kw in ['grocery', 'food', 'खाना', 'किराना', 'सब्जी']):
            result['category'] = 'Food'
        elif any(kw in lower_text for kw in ['uber', 'ride', 'bus', 'taxi', 'बस', 'किराया']):
            result['category'] = 'Transport'
        result['success'] = True

    return result

def transcribe_hindi_audio(audio_file_path):
    """Transcribes Hindi audio using SpeechRecognition."""
    import speech_recognition as sr
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_file_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="hi-IN")
            return text
    except Exception as e:
        print(f"Speech Recognition Error: {e}")
        return None
