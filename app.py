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
        
        # Seed test users
        cursor.execute("SELECT * FROM users WHERE username=?", ('customer@example.com',))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('customer@example.com', 'password123', 'customer'))
            
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
                if user['role'] == 'provider':
                    return redirect(url_for('provider_dashboard'))
                return redirect(url_for('customer_dashboard'))
            else:
                return "Invalid Username or Password", 401
        except Exception as e:
            return f"Database Error: {str(e)}", 500
            
    # Fallback login view if login.html doesn't exist
    return '''
        <h3>Login</h3>
        <form method="POST">
            Username: <input type="text" name="username"><br><br>
            Password: <input type="password" name="password"><br><br>
            <input type="submit" value="Login">
        </form>
        <br><a href="/register">Register new account</a>
    '''

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
            
    return '''
        <h3>Register</h3>
        <form method="POST">
            Username: <input type="text" name="username"><br><br>
            Password: <input type="password" name="password"><br><br>
            <input type="submit" value="Register">
        </form>
        <br><a href="/login">Back to Login</a>
    '''

@app.route('/customer')
def customer_dashboard():
    return render_template('customer.html')

@app.route('/provider')
def provider_dashboard():
    return render_template('provider.html')

@app.route('/book', methods=['POST'])
def book_appointment():
    slot_time_str = request.form.get('slot_time')
    if not slot_time_str:
        return jsonify({"error": "slot_time is required"}), 400

    try:
        slot_time = datetime.strptime(slot_time_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD HH:MM:SS"}), 400

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
        return jsonify({"message": "Appointment booked successfully!"}), 200
    except sqlite3.IntegrityError:
        return jsonify({"error": "Conflict: This slot is already booked."}), 409

if __name__ == '__main__':
    app.run(debug=True)