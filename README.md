# AI based Online Exam Proctoring System
The AI-Powered Online Proctoring System is a state-of-the-art solution designed to ensure the integrity and security of online exams. By leveraging advanced artificial intelligence and machine learning techniques, this system provides real-time monitoring and analysis of test-takers to detect and prevent cheating behaviors. It is ideal for educational institutions, certification bodies, and organizations conducting remote assessments.

## Key Features
1. **Real-Time Video Monitoring:** Utilizes webcam feeds to monitor test-takers in real-time, ensuring they adhere to exam rules.
2. **Face Detection and Recognition:** Detects and verifies the identity of the test-taker using facial recognition technology.
3. **Person Counting:** Uses OpenCV Haar Cascades to count the number of faces in the frame and flag unauthorized persons.
4. **Object Detection:** Identifies prohibited objects (e.g., phones, books) in the test environment using YOLO.
5. **User Notifications:** Users can view real-time notifications about violations or suspicious activities.
6. **Secure Exam Environment:** Restricts access to other applications, websites, or system resources during the exam.

## Technologies Used
1. **AI/ML Frameworks:** TensorFlow, DeepFace, OpenCV
2. **Face Recognition:** dlib, face_recognition
3. **Object Detection:** YOLO (You Only Look Once)
4. **Web Development:** Flask (Backend), HTML, CSS, JS (Frontend)
5. **Database:** MySQL
