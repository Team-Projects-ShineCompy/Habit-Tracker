import os
import secrets
import re
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from dotenv import load_dotenv
load_dotenv()

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
_secret_key = os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY")
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


ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
OTP_TTL = timedelta(minutes=5)
OTP_RESEND_COOLDOWN = timedelta(seconds=60)
OTP_MAX_ATTEMPTS = 5


def normalize_email(value):
    email = (value or '').strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return None
    return email


def validate_password(password):
    return isinstance(password, str) and len(password) >= 8


def generate_otp():
    return f"{secrets.randbelow(1000000):06d}"


def send_otp_email(email, otp):
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM") or user
    if not host or not user or not password or not sender:
        raise RuntimeError("SMTP email configuration is incomplete.")

    message = EmailMessage()
    message["Subject"] = "Your Verification Code"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        f"Your verification code is:\n\n{otp}\n\nThis code expires in 5 minutes."
    )
    port = int(os.environ.get("SMTP_PORT", "587"))
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
            smtp.login(user, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(message)


def request_otp(email, purpose):
    now = datetime.utcnow()
    current = database.get_latest_otp(email, purpose)
    if current:
        sent_at = current['last_sent_at']
        if isinstance(sent_at, str):
            sent_at = datetime.fromisoformat(sent_at)
        remaining = int((OTP_RESEND_COOLDOWN - (now - sent_at)).total_seconds())
        if remaining > 0:
            return False, f"Please wait before requesting another OTP. Try again in {remaining} seconds."

    otp = generate_otp()
    database.create_otp(
        email, generate_password_hash(otp), purpose,
        now + OTP_TTL, now
    )
    try:
        send_otp_email(email, otp)
    except Exception as e:
        import traceback
        print(f"[OTP EMAIL ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()
        # Do not leave a code active when delivery failed.
        latest = database.get_latest_otp(email, purpose)
        if latest:
            database.mark_otp_verified(latest['id'])
        raise
    return True, None


def verify_otp(email, purpose, supplied_otp):
    record = database.get_latest_otp(email, purpose)
    if not record:
        return False, "Verification code expired or invalid."
    expires_at = record['expires_at']
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if datetime.utcnow() >= expires_at:
        database.mark_otp_verified(record['id'])
        return False, "Verification code expired."
    if record['attempts'] >= OTP_MAX_ATTEMPTS:
        database.mark_otp_verified(record['id'])
        return False, "Too many incorrect attempts. Please request a new code."
    if not isinstance(supplied_otp, str) or not re.fullmatch(r"\d{6}", supplied_otp):
        attempts = record['attempts'] + 1
        database.update_otp_attempts(record['id'], attempts, attempts >= OTP_MAX_ATTEMPTS)
        return False, "Invalid verification code."
    if not check_password_hash(record['otp_hash'], supplied_otp):
        attempts = record['attempts'] + 1
        database.update_otp_attempts(record['id'], attempts, attempts >= OTP_MAX_ATTEMPTS)
        if attempts >= OTP_MAX_ATTEMPTS:
            return False, "Too many incorrect attempts. Please request a new code."
        return False, "Invalid verification code."
    database.mark_otp_verified(record['id'])
    return True, None


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({"error": "Admin authorization required."}), 401
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


@app.route('/forgot-password')
def forgot_password_page():
    return render_template('forgot_password.html')

@app.route('/admin/login')
def admin_login_page():
    return render_template('admin_login.html')


@app.route('/admin')
def admin_page():
    return render_template('admin.html')


@app.route('/admin/user/<int:user_id>')
def admin_user_detail_page(user_id):
    return render_template('admin_user_detail.html', target_user_id=user_id)
    

@app.route('/t_p_2.4.css')
def serve_template_css():
    return send_file(os.path.join(app.template_folder, 't_p_2.4.css'))

ALLOWED_JS_FILES = {
                    'config.js',
                    'calendar.js', 
                    'habits.js',
                    'statistics.js',
                    'main.js',
                    'jquery.min.js',
                    'admin.js',
                    'admin_detail.js'
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
    return jsonify({"error": "Email verification is required before creating an account."}), 410


@app.route('/api/auth/signup/send-otp', methods=['POST'])
def signup_send_otp():
    email = normalize_email((request.get_json() or {}).get('email'))
    if not email:
        return jsonify({"error": "Please enter a valid email address."}), 400
    if database.get_user_by_email(email):
        return jsonify({"error": "User with this email already exists."}), 400
    try:
        allowed, error = request_otp(email, 'signup')
        if not allowed:
            return jsonify({"error": error}), 429
        return jsonify({"message": "Verification code sent."}), 200
    except Exception:
        return jsonify({"error": "Unable to send verification code."}), 500


@app.route('/api/auth/signup/verify-otp', methods=['POST'])
def signup_verify_otp():
    data = request.get_json() or {}
    email = normalize_email(data.get('email'))
    valid, error = verify_otp(email, 'signup', data.get('otp')) if email else (False, "Invalid verification code.")
    if not valid:
        return jsonify({"error": error}), 400
    session['signup_verified_email'] = email
    return jsonify({"message": "Email verified successfully."}), 200


@app.route('/api/auth/signup/create-password', methods=['POST'])
def signup_create_password():
    email = session.get('signup_verified_email')
    password = (request.get_json() or {}).get('password', '')
    if not email:
        return jsonify({"error": "Please verify your email first."}), 400
    if not validate_password(password):
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if database.get_user_by_email(email):
        session.pop('signup_verified_email', None)
        return jsonify({"error": "User with this email already exists."}), 400
    user_id = database.create_user(email, generate_password_hash(password))
    if not user_id:
        return jsonify({"error": "Failed to create account."}), 500
    session.pop('signup_verified_email', None)
    session['user_id'] = user_id
    session['user_email'] = email
    return jsonify({"message": "Account created successfully.", "user_id": user_id}), 201


@app.route('/api/auth/reset/send-otp', methods=['POST'])
def reset_send_otp():
    email = normalize_email((request.get_json() or {}).get('email'))
    if not email:
        return jsonify({"message": "If the account exists, a verification code has been sent."}), 200
    try:
        if database.get_user_by_email(email):
            allowed, error = request_otp(email, 'password_reset')
            if not allowed:
                return jsonify({"error": error}), 429
    except Exception:
        return jsonify({"error": "Unable to send verification code."}), 500
    return jsonify({"message": "If the account exists, a verification code has been sent."}), 200


@app.route('/api/auth/reset/verify-otp', methods=['POST'])
def reset_verify_otp():
    data = request.get_json() or {}
    email = normalize_email(data.get('email'))
    valid, error = verify_otp(email, 'password_reset', data.get('otp')) if email else (False, "Invalid verification code.")
    if not valid:
        return jsonify({"error": error}), 400
    session['reset_verified_email'] = email
    return jsonify({"message": "Email verified successfully."}), 200


@app.route('/api/auth/reset/new-password', methods=['POST'])
def reset_new_password():
    email = session.get('reset_verified_email')
    password = (request.get_json() or {}).get('password', '')
    if not email:
        return jsonify({"error": "Please verify your email first."}), 400
    if not validate_password(password):
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    user = database.get_user_by_email(email)
    if not user or not database.update_user_password(user['id'], generate_password_hash(password)):
        return jsonify({"error": "Unable to update password."}), 400
    session.pop('reset_verified_email', None)
    return jsonify({"message": "Password updated successfully."}), 200


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

    session.clear()
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

# ==========================================
# ADMIN — AUTH
# ==========================================

@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')

    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        return jsonify({"error": "Admin login is not configured on the server."}), 500

    valid = secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(password, ADMIN_PASSWORD)
    if not valid:
        return jsonify({"error": "Invalid admin credentials"}), 401

    session.clear()  # regular user session ရှိရင် clear (admin/user session ရောမနေအောင်)
    session['is_admin'] = True
    return jsonify({"message": "Admin login successful"}), 200


@app.route('/api/admin/logout', methods=['POST'])
def api_admin_logout():
    session.clear()
    return jsonify({"message": "Logged out"}), 200


@app.route('/api/admin/me', methods=['GET'])
@admin_required
def api_admin_me():
    return jsonify({"is_admin": True}), 200


# ==========================================
# ADMIN — DATA (READ-ONLY, except delete)
# ==========================================

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def api_admin_users():
    users = database.get_all_users()
    return jsonify({"users": users}), 200


@app.route('/api/admin/user/<int:user_id>', methods=['GET'])
@admin_required
def api_admin_user_info(user_id):
    user = database.get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user": user}), 200


@app.route('/api/admin/user/<int:user_id>/habits', methods=['GET'])
@admin_required
def api_admin_user_habits(user_id):
    habits = database.get_user_habits(user_id)
    return jsonify({"habits": habits}), 200


@app.route('/api/admin/user/<int:user_id>/logs', methods=['GET'])
@admin_required
def api_admin_user_logs(user_id):
    logs = database.get_user_habit_logs(user_id)
    return jsonify({"logs": logs}), 200


@app.route('/api/admin/user/<int:user_id>/statistics', methods=['GET'])
@admin_required
def api_admin_user_statistics(user_id):
    stats = real_statistics.get_user_statistics(user_id)
    return jsonify(stats), 200


@app.route('/api/admin/user/<int:user_id>/statistics/daily', methods=['GET'])
@admin_required
def api_admin_user_daily(user_id):
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    if year and month:
        data = real_statistics.get_daily_completion_rates_for_month(user_id, year, month)
    else:
        data = real_statistics.get_daily_completion_rates(user_id)
    return jsonify(data), 200


@app.route('/api/admin/user/<int:user_id>/statistics/habits', methods=['GET'])
@admin_required
def api_admin_user_habit_breakdown(user_id):
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    if year and month:
        data = real_statistics.get_per_habit_breakdown_for_month(user_id, year, month)
    else:
        data = real_statistics.get_per_habit_breakdown(user_id)
    return jsonify(data), 200


# ==========================================
# ADMIN — DELETE USER (only allowed mutation)
# ==========================================

@app.route('/api/admin/user/<int:user_id>', methods=['DELETE'])
@admin_required
def api_admin_delete_user(user_id):
    success = database.delete_user(user_id)
    if success:
        return jsonify({"message": "User deleted"}), 200
    return jsonify({"error": "Failed to delete user"}), 400

database.init_db()


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # CRITICAL: debug must NEVER be True in production (exposes Werkzeug RCE debugger)
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
