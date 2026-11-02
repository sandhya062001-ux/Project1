import os
import sqlite3
import random
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, session, render_template_string, redirect

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'appointment-system-super-secret-key')
DB_FILE = 'database.db'

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except Exception:
            pass

    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT CHECK(role IN ('customer', 'provider')) NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 2. Providers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                category TEXT NOT NULL,
                bio TEXT,
                slot_minutes INTEGER DEFAULT 30,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # 3. Availability table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS availability (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id INTEGER NOT NULL,
                day_of_week TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                FOREIGN KEY(provider_id) REFERENCES providers(id) ON DELETE CASCADE
            )
        ''')
        
        # 4. Appointments table with Unique Index for 409 Conflict protection
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_ref TEXT UNIQUE NOT NULL,
                customer_id INTEGER NOT NULL,
                provider_id INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                status TEXT CHECK(status IN ('booked', 'cancelled', 'completed', 'no_show')) DEFAULT 'booked',
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(customer_id) REFERENCES users(id),
                FOREIGN KEY(provider_id) REFERENCES providers(id)
            )
        ''')
        
        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_active_slot 
            ON appointments(provider_id, start_time) 
            WHERE status = 'booked'
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_appointments_customer ON appointments(customer_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_appointments_provider ON appointments(provider_id, start_time)')

        # 5. Appointment Status History table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS appointment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appointment_id INTEGER NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                changed_by INTEGER NOT NULL,
                reason TEXT,
                changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
                FOREIGN KEY(changed_by) REFERENCES users(id)
            )
        ''')
        
        # --- SEED 7 PROVIDERS & TEST CUSTOMER ---
        seed_providers = [
            ("Dr. John Smith", "dr.smith@test.com", "Doctor", "General practitioner with 10 years experience."),
            ("Dr. Emily Jones", "dr.jones@test.com", "Dentist", "Specialist in cosmetic and family dentistry."),
            ("Dr. Robert Adams", "dr.adams@test.com", "Cardiologist", "Board-certified heart specialist."),
            ("Lisa Therapy", "provider.lisa@test.com", "Therapist", "Licensed mental health counselor."),
            ("Mark Dermatology", "provider.mark@test.com", "Dermatologist", "Skin care and clinical treatments."),
            ("Sarah Pediatrics", "provider.sarah@test.com", "Pediatrician", "Dedicated child healthcare provider."),
            ("Kevin Neurology", "provider.kevin@test.com", "Neurologist", "Brain and nervous system disorders specialist.")
        ]
        
        for name, email, category, bio in seed_providers:
            cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, 'password123', 'provider')", (name, email))
            user_id = cursor.lastrowid
            cursor.execute("INSERT INTO providers (user_id, category, bio, slot_minutes) VALUES (?, ?, ?, 30)", (user_id, category, bio))
            prov_id = cursor.lastrowid
            
            for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
                cursor.execute("INSERT INTO availability (provider_id, day_of_week, start_time, end_time) VALUES (?, ?, '09:00', '17:00')", (prov_id, day))

        # Seed Customer
        cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES ('Test Customer', 'customer@test.com', 'password123', 'customer')")
        conn.commit()

init_db()

# --- HTML TEMPLATES ---
BASE_LAYOUT = '''
<!DOCTYPE html>
<html>
<head>
    <title>Appointment Booking System</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; background: #f4f6f9; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1, h2 { color: #0066cc; }
        .btn { background: #0066cc; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; }
        .btn:hover { background: #004fb3; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input, select, textarea { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
        .error { color: red; margin-bottom: 15px; font-weight: bold; }
        .success { color: green; margin-bottom: 15px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>
'''

INDEX_HTML = BASE_LAYOUT.replace('{% block content %}{% endblock %}', '''
    <h1>Appointment Booking System</h1>
    <p>Welcome! Please choose an option below:</p>
    <p><a href="/login-page" class="btn">Go to Login</a>   <a href="/register-page" class="btn">Register</a></p>
''')

LOGIN_HTML = BASE_LAYOUT.replace('{% block content %}{% endblock %}', '''
    <h2>Login</h2>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST" action="/auth/login">
        <div class="form-group">
            <label>Email Address</label>
            <input type="email" name="email" required value="customer@test.com">
        </div>
        <div class="form-group">
            <label>Password</label>
            <input type="password" name="password" required value="password123">
        </div>
        <button type="submit" class="btn">Login</button>
    </form>
    <p><br>Don't have an account? <a href="/register-page">Register here</a> | <a href="/">Home</a></p>
''')

CUSTOMER_HTML = BASE_LAYOUT.replace('{% block content %}{% endblock %}', '''
    <h2>Customer Dashboard</h2>
    <p>Welcome, Customer! (<a href="/">Logout / Home</a>)</p>
    <hr>
    <h3>Book an Appointment</h3>
    <div id="result"></div>
    <form id="bookingForm" onsubmit="bookAppointment(event)">
        <div class="form-group">
            <label>Select Service Provider</label>
            <select id="provider_id" required>
                {% for p in providers %}
                <option value="{{ p.id }}">{{ p.name }} ({{ p.category }})</option>
                {% endfor %}
            </select>
        </div>
        <div class="form-group">
            <label>Start Time (Format: YYYY-MM-DD HH:MM:SS)</label>
            <input type="text" id="start_time" placeholder="2026-11-15 10:00:00" required>
        </div>
        <button type="submit" class="btn">Confirm Booking</button>
    </form>

    <script>
    async function bookAppointment(e) {
        e.preventDefault();
        const provider_id = document.getElementById('provider_id').value;
        const start_time = document.getElementById('start_time').value;
        
        const res = await fetch('/appointments', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({provider_id, start_time})
        });
        const data = await res.json();
        const resDiv = document.getElementById('result');
        if(res.ok) {
            resDiv.className = 'success';
            resDiv.innerText = "Appointment booked successfully! Reference: " + data.booking_ref;
        } else {
            resDiv.className = 'error';
            resDiv.innerText = "Booking Error: " + data.error;
        }
    }
    </script>
''')

PROVIDER_HTML = BASE_LAYOUT.replace('{% block content %}{% endblock %}', '''
    <h2>Provider Dashboard</h2>
    <p>Welcome Provider! (<a href="/">Logout / Home</a>)</p>
    <hr>
    <h3>Set Weekly Availability & Working Hours</h3>
    <form method="POST" action="/provider/availability">
        <div class="form-group">
            <label>Start Time & End Time</label>
            <input type="text" name="start_time" value="09:00" style="width:48%; display:inline-block;"> to 
            <input type="text" name="end_time" value="17:00" style="width:48%; display:inline-block;">
        </div>
        <button type="submit" class="btn">Save Availability</button>
    </form>
''')

# --- ROUTES ---
@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/login-page')
def login_page():
    return render_template_string(LOGIN_HTML)

@app.route('/register-page')
def register_page():
    return render_template_string(BASE_LAYOUT.replace('{% block content %}{% endblock %}', '<h2>Register</h2><form method="POST" action="/auth/register"><div class="form-group"><label>Name</label><input type="text" name="name" required></div><div class="form-group"><label>Email</label><input type="email" name="email" required></div><div class="form-group"><label>Password</label><input type="password" name="password" required></div><div class="form-group"><label>Role</label><select name="role"><option value="customer">Customer</option><option value="provider">Provider</option></select></div><button type="submit" class="btn">Register</button></form><p><a href="/login-page">Back to Login</a></p>'))

@app.route('/customer')
def customer_dashboard():
    with get_db() as conn:
        providers = conn.cursor().execute("SELECT p.id, u.name, p.category FROM providers p JOIN users u ON p.user_id = u.id").fetchall()
    return render_template_string(CUSTOMER_HTML, providers=providers)

@app.route('/provider')
def provider_dashboard():
    return render_template_string(PROVIDER_HTML)

# Unified Login supporting both Form and JSON requests
@app.route('/auth/login', methods=['POST'])
def login():
    if request.is_json:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        is_api = True
    else:
        email = request.form.get('email')
        password = request.form.get('password')
        is_api = False

    with get_db() as conn:
        user = conn.cursor().execute("SELECT * FROM users WHERE email = ? AND password_hash = ?", (email, password)).fetchone()

    if user:
        session['user_id'] = user['id']
        session['role'] = user['role']
        if is_api:
            return jsonify({"message": "Login successful", "role": user['role']}), 200
        if user['role'] == 'provider':
            return redirect('/provider')
        return redirect('/customer')
    
    if is_api:
        return jsonify({"error": "Invalid email or password"}), 401
    return render_template_string(LOGIN_HTML, error="Invalid email or password")

@app.route('/auth/register', methods=['POST'])
def register():
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role', 'customer')
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)", (name, email, password, role))
            if role == 'provider':
                cursor.execute("INSERT INTO providers (user_id, category, bio) VALUES (?, 'General', '')", (cursor.lastrowid,))
            conn.commit()
        return redirect('/login-page')
    except Exception as e:
        return f"Registration Error: {str(e)}"

@app.route('/appointments', methods=['POST'])
def create_appointment():
    data = request.get_json() or request.form
    customer_id = session.get('user_id', 1)
    provider_id = data.get('provider_id')
    start_time_str = data.get('start_time')

    try:
        start_dt = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return jsonify({"error": "Invalid format. Use YYYY-MM-DD HH:MM:SS"}), 400

    now = datetime.now()
    if start_dt < now:
        return jsonify({"error": "Cannot book in the past"}), 400
    if start_dt > now + timedelta(days=30):
        return jsonify({"error": "Booking allowed up to 30 days ahead"}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        
        year_month = start_dt.strftime('%Y-%m')
        if cursor.execute("SELECT id FROM appointments WHERE customer_id = ? AND status = 'booked' AND strftime('%Y-%m', start_time) = ?", (customer_id, year_month)).fetchone():
            return jsonify({"error": "Monthly limit reached: already booked this month."}), 400

        end_time_str = (start_dt + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
        booking_ref = f"APT-{start_dt.year}-{random.randint(100000, 999999)}"

        try:
            cursor.execute("INSERT INTO appointments (booking_ref, customer_id, provider_id, start_time, end_time, status) VALUES (?, ?, ?, ?, ?, 'booked')",
                           (booking_ref, customer_id, provider_id, start_time_str, end_time_str))
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "Conflict: This slot is already booked."}), 409

    return jsonify({"message": "Booked successfully", "booking_ref": booking_ref}), 201

if __name__ == '__main__':
    app.run(debug=True)