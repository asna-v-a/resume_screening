import re
import os
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import nltk
from nltk.corpus import stopwords
from utils.parser import extract_skills, get_nlp

def clean_text_for_similarity(text):
    """Cleans text for TF-IDF vectorization: lowercase, remove non-letters, remove stopwords."""
    text = re.sub(r'[^a-zA-Z\s]', ' ', str(text))
    text = text.lower()
    words = text.split()
    
    try:
        stop_words = set(stopwords.words('english'))
    except Exception:
        # Fallback in case stopwords aren't available
        stop_words = set(['i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours', 
                          'he', 'him', 'his', 'himself', 'she', 'her', 'hers', 'herself', 'it', 'its', 'itself', 
                          'they', 'them', 'their', 'theirs', 'themselves', 'what', 'which', 'who', 'whom', 
                          'this', 'that', 'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 
                          'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an', 'the', 'and', 
                          'but', 'if', 'or', 'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 
                          'about', 'against', 'between', 'into', 'through', 'during', 'before', 'after', 'above', 
                          'below', 'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again', 
                          'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 
                          'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 
                          'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', 'should', 'now'])
                          
    words = [word for word in words if word not in stop_words and len(word) > 2]
    return " ".join(words)

def calculate_match_score(resume_text, jd_text):
    """Computes TF-IDF Cosine Similarity percentage between resume and JD."""
    cleaned_resume = clean_text_for_similarity(resume_text)
    cleaned_jd = clean_text_for_similarity(jd_text)
    
    if not cleaned_resume or not cleaned_jd:
        return 0.0
        
    vectorizer = TfidfVectorizer()
    try:
        tfidf_matrix = vectorizer.fit_transform([cleaned_resume, cleaned_jd])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        # Return percentage rounded to 1 decimal place
        return round(float(similarity * 100), 1)
    except Exception as e:
        print(f"Error calculating similarity: {e}")
        return 0.0

def extract_keywords_from_jd(jd_text):
    """Extracts important keywords (skills + nouns + noun chunks) from the JD using spaCy."""
    spacy_nlp = get_nlp()
    
    # 1. Extract explicit skills from our database in the JD
    jd_skills = set(extract_skills(jd_text))
    
    # 2. Extract key nouns and proper nouns from the JD using spaCy POS
    doc = spacy_nlp(jd_text.lower())
    pos_keywords = set()
    for token in doc:
        # We target nouns, proper nouns, and adjectives (to capture descriptive requirements)
        if token.pos_ in ['NOUN', 'PROPN'] and not token.is_stop and len(token.text) > 2:
            pos_keywords.add(token.text)
            
    # 3. Extract short noun chunks (e.g. "project management", "software engineer")
    chunk_keywords = set()
    for chunk in doc.noun_chunks:
        clean_chunk = chunk.text.strip().lower()
        words = clean_chunk.split()
        # Keep chunks of 2-3 words that are relevant (exclude stopwords)
        if 1 < len(words) <= 3 and not any(w in spacy_nlp.Defaults.stop_words for w in words):
            # Clean up leading characters
            clean_chunk = re.sub(r'^[^a-z0-9]+|[^a-z0-9]+$', '', clean_chunk)
            if len(clean_chunk) > 3:
                chunk_keywords.add(clean_chunk)
                
    # Combine skills, individual nouns, and chunks
    all_jd_keywords = jd_skills.union(pos_keywords).union(chunk_keywords)
    
    # Filter out very generic stop/noise words that might pass POS tags
    noise_words = {'years', 'experience', 'candidate', 'role', 'team', 'work', 'skills', 'requirements', 
                   'ability', 'knowledge', 'position', 'responsibilities', 'development', 'design', 
                   'support', 'opportunity', 'company', 'business', 'project', 'projects', 'system',
                   'systems', 'job', 'description', 'tasks', 'duties', 'status', 'level', 'environment'}
    
    filtered_keywords = {kw for kw in all_jd_keywords if kw not in noise_words and len(kw) > 1}
    return sorted(list(filtered_keywords))

def match_keywords(resume_text, jd_text):
    """Identifies which Job Description keywords are present or missing in the resume."""
    jd_keywords = extract_keywords_from_jd(jd_text)
    resume_lower = resume_text.lower()
    
    matching_keywords = []
    missing_keywords = []
    
    for kw in jd_keywords:
        escaped_kw = re.escape(kw)
        # Handle word boundaries
        if kw in ['c++', 'c#']:
            pattern = rf'\b{escaped_kw}(?:\b|[^\w]|$)'
        elif kw.startswith('.'):
            pattern = rf'{escaped_kw}\b'
        else:
            pattern = rf'\b{escaped_kw}\b'
            
        # Match case-insensitively
        if re.search(pattern, resume_lower):
            matching_keywords.append(kw)
        else:
            missing_keywords.append(kw)
            
    return matching_keywords, missing_keywords

# Global placeholders for loaded model and vectorizer
_ML_MODEL = None
_ML_VECTORIZER = None

def _load_ml_model():
    global _ML_MODEL, _ML_VECTORIZER
    if _ML_MODEL is None or _ML_VECTORIZER is None:
        model_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'model')
        model_path = os.path.join(model_dir, 'model.pkl')
        vec_path = os.path.join(model_dir, 'vectorizer.pkl')
        
        if os.path.exists(model_path) and os.path.exists(vec_path):
            try:
                with open(model_path, 'rb') as f:
                    _ML_MODEL = pickle.load(f)
                with open(vec_path, 'rb') as f:
                    _ML_VECTORIZER = pickle.load(f)
            except Exception as e:
                print(f"Error loading local model files: {e}")
        else:
            print("Local ML model or vectorizer file not found.")

def predict_selection(resume_text, jd_text):
    """Predicts selection status (1 for Selected, 0 for Rejected) using the local RF model."""
    _load_ml_model()
    if _ML_MODEL is None or _ML_VECTORIZER is None:
        # Fallback to a threshold on cosine similarity match score if model is not loaded
        score = calculate_match_score(resume_text, jd_text)
        return 1 if score >= 40.0 else 0
        
    try:
        # Preprocess and clean text using the cleaning function logic
        cleaned_resume = clean_text_for_similarity(resume_text)
        cleaned_jd = clean_text_for_similarity(jd_text)
        combined = cleaned_resume + " " + cleaned_jd
        
        features = _ML_VECTORIZER.transform([combined])
        prediction = _ML_MODEL.predict(features)[0]
        return int(prediction)
    except Exception as e:
        print(f"Error during model prediction: {e}")
        return 0

