import os
import sqlite3
import random
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'appointment-system-super-secret-key')
DB_FILE = 'database.db'

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
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
        
        # 4. Appointments table with Unique Index to enforce 409 Conflict on double booking
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
        
        # Unique index ensuring no two active 'booked' appointments share the same provider and start time
        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_active_slot 
            ON appointments(provider_id, start_time) 
            WHERE status = 'booked'
        ''')
        
        # Additional performance indexes
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
        
        # --- SEED 6-7 PROVIDER RECORDS & TEST CUSTOMER ---
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
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            if not row:
                pw_hash = generate_password_hash("password123")
                cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'provider')", (name, email, pw_hash))
                user_id = cursor.lastrowid
                cursor.execute("INSERT INTO providers (user_id, category, bio, slot_minutes) VALUES (?, ?, ?, 30)", (user_id, category, bio))
                
                # Default availability for all seed providers (Monday to Friday, 09:00 to 17:00)
                days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
                for day in days:
                    cursor.execute("INSERT INTO availability (provider_id, day_of_week, start_time, end_time) VALUES (?, ?, '09:00', '17:00')", (cursor.lastrowid, day))

        # Seed Test Customer
        cursor.execute("SELECT id FROM users WHERE email = ?", ("customer@test.com",))
        if not cursor.fetchone():
            pw_hash = generate_password_hash("password123")
            cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES ('Test Customer', 'customer@test.com', ?, 'customer')", (pw_hash,))

        conn.commit()

init_db()

# --- AUTHENTICATION & REGISTRATION ENDPOINTS ---
@app.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json() or request.form
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'customer')
    category = data.get('category', 'General')
    bio = data.get('bio', '')

    if not name or not email or not password or role not in ('customer', 'provider'):
        return jsonify({"error": "Missing required fields or invalid role"}), 400

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            pw_hash = generate_password_hash(password)
            cursor.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)", (name, email, pw_hash, role))
            user_id = cursor.lastrowid
            
            if role == 'provider':
                cursor.execute("INSERT INTO providers (user_id, category, bio) VALUES (?, ?, ?)", (user_id, category, bio))
            conn.commit()
        return jsonify({"message": "Registration successful", "user_id": user_id}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already exists"}), 400

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json() or request.form
    email = data.get('email')
    password = data.get('password')

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

    if user and check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['role'] = user['role']
        session['email'] = user['email']
        
        provider_id = None
        if user['role'] == 'provider':
            with get_db() as conn:
                p = conn.cursor().execute("SELECT id FROM providers WHERE user_id = ?", (user['id'],)).fetchone()
                if p: provider_id = p['id']

        return jsonify({
            "message": "Login successful",
            "user_id": user['id'],
            "role": user['role'],
            "provider_id": provider_id,
            "name": user['name']
        }), 200

    return jsonify({"error": "Invalid email or password"}), 401

@app.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200

# --- PROVIDER & SLOTS ENDPOINTS ---
@app.route('/providers', methods=['GET'])
def get_providers():
    q = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()

    query = '''
        SELECT p.id as provider_id, u.name, p.category, p.bio, p.slot_minutes 
        FROM providers p 
        JOIN users u ON p.user_id = u.id 
        WHERE p.is_active = 1
    '''
    params = []

    if q:
        query += " AND (u.name LIKE ? OR p.bio LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])
    if category and category != 'All Categories':
        query += " AND p.category = ?"
        params.append(category)

    with get_db() as conn:
        providers = conn.cursor().execute(query, params).fetchall()

    return jsonify([dict(p) for p in providers]), 200

@app.route('/providers/<int:id>/slots', methods=['GET'])
def get_provider_slots(id):
    date_str = request.args.get('date') # YYYY-MM-DD
    if not date_str:
        return jsonify({"error": "Date parameter is required (YYYY-MM-DD)"}), 400

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    day_name = target_date.strftime('%A')

    with get_db() as conn:
        cursor = conn.cursor()
        provider = cursor.cursor().execute("SELECT * FROM providers WHERE id = ?", (id,)).fetchone() if hasattr(cursor, 'cursor') else cursor.execute("SELECT * FROM providers WHERE id = ?", (id,)).fetchone()
        if not provider:
            return jsonify({"error": "Provider not found"}), 404

        avail = cursor.execute("SELECT * FROM availability WHERE provider_id = ? AND day_of_week = ?", (id, day_name)).fetchall()
        
        # Fetch already booked/active slots for this provider on this date
        start_day_str = f"{date_str} 00:00:00"
        end_day_str = f"{date_str} 23:59:59"
        booked = cursor.execute('''
            SELECT start_time FROM appointments 
            WHERE provider_id = ? AND status = 'booked' AND start_time BETWEEN ? AND ?
        ''', (id, start_day_str, end_day_str)).fetchall()
        booked_times = {row['start_time'] for row in booked}

    slot_minutes = provider['slot_minutes'] or 30
    available_slots = []

    for a in avail:
        t_start = datetime.strptime(f"{date_str} {a['start_time']}", '%Y-%m-%d %H:%M')
        t_end = datetime.strptime(f"{date_str} {a['end_time']}", '%Y-%m-%d %H:%M')
        
        curr = t_start
        while curr + timedelta(minutes=slot_minutes) <= t_end:
            slot_start_str = curr.strftime('%Y-%m-%d %H:%M:%S')
            slot_end_str = (curr + timedelta(minutes=slot_minutes)).strftime('%Y-%m-%d %H:%M:%S')
            
            if slot_start_str not in booked_times and curr > datetime.now():
                available_slots.append({
                    "start_time": slot_start_str,
                    "end_time": slot_end_str
                })
            curr += timedelta(minutes=slot_minutes)

    return jsonify({"provider_id": id, "date": date_str, "slots": available_slots}), 200

@app.route('/provider/availability', methods=['PUT'])
def update_availability():
    if session.get('role') != 'provider':
        return jsonify({"error": "Forbidden: Providers only"}), 403

    data = request.get_json()
    user_id = session.get('user_id')
    
    with get_db() as conn:
        cursor = conn.cursor()
        p = cursor.execute("SELECT id FROM providers WHERE user_id = ?", (user_id,)).fetchone()
        if not p: return jsonify({"error": "Provider profile not found"}), 404
        provider_id = p['id']

        # Expecting JSON list of availability rules: e.g., [{"day_of_week": "Monday", "start_time": "09:00", "end_time": "17:00"}, ...]
        rules = data.get('availability', [])
        cursor.execute("DELETE FROM availability WHERE provider_id = ?", (provider_id,))
        for r in rules:
            cursor.execute("INSERT INTO availability (provider_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
                           (provider_id, r.get('day_of_week'), r.get('start_time'), r.get('end_time')))
        conn.commit()

    return jsonify({"message": "Availability updated successfully"}), 200

# --- APPOINTMENT BOOKING & MANAGEMENT ENDPOINTS ---
@app.route('/appointments', methods=['POST'])
def create_appointment():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or request.form
    customer_id = session['user_id']
    provider_id = data.get('provider_id')
    start_time_str = data.get('start_time') # Format: 'YYYY-MM-DD HH:MM:SS'
    notes = data.get('notes', '')

    if not provider_id or not start_time_str:
        return jsonify({"error": "provider_id and start_time are required"}), 400

    try:
        start_dt = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return jsonify({"error": "Invalid start_time format. Use YYYY-MM-DD HH:MM:SS"}), 400

    now = datetime.now()
    if start_dt < now:
        return jsonify({"error": "Cannot book appointments in the past"}), 400
    if start_dt > now + timedelta(days=30):
        return jsonify({"error": "Booking allowed only up to 30 days ahead"}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check monthly booking limit rule for customer (max 1 appointment per calendar month)
        year_month = start_dt.strftime('%Y-%m')
        existing_month_appt = cursor.execute('''
            SELECT id FROM appointments 
            WHERE customer_id = ? AND status = 'booked' AND strftime('%Y-%m', start_time) = ?
        ''', (customer_id, year_month)).fetchone()

        if existing_month_appt:
            return jsonify({"error": "Monthly limit reached: You already have an active booking this month."}), 400

        # Get slot duration from provider profile
        p = cursor.execute("SELECT slot_minutes FROM providers WHERE id = ?", (provider_id,)).fetchone()
        if not p: return jsonify({"error": "Provider not found"}), 404
        slot_minutes = p['slot_minutes'] or 30
        
        end_dt = start_dt + timedelta(minutes=slot_minutes)
        end_time_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')

        # Auto-generate unique booking reference e.g., APT-2026-000123
        rand_num = random.randint(100000, 999999)
        booking_ref = f"APT-{start_dt.year}-{rand_num}"

        try:
            cursor.execute('''
                INSERT INTO appointments (booking_ref, customer_id, provider_id, start_time, end_time, status, notes)
                VALUES (?, ?, ?, ?, ?, 'booked', ?)
            ''', (booking_ref, customer_id, provider_id, start_time_str, end_time_str, notes))
            
            appt_id = cursor.lastrowid
            
            # Record status history
            cursor.execute('''
                INSERT INTO appointment_history (appointment_id, old_status, new_status, changed_by, reason)
                VALUES (?, NULL, 'booked', ?, 'Initial booking created')
            ''', (appt_id, customer_id))
            
            conn.commit()
        except sqlite3.IntegrityError:
            # Enforces 409 Conflict as mandated in assignment requirements
            return jsonify({"error": "Conflict: This time slot is already booked."}), 409

    return jsonify({
        "message": "Appointment booked successfully",
        "booking_ref": booking_ref,
        "appointment_id": appt_id,
        "start_time": start_time_str,
        "end_time": end_time_str
    }), 201

@app.route('/appointments/mine', methods=['GET'])
def get_my_appointments():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session['user_id']
    role = session['role']

    with get_db() as conn:
        cursor = conn.cursor()
        if role == 'customer':
            query = '''
                SELECT a.*, u.name as provider_name, p.category 
                FROM appointments a 
                JOIN providers p ON a.provider_id = p.id 
                JOIN users u ON p.user_id = u.id 
                WHERE a.customer_id = ? 
                ORDER BY a.start_time DESC
            '''
            appts = cursor.execute(query, (user_id,)).fetchall()
        else:
            p = cursor.execute("SELECT id FROM providers WHERE user_id = ?", (user_id,)).fetchone()
            if not p: return jsonify([]), 200
            query = '''
                SELECT a.*, u.name as customer_name 
                FROM appointments a 
                JOIN users u ON a.customer_id = u.id 
                WHERE a.provider_id = ? 
                ORDER BY a.start_time DESC
            '''
            appts = cursor.execute(query, (p['id'],)).fetchall()

    return jsonify([dict(a) for a in appts]), 200

@app.route('/appointments/<int:id>/cancel', methods=['PATCH'])
def cancel_appointment(id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session['user_id']
    role = session['role']
    data = request.get_json() or request.form
    reason = data.get('reason', 'No reason provided')

    with get_db() as conn:
        cursor = conn.cursor()
        appt = cursor.execute("SELECT * FROM appointments WHERE id = ?", (id,)).fetchone()
        if not appt:
            return jsonify({"error": "Appointment not found"}), 404

        # Ownership or authorization check
        is_owner = (appt['customer_id'] == user_id)
        is_provider = False
        if role == 'provider':
            p = cursor.execute("SELECT id FROM providers WHERE user_id = ?", (user_id,)).fetchone()
            if p and p['id'] == appt['provider_id']:
                is_provider = True

        if not is_owner and not is_provider:
            return jsonify({"error": "Forbidden: You cannot cancel this appointment"}), 403

        if appt['status'] != 'booked':
            return jsonify({"error": f"Cannot cancel appointment with status: {appt['status']}"}), 400

        start_dt = datetime.strptime(appt['start_time'], '%Y-%m-%d %H:%M:%S')
        
        # Rule: cancel or reschedule only up to 2 hours before start time (applies to customer)
        if is_owner and not is_provider:
            if datetime.now() + timedelta(hours=2) > start_dt:
                return jsonify({"error": "Cancellations are only permitted up to 2 hours before the start time."}), 400

        cursor.execute("UPDATE appointments SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (id,))
        cursor.execute('''
            INSERT INTO appointment_history (appointment_id, old_status, new_status, changed_by, reason)
            VALUES (?, 'booked', 'cancelled', ?, ?)
        ''', (id, user_id, reason))
        conn.commit()

    return jsonify({"message": "Appointment cancelled successfully"}), 200

@app.route('/appointments/<int:id>/reschedule', methods=['PATCH'])
def reschedule_appointment(id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session['user_id']
    data = request.get_json() or request.form
    new_start_str = data.get('start_time')

    if not new_start_str:
        return jsonify({"error": "new start_time is required"}), 400

    try:
        new_start_dt = datetime.strptime(new_start_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD HH:MM:SS"}), 400

    now = datetime.now()
    if new_start_dt < now:
        return jsonify({"error": "Cannot reschedule into the past"}), 400
    if new_start_dt > now + timedelta(days=30):
        return jsonify({"error": "Rescheduling allowed only up to 30 days ahead"}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        appt = cursor.execute("SELECT * FROM appointments WHERE id = ?", (id,)).fetchone()
        if not appt: return jsonify({"error": "Appointment not found"}), 404

        if appt['customer_id'] != user_id:
            return jsonify({"error": "Forbidden: Only the booking customer can reschedule"}), 403

        if appt['status'] != 'booked':
            return jsonify({"error": "Can only reschedule active 'booked' appointments"}), 400

        old_start_dt = datetime.strptime(appt['start_time'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() + timedelta(hours=2) > old_start_dt:
            return jsonify({"error": "Rescheduling is only permitted up to 2 hours before the original start time."}), 400

        slot_duration = 30
        p = cursor.execute("SELECT slot_minutes FROM providers WHERE id = ?", (appt['provider_id'],)).fetchone()
        if p: slot_duration = p['slot_minutes']

        new_end_str = (new_start_dt + timedelta(minutes=slot_duration)).strftime('%Y-%m-%d %H:%M:%S')

        try:
            cursor.execute('''
                UPDATE appointments 
                SET start_time = ?, end_time = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (new_start_str, new_end_str, id))

            cursor.execute('''
                INSERT INTO appointment_history (appointment_id, old_status, new_status, changed_by, reason)
                VALUES (?, 'booked', 'booked', ?, 'Rescheduled appointment time')
            ''', (id, user_id))
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "Conflict: New target slot is already booked."}), 409

    return jsonify({"message": "Appointment rescheduled successfully", "new_start_time": new_start_str}), 200

# --- PROVIDER SPECIFIC ENDPOINTS ---
@app.route('/provider/appointments', methods=['GET'])
def get_provider_appointments():
    if session.get('role') != 'provider':
        return jsonify({"error": "Forbidden: Providers only"}), 403

    user_id = session['user_id']
    date_filter = request.args.get('date')
    status_filter = request.args.get('status')
    page = int(request.args.get('page', 1))
    limit = 10
    offset = (page - 1) * limit

    with get_db() as conn:
        cursor = conn.cursor()
        p = cursor.execute("SELECT id FROM providers WHERE user_id = ?", (user_id,)).fetchone()
        if not p: return jsonify({"error": "Provider not found"}), 404
        provider_id = p['id']

        query = '''
            SELECT a.*, u.name as customer_name, u.email as customer_email 
            FROM appointments a 
            JOIN users u ON a.customer_id = u.id 
            WHERE a.provider_id = ?
        '''
        params = [provider_id]

        if date_filter:
            query += " AND a.start_time LIKE ?"
            params.append(f"{date_filter}%")
        if status_filter:
            query += " AND a.status = ?"
            params.append(status_filter)

        query += " ORDER BY a.start_time ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        appts = cursor.execute(query, params).fetchall()

    return jsonify([dict(a) for a in appts]), 200

@app.route('/appointments/<int:id>/status', methods=['PATCH'])
def update_appointment_status(id):
    if session.get('role') != 'provider':
        return jsonify({"error": "Forbidden: Providers only"}), 403

    user_id = session['user_id']
    data = request.get_json() or request.form
    new_status = data.get('status')
    reason = data.get('reason', 'Status updated by provider')

    if new_status not in ('completed', 'no_show', 'cancelled'):
        return jsonify({"error": "Invalid status value"}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        p = cursor.execute("SELECT id FROM providers WHERE user_id = ?", (user_id,)).fetchone()
        if not p: return jsonify({"error": "Provider profile not found"}), 404

        appt = cursor.execute("SELECT * FROM appointments WHERE id = ? AND provider_id = ?", (id, p['id'])).fetchone()
        if not appt:
            return jsonify({"error": "Appointment not found or unauthorized"}), 404

        old_status = appt['status']
        cursor.execute("UPDATE appointments SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_status, id))
        
        cursor.execute('''
            INSERT INTO appointment_history (appointment_id, old_status, new_status, changed_by, reason)
            VALUES (?, ?, ?, ?, ?)
        ''', (id, old_status, new_status, user_id, reason))
        conn.commit()

    return jsonify({"message": f"Appointment status updated to {new_status}"}), 200

@app.route('/dashboard/summary', methods=['GET'])
def provider_dashboard_summary():
    if session.get('role') != 'provider':
        return jsonify({"error": "Forbidden: Providers only"}), 403

    user_id = session['user_id']
    today_str = datetime.now().strftime('%Y-%m-%d')

    with get_db() as conn:
        cursor = conn.cursor()
        p = cursor.execute("SELECT id FROM providers WHERE user_id = ?", (user_id,)).fetchone()
        if not p: return jsonify({"error": "Provider not found"}), 404
        provider_id = p['id']

        # Today's schedule count
        today_count = cursor.execute('''
            SELECT COUNT(*) as count FROM appointments 
            WHERE provider_id = ? AND start_time LIKE ? AND status = 'booked'
        ''', (provider_id, f"{today_str}%")).fetchone()['count']

        # Counts by status
        status_counts = cursor.execute('''
            SELECT status, COUNT(*) as count FROM appointments 
            WHERE provider_id = ? GROUP BY status
        ''', (provider_id,)).fetchall()
        
        counts_dict = {row['status']: row['count'] for row in status_counts}

        # Busiest days using SQL GROUP BY
        busiest_days = cursor.execute('''
            SELECT substr(start_time, 1, 10) as date, COUNT(*) as bookings_count 
            FROM appointments 
            WHERE provider_id = ? 
            GROUP BY date 
            ORDER BY bookings_count DESC 
            LIMIT 5
        ''', (provider_id,)).fetchall()

    return jsonify({
        "today_scheduled": today_count,
        "status_breakdown": counts_dict,
        "busiest_days": [dict(d) for d in busiest_days]
    }), 200

if __name__ == '__main__':
    app.run(debug=True)