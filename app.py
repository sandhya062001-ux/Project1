import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'super-secret-key'
DB_FILE = 'database.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # Insert test users (both email format and standard username)
    test_users = [
        ('customer', 'password123'),
        ('customer@example.com', 'password123'),
        ('customer@test.com', 'password123')
    ]
    for user, pwd in test_users:
        cursor.execute("SELECT * FROM users WHERE username=?", (user,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (user, pwd))
            
    conn.commit()
    conn.close()

# Initialize database on app startup
init_db()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username') or request.form.get('email')
        password = request.form.get('password')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
            user = cursor.fetchone()
            conn.close()
            
            if user:
                session['user'] = user['username']
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
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except Exception as e:
            return f"Registration Error: {str(e)}", 500
            
    return render_template('register.html')

if __name__ == '__main__':
    app.run(debug=True)