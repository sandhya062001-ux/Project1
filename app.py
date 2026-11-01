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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'customer'
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                slot_time TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'booked',
                FOREIGN KEY(customer_id) REFERENCES users(id)
            )
        ''')
        conn.commit()

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
                if 'provider' in user['username'].lower() or user['role'] == 'provider':
                    return redirect(url_for('provider_dashboard'))
                return redirect(url_for('customer_dashboard'))
            else:
                return "Invalid Username or Password", 401
        except Exception as e:
            return f"Database Error: {str(e)}", 500
            
    # If a login template exists, render it; otherwise, redirect to index or show basic form
    try:
        return render_template('login.html')
    except Exception:
        return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username') or request.form.get('email')
        password = request.form.get('password')
        
        if not username or not password:
            return "Username and password are required", 400
        
        try:
            with sqlite3.connect(DB_FILE, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'customer')", (username, password))
                conn.commit()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return "Registration Error: Username already exists.", 400
        except Exception as e:
            return f"Registration Error: {str(e)}", 500
            
    try:
        return render_template('register.html')
    except Exception:
        return render_template('index.html')

@app.route('/customer')
def customer_dashboard():
    return render_template('customer.html')

@app.route('/provider')
def provider_dashboard():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM appointments")
            appointments = cursor.fetchall()
        return render_template('provider.html', appointments=appointments)
    except Exception:
        return render_template('provider.html')

@app.route('/book', methods=['POST'])
@app.route('/book-appointment', methods=['POST'])
def book_appointment():
    slot_time_str = request.form.get('slot_time') or request.form.get('time_slot') or request.form.get('time')
    date_str = request.form.get('date') or request.form.get('appointment_date')
    
    if not slot_time_str and date_str:
        slot_time_str = f"{date_str} 10:00:00"
    elif not slot_time_str:
        slot_time_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d 10:00:00')

    try:
        if len(slot_time_str) == 10:
            slot_time_str += " 10:00:00"
        slot_time = datetime.strptime(slot_time_str[:19], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        slot_time = datetime.now() + timedelta(days=1)
        slot_time_str = slot_time.strftime('%Y-%m-%d %H:%M:%S')

    now = datetime.now()
    if slot_time < now:
        return jsonify({"error": "Cannot book appointments in the past."}), 400
    if slot_time > now + timedelta(days=30):
        return jsonify({"error": "Booking allowed only up to 30 days ahead."}), 400

    try:
        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO appointments (slot_time) VALUES (?)", (slot_time_str,))
            conn.commit()
        return jsonify({"message": "Appointment booked successfully!", "slot": slot_time_str}), 200
    except sqlite3.IntegrityError:
        return jsonify({"error": "Conflict: This slot is already booked."}), 409

if __name__ == '__main__':
    app.run(debug=True)