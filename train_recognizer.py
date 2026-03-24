import cv2
import os
import numpy as np

UPLOAD_PATH = "static/uploads"
MODEL_PATH = "trainer/face_model.yml"


def train_model():
    # LBPH Face recognizer
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    face_samples = []
    ids = []

    if not os.path.exists(UPLOAD_PATH):
        print("❌ Folder not found:", UPLOAD_PATH)
        return

    print("\n📌 Reading images from:", UPLOAD_PATH)

    for filename in os.listdir(UPLOAD_PATH):
        if filename.lower().endswith((".jpg", ".png", ".jpeg")):

            student_id_txt = os.path.splitext(filename)[0]

            # must be integer id
            try:
                student_id = int(student_id_txt)
            except:
                print(f"⚠ Skipped (Filename not a valid id) → {filename}")
                continue

            img_path = os.path.join(UPLOAD_PATH, filename)
            img = cv2.imread(img_path)

            if img is None:
                print("⚠ Cannot read:", filename)
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)

            if len(faces) == 0:
                print(f"⚠ No face detected in {filename}")
                continue

            for (x, y, w, h) in faces:
                face_samples.append(gray[y:y + h, x:x + w])
                ids.append(student_id)

    if len(face_samples) == 0:
        print("\n❌ No valid face samples found. Training failed.")
        return

    ids = np.array(ids)

    # ensure trainer folder exists
    os.makedirs("trainer", exist_ok=True)

    print("\n⏳ Training LBPH model...")
    recognizer.train(face_samples, ids)

    recognizer.write(MODEL_PATH)
    print("\n✔ TRAINING COMPLETE!")
    print("Model saved at:", MODEL_PATH)


if __name__ == "__main__":
    train_model()
