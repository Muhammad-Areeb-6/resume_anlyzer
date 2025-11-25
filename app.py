import os
from flask import Flask, request, render_template, redirect, url_for
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import PyPDF2
import docx
import google.generativeai as genai
import re # Added for parsing the AI score

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

# Configure Gemini
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
except Exception as e:
    print(f"Error configuring Google Gemini API: {e}")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(filepath):
    text = ""
    with open(filepath, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += page.extract_text()
    return text

def extract_text_from_docx(filepath):
    doc = docx.Document(filepath)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

# --- EXISTING RULE-BASED SCORING (No Changes) ---
def score_resume(text):
    score = 0
    score_breakdown = {}
    
    action_verbs = ['developed', 'managed', 'led', 'created', 'implemented', 'achieved', 'analyzed']
    tech_keywords = ['python', 'java', 'flask', 'django', 'react', 'sql', 'aws', 'docker']
    
    if 'experience' in text.lower():
        score += 20
        score_breakdown['Experience Section'] = 20
    if 'education' in text.lower():
        score += 10
        score_breakdown['Education Section'] = 10
    if 'skills' in text.lower():
        score += 15
        score_breakdown['Skills Section'] = 15

    verb_count = sum(1 for verb in action_verbs if verb in text.lower())
    action_verb_score = min(verb_count * 5, 25)
    score += action_verb_score
    score_breakdown['Action Verbs'] = f"{action_verb_score} (Found {verb_count} verbs)"

    keyword_count = sum(1 for keyword in tech_keywords if keyword in text.lower())
    keyword_score = min(keyword_count * 4, 20)
    score += keyword_score
    score_breakdown['Technical Keywords'] = f"{keyword_score} (Found {keyword_count} keywords)"

    if len(text.split()) > 300:
        score += 10
        score_breakdown['Resume Length'] = 10
    
    score = min(score, 100)
    return score, score_breakdown

# --- EXISTING SUMMARY FUNCTION (No Changes) ---
def get_ai_summary_gemini(text):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        You are a professional HR manager. Summarize this resume text.
        Provide a summary, key strengths, and one suggestion.
        Resume Text: {text}
        """
        response = model.generate_content(prompt)
        return response.text if response.parts else "Error generating summary."
    except Exception as e:
        return f"Error: {e}"

# --- NEW ADVANCED AI SCORING FUNCTION ---
def get_ai_score_gemini(text):
    """Asks Gemini to score the resume 0-100 and give a reason."""
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # We ask for a specific format to make parsing easy
        prompt = f"""
        Act as a strict recruiter. Analyze the following resume text and give it a score out of 100.
        
        CRITERIA:
        - Clarity and formatting
        - Impact of descriptions
        - Relevance of skills
        
        OUTPUT FORMAT (Strictly follow this):
        SCORE: [Insert Number Here]
        REASON: [Insert a 1-2 sentence explanation for the score]
        
        Resume Text:
        {text}
        """
        
        response = model.generate_content(prompt)
        content = response.text if response.parts else "SCORE: 0\nREASON: AI Error"
        
        # Extract the score using Regex
        score_match = re.search(r'SCORE:\s*(\d+)', content)
        reason_match = re.search(r'REASON:\s*(.*)', content, re.DOTALL)
        
        ai_score = int(score_match.group(1)) if score_match else 0
        ai_reason = reason_match.group(1).strip() if reason_match else "Could not parse reasoning."
        
        return ai_score, ai_reason

    except Exception as e:
        print(f"AI Scoring Error: {e}")
        return 0, "Error connecting to AI scoring service."

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            if filename.lower().endswith('.pdf'):
                resume_text = extract_text_from_pdf(filepath)
            elif filename.lower().endswith('.docx'):
                resume_text = extract_text_from_docx(filepath)
            else:
                return redirect(request.url)
            
            os.remove(filepath)

            # 1. Always do Rule-Based Scoring
            rule_score, rule_breakdown = score_resume(resume_text)
            
            # 2. Always do AI Summary
            summary = get_ai_summary_gemini(resume_text)

            # 3. Conditionally do AI Scoring based on Checkbox
            ai_score = None
            ai_reason = None
            
            # In HTML forms, if a checkbox is unchecked, it sends nothing. 
            # If checked, it sends 'on' (or the value attribute).
            if request.form.get('enable_ai_scoring'):
                ai_score, ai_reason = get_ai_score_gemini(resume_text)

            results = {
                'rule_score': rule_score,
                'rule_breakdown': rule_breakdown,
                'summary': summary,
                'ai_score': ai_score,   # Will be None if checkbox is off
                'ai_reason': ai_reason
            }
            
            return render_template('index.html', results=results)

    return render_template('index.html', results=None)

if __name__ == '__main__':
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    app.run(debug=True)