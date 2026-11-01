import pytest
from app import app, init_db, DB_FILE
import sqlite3

@pytest.fixture
def client():
    app.config['TESTING'] = True
    init_db()
    with app.test_client() as client:
        yield client

def test_index_page(client):
    response = client.get('/')
    assert response.status_code == 200

def test_login_failure(client):
    response = client.post('/login', data={'username': 'wrong@test.com', 'password': 'wrongpassword'}, follow_redirects=True)
    assert response.status_code == 401
    assert b"Invalid Username or Password" in response.data

def test_booking_in_past(client):
    response = client.post('/book', data={'slot_time': '2020-01-01 10:00:00'})
    assert response.status_code == 400
    assert b"Cannot book appointments in the past" in response.data

def test_booking_beyond_30_days(client):
    response = client.post('/book', data={'slot_time': '2099-12-31 10:00:00'})
    assert response.status_code == 400
    assert b"Booking allowed only up to 30 days ahead" in response.data

def test_double_booking_conflict(client):
    slot = '2026-11-25 14:00:00'
    
    # First booking succeeds
    res1 = client.post('/book', data={'slot_time': slot})
    assert res1.status_code == 200
    
    # Second booking for the exact same slot returns 409 Conflict
    res2 = client.post('/book', data={'slot_time': slot})
    assert res2.status_code == 409
    assert b"Conflict" in res2.data

def test_cancel_too_late(client):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO appointments (id, slot_time) VALUES (999, '2026-11-01 09:00:00')")
        conn.commit()
        
    response = client.post('/cancel/999')
    assert response.status_code == 400
    assert b"Cannot cancel or reschedule within 2 hours" in response.data