import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = 'super-secret-key'
DB_FILE = 'database.db'

def init_db():
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        
        # 1. Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'customer'
            )
        ''')
        
        # 2. Appointments table with UNIQUE constraint on slot_time
        # Enforces NO DOUBLE BOOKING directly in the database schema
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                slot_time TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'booked',
                FOREIGN KEY(customer_id) REFERENCES users(id)
            )
        ''')
        
        # --- SEED DATA: 10 TRIAL RECORDS FOR INTERVIEWER ---
        # Seed test users
        test_users = [
            ('customer', 'password123', 'customer'),
            ('customer@example.com', 'password123', 'customer'),
            ('customer@test.com', 'password123', 'customer'),
            ('provider1@test.com', 'password123', 'provider'),
            ('provider2@test.com', 'password123', 'provider')
        ]
        for user, pwd, role in test_users:
            cursor.execute("SELECT * FROM users WHERE username=?", (user,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (user, pwd, role))

        # Seed initial appointment slots to equal at least 10 trial records across the DB
        seed_slots = [
            (1, '2026-11-05 09:00:00'),
            (1, '2026-11-05 10:00:00'),
            (2, '2026-11-06 11:00:00'),
            (2, '2026-11-07 14:00:00'),
            (3, '2026-11-08 15:30:00')
        ]
        for cid, slot in seed_slots:
            try:
                cursor.execute("INSERT INTO appointments (customer_id, slot_time) VALUES (?, ?)", (cid, slot))
            except sqlite3.IntegrityError:
                pass  # Slot already exists
                
        conn.commit()

# Initialize database on app startup
init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username') or request.form.get('email')
        password = request.form.get('password')
        
        try:
            with sqlite3.connect(DB_FILE, timeout=30) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
                user = cursor.fetchone()
            
            if user:
                session['user'] = user['username']
                session['role'] = user['role']
                return redirect(url_for('index'))
            else:
                return "Invalid Username or Password", 401
        except Exception as e:
            return f"Database Error: {str(e)}", 500
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username') or request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'customer')
        
        try:
            with sqlite3.connect(DB_FILE, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, role))
                conn.commit()
            return redirect(url_for('login'))
        except Exception as e:
            return f"Registration Error: {str(e)}", 500
            
    return render_template('register.html')

# --- BOOKING BUSINESS RULES & DOUBLE BOOKING PROTECTION ---

@app.route('/book', methods=['POST'])
def book_appointment():
    slot_time_str = request.form.get('slot_time') # Format expected: 'YYYY-MM-DD HH:MM:SS'
    if not slot_time_str:
        return jsonify({"error": "slot_time is required"}), 400

    try:
        slot_time = datetime.strptime(slot_time_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD HH:MM:SS"}), 400

    now = datetime.now()
    max_date = now + timedelta(days=30)

    # Rule 1: No booking in the past
    if slot_time < now:
        return jsonify({"error": "Cannot book appointments in the past."}), 400

    # Rule 2: Booking allowed only up to 30 days ahead
    if slot_time > max_date:
        return jsonify({"error": "Booking allowed only up to 30 days ahead."}), 400

    try:
        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            cursor = conn.cursor()
            # Database UNIQUE constraint prevents two bookings on the exact same slot
            cursor.execute("INSERT INTO appointments (slot_time) VALUES (?)", (slot_time_str,))
            conn.commit()
        return jsonify({"message": "Appointment booked successfully!"}), 200
    except sqlite3.IntegrityError:
        # Enforce 409 Conflict HTTP status code when double-booked at DB level
        return jsonify({"error": "Conflict: This slot is already booked."}), 409

@app.route('/cancel/<int:appointment_id>', methods=['POST'])
def cancel_appointment(appointment_id):
    try:
        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT slot_time FROM appointments WHERE id = ?", (appointment_id,))
            appointment = cursor.fetchone()

            if not appointment:
                return jsonify({"error": "Appointment not found"}), 404

            slot_time = datetime.strptime(appointment['slot_time'], '%Y-%m-%d %H:%M:%S')
            now = datetime.now()

            # Rule 3: Cancel or reschedule allowed only up to 2 hours before start time
            if (slot_time - now) < timedelta(hours=2):
                return jsonify({"error": "Cannot cancel or reschedule within 2 hours of appointment start time."}), 400

            cursor.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
            conn.commit()
        return jsonify({"message": "Appointment cancelled successfully."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)