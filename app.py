
from flask import Flask, render_template, request, redirect, url_for, session
import random
import sympy as sp
import gspread , os
from oauth2client.service_account import ServiceAccountCredentials
from gspread_formatting import *
from datetime import datetime


app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
x = sp.symbols('x')

def format_expr(expr):
    return str(expr).replace('**', '^').replace('*x', 'x').replace('*', '')

creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE")

def init_google_sheets():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]
    
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
    client = gspread.authorize(creds)
    sheet = client.open("Math Quiz Results").sheet1

    headers = ["Name", "Class", "Section", "Question", "User Answer", "Correct Answer", "Status", "Timestamp", "Score"]
    current_headers = sheet.row_values(1)
    if current_headers != headers:
        if current_headers:
            sheet.delete_row(1)
        sheet.insert_row(headers, 1)

    return sheet


sheet = None
client = None

def get_sheet():
    global sheet, client
    if sheet is None or client is None:
        try:
            sheet, client = init_google_sheets()
        except Exception as e:
            print(f"Error initializing Google Sheets: {e}")
            sheet = None
            client = None
    return sheet

def get_student_color(name):
    colors = [
        Color(0.9, 0.9, 1),
        Color(0.9, 1, 0.9),
        Color(1, 0.9, 0.9),
        Color(1, 1, 0.8),
        Color(0.95, 0.85, 1),
        Color(0.8, 1, 1),
    ]
    return colors[hash(name) % len(colors)]

def generate_linear():
    while True:
        a = random.randint(1, 10)
        x_val = random.randint(-20, 20)
        b = random.randint(-10, 10)
        c = a * x_val + b
        lhs = a * x + b
        rhs = c
        solution = sp.solve(sp.Eq(lhs, rhs), x)
        if len(solution) == 1 and solution[0].is_real and solution[0] == int(solution[0]):
            return f"{format_expr(lhs)} = {format_expr(rhs)}", [int(solution[0])]

def generate_quadratic():
    while True:
        root = random.randint(-10, 10)
        lhs = (x - root)**2
        rhs = 0
        solution = sp.solve(sp.Eq(lhs, rhs), x)
        if len(solution) == 1 and solution[0].is_real and solution[0] == int(solution[0]):
            return f"{format_expr(lhs)} = {format_expr(rhs)}", [int(solution[0])]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/solve_equation', methods=['POST'])
def solve_equation():
    try:
        a = int(request.form['a'])
        b = int(request.form['b'])
        c = int(request.form['c'])
        eq_type = request.form.get('equation_type')
    except:
        return "Please enter valid integer coefficients.", 400

    if eq_type == 'linear':
        eq = sp.Eq(a * x + b, c)
    elif eq_type == 'quadratic':
        eq = sp.Eq(a * x**2 + b * x + c, 0)
    else:
        return "Invalid equation type", 400

    solution = sp.solve(eq, x)
    solution = [f"{sol.evalf():.3f}" for sol in solution if sol.is_real]

    return render_template('solution.html',
                           name=None,
                           student_class=None,
                           section=None,
                           equation=format_expr(eq.lhs) + " = " + format_expr(eq.rhs),
                           solution=solution)

@app.route('/start_quiz', methods=['POST'])
def start_quiz():
    session['name'] = request.form['name']
    session['class'] = request.form['class']
    session['section'] = request.form['section']

    questions = []
    while len(questions) < 10:
        if random.choice([True, False]):
            q, sol = generate_linear()
        else:
            q, sol = generate_quadratic()
        questions.append({'question': q, 'answer': sol})
    
    session['questions'] = questions
    session['start_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return redirect(url_for('quiz'))

@app.route('/quiz')
def quiz():
    return render_template('quiz.html', questions=session.get('questions', []))

@app.route('/submit_quiz', methods=['POST'])
def submit_quiz():
    questions = session.get('questions', [])
    name = session.get('name', 'Student')
    student_class = session.get('class', '-')
    section = session.get('section', '-')
    score = 0
    results = []
    start_time = session.get('start_time', '')
    submit_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sheet=get_sheet()
    rows_to_append = []

    for i, q in enumerate(questions):
        user_input = request.form.get(f'answer_{i}', '')
        try:
            user_val = int(user_input.strip())
            correct_val = q['answer'][0]
            correct = user_val == correct_val
        except:
            correct = False
            user_val = user_input

        if correct:
            score += 1

        results.append({
            'question': q['question'],
            'correct_answer': str(q['answer'][0]),
            'your_answer': user_input,
            'is_correct': correct
        })

        row = [
            name,
            student_class,
            section,
            q['question'],
            user_input,
            str(q['answer'][0]),
            "Correct" if correct else "Incorrect",
            start_time if i == 0 else "",
            ""  # placeholder for score
        ]
        rows_to_append.append(row)

    rows_to_append[-1][7] = submit_time
    rows_to_append[-1][8] = str(score)

    for row in reversed(rows_to_append):
        sheet.insert_row(row, 2)

    color = get_student_color(name)
    format_cell_range(sheet, f'A2:I{2 + len(rows_to_append) - 1}', CellFormat(backgroundColor=color))

    headers = ["Name", "Class", "Section", "Question", "User Answer", "Correct Answer", "Status", "Timestamp", "Score"]
    records = sheet.get_all_records(expected_headers=headers)

    scores = [(r['Name'].strip().lower(), int(r.get('Score', 0))) for r in records if r.get('Score')]
    sorted_scores = sorted(scores, key=lambda x: x[1], reverse=True)
    rank = next((i + 1 for i, s in enumerate(sorted_scores) if s[0] == name.strip().lower()), 'N/A')

    return render_template('result.html',
                           name=name,
                           student_class=student_class,
                           section=section,
                           score=score,
                           total=len(questions),
                           results=results,
                           rank=rank)

@app.route('/rankings')
def rankings():
    headers = ["Name", "Class", "Section", "Question", "User Answer", "Correct Answer", "Status", "Timestamp", "Score"]
    
    sheet=get_sheet()
    records = sheet.get_all_records(expected_headers=headers)
    
    students = []
    for r in records:
        try:
            score = int(r.get('Score', 0))
            students.append({
                'name': r.get('Name', 'Unknown'),
                'class': r.get('Class', '-'),
                'section': r.get('Section', '-'),
                'score': score
            })
        except ValueError:
            continue

    students_sorted = sorted(students, key=lambda x: x['score'], reverse=True)

    rank_list = []
    last_score = None
    rank = 0
    count = 0
    for student in students_sorted:
        count += 1
        if student['score'] != last_score:
            rank = count
            last_score = student['score']
        rank_list.append({**student, 'rank': rank})

    return render_template('rankings.html', rankings=rank_list)

if __name__ == '__main__':
    app.run(debug=True)
