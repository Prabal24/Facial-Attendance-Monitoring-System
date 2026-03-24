import cv2
import numpy as np
import os
import mysql.connector
from db_config import get_db_connection

MODEL_PATH = "trainer/face_model.yml"


def mark_attendance_db(student_id, session_id=None, subject=None, marked_by=None):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # 1️⃣ CHECK IF student_id EXISTS (PREVENT FOREIGN KEY ERROR)
    cur.execute("SELECT id FROM students WHERE id=%s", (student_id,))
    valid = cur.fetchone()
    if not valid:
        print(f"❌ ERROR: Invalid Student ID detected → {student_id}")
        cur.close()
        conn.close()
        return

    # 2️⃣ CHECK IF ALREADY MARKED FOR THIS SESSION
    cur.execute(
        "SELECT id FROM attendance WHERE session_id=%s AND student_id=%s",
        (session_id, student_id),
    )
    exists = cur.fetchone()
    if exists:
        print("✔ Already marked earlier for this session.")
        cur.close()
        conn.close()
        return

    # 3️⃣ INSERT RECORD SAFELY
    cur.execute(
        """
        INSERT INTO attendance 
        (student_id, attendance_date, attendance_time, status, subject, marked_by, session_id)
        VALUES (%s, CURDATE(), CURTIME(), %s, %s, %s, %s)
        """,
        (student_id, "Present", subject, marked_by, session_id),
    )
    conn.commit()

    cur.close()
    conn.close()
    print(f"🎉 ATTENDANCE MARKED → Student ID {student_id}")


def start_camera(session_id=None, subject=None, marked_by=None):
    # Check model exists
    if not os.path.exists(MODEL_PATH):
        print("❌ Model file not found:", MODEL_PATH)
        return

    # Load recognizer
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(MODEL_PATH)

    # Face detector
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    # Open camera
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        print("❌ ERROR: Could not open camera.")
        return

    print("📷 Camera started. Press Q to exit manually.")
    attendance_done = False

    while True:
        success, frame = cam.read()
        if not success:
            print("⚠ Warning: Could not read frame from camera.")
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)

        for (x, y, w, h) in faces:
            face = gray[y:y + h, x:x + w]

            try:
                predicted_id, confidence = recognizer.predict(face)
            except Exception as e:
                print("❌ Recognition error:", e)
                continue

            # LBPH: LOWER confidence = better match
            if confidence < 70:
                print(f"Detected Model ID = {predicted_id}, Confidence = {int(confidence)}")

                # Validate ID exists before marking
                mark_attendance_db(
                    predicted_id, session_id=session_id, subject=subject, marked_by=marked_by
                )

                attendance_done = True

                # show green box
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, f"ID: {predicted_id}", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                # Show for a short moment then exit
                cv2.imshow("Mark Attendance", frame)
                cv2.waitKey(700)
                
                cam.release()
                cv2.destroyAllWindows()
                print("✔ Attendance recorded. Camera closed.")
                return

            else:
                # Unknown face → red box
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                cv2.putText(frame, "Unknown", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        cv2.imshow("Mark Attendance", frame)

        # Exit manually
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Camera closed manually.")
            break

    cam.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    import sys
    
    session_id = None
    subject = None
    marked_by = None

    if len(sys.argv) >= 2:
        session_id = int(sys.argv[1])

    if len(sys.argv) >= 3:
        subject = sys.argv[2]

    if len(sys.argv) >= 4:
        marked_by = sys.argv[3]

    start_camera(session_id=session_id, subject=subject, marked_by=marked_by)
