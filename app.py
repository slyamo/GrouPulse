from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_mysqldb import MySQL
from flask_cors import CORS
import config
import random
import string

app = Flask(__name__)
CORS(app)

# load config
app.secret_key = config.SECRET_KEY
app.config['MYSQL_HOST'] = config.DB_HOST
app.config['MYSQL_USER'] = config.DB_USER
app.config['MYSQL_PASSWORD'] = config.DB_PASSWORD
app.config['MYSQL_DB'] = config.DB_NAME

mysql = MySQL(app)


# ─────────────────────────────────────────
# PAGE ROUTES
# ─────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/lobby')
def lobby():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('lobby.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/tasks')
def tasks():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('tasks.html')

@app.route('/progress')
def progress():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('progress.html')

@app.route('/evaluation')
def evaluation():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('evaluation.html')


# ─────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────

# register a new user
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')

    if not name or not email or not password or not role:
        return jsonify({'success': False, 'message': 'Please fill in all fields!'})

    cur = mysql.connection.cursor()

    # check if email already exists
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    existing = cur.fetchone()

    if existing:
        cur.close()
        return jsonify({'success': False, 'message': 'Email already registered!'})

    cur.execute("INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                (name, email, password, role))
    mysql.connection.commit()
    cur.close()

    return jsonify({'success': True, 'message': 'Account created! You can now login.'})


# login
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'success': False, 'message': 'Please fill in all fields!'})

    cur = mysql.connection.cursor()
    cur.execute("SELECT id, name, email, role FROM users WHERE email = %s AND password = %s",
                (email, password))
    user = cur.fetchone()
    cur.close()

    if user:
        session['user_id'] = user[0]
        session['user_name'] = user[1]
        session['user_email'] = user[2]
        session['user_role'] = user[3]
        return jsonify({
            'success': True,
            'user': {
                'id': user[0],
                'name': user[1],
                'email': user[2],
                'role': user[3]
            }
        })
    else:
        return jsonify({'success': False, 'message': 'Wrong email or password!'})


# logout
@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})


# get current logged in user
@app.route('/api/me', methods=['GET'])
def get_me():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    return jsonify({
        'success': True,
        'user': {
            'id': session['user_id'],
            'name': session['user_name'],
            'email': session['user_email'],
            'role': session['user_role']
        }
    })


# ─────────────────────────────────────────
# GROUP ROUTES
# ─────────────────────────────────────────

# generate a random group code
def generate_code():
    return "GP-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# create a new group
@app.route('/api/groups/create', methods=['POST'])
def create_group():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    data = request.get_json()
    name = data.get('name')
    subject = data.get('subject')
    description = data.get('description')
    max_members = data.get('maxMembers')
    due_date = data.get('dueDate')

    if not name or not subject or not max_members or not due_date:
        return jsonify({'success': False, 'message': 'Please fill in all required fields!'})

    code = generate_code()
    leader_id = session['user_id']

    cur = mysql.connection.cursor()

    cur.execute("""INSERT INTO groups_ (code, name, subject, description, max_members, due_date, leader_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (code, name, subject, description, max_members, due_date, leader_id))

    group_id = cur.lastrowid

    # add leader as a member
    cur.execute("INSERT INTO group_members (group_id, user_id, role) VALUES (%s, %s, 'leader')",
                (group_id, leader_id))

    mysql.connection.commit()
    cur.close()

    return jsonify({'success': True, 'code': code, 'group_id': group_id})


# join a group by code
@app.route('/api/groups/join', methods=['POST'])
def join_group():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    data = request.get_json()
    code = data.get('code', '').strip().upper()

    if not code:
        return jsonify({'success': False, 'message': 'Please enter a group code!'})

    cur = mysql.connection.cursor()

    # find the group
    cur.execute("SELECT id, name, max_members FROM groups_ WHERE code = %s", (code,))
    group = cur.fetchone()

    if not group:
        cur.close()
        return jsonify({'success': False, 'message': 'Group code not found!'})

    group_id = group[0]
    group_name = group[1]
    max_members = group[2]
    user_id = session['user_id']
    user_role = session['user_role']

    # check if already in the group
    cur.execute("SELECT id FROM group_members WHERE group_id = %s AND user_id = %s",
                (group_id, user_id))
    already_in = cur.fetchone()

    if already_in:
        cur.close()
        return jsonify({'success': False, 'message': 'You are already in this group!'})

    # instructors join as instructor role
    if user_role == 'instructor':
        cur.execute("INSERT INTO group_members (group_id, user_id, role) VALUES (%s, %s, 'instructor')",
                    (group_id, user_id))
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True, 'message': 'Access granted to: ' + group_name, 'group_id': group_id})

    # check if group is full (only count students)
    cur.execute("SELECT COUNT(*) FROM group_members WHERE group_id = %s AND role != 'instructor'",
                (group_id,))
    member_count = cur.fetchone()[0]

    if member_count >= max_members:
        cur.close()
        return jsonify({'success': False, 'message': 'This group is full!'})

    cur.execute("INSERT INTO group_members (group_id, user_id, role) VALUES (%s, %s, 'member')",
                (group_id, user_id))
    mysql.connection.commit()
    cur.close()

    return jsonify({'success': True, 'message': 'Joined group: ' + group_name, 'group_id': group_id})


# get all groups for the logged in user
@app.route('/api/groups', methods=['GET'])
def get_groups():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    user_id = session['user_id']
    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT g.id, g.code, g.name, g.subject, g.description, g.max_members, g.due_date,
               g.leader_id, u.name as leader_name, gm.role as my_role,
               (SELECT COUNT(*) FROM group_members WHERE group_id = g.id AND role != 'instructor') as member_count
        FROM groups_ g
        JOIN group_members gm ON g.id = gm.group_id
        JOIN users u ON g.leader_id = u.id
        WHERE gm.user_id = %s
    """, (user_id,))

    rows = cur.fetchall()
    cur.close()

    groups = []
    for row in rows:
        groups.append({
            'id': row[0],
            'code': row[1],
            'name': row[2],
            'subject': row[3],
            'description': row[4],
            'maxMembers': row[5],
            'dueDate': str(row[6]),
            'leaderId': row[7],
            'leaderName': row[8],
            'myRole': row[9],
            'memberCount': row[10]
        })

    return jsonify({'success': True, 'groups': groups})


# get a single group details
@app.route('/api/groups/<int:group_id>', methods=['GET'])
def get_group(group_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT g.id, g.code, g.name, g.subject, g.description, g.max_members, g.due_date,
               g.leader_id, u.name as leader_name
        FROM groups_ g
        JOIN users u ON g.leader_id = u.id
        WHERE g.id = %s
    """, (group_id,))

    group = cur.fetchone()

    if not group:
        cur.close()
        return jsonify({'success': False, 'message': 'Group not found!'})

    # get members
    cur.execute("""
        SELECT u.id, u.name, gm.role
        FROM group_members gm
        JOIN users u ON gm.user_id = u.id
        WHERE gm.group_id = %s AND gm.role != 'instructor'
    """, (group_id,))

    members = cur.fetchall()
    cur.close()

    member_list = []
    for m in members:
        member_list.append({'id': m[0], 'name': m[1], 'role': m[2]})

    return jsonify({
        'success': True,
        'group': {
            'id': group[0],
            'code': group[1],
            'name': group[2],
            'subject': group[3],
            'description': group[4],
            'maxMembers': group[5],
            'dueDate': str(group[6]),
            'leaderId': group[7],
            'leaderName': group[8],
            'members': member_list
        }
    })


# ─────────────────────────────────────────
# TASK ROUTES
# ─────────────────────────────────────────

# get all tasks for a group
@app.route('/api/groups/<int:group_id>/tasks', methods=['GET'])
def get_tasks(group_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT t.id, t.name, t.description, t.due_date, t.status, u.name as assigned_to, u.id as assigned_to_id
        FROM tasks t
        JOIN users u ON t.assigned_to = u.id
        WHERE t.group_id = %s
        ORDER BY t.created_at ASC
    """, (group_id,))

    rows = cur.fetchall()
    cur.close()

    tasks = []
    for row in rows:
        tasks.append({
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'dueDate': str(row[3]),
            'status': row[4],
            'assignedTo': row[5],
            'assignedToId': row[6]
        })

    return jsonify({'success': True, 'tasks': tasks})


# add a task
@app.route('/api/groups/<int:group_id>/tasks/add', methods=['POST'])
def add_task(group_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    data = request.get_json()
    name = data.get('name')
    description = data.get('description')
    assigned_to = data.get('assignedTo')
    due_date = data.get('dueDate')

    if not name or not assigned_to or not due_date:
        return jsonify({'success': False, 'message': 'Please fill in all required fields!'})

    cur = mysql.connection.cursor()
    cur.execute("""INSERT INTO tasks (group_id, name, description, assigned_to, due_date)
                   VALUES (%s, %s, %s, %s, %s)""",
                (group_id, name, description, assigned_to, due_date))
    mysql.connection.commit()
    cur.close()

    return jsonify({'success': True, 'message': 'Task added successfully!'})


# mark task as done
@app.route('/api/tasks/<int:task_id>/done', methods=['POST'])
def mark_done(task_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    cur = mysql.connection.cursor()
    cur.execute("UPDATE tasks SET status = 'Done' WHERE id = %s", (task_id,))
    mysql.connection.commit()
    cur.close()

    return jsonify({'success': True})


# delete a task
@app.route('/api/tasks/<int:task_id>/delete', methods=['POST'])
def delete_task(task_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
    mysql.connection.commit()
    cur.close()

    return jsonify({'success': True})


# ─────────────────────────────────────────
# EVALUATION ROUTES
# ─────────────────────────────────────────

# submit evaluation
@app.route('/api/groups/<int:group_id>/evaluations/add', methods=['POST'])
def add_evaluation(group_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    data = request.get_json()
    evaluated_user = data.get('evaluatedUser')
    contribution = data.get('contribution')
    teamwork = data.get('teamwork')
    deadline_rating = data.get('deadline')
    comment = data.get('comment')

    if not evaluated_user or not contribution or not teamwork or not deadline_rating:
        return jsonify({'success': False, 'message': 'Please complete all required fields!'})

    evaluated_by = session['user_id']

    cur = mysql.connection.cursor()

    # check if already evaluated this person
    cur.execute("""SELECT id FROM evaluations
                   WHERE group_id = %s AND evaluated_by = %s AND evaluated_user = %s""",
                (group_id, evaluated_by, evaluated_user))
    already = cur.fetchone()

    if already:
        cur.close()
        return jsonify({'success': False, 'message': 'You already evaluated this member!'})

    cur.execute("""INSERT INTO evaluations (group_id, evaluated_by, evaluated_user, contribution, teamwork, deadline_rating, comment)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (group_id, evaluated_by, evaluated_user, contribution, teamwork, deadline_rating, comment))
    mysql.connection.commit()
    cur.close()

    return jsonify({'success': True, 'message': 'Evaluation submitted!'})


# get evaluations for a group
@app.route('/api/groups/<int:group_id>/evaluations', methods=['GET'])
def get_evaluations(group_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT u1.name as evaluated_by, u2.name as evaluated_user,
               e.contribution, e.teamwork, e.deadline_rating, e.comment
        FROM evaluations e
        JOIN users u1 ON e.evaluated_by = u1.id
        JOIN users u2 ON e.evaluated_user = u2.id
        WHERE e.group_id = %s
    """, (group_id,))

    rows = cur.fetchall()
    cur.close()

    evals = []
    for row in rows:
        evals.append({
            'evaluatedBy': row[0],
            'member': row[1],
            'contribution': row[2],
            'teamwork': row[3],
            'deadline': row[4],
            'comment': row[5]
        })

    return jsonify({'success': True, 'evaluations': evals})


# ─────────────────────────────────────────
# RUN APP
# ─────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True)
