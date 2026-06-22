import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database.db')

def get_db_connection():
    """Establishes and returns a database connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema if tables do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create Job Descriptions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS job_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create Resumes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jd_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            candidate_name TEXT,
            candidate_email TEXT,
            skills TEXT,
            education TEXT,
            experience TEXT,
            raw_text TEXT,
            match_score REAL,
            ats_score REAL,
            suggestions TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (jd_id) REFERENCES job_descriptions (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

def save_job_description(title, description):
    """Saves a new job description and returns its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO job_descriptions (title, description) VALUES (?, ?)',
        (title, description)
    )
    conn.commit()
    jd_id = cursor.lastrowid
    conn.close()
    return jd_id

def get_all_job_descriptions():
    """Retrieves all job descriptions, sorted by latest first."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM job_descriptions ORDER BY created_at DESC')
    jds = cursor.fetchall()
    conn.close()
    return jds

def get_job_description(jd_id):
    """Retrieves a single job description by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM job_descriptions WHERE id = ?', (jd_id,))
    jd = cursor.fetchone()
    conn.close()
    return jd

def save_resume(jd_id, filename, filepath, candidate_name, candidate_email, skills, education, experience, raw_text, match_score, ats_score, suggestions):
    """Saves a parsed resume with its screening results."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Convert lists/dicts to strings (comma-separated or JSON)
    skills_str = ", ".join(skills) if isinstance(skills, list) else str(skills)
    suggestions_json = json.dumps(suggestions) if isinstance(suggestions, (dict, list)) else str(suggestions)
    
    cursor.execute('''
        INSERT INTO resumes (
            jd_id, filename, filepath, candidate_name, candidate_email, 
            skills, education, experience, raw_text, match_score, ats_score, suggestions
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        jd_id, filename, filepath, candidate_name, candidate_email,
        skills_str, education, experience, raw_text, match_score, ats_score, suggestions_json
    ))
    
    conn.commit()
    resume_id = cursor.lastrowid
    conn.close()
    return resume_id

def get_resumes_for_jd(jd_id):
    """Retrieves all resumes associated with a specific JD, sorted by combined score first."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Rank by: 60% match_score + 40% ats_score
    cursor.execute('''
        SELECT *, (match_score * 0.6 + ats_score * 0.4) as final_score 
        FROM resumes 
        WHERE jd_id = ? 
        ORDER BY final_score DESC
    ''', (jd_id,))
    resumes = cursor.fetchall()
    conn.close()
    return resumes

def get_resume_by_id(resume_id):
    """Retrieves details for a specific resume."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM resumes WHERE id = ?', (resume_id,))
    resume = cursor.fetchone()
    conn.close()
    return resume

def get_analytics_for_jd(jd_id):
    """Calculates basic analytics for a specific JD."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total count and average scores
    cursor.execute('''
        SELECT 
            COUNT(*) as total_resumes,
            AVG(match_score) as avg_match_score,
            AVG(ats_score) as avg_ats_score
        FROM resumes 
        WHERE jd_id = ?
    ''', (jd_id,))
    stats = cursor.fetchone()
    
    # Top candidate
    cursor.execute('''
        SELECT candidate_name, match_score, ats_score, (match_score * 0.6 + ats_score * 0.4) as final_score
        FROM resumes 
        WHERE jd_id = ? 
        ORDER BY final_score DESC 
        LIMIT 1
    ''', (jd_id,))
    top_candidate = cursor.fetchone()
    
    conn.close()
    
    return {
        'total_resumes': stats['total_resumes'] if stats and stats['total_resumes'] else 0,
        'avg_match_score': round(stats['avg_match_score'], 1) if stats and stats['avg_match_score'] else 0.0,
        'avg_ats_score': round(stats['avg_ats_score'], 1) if stats and stats['avg_ats_score'] else 0.0,
        'top_candidate': top_candidate['candidate_name'] if top_candidate else "N/A",
        'top_score': round(top_candidate['final_score'], 1) if top_candidate else 0.0
    }

def delete_resume_record(resume_id):
    """Deletes a resume record by ID from the database and returns filepath for physical deletion."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT filepath FROM resumes WHERE id = ?', (resume_id,))
    row = cursor.fetchone()
    filepath = row['filepath'] if row else None
    
    if filepath:
        cursor.execute('DELETE FROM resumes WHERE id = ?', (resume_id,))
        conn.commit()
    conn.close()
    return filepath

def update_resume_suggestions(resume_id, suggestions_dict):
    """Updates the suggestions column for a specific resume record."""
    conn = get_db_connection()
    cursor = conn.cursor()
    suggestions_json = json.dumps(suggestions_dict)
    cursor.execute('UPDATE resumes SET suggestions = ? WHERE id = ?', (suggestions_json, resume_id))
    conn.commit()
    conn.close()

def get_jds_with_stats():
    """Retrieves all job descriptions along with aggregated candidate statistics."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            jd.id, 
            jd.title, 
            jd.description, 
            jd.created_at,
            COUNT(r.id) as candidate_count,
            AVG(r.match_score) as avg_match,
            AVG(r.ats_score) as avg_ats,
            MAX(r.match_score) as top_match
        FROM job_descriptions jd
        LEFT JOIN resumes r ON jd.id = r.jd_id
        GROUP BY jd.id
        ORDER BY jd.created_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_job_description_record(jd_id):
    """Deletes a job description and all associated resume records. Returns list of filepaths to clean up physically."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get filepaths for physical deletion
    cursor.execute('SELECT filepath FROM resumes WHERE jd_id = ?', (jd_id,))
    rows = cursor.fetchall()
    filepaths = [row['filepath'] for row in rows if row['filepath']]
    
    # Delete resume rows and JD row
    cursor.execute('DELETE FROM resumes WHERE jd_id = ?', (jd_id,))
    cursor.execute('DELETE FROM job_descriptions WHERE id = ?', (jd_id,))
    
    conn.commit()
    conn.close()
    return filepaths
