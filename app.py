from flask import Flask, render_template, request, redirect, url_for, session, flash, get_flashed_messages
from db_config import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash
import os
import subprocess
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_PATH = "static/uploads"
MODEL_PATH = "trainer/face_model.yml"

# ------------------------------
# Helper: class options
# ------------------------------
CLASS_OPTIONS = ["BCA-1", "BCA-2", "BCA-3", "MCA-1", "MCA-2", "MCA-3"]

# -------------------------------------------------
# INDEX
# -------------------------------------------------
@app.route("/")
def index():
    if "role" in session:
        return redirect("/home")
    return redirect("/login")

# -------------------------------------------------
# LOGIN
# -------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    success = None

    flashed = get_flashed_messages(category_filter=["success"])
    if flashed:
        success = True

    if request.method == "POST":
        role = request.form.get("role")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not role:
            error = "Please select a role."
            return render_template("login.html", error=error, success=success)

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)

        if role == "teacher":
            cur.execute("SELECT * FROM teachers WHERE username=%s", (username,))
            teacher = cur.fetchone()
            conn.close()

            if teacher and check_password_hash(teacher["password"], password):
                session["role"] = "teacher"
                session["name"] = teacher["name"]
                session["username"] = teacher["username"]
                return redirect("/home")
            error = "Invalid Teacher Credentials"

        elif role == "student":
            cur.execute("SELECT * FROM students WHERE roll_no=%s", (username,))
            student = cur.fetchone()
            conn.close()

            if student and check_password_hash(student["password"], password):
                session["role"] = "student"
                session["name"] = student["name"]
                session["student_id"] = student["id"]
                session["username"] = student["roll_no"]
                # store student's class for convenience (may be None)
                session["class_name"] = student.get("class_name")
                return redirect("/home")
            error = "Invalid Student Credentials"

    return render_template("login.html", error=error, success=success)

# -------------------------------------------------
# HOME
# -------------------------------------------------
@app.route("/home")
def home():
    if "role" not in session:
        return redirect("/login")

    role = session["role"]
    name = session["name"]

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    recent_sessions = []
    if role == "teacher":
        cur.execute("SELECT * FROM sessions ORDER BY id DESC LIMIT 5")
        recent_sessions = cur.fetchall()
    elif role == "student":
        # For student show recent sessions for their class (limit 5)
        class_name = session.get("class_name")
        if class_name:
            cur.execute("SELECT * FROM sessions WHERE class_name=%s ORDER BY id DESC LIMIT 5", (class_name,))
            recent_sessions = cur.fetchall()

    conn.close()
    return render_template("home.html", name=name, role=role, recent_sessions=recent_sessions)

# -------------------------------------------------
# TEACHER REGISTER
# -------------------------------------------------
@app.route("/teacher_register", methods=["GET", "POST"])
def teacher_register():
    errors = []

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one number.")
        special = "!@#$%^&*()-_=+[]{};:,<.>/?|"
        if not any(c in special for c in password):
            errors.append("Password must contain at least one special character.")
        if password != confirm_password:
            errors.append("Passwords do not match.")

        if errors:
            return render_template("teacher_register.html", error=errors)

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM teachers WHERE username=%s", (username,))
        exists = cur.fetchone()
        if exists:
            conn.close()
            errors.append("This username already exists.")
            return render_template("teacher_register.html", error=errors)

        hashed_pass = generate_password_hash(password)

        cur_ins = conn.cursor()
        cur_ins.execute(
            "INSERT INTO teachers (username, password, name) VALUES (%s, %s, %s)",
            (username, hashed_pass, name)
        )
        conn.commit()
        cur_ins.close()
        conn.close()

        flash("Registration successful! You may login now.", "success")
        return redirect("/login")

    return render_template("teacher_register.html")

# -------------------------------------------------
# ADD STUDENT (teacher assigns class_name)
# -------------------------------------------------
@app.route("/add_student", methods=["GET", "POST"])
def add_student():
    if "role" not in session or session["role"] != "teacher":
        return redirect("/login")

    msg = None
    error = None

    if request.method == "POST":
        roll_no = request.form.get("roll_no", "").strip()
        name = request.form.get("name", "").strip()
        course = request.form.get("course")
        semester = request.form.get("semester")
        class_name = request.form.get("class_name")
        photo = request.files.get("photo")

        if not roll_no or not name or not course or not semester or not class_name or not photo:
            error = "All fields are required!"
            return render_template("add_student.html", msg=None, error=error, class_options=CLASS_OPTIONS)

        os.makedirs(UPLOAD_PATH, exist_ok=True)

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM students WHERE roll_no=%s", (roll_no,))
        if cur.fetchone():
            conn.close()
            error = "Student already exists!"
            return render_template("add_student.html", msg=None, error=error, class_options=CLASS_OPTIONS)

        hashed_pass = generate_password_hash(roll_no)

        # Insert student with class_name
        cur_ins = conn.cursor()
        cur_ins.execute("""
            INSERT INTO students (roll_no, name, course, semester, class_name, photo_filename, password)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (roll_no, name, course, semester, class_name, None, hashed_pass))
        conn.commit()

        student_id = cur_ins.lastrowid

        # Save actual photo file as {student_id}.jpg
        filename = f"{student_id}.jpg"
        save_path = os.path.join(UPLOAD_PATH, filename)
        photo.save(save_path)

        # Update student's photo_filename with final filename
        cur_upd = conn.cursor()
        cur_upd.execute("UPDATE students SET photo_filename=%s WHERE id=%s", (filename, student_id))
        conn.commit()

        # Close cursors & connection
        try:
            cur_upd.close()
        except:
            pass
        try:
            cur_ins.close()
        except:
            pass
        try:
            cur.close()
        except:
            pass
        conn.close()

        # start train_model.py in background (non-blocking)
        try:
            subprocess.Popen(["python", "train_model.py"])
        except Exception as e:
            print("Failed to start train_model.py:", e)

        msg = "✔ Student added successfully! Model training started in background."
        return render_template("add_student.html", msg=msg, error=None, class_options=CLASS_OPTIONS)

    return render_template("add_student.html", msg=None, error=None, class_options=CLASS_OPTIONS)

# -------------------------------------------------
# CREATE SESSION
# -------------------------------------------------
@app.route("/create_session", methods=["GET", "POST"])
def create_session():
    if "role" not in session or session["role"] != "teacher":
        return redirect("/login")

    if request.method == "POST":
        class_name = request.form.get("class_name")
        subject = request.form.get("subject")
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")

        if not class_name or not subject or not start_time or not end_time:
            return render_template("create_session.html", error="All fields are required!", class_options=CLASS_OPTIONS)

        if start_time >= end_time:
            return render_template("create_session.html", error="End time must be greater than start time!", class_options=CLASS_OPTIONS)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sessions (class_name, subject, start_time, end_time, teacher_name) VALUES (%s, %s, %s, %s, %s)",
            (class_name, subject, start_time, end_time, session["name"])
        )
        conn.commit()
        conn.close()

        return redirect("/view_sessions")

    return render_template("create_session.html", class_options=CLASS_OPTIONS)

# -------------------------------------------------
# STOP SESSION
# -------------------------------------------------
@app.route("/stop_session/<int:session_id>", methods=["POST"])
def stop_session(session_id):
    if "role" not in session or session["role"] != "teacher":
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE sessions SET end_time=%s WHERE id=%s", (datetime.now(), session_id))
    conn.commit()
    conn.close()

    flash("Session stopped successfully!", "success")
    return redirect("/view_sessions")

# -------------------------------------------------
# DELETE SESSION
# -------------------------------------------------
@app.route("/delete_session/<int:session_id>", methods=["POST"])
def delete_session(session_id):
    if "role" not in session or session["role"] != "teacher":
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    # Delete attendance first
    cur.execute("DELETE FROM attendance WHERE session_id=%s", (session_id,))

    # Delete session
    cur.execute("DELETE FROM sessions WHERE id=%s", (session_id,))
    conn.commit()
    conn.close()

    flash("Session deleted successfully!", "success")
    return redirect("/view_sessions")

# -------------------------------------------------
# VIEW SESSIONS (teacher)
# -------------------------------------------------
@app.route("/view_sessions")
def view_sessions():
    if "role" not in session:
        return redirect("/login")

    selected_class = request.args.get("class_name", "")   # class filter

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    if selected_class:
        cur.execute("SELECT * FROM sessions WHERE class_name=%s ORDER BY id DESC", (selected_class,))
    else:
        cur.execute("SELECT * FROM sessions ORDER BY id DESC")

    rows = cur.fetchall()
    conn.close()

    now = datetime.now()
    for s in rows:
        if s["start_time"] is None:
            s["status"] = "pending"
        elif s["end_time"] > now:
            s["status"] = "active"
        else:
            s["status"] = "ended"

    return render_template(
        "view_sessions.html",
        sessions=rows,
        selected_class=selected_class,
        class_options=CLASS_OPTIONS,
        now=now
    )

# -------------------------------------------------
# VIEW STUDENTS (class filter + search + delete)
# -------------------------------------------------
@app.route("/view_students", methods=["GET", "POST"])
def view_students():
    if "role" not in session or session["role"] != "teacher":
        return redirect("/login")

    class_name = request.args.get("class", "")
    search = request.args.get("search", "").strip()

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    query = "SELECT * FROM students WHERE 1=1"
    params = []

    if class_name:
        query += " AND class_name=%s"
        params.append(class_name)

    if search:
        query += " AND (roll_no LIKE %s OR name LIKE %s)"
        params.append("%" + search + "%")
        params.append("%" + search + "%")

    cur.execute(query, tuple(params))
    students = cur.fetchall()
    conn.close()

    return render_template(
        "view_students.html",
        students=students,
        class_options=CLASS_OPTIONS,
        selected_class=class_name,
        search=search
    )

@app.route("/delete_student/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    if "role" not in session or session["role"] != "teacher":
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    cur2 = conn.cursor(dictionary=True)
    cur2.execute("SELECT photo_filename FROM students WHERE id=%s", (student_id,))
    row = cur2.fetchone()

    if row and row.get("photo_filename"):
        file_path = os.path.join(UPLOAD_PATH, row["photo_filename"])
        if os.path.exists(file_path):
            os.remove(file_path)

    cur.execute("DELETE FROM students WHERE id=%s", (student_id,))
    conn.commit()
    conn.close()
    flash("Student deleted successfully!", "success")
    return redirect("/view_students")

# -----------------------------------------------
# START ATTENDANCE (teacher-run; runs full session camera scan)
# -------------------------------------------------
@app.route("/start_attendance/<int:session_id>")
def start_attendance(session_id):
    if "role" not in session or session["role"] != "teacher":
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM sessions WHERE id=%s", (session_id,))
    s = cur.fetchone()
    conn.close()

    if not s:
        flash("Session not found.", "error")
        return redirect("/view_sessions")

    subject = s.get("subject", "")
    marked_by = session.get("name", "")

    # Run the attendance script (server-side)
    try:
        subprocess.Popen(["python", "mark_attendance.py", str(session_id), subject, marked_by])
        flash("Attendance process started (server).", "success")
    except Exception as e:
        flash(f"Error launching attendance: {e}", "error")

    return redirect("/view_sessions")

# -------------------------------------------------
# MARK ATTENDANCE (student-run; they mark their own attendance via camera)
# -------------------------------------------------
@app.route("/mark_attendance/<int:session_id>")
def mark_attendance_route(session_id):
    if "role" not in session or session["role"] != "student":
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM sessions WHERE id=%s", (session_id,))
    s = cur.fetchone()
    conn.close()

    if not s:
        flash("Session not found.", "error")
        return redirect("/student_sessions")

    # Start camera script in background so Flask doesn't block (use Popen)
    try:
        subprocess.Popen(["python", "mark_attendance.py", str(session_id), s.get("subject", ""), session.get("name", "")])
        flash("Attendance marking started. Please allow camera (if prompted).", "success")
    except Exception as e:
        flash(f"Error running camera: {e}", "error")

    return redirect("/student_sessions")

# optional helper route — a small page if you want a 'Mark Attendance' landing page
@app.route("/mark_attendance_page/<int:session_id>")
def mark_attendance_page(session_id):
    # This renders a small page telling student to click start (if you want)
    if "role" not in session or session["role"] != "student":
        return redirect("/login")
    return render_template("mark_attendance_page.html", session_id=session_id)

# -------------------------------------------------
# STUDENT: view sessions for student's class (and attendance status)
# -------------------------------------------------
@app.route("/student_sessions")
def student_sessions():
    if "role" not in session or session["role"] != "student":
        return redirect("/login")

    student_id = session.get("student_id")
    class_name = session.get("class_name")

    # Fetch class_name if missing
    if not class_name and student_id:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT class_name FROM students WHERE id=%s", (student_id,))
        r = cur.fetchone()
        conn.close()

        class_name = r.get("class_name") if r else None
        session["class_name"] = class_name

    if not class_name:
        flash("No class assigned to your profile. Contact teacher.", "error")
        return redirect("/home")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT * FROM sessions WHERE class_name=%s ORDER BY id DESC", (class_name,))
    sessions = cur.fetchall()

    now = datetime.now()

    for s in sessions:
        s_id = s["id"]

        # Convert end_time (string -> datetime)
        end_time = s.get("end_time")
        if isinstance(end_time, str):
            try:
                end_time = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            except:
                end_time = None

        # Check attendance for this student
        cur.execute("SELECT * FROM attendance WHERE session_id=%s AND student_id=%s",
                    (s_id, student_id))
        att = cur.fetchone()

        if att:
            s["att_status"] = "Present"
            s["att_time"] = att.get("attendance_time")
        else:
            # No attendance found
            if end_time and end_time < now:
                s["att_status"] = "Missed"
            else:
                s["att_status"] = "Not Marked"

    cur.close()
    conn.close()

    return render_template("student_sessions.html", sessions=sessions, now=now)

# -------------------------------------------------
# STUDENT: view own attendance overview (overall + subject-wise)
# -------------------------------------------------
@app.route("/student_attendance")
def student_attendance():
    if "role" not in session or session["role"] != "student":
        return redirect("/login")

    student_id = session.get("student_id")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # all attendance rows for student (with session subject & class)
    cur.execute("""
        SELECT a.*, s.subject, s.class_name, s.end_time
        FROM attendance a
        LEFT JOIN sessions s ON a.session_id = s.id
        WHERE a.student_id=%s
        ORDER BY a.attendance_date DESC, a.attendance_time DESC
    """, (student_id,))
    attendance_rows = cur.fetchall()

    # student's class
    cur.execute("SELECT class_name FROM students WHERE id=%s", (student_id,))
    cls = cur.fetchone()
    class_name = cls.get("class_name") if cls else None

    now = datetime.now()

    # total past sessions for class
    total_sessions = 0
    if class_name:
        cur.execute("SELECT COUNT(*) AS cnt FROM sessions WHERE class_name=%s AND end_time < %s", (class_name, now))
        r = cur.fetchone()
        total_sessions = r.get("cnt", 0) if r else 0

    # present count in past sessions (distinct session_id where session ended in past)
    cur.execute("""
        SELECT COUNT(DISTINCT a.session_id) AS present_count
        FROM attendance a
        JOIN sessions s ON a.session_id = s.id
        WHERE a.student_id=%s AND s.class_name=%s AND s.end_time < %s
    """, (student_id, class_name, now))
    r = cur.fetchone()
    present_count = r.get("present_count", 0) if r else 0

    missed_count = max(0, total_sessions - present_count)

    # subject-wise stats for past sessions
    cur.execute("""
        SELECT s.subject,
               COUNT(*) AS subject_total,
               SUM(
                   CASE WHEN EXISTS (
                       SELECT 1 FROM attendance a
                       WHERE a.session_id = s.id AND a.student_id = %s
                   ) THEN 1 ELSE 0 END
               ) AS present_for_subject
        FROM sessions s
        WHERE s.class_name = %s AND s.end_time < %s
        GROUP BY s.subject
    """, (student_id, class_name, now))
    subject_stats = cur.fetchall()

    conn.close()

    return render_template(
        "student_attendance.html",
        attendance=attendance_rows,
        total_sessions=total_sessions,
        present_count=present_count,
        missed_count=missed_count,
        subject_stats=subject_stats,
        class_name=class_name
    )

# -------------------------------------------------
# VIEW ATTENDANCE (teacher or student can view session attendance)
# -------------------------------------------------
@app.route("/view_attendance/<int:session_id>")
def view_attendance(session_id):
    if "role" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT a.*, s.roll_no, s.name AS student_name
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE a.session_id=%s
        ORDER BY a.attendance_time DESC
    """, (session_id,))
    data = cur.fetchall()

    cur.execute("SELECT * FROM sessions WHERE id=%s", (session_id,))
    session_info = cur.fetchone()

    conn.close()
    return render_template("view_attendance.html", attendance=data, session_id=session_id, session_info=session_info)

# -------------------------------------------------
# LOGOUT
# -------------------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# -------------------------------------------------
# RUN
# -------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
