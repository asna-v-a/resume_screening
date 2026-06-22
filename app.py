import os
import json
import csv
from io import StringIO
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, make_response, session
from werkzeug.utils import secure_filename

# Import custom utilities
from utils.db import (
    init_db, save_job_description, get_all_job_descriptions, get_job_description,
    save_resume, get_resumes_for_jd, get_resume_by_id, get_analytics_for_jd, delete_resume_record,
    get_db_connection, get_jds_with_stats, delete_job_description_record, update_resume_suggestions
)
from utils.parser import parse_resume
from utils.matcher import calculate_match_score, match_keywords, predict_selection
from utils.ats_checker import check_ats_compatibility
from utils.optimizer import get_ai_optimization

# Create Flask App
app = Flask(__name__)
app.secret_key = 'super_secret_session_key_for_resume_screener'

# Configure upload folder
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB Upload Limit

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize database on startup
init_db()

# Pre-run NLTK setup to prevent route delays
import nltk
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

# Inject active page for navbar highlight
@app.context_processor
def inject_active_page():
    return dict(active_page=None)

# -----------------------------------------------------
# 1. Page Routes
# -----------------------------------------------------

@app.route('/')
def home():
    """Home page containing the Job Description definition and file upload drag-and-drop form."""
    jds = get_all_job_descriptions()
    return render_template('index.html', jds=jds, active_page='home')


@app.route('/upload')
def upload_page():
    """Redirect upload page request to home, as upload is now integrated on the homepage."""
    return redirect(url_for('home'))


@app.route('/dashboard')
def dashboard_page():
    """Redirect legacy dashboard request to rankings."""
    return redirect(url_for('rankings_page'))


@app.route('/rankings')
def rankings_page():
    """Renders candidate rankings and screening results for the active session."""
    # Check if a specific JD ID is passed in query parameters
    jd_id = request.args.get('jd_id')
    if jd_id:
        try:
            session['current_jd_id'] = int(jd_id)
        except ValueError:
            pass
            
    # Retrieve the active session JD ID
    active_jd_id = session.get('current_jd_id')
    
    if not active_jd_id:
        flash("No active screening session. Paste a Job Description and upload resumes to start.", "info")
        return redirect(url_for('home'))
        
    selected_jd = get_job_description(active_jd_id)
    if not selected_jd:
        flash("Screening session details not found.", "error")
        session.pop('current_jd_id', None)
        return redirect(url_for('home'))
        
    # Fetch resumes matching this JD
    raw_resumes = get_resumes_for_jd(active_jd_id)
    resumes = []
    
    for r in raw_resumes:
        r_dict = dict(r)
        
        # Parse suggestions JSON
        try:
            sugg = json.loads(r_dict['suggestions'])
        except Exception:
            sugg = {'issues': [], 'suggestions': []}
            
        r_dict['issues_list'] = sugg.get('issues', [])
        r_dict['issues_count'] = len(sugg.get('issues', []))
        
        # Determine missing keywords
        _, missing_kws = match_keywords(r_dict['raw_text'], selected_jd['description'])
        r_dict['missing_keywords'] = missing_kws
        
        # Predict selection status using local ML model
        r_dict['predicted_selection'] = predict_selection(r_dict['raw_text'], selected_jd['description'])
        
        # Set ATS Status
        score = r_dict['ats_score']
        if score >= 80:
            r_dict['ats_status'] = 'Optimized'
            r_dict['ats_status_class'] = 'badge-success'
        elif score >= 60:
            r_dict['ats_status'] = 'Needs Review'
            r_dict['ats_status_class'] = 'badge-warning'
        else:
            r_dict['ats_status'] = 'Action Required'
            r_dict['ats_status_class'] = 'badge-danger'
            
        resumes.append(r_dict)
        
    # Sort automatically by Match Score descending (primary) and ATS Score descending (secondary)
    resumes.sort(key=lambda x: (x['match_score'], x['ats_score']), reverse=True)
    analytics = get_analytics_for_jd(active_jd_id)
    
    return render_template(
        'dashboard.html',
        selected_jd=selected_jd,
        resumes=resumes,
        analytics=analytics,
        active_page='rankings'
    )


@app.route('/history')
def history_page():
    """Renders the list of previous screenings/sessions."""
    jds = get_jds_with_stats()
    return render_template('history.html', jds=jds, active_page='history')


@app.route('/history/open/<int:jd_id>')
def history_open(jd_id):
    """Sets a past JD session as active in session and redirects to rankings page."""
    session['current_jd_id'] = jd_id
    return redirect(url_for('rankings_page'))


@app.route('/delete-jd/<int:jd_id>', methods=['POST'])
def delete_jd(jd_id):
    """Deletes a past Job Description session, associated candidates, and physical uploads."""
    try:
        # Delete JD and get paths of associated resume files
        filepaths = delete_job_description_record(jd_id)
        
        # Clean physical files
        for path in filepaths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"Error removing file {path}: {e}")
                    
        # If the active session is deleted, clear it from session storage
        if session.get('current_jd_id') == jd_id:
            session.pop('current_jd_id', None)
            
        flash("Screening session and all associated files deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting screening session: {e}", "error")
        
    return redirect(url_for('history_page'))


@app.route('/candidate/<int:resume_id>')
def candidate_results(resume_id):
    """Detailed parsing, keyword gaps, and ATS health suggestions for one candidate."""
    resume = get_resume_by_id(resume_id)
    if not resume:
        flash("Candidate record not found.", "error")
        return redirect(url_for('dashboard_page'))
        
    jd = get_job_description(resume['jd_id'])
    
    # Load suggestions JSON back to Python dict
    suggestions_dict = {}
    try:
        suggestions_dict = json.loads(resume['suggestions'])
    except Exception:
        suggestions_dict = {'issues': [], 'suggestions': []}
        
    # Re-calculate keyword match dynamically for detail report
    matching_keywords, missing_keywords = match_keywords(resume['raw_text'], jd['description'])
    
    # Predict selection status using local model
    predicted_selection = predict_selection(resume['raw_text'], jd['description'])
    
    return render_template(
        'results.html',
        resume=resume,
        jd=jd,
        suggestions_dict=suggestions_dict,
        matching_keywords=matching_keywords,
        missing_keywords=missing_keywords,
        predicted_selection=predicted_selection,
        active_page='dashboard'
    )


# -----------------------------------------------------
# 2. Sequential Upload and Processing APIs
# -----------------------------------------------------

@app.route('/api/save-jd', methods=['POST'])
def save_jd():
    """API endpoint: Saves Job Description details."""
    title = request.form.get('job_title')
    description = request.form.get('job_description')
    
    if not title or not description:
        return jsonify({'success': False, 'error': 'Missing title or description.'}), 400
        
    try:
        jd_id = save_job_description(title, description)
        return jsonify({'success': True, 'jd_id': jd_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/upload-resume', methods=['POST'])
def upload_resume():
    """API endpoint: Accepts a single file, processes it, and saves candidate stats."""
    jd_id = request.form.get('jd_id')
    file = request.files.get('resume')
    
    if not jd_id or not file or file.filename == '':
        return jsonify({'success': False, 'error': 'Missing Job Description ID or file upload.'}), 400
        
    # Validate extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.pdf', '.docx', '.txt']:
        return jsonify({'success': False, 'error': 'Unsupported file format.'}), 400
        
    try:
        # Save file securely to uploads folder
        filename = secure_filename(file.filename)
        # Handle duplicate filenames in uploads folder by prepending unique tags
        import uuid
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        # 1. Parse File details
        parsed = parse_resume(filepath)
        
        # 2. Get JD details for comparison
        jd = get_job_description(jd_id)
        if not jd:
            return jsonify({'success': False, 'error': 'Associated Job Description not found.'}), 404
            
        # 3. Match Resume against JD (TF-IDF Cosine Similarity)
        match_score = calculate_match_score(parsed['raw_text'], jd['description'])
        matching_kws, missing_kws = match_keywords(parsed['raw_text'], jd['description'])
        
        # 4. Check ATS Compatibility Health
        ats_results = check_ats_compatibility(
            parsed['raw_text'], 
            parsed['sections'], 
            matching_kws, 
            missing_kws, 
            filepath
        )
        
        # 5. Save candidate records to SQLite DB
        resume_id = save_resume(
            jd_id=int(jd_id),
            filename=filename,
            filepath=filepath,
            candidate_name=parsed['name'],
            candidate_email=parsed['email'],
            skills=parsed['skills'],
            education=parsed['education'],
            experience=parsed['experience'],
            raw_text=parsed['raw_text'],
            match_score=match_score,
            ats_score=ats_results['ats_score'],
            suggestions={
                'issues': ats_results['issues'],
                'suggestions': ats_results['suggestions']
            }
        )
        
        return jsonify({
            'success': True, 
            'resume_id': resume_id,
            'candidate_name': parsed['name']
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/optimize-resume/<int:resume_id>', methods=['POST'])
def optimize_resume_api(resume_id):
    """API endpoint: Tailors/optimizes candidate resume text using Groq Llama-3.1 API and saves it in DB."""
    resume = get_resume_by_id(resume_id)
    if not resume:
        return jsonify({'success': False, 'error': 'Candidate record not found.'}), 404
        
    jd = get_job_description(resume['jd_id'])
    if not jd:
        return jsonify({'success': False, 'error': 'Associated Job Description not found.'}), 404
        
    # Load suggestions JSON
    try:
        suggestions_dict = json.loads(resume['suggestions'])
    except Exception:
        suggestions_dict = {'issues': [], 'suggestions': []}
        
    # If already generated, return cached optimized resume
    if 'optimized_resume' in suggestions_dict and suggestions_dict['optimized_resume']:
        return jsonify({
            'success': True,
            'optimized_resume': suggestions_dict['optimized_resume']
        })
        
    # Call Groq API
    result = get_ai_optimization(resume['raw_text'], jd['description'])
    if not result.get('success'):
        return jsonify({'success': False, 'error': result.get('error', 'Failed to call Groq AI.')}), 500
        
    # Update suggestions dict and save in DB
    suggestions_dict['optimized_resume'] = result['optimized_resume']
    try:
        update_resume_suggestions(resume_id, suggestions_dict)
        return jsonify({
            'success': True,
            'optimized_resume': result['optimized_resume']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f"Failed to save optimized resume to database: {str(e)}"}), 500


# -----------------------------------------------------
# 3. Actions / Utility Routes
# -----------------------------------------------------

@app.route('/delete-resume/<int:resume_id>', methods=['POST'])
def delete_resume(resume_id):
    """Deletes a candidate record from the DB and removes their physical file."""
    try:
        # Delete from DB and get file path
        filepath = delete_resume_record(resume_id)
        
        # Physically delete the uploaded file
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            
        flash("Candidate record and uploaded file deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting record: {e}", "error")
        
    return redirect(request.referrer or url_for('dashboard_page'))


@app.route('/export-csv/<int:jd_id>')
def export_csv(jd_id):
    """Exports candidate leaderboard ranking for a JD as a downloadable CSV."""
    jd = get_job_description(jd_id)
    if not jd:
        flash("Job Description not found.", "error")
        return redirect(url_for('dashboard_page'))
        
    resumes = get_resumes_for_jd(jd_id)
    
    # Create an in-memory string buffer for CSV
    si = StringIO()
    cw = csv.writer(si)
    
    # Write header
    cw.writerow(['Rank', 'Candidate Name', 'Email', 'JD Match Score (%)', 'ATS Score (%)', 'Weighted Score (60/40)', 'Extracted Skills', 'Parsed Date'])
    
    # Write candidate rows
    for index, resume in enumerate(resumes, start=1):
        cw.writerow([
            index,
            resume['candidate_name'],
            resume['candidate_email'],
            resume['match_score'],
            resume['ats_score'],
            round(resume['final_score'], 1),
            resume['skills'],
            resume['uploaded_at']
        ])
        
    output = make_response(si.getvalue())
    clean_title = secure_filename(jd['title'].lower().replace(' ', '_'))
    output.headers["Content-Disposition"] = f"attachment; filename=leaderboard_{clean_title}.csv"
    output.headers["Content-type"] = "text/csv"
    return output


@app.route('/upload-files', methods=['POST'])
def upload_files():
    """Non-AJAX fallback route if JS Sequential Uploader fails (supports direct posts)."""
    # This route is a backup structure
    flash("Browser JavaScript is required for optimized sequential uploads.", "error")
    return redirect(url_for('upload_page'))


# Run application
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
