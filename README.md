# Flask Appointment Booking System

## Live Application URL
- [https://appointment-booking-system-8nbr.onrender.com](https://appointment-booking-system-8nbr.onrender.com)

## GitHub Repository
- [https://github.com/sandhya062001-ux/Project1](https://github.com/sandhya062001-ux/Project1)

## Manual Testing Checklist
- [ ] **User Registration**: Register a new user account successfully via `/register`.
- [ ] **Login Failure**: Attempt login with incorrect credentials (returns `401 Unauthorized`).
- [ ] **Role Restrictions**: Verify regular customers cannot access restricted provider endpoints.
- [ ] **Past Booking Validation**: Attempt booking a date/time in the past (returns `400 Bad Request`).
- [ ] **30-Day Window Validation**: Attempt booking more than 30 days ahead (returns `400 Bad Request`).
- [ ] **Double-Booking Protection**: Send two simultaneous requests for the exact same appointment slot (Enforces database-level unique constraint: first succeeds with `200 OK`, second returns `409 Conflict`).
- [ ] **Cancellation Buffer Rule**: Verify appointment cancellation is blocked if attempted within 2 hours of the start time.

## Running Automated Tests Locally
Run the `pytest` test suite using:
```bash
python -m pytest