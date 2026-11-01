from flask import Flask, render_template, request, redirect, url_for, session
import pymysql

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Database Connection Configuration
def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='root1234',  # <--- Your correct MySQL password
        database='appointment_db',
        cursorclass=pymysql.cursors.DictCursor
    )

# Home Route
@app.route('/')
def home():
    return render_template('index.html')

# Registration Route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            existing_user = cursor.fetchone()
            
            if existing_user:
                conn.close()
                return "Email already registered! <a href='/register'>Try again</a>"
            
            cursor.execute(
                "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                (name, email, password, role)
            )
            conn.commit()
        conn.close()
        return redirect(url_for('login'))
        
    return render_template('register.html')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
            user = cursor.fetchone()
        conn.close()
        
        if user:
            session['user_email'] = user['email']
            session['user_role'] = user['role']
            session['user_name'] = user['name']
            
            if user['role'] == 'customer':
                return redirect(url_for('customer_dashboard'))
            elif user['role'] == 'provider':
                return redirect(url_for('provider'))
        else:
            return "Invalid email or password! <a href='/login'>Try again</a>"
            
    return render_template('login.html')

# Customer Dashboard Route
@app.route('/customer')
def customer_dashboard():
    if 'user_email' in session and session.get('user_role') == 'customer':
        return render_template('customer.html', name=session.get('user_name'))
    return redirect(url_for('login'))

# Booking Route
@app.route('/book-appointment', methods=['POST'])
def book_appointment():
    customer_email = request.form.get('customer_email')
    provider_name = request.form.get('provider_name')
    appointment_date = request.form.get('appointment_date')
    slot = request.form.get('slot')
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "INSERT INTO appointments (customer_email, provider_name, appointment_date, slot) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (customer_email, provider_name, appointment_date, slot))
            conn.commit()
        conn.close()
        return "Appointment booked successfully! <a href='/customer'>Go back to Dashboard</a>"
    except Exception as e:
        return f"Error booking appointment: {e}. <a href='/customer'>Go Back</a>"

# Provider Dashboard Route
@app.route('/provider')
def provider():
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM appointments")
        appointments = cursor.fetchall()
    conn.close()
    return render_template('provider.html', appointments=appointments)

if __name__ == '__main__':
    app.run(debug=True)