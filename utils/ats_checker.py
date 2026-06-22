import os

def check_ats_compatibility(resume_text, parsed_sections, matching_keywords, missing_keywords, filepath):
    """
    Computes an ATS score (0 to 100) based on four components:
    1. Keyword Match (40 pts max)
    2. Essential Sections (30 pts max)
    3. Resume Length / Word Count (15 pts max)
    4. Formatting & File Checks (15 pts max)
    
    Returns a dict with 'ats_score', 'issues' list, and 'suggestions' list.
    """
    score = 0
    issues = []
    suggestions = []
    
    # ---------------------------------------------------------
    # 1. Keyword Match (Max 40 points)
    # ---------------------------------------------------------
    total_keywords = len(matching_keywords) + len(missing_keywords)
    if total_keywords > 0:
        keyword_match_ratio = len(matching_keywords) / total_keywords
        keyword_score = keyword_match_ratio * 40
        score += keyword_score
        
        if keyword_match_ratio < 0.4:
            issues.append("Low keyword overlap with the Job Description.")
            # Suggest missing keywords
            top_missing = missing_keywords[:5]
            suggestions.append(f"Integrate key missing terms from the job description: {', '.join(top_missing)}.")
        elif keyword_match_ratio < 0.7:
            top_missing = missing_keywords[:3]
            suggestions.append(f"Consider adding these relevant keywords to improve your score: {', '.join(top_missing)}.")
    else:
        # Fallback if JD has no detectable keywords
        score += 40
        
    # ---------------------------------------------------------
    # 2. Section Presence (Max 30 points)
    # ---------------------------------------------------------
    # Look for 'Skills', 'Education', 'Experience' sections in parsed_sections
    essential_sections = {
        'skills': ('Skills', 10),
        'education': ('Education', 10),
        'experience': ('Experience', 10)
    }
    
    for key, (name, points) in essential_sections.items():
        content = parsed_sections.get(key, '').strip()
        # Ensure section exists and contains more than just a couple of characters
        if len(content) > 30:
            score += points
        else:
            issues.append(f"Missing or extremely brief '{name}' section.")
            suggestions.append(f"Create a dedicated and clearly labeled '{name}' section to help ATS parser identify your details.")
            
    # ---------------------------------------------------------
    # 3. Resume Length & Word Count (Max 15 points)
    # ---------------------------------------------------------
    words = resume_text.split()
    word_count = len(words)
    
    if 400 <= word_count <= 1200:
        score += 15
    elif 250 <= word_count < 400:
        score += 10
        suggestions.append("Your resume is slightly short. Expand on your professional accomplishments and project details.")
    elif 1200 < word_count <= 2000:
        score += 10
        suggestions.append("Your resume is quite long. Keeping it to a concise 1-2 pages (under 1200 words) helps human reviewers and ATS scanners.")
    else:
        score += 5
        issues.append(f"Atypical word count detected ({word_count} words).")
        if word_count < 250:
            suggestions.append("Your resume is extremely short. Ensure you include descriptions of your roles and bullet points detailing technologies used.")
        else:
            suggestions.append("Your resume is very wordy. Condense your bullet points and remove outdated or irrelevant experiences.")
            
    # ---------------------------------------------------------
    # 4. Formatting and OCR Checks (Max 15 points)
    # ---------------------------------------------------------
    has_tables = False
    has_images = False
    is_scanned = False
    
    ext = os.path.splitext(filepath)[1].lower()
    
    # Analyze formatting if file is a PDF
    if ext == '.pdf' and os.path.exists(filepath):
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                total_tables = 0
                total_images = 0
                for page in pdf.pages:
                    # Detect tables
                    tables = page.find_tables()
                    total_tables += len(tables)
                    
                    # Detect images
                    images = page.images
                    total_images += len(images)
                
                if total_tables > 0:
                    has_tables = True
                if total_images > 0:
                    has_images = True
        except Exception as e:
            # Fallback if pdfplumber encounters an issue
            print(f"pdfplumber checking failed: {e}")
            
    # Check if text is extremely short relative to file size (likely scanned image / OCR failure)
    if os.path.exists(filepath):
        filesize = os.path.getsize(filepath)
        # If file is larger than 100KB but has fewer than 60 words
        if filesize > 100 * 1024 and word_count < 60:
            is_scanned = True
            
    formatting_score = 15
    if is_scanned:
        formatting_score -= 15
        issues.append("Resume appears to be a scanned image (no selectable text).")
        suggestions.append("Crucial: Re-save or re-create your resume as a text-based PDF/DOCX. ATS systems cannot read text inside scanned image files.")
    else:
        if has_images:
            formatting_score -= 5
            issues.append("Images, logos, or complex graphics detected.")
            suggestions.append("Remove images, icons, and infographics. ATS scanners frequently fail to parse graphical components.")
        if has_tables:
            formatting_score -= 3
            suggestions.append("If using tables, ensure the structure is simple. Plain text, tabbed spacing, or bullet lists are much safer for older ATS models.")
            
    score += formatting_score
    
    # Bound the score between 0 and 100
    final_score = min(100, max(0, int(round(score))))
    
    if final_score == 100:
        suggestions.append("Excellent! Your resume formatting and content structure are highly optimized for modern ATS systems.")
        
    return {
        'ats_score': final_score,
        'issues': issues,
        'suggestions': suggestions
    }
