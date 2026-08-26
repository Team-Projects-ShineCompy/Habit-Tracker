import os
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash

import database
import real_statistics

app = Flask(__name__, template_folder="templates", static_folder="static")

# --- Critical Security Configuration ---
# SECRET_KEY must be set as an environment variable. No fallback allowed.
# NOTE: In multi-worker deployments, this random per-process fallback will invalidate sessions
# across workers and is therefore only acceptable in local dev/testing, never in production.
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    import warnings
    warnings.warn(
        "WARNING: SECRET_KEY environment variable is not set. "
        "Using an insecure temporary key. Set SECRET_KEY in production!",
        RuntimeWarning
    )
    _secret_key = os.urandom(32)  # Random per-process key (safe for dev, not for multi-process prod)
app.config['SECRET_KEY'] = _secret_key

# Session Cookie Security
app.config['SESSION_COOKIE_HTTPONLY'] = True       # Prevent JS access to session cookie
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'     # Protect against CSRF
app.config['SESSION_COOKIE_SECURE'] = os.environ.get("HTTPS_ENABLED", "false").lower() == "true"


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Unauthorized. Please log in."}), 401
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# PAGE ROUTING (HTML TEMPLATES)
# ==========================================


@app.route('/')
def index_page():
    return render_template('t_p_2.4.html', show_normal_mode=False)


@app.route('/login')
def login_page():
    return render_template('login.html')


@app.route('/register')
def register_page():
    return render_template('register.html')
    

@app.route('/t_p_2.4.css')
def serve_template_css():
    return send_file(os.path.join(app.template_folder, 't_p_2.4.css'))

ALLOWED_JS_FILES = {
                    'config.js',
                    'calendar.js', 
                    'habits.js',
                    'statistics.js',
                    'main.js',
                    'jquery.min.js'
                    }

@app.route('/<path:filename>.js')
def serve_js(filename):
    full_name = f"{filename}.js"
    if full_name not in ALLOWED_JS_FILES:
        return jsonify({"error": "Not found"}), 404
    return send_file(os.path.join(app.template_folder, full_name))


# ==========================================
# REST API ENDPOINTS
# ==========================================

# 1. User Registration
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    existing_user = database.get_user_by_email(email)
    if existing_user:
        return jsonify({"error": "User with this email already exists"}), 400

    password_hash = generate_password_hash(password)
    user_id = database.create_user(email, password_hash)

    if user_id:
        return jsonify({"message": "Register successful", "user_id": user_id}), 201
    else:
        return jsonify({"error": "Failed to create account"}), 500


# 2. User Login
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = database.get_user_by_email(email)
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({"error": "Invalid email or password"}), 401

    # Store user identity directly in encrypted Flask Backend Session
    session['user_id'] = user['id']
    session['user_email'] = user['email']

    return jsonify({"message": "Login successful", "user_id": user['id'], "email": user['email']}), 200


# 2b. User Logout
@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200


# 2c. Get Current Session User info
@app.route('/api/me', methods=['GET'])
@login_required
def api_me():
    return jsonify({"user_id": session['user_id'], "email": session.get('user_email')}), 200


# 3. Create Habit Definition (Secured with session['user_id'])
@app.route('/api/habit/create', methods=['POST'])
@login_required
def api_create_habit():
    data = request.get_json() or {}
    user_id = session['user_id']  # Get user_id directly from session!
    habit_name = data.get('habit_name')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    repeat_type = data.get('repeat_type', 'weekly')
    repeat_pattern = data.get('repeat_pattern', {})

    if not habit_name or not start_time or not end_time:
        return jsonify({"error": "Missing required fields for habit creation"}), 400

    if repeat_type not in ("weekly", "custom"):
        return jsonify({"error": "repeat_type must be either 'weekly' or 'custom'"}), 400

    habit = database.create_habit(
        user_id=user_id,
        habit_name=habit_name,
        start_time=start_time,
        end_time=end_time,
        repeat_type=repeat_type,
        repeat_pattern=repeat_pattern
    )

    return jsonify({"message": "Habit created successfully", "habit": habit}), 201


# 4. List User Habits (Secured with session['user_id'])
@app.route('/api/habit/list', methods=['GET'])
@app.route('/api/habit/list/<int:user_id>', methods=['GET'])
@login_required
def api_list_habits(user_id=None):
    # The URL user_id is intentionally ignored; session auth is the source of truth.
    current_user_id = session['user_id']
    habits = database.get_user_habits(current_user_id)
    return jsonify({"habits": habits}), 200


# 5. Delete Habit (Secured with Ownership Verification)
@app.route('/api/habit/delete/<int:habit_id>', methods=['DELETE'])
@login_required
def api_delete_habit(habit_id):
    current_user_id = session['user_id']
    
    # Verify that the habit belongs to the logged-in user!
    if not database.verify_habit_ownership(habit_id, current_user_id):
        return jsonify({"error": "Forbidden. Habit does not belong to your account."}), 403

    success = database.delete_habit(habit_id)
    if success:
        return jsonify({"message": "Habit deleted"}), 200
    return jsonify({"error": "Failed to delete habit"}), 400


# 6. Submit Habit Completion Log / Stage Status (Secured with Ownership Verification)
@app.route('/api/habit/log', methods=['POST'])
@login_required
def api_habit_log():
    data = request.get_json() or {}
    habit_id = data.get('habit_id')
    log_date = data.get('date')
    status = data.get('status')
    current_user_id = session['user_id']

    if status is None:
        completed = data.get('completed', False)
        status = "done" if completed else "ready"

    if not habit_id or not log_date:
        return jsonify({"error": "habit_id and date are required"}), 400

    # Verify that the habit belongs to the logged-in user!
    if not database.verify_habit_ownership(habit_id, current_user_id):
        return jsonify({"error": "Forbidden. Habit does not belong to your account."}), 403

    database.upsert_habit_log(habit_id, log_date, status)
    return jsonify({"message": "Habit status updated", "status": status}), 200


# 6b. Get User Habit Logs Map (Secured with session['user_id'])
@app.route('/api/habit/logs', methods=['GET'])
@app.route('/api/habit/logs/<int:user_id>', methods=['GET'])
@login_required
def api_get_habit_logs(user_id=None):
    # The URL user_id is intentionally ignored; session auth is the source of truth.
    current_user_id = session['user_id']
    logs = database.get_user_habit_logs(current_user_id)
    return jsonify({"logs": logs}), 200


# 7. Get User Statistics (Secured with session['user_id'])
@app.route('/api/statistics', methods=['GET'])
@app.route('/api/statistics/<int:user_id>', methods=['GET'])
@login_required
def api_statistics(user_id=None):
    # The URL user_id is intentionally ignored; session auth is the source of truth.
    current_user_id = session['user_id']
    stats = real_statistics.get_user_statistics(current_user_id)
    return jsonify(stats), 200


@app.route('/api/statistics/daily', methods=['GET'])
@login_required
def api_daily_stats():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    if year and month:
        data = real_statistics.get_daily_completion_rates_for_month(session['user_id'], year, month)
    else:
        data = real_statistics.get_daily_completion_rates(session['user_id'])
    return jsonify(data), 200


@app.route('/api/statistics/habits', methods=['GET'])
@login_required
def api_habit_breakdown():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    if year and month:
        data = real_statistics.get_per_habit_breakdown_for_month(session['user_id'], year, month)
    else:
        data = real_statistics.get_per_habit_breakdown(session['user_id'])
    return jsonify(data), 200

database.init_db()


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # CRITICAL: debug must NEVER be True in production (exposes Werkzeug RCE debugger)
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
