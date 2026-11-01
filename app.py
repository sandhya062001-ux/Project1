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
    return '''
        <h2>Appointment Booking System</h2>
        <p><b>Quick Access Links:</b></p>
        <ul>
            <li><a href="/customer">Go to Customer Dashboard (Book Appointments)</a></li>
            <li><a href="/provider">Go to Provider Dashboard (View Bookings)</a></li>
            <li><a href="/login">Login Page</a></li>
            <li><a href="/register">Register Page</a></li>
        </ul>
    '''

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        return redirect(url_for('customer_dashboard'))
    return '''
        <h3>Login</h3>
        <form method="POST">
            Username / Email: <input type="text" name="username" required><br><br>
            Password: <input type="password" name="password" required><br><br>
            <input type="submit" value="Login">
        </form>
        <br><a href="/customer">Skip to Customer Dashboard</a> | <a href="/provider">Skip to Provider Dashboard</a>
    '''

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        return redirect(url_for('login'))
    return '''
        <h3>Register</h3>
        <form method="POST">
            Username / Email: <input type="text" name="username" required><br><br>
            Password: <input type="password" name="password" required><br><br>
            <input type="submit" value="Register">
        </form>
        <br><a href="/login">Back to Login</a>
    '''

@app.route('/customer')
def customer_dashboard():
    try:
        return render_template('customer.html')
    except Exception:
        return '''
            <h3>Customer Dashboard</h3>
            <form action="/book" method="POST">
                Slot Time (YYYY-MM-DD HH:MM:SS): <input type="text" name="slot_time" value="2026-11-05 10:00:00"><br><br>
                <input type="submit" value="Book Appointment">
            </form>
            <br><a href="/provider">View Provider Dashboard</a>
        '''

@app.route('/provider')
def provider_dashboard():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM appointments")
            appointments = cursor.fetchall()
        
        html = "<h2>Provider Dashboard - Booked Appointments</h2>"
        html += "<p><a href='/customer'>← Back to Customer Dashboard</a></p><hr><ul>"
        if not appointments:
            html += "<li>No appointments booked yet.</li>"
        for appt in appointments:
            html += f"<li><b>Appointment ID:</b> {appt['id']} | <b>Slot Time:</b> {appt['slot_time']} | <b>Status:</b> {appt['status']}</li>"
        html += "</ul>"
        return html
    except Exception as e:
        return f"Error loading provider dashboard: {str(e)}"

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