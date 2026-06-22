import json
import os
import urllib.request
import urllib.error

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

def _get_api_key():
    """Retrieves API key from config.json or environment variables."""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            return config.get("GROQ_API_KEY", "")
        except Exception:
            pass
    return os.environ.get("GROQ_API_KEY", "")

def get_ai_optimization(resume_text, jd_text):
    """
    Calls the Groq API using Llama-3.1-8b-instant to optimize the candidate's resume
    against the provided Job Description.
    """
    api_key = _get_api_key()
    if not api_key:
        return {
            'success': False,
            'error': 'API key not configured. Please check config.json.'
        }
        
    system_prompt = (
        "You are Be10x - ATS Resume Generator. Your task is to rewrite, optimize, "
        "and clean the candidate's resume to match the Job Description. Add missing keywords naturally, "
        "rephrase achievements using the STAR method, and output the optimized resume in a clean, "
        "professional, and ATS-friendly format. "
        "Output ONLY the raw optimized resume text in markdown format. Do not add any conversational intro or outro."
    )
    
    user_prompt = f"JOB DESCRIPTION:\n{jd_text}\n\nCANDIDATE RESUME:\n{resume_text}"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(GROQ_API_URL, data=data, headers=headers, method="POST")
        
        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = response.read().decode('utf-8')
            res_json = json.loads(res_data)
            
            ai_content = res_json['choices'][0]['message']['content'].strip()
            return {
                'success': True,
                'optimized_resume': ai_content
            }
            
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode('utf-8')
        print(f"Groq API HTTP Error: {e.code} - {error_msg}")
        return {
            'success': False,
            'error': f"API Error: {e.code}"
        }
    except Exception as e:
        print(f"Error calling Groq API: {e}")
        return {
            'success': False,
            'error': str(e)
        }
