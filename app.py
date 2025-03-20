from flask import Flask, render_template, request, redirect, flash, jsonify, session, url_for, session, send_file, Response, stream_with_context, make_response
from flask_socketio import SocketIO, emit, join_room, leave_room
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import os
import base64
from io import BytesIO
from uuid import uuid4
import uuid  # For generating unique session id
exam_link = str(uuid.uuid4())
from datetime import datetime
import io
import cv2
import numpy as np
import re
import logging
import time
import json
from deepface import DeepFace
from concurrent.futures import ThreadPoolExecutor
from ultralytics import YOLO
from PIL import Image
import tensorflow as tf
import os
import warnings
from object_detect import ExamProctor
import dlib
import datetime
import face_recognition
# Add this import at the top of your file
import bcrypt

from flask_wtf.csrf import CSRFProtect












app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key')  # Use environment variable for secret key


# MySQL Database Configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': ''
}


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}




@app.route('/')
def home():
    return render_template('student/home.html')


@app.template_filter('b64encode')
def b64encode_filter(data):
    if data is None:
        return ''
    return base64.b64encode(data).decode('utf-8')



@app.route('/signup', methods=['GET', 'POST'])
def stu_signup():
    if request.method == 'POST':
        fullname = request.form['fullname']
        email = request.form['email']
        username = request.form['username']
        contact = request.form['contact']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        profile_pic = request.files.get('profile_pic')  # Get uploaded file

        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "signup_error")
            return redirect(url_for('stu_signup'))

        if len(password) < 5 or len(password) > 12:
            flash("Password must be between 5 and 12 characters.", "signup_error")
            return redirect(url_for('stu_signup'))
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        connection = None
        try:
            connection = mysql.connector.connect(**db_config)
            cursor = connection.cursor()

            # Insert user into users table
            user_query = """
                INSERT INTO users (fullname, email, username, contact, password)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(user_query, (fullname, email, username, contact, hashed_password))
            user_id = cursor.lastrowid  # Get the newly created user's ID

            # Process profile picture
            image_data = None
            if profile_pic and allowed_file(profile_pic.filename):
                image_data = profile_pic.read()

            # Insert into student_profiles
            profile_query = """
                INSERT INTO student_profiles (id, profile_image)
                VALUES (%s, %s)
            """
            cursor.execute(profile_query, (user_id, image_data))

            connection.commit()

            flash("Account created successfully. Please log in.", "signup_success")
            return redirect(url_for('stu_login'))

        except mysql.connector.Error as err:
            connection.rollback()  # Rollback on error
            flash(f"Error: {err}", "signup_error")
            return redirect(url_for('stu_signup'))
        finally:
            if connection.is_connected():
                cursor.close()
                connection.close()

    return render_template('student/stu_signup.html')


@app.route('/login', methods=['GET', 'POST'])
def stu_login():
    exam_link = request.args.get('exam_link')  # Get exam_link from query params
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        exam_link = request.form.get('exam_link')  # From hidden input

        try:
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            
            # Authenticate user
            cursor.execute("SELECT user_id, username, password, session_id FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user[2], password):
                # Check if user already has an active session
                if user[3] is not None:
                    # If there's any active session, prevent login
                    flash("This account is already in use. Please log out from other sessions first.", "danger")
                    return redirect(url_for('stu_login', exam_link=exam_link))
                
                # Create new session
                session_id = str(uuid.uuid4())
                session['user_id'] = user[0]
                session['username'] = user[1]
                
                # Update the session_id in the database
                cursor.execute("UPDATE users SET session_id = %s WHERE user_id = %s", (session_id, user[0]))
                conn.commit()
                
                # Set a cookie with the session_id
                response = make_response(redirect(url_for('studash') if not exam_link else url_for('exam', exam_link=exam_link)))
                response.set_cookie('session_id', session_id, max_age=86400)  # Expires in 24 hours
                
                return response
            else:
                flash("Invalid credentials!", "danger")
                return redirect(url_for('stu_login', exam_link=exam_link))
            
        except mysql.connector.Error as err:
            flash(f"Database error: {err}", "danger")
            return redirect(url_for('stu_login', exam_link=exam_link))
        
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    
    # For GET requests, pass exam_link to the template
    return render_template('student/stu_login.html', exam_link=exam_link)

# for login session
# Add this function to your application
def verify_session(user_id, session_id):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        cursor.execute("SELECT session_id FROM users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        
        if result and result[0] == session_id:
            return True
        return False
        
    except mysql.connector.Error:
        return False
    
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn and conn.is_connected():
            conn.close()


@app.route('/studash')
def studash():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('stu_login'))

    db = None
    cursor = None
    profile_image = None
    fullname = None

    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor()

        # Fetch full name from users table
        cursor.execute("SELECT fullname FROM users WHERE user_id = %s", (user_id,))
        user_info = cursor.fetchone()
        if user_info:
            fullname = user_info[0]

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM student_profiles WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        if result and result[0]:
            profile_image = base64.b64encode(result[0]).decode('utf-8')  # Convert binary to base64 for HTML

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return render_template('student/studash.html', fullname=fullname, profile_image=profile_image)  


@app.route('/history')
def history():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('stu_login'))

    db = None
    cursor = None
    profile_image = None
    fullname = None

    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor()

        # Fetch full name from users table
        cursor.execute("SELECT fullname FROM users WHERE user_id = %s", (user_id,))
        user_info = cursor.fetchone()
        if user_info:
            fullname = user_info[0]

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM student_profiles WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        if result and result[0]:
            profile_image = base64.b64encode(result[0]).decode('utf-8')  # Convert binary to base64 for HTML

    except mysql.connector.Error as err:
        return redirect(url_for('stu_login'))

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return render_template('student/history.html', profile_image=profile_image, fullname=fullname)


@app.route('/stu_result')
def stu_result():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('stu_login'))

    db = None
    cursor = None
    profile_image = None
    fullname = None
    results_data = []

    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor(dictionary=True)

        # Fetch student's full name
        cursor.execute("SELECT fullname FROM users WHERE user_id = %s", (user_id,))
        user_info = cursor.fetchone()
        fullname = user_info['fullname'] if user_info else None

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM student_profiles WHERE id = %s", (user_id,))
        profile_result = cursor.fetchone()
        if profile_result and profile_result['profile_image']:
            profile_image = base64.b64encode(profile_result['profile_image']).decode('utf-8')

        # Fetch student's results (including exam_id)
        cursor.execute("""
            SELECT exam_title, submitted_at, score, status, answer_id, exam_id 
            FROM student_result 
            WHERE user_id = %s
            ORDER BY submitted_at DESC
        """, (user_id,))
        results_data = cursor.fetchall()

        print(results_data)  # Debugging: Check the structure of results_data

    except mysql.connector.Error as err:
        flash("Database error occurred", "error")
        return redirect(url_for('stu_login'))

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return render_template(
        'student/stu_result.html',
        profile_image=profile_image,
        fullname=fullname,
        results=results_data
    )


@app.route('/submit_complaint', methods=['POST'])
def submit_complaint():
    if request.method == 'POST':
        complaint_text = request.form['complaint_text']
        user_id = session.get('user_id')  # Get user_id from session

        if not user_id:
            return redirect(url_for('stu_login'))

        connection = None
        try:
            connection = mysql.connector.connect(**db_config)
            cursor = connection.cursor()

            # Insert the complaint into the complaints table
            query = '''INSERT INTO complaints (user_id, complaint_text, status)
                       VALUES (%s, %s, %s)'''
            cursor.execute(query, (user_id, complaint_text, 'Pending'))
            connection.commit()

            return redirect(url_for('stu_complaint'))  # Redirect to complaint page

        except mysql.connector.Error as err:
            return redirect(url_for('stu_complaint'))  # Redirect to complaint page on error

        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    return redirect(url_for('stu_complaint'))


@app.route('/stu_complaint')
def stu_complaint():
    user_id = session.get('user_id')  # Get user ID from session

    if not user_id:
        return redirect(url_for('stu_login'))

    connection = None
    profile_image = None
    complaints = []
    fullname = None  # Add a variable to store the full name

    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)

        # Fetch full name from users table
        cursor.execute("SELECT fullname FROM users WHERE user_id = %s", (user_id,))
        user_info = cursor.fetchone()
        if user_info:
            fullname = user_info['fullname']

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM student_profiles WHERE id = %s", (user_id,))
        result = cursor.fetchone()

        if result and result['profile_image']:
            profile_image = base64.b64encode(result['profile_image']).decode('utf-8')

        # Retrieve complaints of the logged-in user
        query = "SELECT complaint_text, reply_text, status FROM complaints WHERE user_id = %s ORDER BY complaint_id DESC"
        cursor.execute(query, (user_id,))
        complaints = cursor.fetchall()  # Fetch all complaints

    except mysql.connector.Error as err:
        flash(f"Error retrieving complaints: {err}", "error")

    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

    return render_template('student/stu_complaint.html', complaints=complaints, profile_image=profile_image, fullname=fullname)



@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('stu_login'))

    connection = None
    cursor = None
    profile_image = None
    fullname = None

    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Fetch full name
        cursor.execute("SELECT fullname FROM users WHERE user_id = %s", (user_id,))
        user_info = cursor.fetchone()
        if user_info:
            fullname = user_info[0]

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM student_profiles WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        if result and result[0]:
            profile_image = base64.b64encode(result[0]).decode('utf-8')

        if request.method == 'POST':
            # Handle image removal
            if 'remove' in request.form:
                cursor.execute("""
                    UPDATE student_profiles
                    SET profile_image = NULL
                    WHERE id = %s
                """, (user_id,))
                connection.commit()
                flash("Image removed!", "success")
                return redirect(url_for('studash'))

            # Handle new image upload
            elif 'profile-picture' in request.files:
                file = request.files['profile-picture']
                if file.filename != '' and allowed_file(file.filename):
                    image_data = file.read()
                    cursor.execute("""
                        UPDATE student_profiles
                        SET profile_image = %s
                        WHERE id = %s
                    """, (image_data, user_id))
                    connection.commit()
                    flash("Image updated!", "success")
                    return redirect(url_for('studash'))

    except mysql.connector.Error as err:
        if connection:
            connection.rollback()
        flash(f"Error: {str(err)}", "error")
        return redirect(url_for('studash'))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return render_template('student/edit_profile.html', profile_image=profile_image, fullname=fullname)

    


@app.route('/stu_profile')
def stu_profile():
    connection = None
    cursor = None
    student_data = {}

    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Fetch user_id from session
        user_id = session.get('user_id')

        if not user_id:
            flash("User ID not found. Please log in again.", "error")
            return redirect(url_for('stu_login'))

        # Fetch full name, email, and phone from users table
        query = '''SELECT fullname, email, contact FROM users WHERE user_id = %s'''
        cursor.execute(query, (user_id,))
        user_info = cursor.fetchone()

        # Fetch address from student_personal_info table
        query = '''SELECT address FROM student_personal_info WHERE user_id = %s'''
        cursor.execute(query, (user_id,))
        personal_info = cursor.fetchone()

        # Fetch academic information
        query = '''SELECT course, year FROM student_academic_info WHERE user_id = %s'''
        cursor.execute(query, (user_id,))
        academic_info = cursor.fetchone()

        # Fetch skills
        query = '''SELECT skill FROM student_skills WHERE user_id = %s'''
        cursor.execute(query, (user_id,))
        skills = cursor.fetchall()

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM student_profiles WHERE id = %s", (user_id,))
        result = cursor.fetchone()

        profile_image = None
        if result and result[0]:
            profile_image = base64.b64encode(result[0]).decode('utf-8')  # Convert binary to base64 for HTML

        # Store data
        if user_info:
            student_data = {
                'fullname': user_info[0],
                'email': user_info[1],
                'phone': user_info[2],
                'address': personal_info[0] if personal_info else "Not provided"
            }

        if academic_info:
            student_data.update({
                'course': academic_info[0],
                'year': academic_info[1]
            })

        if skills:
            student_data.update({
                'skills': [skill[0] for skill in skills]
            })

        return render_template('student/stu_profile.html', student=student_data, profile_image=profile_image)

    except mysql.connector.Error as err:
        flash(f"Error: {err}", "error")
        return redirect(url_for('stu_profile'))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route('/edit_personal_info', methods=['GET', 'POST'])
def edit_personal_info():
    connection = None
    cursor = None
    student_data = {}

    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('stu_login'))

        if request.method == 'GET':
            # Fetch user details from users table
            query = '''SELECT fullname, email, contact FROM users WHERE user_id = %s'''
            cursor.execute(query, (user_id,))
            user_info = cursor.fetchone()

            # Fetch address from student_personal_info table
            query = '''SELECT address FROM student_personal_info WHERE user_id = %s'''
            cursor.execute(query, (user_id,))
            address_info = cursor.fetchone()

            if user_info:
                student_data = {
                    'fullname': user_info[0],
                    'email': user_info[1],
                    'phone': user_info[2],
                    'address': address_info[0] if address_info else "Not provided"
                }

            return render_template('student/edit_personal_info.html', student_data=student_data)

        elif request.method == 'POST':
            # Get form data
            fullname = request.form.get('fullname')
            email = request.form.get('email')
            phone = request.form.get('phone')
            address = request.form.get('address')

            # Update users table
            query = '''UPDATE users SET fullname = %s, email = %s, contact = %s WHERE user_id = %s'''
            cursor.execute(query, (fullname, email, phone, user_id))
            connection.commit()

            # Use INSERT ... ON DUPLICATE KEY UPDATE for student_personal_info
            query = '''
                INSERT INTO student_personal_info (user_id, fullname, email, phone, address) 
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    fullname = VALUES(fullname),
                    email = VALUES(email),
                    phone = VALUES(phone),
                    address = VALUES(address)
            '''
            cursor.execute(query, (user_id, fullname, email, phone, address))
            connection.commit()
            

            # Fetch updated data
            query = '''SELECT fullname, email, contact FROM users WHERE user_id = %s'''
            cursor.execute(query, (user_id,))
            user_info = cursor.fetchone()

            query = '''SELECT address FROM student_personal_info WHERE user_id = %s'''
            cursor.execute(query, (user_id,))
            address_info = cursor.fetchone()

            if user_info:
                student_data = {
                    'fullname': user_info[0],
                    'email': user_info[1],
                    'phone': user_info[2],
                    'address': address_info[0] if address_info else "Not provided"
                }

            flash("Personal information updated successfully!", "success")
            return redirect(url_for('stu_profile'))
        
    except mysql.connector.Error as err:
        flash(f"Error: {err}", "error")
        print("MySQL Error:", err)  # Print the error to debug
        return redirect(url_for('edit_personal_info'))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route('/edit_skills', methods=['GET', 'POST'])
def edit_skills():
    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Fetch user_id from session
        user_id = session.get('user_id')

        if not user_id:
            flash("User ID not found. Please log in again.", "error")
            return redirect(url_for('stu_login'))

        if request.method == 'GET':
            # Fetch existing skills for the user
            query = '''SELECT skill
                       FROM student_skills
                       WHERE user_id = %s'''
            cursor.execute(query, (user_id,))
            skills = cursor.fetchall()

            # Convert the result to a list of skills
            skills_list = [skill[0] for skill in skills]

            return render_template('student/edit_skills.html', skills=skills_list)

        elif request.method == 'POST':
            # Handle form submission
            skills = request.form.getlist('skills[]')

            # Delete existing skills for the user
            query = '''DELETE FROM student_skills
                       WHERE user_id = %s'''
            cursor.execute(query, (user_id,))
            connection.commit()

            # Insert new skills
            for skill in skills:
                query = '''INSERT INTO student_skills (user_id, skill)
                           VALUES (%s, %s)'''
                cursor.execute(query, (user_id, skill))
                connection.commit()

            flash("Skills updated successfully!", "success")
            return redirect(url_for('stu_profile'))

    except mysql.connector.Error as err:
        flash(f"Error: {err}", "error")
        return redirect(url_for('edit_skills'))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route('/edit_academic_info', methods=['GET', 'POST'])
def edit_academic_info():
    connection = None
    cursor = None
    student_data = {}

    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Fetch user_id from session
        user_id = session.get('user_id')

        if not user_id:
            flash("User ID not found. Please log in again.", "error")
            return redirect(url_for('stu_login'))

        if request.method == 'GET':
            # Fetch existing academic data for the user
            query = '''SELECT course, year
                       FROM student_academic_info
                       WHERE user_id = %s'''
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()

            if result:
                student_data = {
                    'course': result[0],
                    'year': result[1]
                }

            return render_template('student/edit_academic_info.html', student_data=student_data)

        elif request.method == 'POST':
            # Handle form submission
            course = request.form.get('course')
            year = request.form.get('year')

            # Debug: Print form data
            print(f"Form Data: course={course}, year={year}")

            # Insert or update student academic info
            query = '''INSERT INTO student_academic_info (user_id, course, year)
                       VALUES (%s, %s, %s)
                       ON DUPLICATE KEY UPDATE course = %s, year = %s'''
            cursor.execute(query, (user_id, course, year, course, year))
            connection.commit()

            flash("Academic Information updated successfully!", "success")
            return redirect(url_for('stu_profile'))

    except Exception as e:
            flash(str(e), "error")
            return redirect(url_for('edit_academic_info'))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route('/about')
def about():
    return render_template('student/about.html')


@app.route('/contact')
def contact():
    return render_template('student/contact.html')




@app.route('/change_password')
def change_password():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('stu_login'))

    db = None
    cursor = None
    profile_image = None
    fullname = None

    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor(dictionary=True)

        # Fetch student's full name
        cursor.execute("SELECT fullname FROM users WHERE user_id = %s", (user_id,))
        user_info = cursor.fetchone()
        fullname = user_info['fullname'] if user_info else None

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM student_profiles WHERE id = %s", (user_id,))
        profile_result = cursor.fetchone()
        if profile_result and profile_result['profile_image']:
            profile_image = base64.b64encode(profile_result['profile_image']).decode('utf-8')


    except mysql.connector.Error as err:
        flash("Database error occurred", "error")
        return redirect(url_for('stu_login'))

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return render_template(
        'student/password.html',
        profile_image=profile_image,
        fullname=fullname
    )

@app.route('/update_password', methods=['POST'])
def update_password():
    # Check if user is logged in
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('stu_login'))

    # Get form data
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    # Validate password match
    if new_password != confirm_password:
        flash("Passwords do not match", "error")
        return redirect(url_for('change_password'))

    # Validate password requirements
    if len(new_password) < 5 or len(new_password) > 12:
        flash("Password must be between 5 and 12 characters", "error")
        return redirect(url_for('change_password'))

    # Hash the password
    hashed_password = generate_password_hash(new_password)

    try:
        # Connect to database
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor()

        # Update password in database
        cursor.execute(
            "UPDATE users SET password = %s WHERE user_id = %s",
            (hashed_password, user_id)
        )
        db.commit()

        flash("Password updated successfully", "success")
        return redirect(url_for('change_password'))

    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")
        return redirect(url_for('change_password'))

    finally:
        # Close database connection
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()


@app.route('/exam')
def exam():
    exam_link = request.args.get('exam_link')
    if not exam_link:
        flash("Exam link is required!", "danger")
        return redirect(url_for('studash'))

    conn = None
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        # Fetch exam details
        cursor.execute("""
            SELECT exam_id, exam_title, exam_date, exam_time, exam_duration, exam_rules 
            FROM exam_info WHERE exam_link = %s LIMIT 1
        """, (exam_link,))
        exam_details = cursor.fetchone()

        if not exam_details:
            return redirect(url_for('studash'))

        return render_template('student/exam.html', exam_details=exam_details)

    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "danger")
        return redirect(url_for('studash'))

    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@app.route('/questions/<int:exam_id>')
def questions(exam_id):
    if 'user_id' not in session:
        return redirect(url_for('stu_login'))

    user_id = session['user_id']
    conn = None
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # Check if exam was already submitted
        cursor.execute("""
            SELECT answer_id 
            FROM student_result
            WHERE user_id = %s AND exam_id = %s
        """, (user_id, exam_id))
        submission = cursor.fetchone()
        
        if submission:
            flash("You have already submitted this exam!", "warning")
            return redirect(url_for('studash'))
        
        # Fetch exam details
        cursor.execute("""
            SELECT exam_title, exam_duration 
            FROM exam_info 
            WHERE exam_id = %s
        """, (exam_id,))
        exam_info = cursor.fetchone()
        
        if not exam_info:
            flash("Exam not found!", "danger")
            return redirect(url_for('studash'))
        
        # Fetch exam questions
        cursor.execute("""
            SELECT question_id, question_text, question_image, marks, options 
            FROM exam_questions 
            WHERE exam_id = %s
        """, (exam_id,))
        questions = cursor.fetchall()
        
        if not questions:
            flash("No questions found for this exam!", "warning")
            return redirect(url_for('studash'))
        
        return render_template(
            'student/questions.html',
            exam_title=exam_info['exam_title'],
            exam_duration=exam_info['exam_duration'],
            questions=questions,
            exam_id=exam_id
        )
    
    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "danger")
        return redirect(url_for('studash'))
    
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()  


@app.route('/submit_exam', methods=['POST'])
def submit_exam():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401

    user_id = session['user_id']
    data = request.get_json()
    exam_id = data.get('exam_id')
    answers = data.get('answers')

    if not exam_id or not answers:
        return jsonify({'success': False, 'error': 'Missing data'}), 400

    conn = None
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Check if user has already submitted the exam
        cursor.execute("""
            SELECT answer_id FROM student_result
            WHERE user_id = %s AND exam_id = %s
        """, (user_id, exam_id))
        existing_submission = cursor.fetchone()

        if existing_submission:
            conn.rollback()
            return jsonify({
                'success': False, 
                'error': 'You have already submitted this exam'
            }), 400

        else:
            # Get user's fullname
            cursor.execute("""
                SELECT fullname FROM users WHERE user_id = %s
            """, (user_id,))
            fullname = cursor.fetchone()[0]

            # Get exam title
            cursor.execute("""
                SELECT exam_title FROM exam_info WHERE exam_id = %s
            """, (exam_id,))
            exam_title = cursor.fetchone()[0]

            # Insert new submission
            cursor.execute("""
                INSERT INTO student_result 
                (user_id, exam_id, fullname, exam_title)
                VALUES (%s, %s, %s, %s)
            """, (user_id, exam_id, fullname, exam_title))
            answer_id = cursor.lastrowid

        # Insert answers
        for answer in answers:
            cursor.execute("""
                INSERT INTO student_answers 
                (answer_id, question_id, answer)
                VALUES (%s, %s, %s)
            """, (answer_id, answer['question_id'], answer['answer']))

        # Commit transaction
        conn.commit()
        return jsonify({'success': True})

    except mysql.connector.IntegrityError as e:
        if conn:
            conn.rollback()
        # Handle unique constraint violation
        return jsonify({
            'success': False, 
            'error': 'You have already submitted this exam'
        }), 400

    except mysql.connector.Error as err:
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'error': str(err)}), 500

    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@app.route('/student/exam_answers')
def student_exam_answers():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('stu_login'))

    answer_id = request.args.get('answer_id')
    if not answer_id:
        flash("Invalid request.", "error")
        return redirect(url_for('stu_result'))

    db = None
    cursor = None
    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor(dictionary=True)

        # Verify the submission belongs to the student
        cursor.execute("""
            SELECT sas.fullname, sas.exam_title 
            FROM student_result sas
            WHERE sas.answer_id = %s AND sas.user_id = %s
        """, (answer_id, user_id))
        submission_info = cursor.fetchone()

        if not submission_info:
            flash("Submission not found.", "error")
            return redirect(url_for('stu_result'))

        # Fetch answers
        cursor.execute("""
            SELECT eq.question_text, eq.options, eq.marks, eq.question_image,
                   sad.answer
            FROM student_answers sad
            JOIN exam_questions eq ON sad.question_id = eq.question_id
            WHERE sad.answer_id = %s
            ORDER BY eq.question_id
        """, (answer_id,))
        answers = cursor.fetchall()

        # Convert images to base64
        for answer in answers:
            if answer['question_image']:
                answer['question_image'] = base64.b64encode(answer['question_image']).decode('utf-8')

        return render_template(
            'student/exam_answers.html',
            fullname=submission_info['fullname'],
            exam_title=submission_info['exam_title'],
            answers=answers
        )

    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")
        return redirect(url_for('stu_result'))
    finally:
        if cursor: cursor.close()
        if db: db.close()


@app.route('/faq')
def faq():
    return render_template('faq.html')

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def process_base64_image(base64_string):
    try:
        if 'data:image' in base64_string:
            base64_string = base64_string.split(',')[1]
        
        image_bytes = base64.b64decode(base64_string)
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return None
            
        return image
    except Exception as e:
        print(f"Error in process_base64_image: {str(e)}")
        return None

def detect_and_encode_face(image):
    try:
        # Detect faces in the image
        face_locations = face_recognition.face_locations(image)
        
        if len(face_locations) != 1:
            return None  # Ensure only one face is present
        
        # Encode the face
        face_encodings = face_recognition.face_encodings(image, face_locations)
        return face_encodings[0]  # Return the first (and only) face encoding
        
    except Exception as e:
        print(f"Error in detect_and_encode_face: {str(e)}")
        return None

def compare_faces(face_encoding1, face_encoding2, threshold=0.6):
    try:
        # Compare the two face encodings
        distance = face_recognition.face_distance([face_encoding1], face_encoding2)[0]
        similarity = 1 - distance
        
        # Determine if the faces match based on the threshold
        is_match = similarity >= threshold
        
        return is_match, similarity * 100
        
    except Exception as e:
        print(f"Error in compare_faces: {str(e)}")
        return False, 0.0

@app.route('/verify_faces', methods=['POST'])
def verify_faces():
    try:
        # Get webcam image from request
        webcam_image = request.json.get('webcam_image')
        reference_embedding = request.json.get('reference_embedding')
        
        if not webcam_image:
            return jsonify({'status': 'error', 'message': 'Webcam image is required'}), 400
        
        # Process image
        webcam_cv = process_base64_image(webcam_image)
        if webcam_cv is None:
            return jsonify({'status': 'error', 'message': 'Invalid webcam image'}), 400
            
        # Check face clarity
        face_encoding = detect_and_encode_face(webcam_cv)
        if face_encoding is None:
            return jsonify({'status': 'error', 'message': 'No face or multiple faces detected in image'}), 400
        
        if reference_embedding:
            # Compare with reference embedding
            reference_embedding = json.loads(reference_embedding)
            similarity = face_recognition.face_distance([reference_embedding], face_encoding)
            similarity = 1 - similarity[0]  # Convert distance to similarity
            
            return jsonify({
                'status': 'success',
                'similarity': float(similarity),
                'embedding': face_encoding.tolist()
            })
        else:
            # For initial verification, just return the embedding
            return jsonify({
                'status': 'success',
                'embedding': face_encoding.tolist()
            })
        
    except Exception as e:
        logger.error(f"Error in verify_faces: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
      






# face_recog on questions.html
# Initialize face and object detection
face_detector = dlib.get_frontal_face_detector()

# Load YOLO model for object detection
try:
    yolo_model = YOLO("yolov5su.pt")
    object_detection_enabled = True
    # Prohibited objects (as per COCO classes)
    PROHIBITED_ITEMS = ["cell phone", "book", "laptop", "tablet", "keyboard", "mouse"]
    print("Object detection initialized successfully")
except Exception as e:
    print(f"Warning: Could not load YOLO model: {e}")
    object_detection_enabled = False

try:
    # Update this path to your shape predictor file location
    landmark_predictor = dlib.shape_predictor('shape_predictor_68_face_landmarks.dat')
    face_detection_enabled = True
except Exception as e:
    print(f"Warning: Could not load facial landmark predictor: {e}")
    face_detection_enabled = False

# Define routes for proctoring system
@app.route('/process_frame', methods=['POST'])
def process_frame():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    user_id = data.get('user_id')
    exam_id = data.get('exam_id')
    image_data = data.get('image')
    violation_type = data.get('violation_type')  # New parameter for specific violation type
    
    if not all([user_id, exam_id, image_data]):
        return jsonify({'error': 'Missing required data'}), 400
    
    # Process the image data (remove data:image/jpeg;base64, prefix)
    image_data = image_data.split(',')[1] if ',' in image_data else image_data
    
    # Decode base64 image
    image_bytes = base64.b64decode(image_data)
    image = Image.open(BytesIO(image_bytes))
    
    # Convert to OpenCV format
    frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    
    # Process for violations
    violations = []
    violation_image = None
    violation_details = {'face_count': 0, 'objects': []}
    
    # Handle specific violation type if provided
    if violation_type == "Unauthorized person detected":
        violations.append(violation_type)
    
    
    # 1. Process face detection violations if enabled
    if face_detection_enabled:
        face_violations, face_details = detect_face_violations(frame)
        violations.extend(face_violations)
        violation_details['face_count'] = face_details.get('face_count', 0)
    
    # 2. Process object detection violations if enabled
    if object_detection_enabled:
        object_violations, object_details = detect_prohibited_objects(frame)
        violations.extend(object_violations)
        violation_details['objects'] = object_details.get('objects', [])
    
    pass
    
    # If violations detected, save the frame
    if violations:
        try:
            # Encode frame as JPEG
            encode_result = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        
            if not encode_result[0] or encode_result[1] is None:
                print("Failed to encode frame as JPEG")
                return jsonify({'error': 'Image processing failed'}), 500

            buffer = encode_result[1]
            violation_image_data = buffer.tobytes()
        
            # Log violation and get ID
            violation_id = log_violation_to_db(
                user_id=user_id,
                exam_id=exam_id,
                violation_type=', '.join(violations),
                face_count=violation_details.get('face_count', 0),
                violation_image=violation_image_data,
                timestamp=datetime.datetime.now()
            )
        
            if violation_id:
                return jsonify({
                    'success': True,
                    'violations': violations,
                    'violation_id': violation_id,
                    'details': violation_details
                })
            
        except Exception as e:
            print(f"Image processing error: {e}")
            return jsonify({'error': 'Image processing failed'}), 500
    
    return jsonify({'success': False, 'violations': violations})


# Add variables to track gaze violation duration
gaze_violation_start_time = 0
current_gaze_status = "center"

# Function to detect face-related violations
def detect_face_violations(frame):
    global gaze_violation_start_time, current_gaze_status
    violations = []
    details = {'face_count': 0}
    
    try:
        # Convert to grayscale for face detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        faces = face_detector(gray)
        face_count = len(faces)
        details['face_count'] = face_count
        
        # Check for multiple faces
        if face_count > 1:
            violations.append("Multiple faces detected")
        
        # Check for no face
        elif face_count == 0:
            violations.append("No face detected")
        
        # Process detected face for looking away and gaze tracking
        elif face_count == 1:
            # Get face landmarks
            landmarks = landmark_predictor(gray, faces[0])
            landmarks_points = []
            
            # Convert landmarks to numpy array
            for i in range(68):
                x, y = landmarks.part(i).x, landmarks.part(i).y
                landmarks_points.append((x, y))
            
            landmarks_np = np.array(landmarks_points)
            
            # Check if looking away
            if detect_looking_away(landmarks_np):
                violations.append("Looking away from screen")
            
        
    except Exception as e:
        print(f"Error in face violation detection: {e}")
    
    return violations, details



    

# Function to detect prohibited objects using YOLO
def detect_prohibited_objects(frame):
    violations = []
    details = {'objects': []}
    
    try:
        # Run YOLO detection
        results = yolo_model(frame)
        
        # Process results
        for result in results:
            for box, cls_id, conf in zip(result.boxes.xyxy, result.boxes.cls, result.boxes.conf):
                class_name = yolo_model.names[int(cls_id)]
                
                if class_name in PROHIBITED_ITEMS and conf > 0.5:  # 0.5 confidence threshold
                    violations.append(f"Prohibited object detected: {class_name}")
                    details['objects'].append({
                        'name': class_name,
                        'confidence': float(conf)
                    })
    
    except Exception as e:
        print(f"Error in object detection: {e}")
    
    return violations, details


# Helper function to detect if person is looking away
def detect_looking_away(landmarks):
    """Detect if the person is looking away based on face landmarks"""
    try:
        # Calculate face orientation
        nose_tip = landmarks[30]
        left_eye = landmarks[36]
        right_eye = landmarks[45]
        
        # Calculate horizontal deviation
        face_center_x = (left_eye[0] + right_eye[0]) / 2
        deviation = abs(nose_tip[0] - face_center_x)
        
        # Threshold for looking away
        return deviation > 30
    except:
        return False


@app.route('/log_violation', methods=['POST'])
def log_violation():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    user_id = data.get('user_id')
    exam_id = data.get('exam_id')
    violation_type = data.get('violation_type')
    details = data.get('details')
    
    if not all([user_id, exam_id, violation_type]):
        return jsonify({'error': 'Missing required data'}), 400
    
    # Log to database
    log_violation_to_db(
        user_id=user_id,
        exam_id=exam_id,
        violation_type=violation_type,
        face_count=0,  # Not applicable for manual violations
        violation_image='none.jpg',  # No image for manual violations
        timestamp=datetime.datetime.now()
    )
    
    return jsonify({'success': True})


# Helper function to get user information
def get_user_info(user_id):
    conn = None
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT fullname, email FROM users WHERE user_id = %s
        """, (user_id,))
        
        user = cursor.fetchone()
        return user if user else {'fullname': 'Unknown', 'email': 'Unknown'}
    
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return {'fullname': 'Unknown', 'email': 'Unknown'}
    
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# Helper function to log violations to database
def log_violation_to_db(user_id, exam_id, violation_type, face_count, violation_image, timestamp):
    conn = None
    violation_id = None
    try:
        user_info = get_user_info(user_id)
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO exam_violations 
            (user_id, exam_id, fullname, email, violation_type, 
             face_count, violation_image, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id, exam_id, user_info['fullname'], user_info['email'], violation_type,
            face_count, violation_image, timestamp
        ))
        
        violation_id = cursor.lastrowid
        conn.commit()
        return violation_id
    
    except mysql.connector.Error as err:
        print(f"Database error when logging violation: {err}")
        return None
    
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


# Upload stream endpoint (keep for backward compatibility)
@app.route('/upload_stream', methods=['POST'])
def upload_stream():
    # This is now replaced by the more robust process_frame endpoint
    # But kept for backward compatibility
    return jsonify({'success': True})


@app.route('/violation_image/<int:violation_id>')
def get_violation_image(violation_id):
    conn = None
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT violation_image FROM exam_violations WHERE violation_id = %s", (violation_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            return Response(result[0], mimetype='image/jpeg')
        else:
            return send_file('static/default.jpg', mimetype='image/jpeg')
    
    except Exception as e:
        print(f"Error retrieving violation image: {e}")
        return send_file('static/default.jpg', mimetype='image/jpeg')
    
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@app.route('/violations/<int:user_id>/<int:exam_id>')
def view_violations(user_id, exam_id):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    # Get exam title
    cursor.execute("SELECT exam_title FROM exam_info WHERE exam_id = %s", (exam_id,))
    exam = cursor.fetchone()
    exam_title = exam['exam_title'] if exam else 'N/A'
    
    # Get violations
    cursor.execute("""
        SELECT v.*, e.exam_title 
        FROM exam_violations v
        LEFT JOIN exam_info e ON v.exam_id = e.exam_id
        WHERE v.user_id = %s AND v.exam_id = %s
        ORDER BY v.timestamp DESC
    """, (user_id, exam_id))
    violations = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('violations.html', 
                         violations=violations,
                         exam_title=exam_title)










#teacher.monitor page
class FaceMonitoringSystem:
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.known_faces = {}  # Cache for verified student faces
        self.violation_threshold = 3  # Number of violations before alert
        self.violation_counters = {}  # Track violations per student
        self.logger = self._setup_logger()

    def _setup_logger(self):
        logger = logging.getLogger('FaceMonitoringSystem')
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    async def process_frame(self, frame_data, student_id, exam_id):
        """Process a single frame for face detection and verification"""
        try:
            # Convert base64 to image
            nparr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Detect faces in frame
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
            
            result = {
                'status': 'ok',
                'violations': [],
                'num_faces': len(faces)
            }

            # No face detected
            if len(faces) == 0:
                self._record_violation(student_id, 'no_face')
                result['violations'].append('No face detected')
                return result

            # Multiple faces detected
            if len(faces) > 1:
                self._record_violation(student_id, 'multiple_faces')
                result['violations'].append('Multiple faces detected')
                return result

            # Verify face matches student
            if not self._verify_student_face(frame, faces[0], student_id):
                self._record_violation(student_id, 'unauthorized_person')
                result['violations'].append('Unauthorized person detected')
                return result

            # Clear violations if everything is ok
            self._clear_violations(student_id)
            return result

        except Exception as e:
            self.logger.error(f"Error processing frame: {str(e)}")
            return {'status': 'error', 'message': str(e)}

    def _verify_student_face(self, frame, face_coords, student_id):
        """Verify detected face matches stored student face"""
        try:
            if student_id not in self.known_faces:
                # Get student's verified face from database
                stored_face = self._get_stored_face(student_id)
                if stored_face is None:
                    return False
                self.known_faces[student_id] = stored_face

            # Extract face region
            x, y, w, h = face_coords
            face_roi = frame[y:y+h, x:x+w]

            # Compare with stored face using DeepFace
            result = DeepFace.verify(
                face_roi,
                self.known_faces[student_id],
                model_name='VGG-Face',
                distance_metric='cosine'
            )

            return result['verified']

        except Exception as e:
            self.logger.error(f"Face verification error: {str(e)}")
            return False

    def _record_violation(self, student_id, violation_type):
        """Record a violation for a student"""
        if student_id not in self.violation_counters:
            self.violation_counters[student_id] = {}
        
        if violation_type not in self.violation_counters[student_id]:
            self.violation_counters[student_id][violation_type] = 0
            
        self.violation_counters[student_id][violation_type] += 1
        
        # Check if threshold exceeded
        if self.violation_counters[student_id][violation_type] >= self.violation_threshold:
            self._trigger_alert(student_id, violation_type)

    def _clear_violations(self, student_id):
        """Clear violation counters for a student"""
        if student_id in self.violation_counters:
            self.violation_counters[student_id] = {}

    def _trigger_alert(self, student_id, violation_type):
        """Trigger alert for repeated violations"""
        alert = {
            'student_id': student_id,
            'violation_type': violation_type,
            'timestamp': time.time(),
            'count': self.violation_counters[student_id][violation_type]
        }
        
        # Send alert to monitoring dashboard
        self._send_alert_to_dashboard(alert)
        
        # Log the alert
        self.logger.warning(f"Alert triggered - Student: {student_id}, "
                          f"Violation: {violation_type}, "
                          f"Count: {alert['count']}")

    async def process_monitoring_feed(self, stream_data):
        """Process incoming monitoring feed data"""
        results = []
        for student_id, frame_data in stream_data.items():
            result = await self.process_frame(frame_data['image'], student_id, frame_data['exam_id'])
            results.append({
                'student_id': student_id,
                'result': result
            })
        return results


# Flask route handlers
@app.route('/verify_stream', methods=['POST'])
async def verify_stream():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        
    data = request.json
    monitor = FaceMonitoringSystem()
    result = await monitor.process_frame(
        data['image'],
        session['user_id'],
        data['exam_id']
    )
    
    return jsonify(result)

@app.route('/monitor_streams', methods=['POST'])
async def monitor_streams():
    if 'authority_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        
    data = request.json
    monitor = FaceMonitoringSystem()
    results = await monitor.process_monitoring_feed(data['streams'])
    
    return jsonify(results)




@app.route('/change1_password')
def change1_password():
    authority_id = session.get('authority_id')
    if not authority_id:
        flash("Please log in first!", "warning")
        return redirect(url_for('teacher_login'))

    db = None
    cursor = None
    profile_image = None
    fullname = None

    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor(dictionary=True)

        # Fetch full name from users table
        cursor.execute("SELECT fullname FROM exam_authority WHERE authority_id = %s", (authority_id,))
        authority_info = cursor.fetchone()
        if authority_info:
            fullname = authority_info['fullname']

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM teacher_profiles WHERE id = %s", (authority_id,))
        result = cursor.fetchone()
        if result and result['profile_image']:
            profile_image = base64.b64encode(result['profile_image']).decode('utf-8')  # Convert binary to base64 for HTML


    except mysql.connector.Error as err:
        flash(f"Error: {err}", "error")
        return redirect(url_for('teacher_login'))

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return render_template('teacher/password.html', fullname=fullname, profile_image=profile_image)

@app.route('/update1_password', methods=['POST'])
def update1_password():
    # Check if user is logged in
    authority_id = session.get('authority_id')
    if not authority_id:
        return redirect(url_for('teacher_login'))

    # Get form data
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    # Validate password match
    if new_password != confirm_password:
        flash("Passwords do not match", "error")
        return redirect(url_for('change1_password'))

    # Validate password requirements
    if len(new_password) < 5 or len(new_password) > 12:
        flash("Password must be between 5 and 12 characters", "error")
        return redirect(url_for('change1_password'))

    # Hash the password
    hashed_password = generate_password_hash(new_password)

    try:
        # Connect to database
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor()

        # Update password in database
        cursor.execute(
            "UPDATE exam_authority SET password = %s WHERE authority_id = %s",
            (hashed_password, authority_id)
        )
        db.commit()

        flash("Password updated successfully", "success")
        return redirect(url_for('change1_password'))

    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")
        return redirect(url_for('change1_password'))

    finally:
        # Close database connection
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()












# Teacher Signup Route
@app.route('/teacher/signup', methods=['GET', 'POST'])
def teacher_signup():
    if request.method == 'POST':
        fullname = request.form['fullname']
        email = request.form['email']
        username = request.form['username']
        contact = request.form['contact']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        profile_pic = request.files.get('profile_pic')

        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "error")
            return redirect(url_for('teacher_signup'))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        connection = None
        try:
            connection = mysql.connector.connect(**db_config)
            cursor = connection.cursor()

            query = "INSERT INTO exam_authority (fullname, email, username, contact, password) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(query, (fullname, email, username, contact, hashed_password))
            authority_id = cursor.lastrowid


            # Process profile picture
            image_data = None
            if profile_pic and allowed_file(profile_pic.filename):
                image_data = profile_pic.read()

            # Insert into student_profiles
            profile_query = """
                INSERT INTO teacher_profiles (id, profile_image)
                VALUES (%s, %s)
            """
            cursor.execute(profile_query, (authority_id, image_data))

            connection.commit()

            flash("Account created successfully. Please log in.", "success")
            return redirect(url_for('teacher_login'))

        except mysql.connector.Error as err:
            flash(f"Error: {err}", "error")
            return redirect(url_for('teacher_signup'))
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    return render_template('teacher/tr_signup.html')



# Teacher Login Route
@app.route('/teacher/login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            connection = mysql.connector.connect(**db_config)
            cursor = connection.cursor()

            query = "SELECT authority_id, username, password FROM exam_authority WHERE username = %s"
            cursor.execute(query, (username,))
            result = cursor.fetchone()

            if result and check_password_hash(result[2], password):
                session['authority_id'] = result[0]
                session['username'] = result[1]
                return redirect(url_for('teacher_dashboard'))  # Redirect to teacher dashboard
            else:
                flash("Invalid username or password. Please try again.", "error")
                return redirect(url_for('teacher_login'))

        except mysql.connector.Error as err:
            flash(f"Error: {err}", "error")
            return redirect(url_for('teacher_login'))

        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    return render_template('teacher/tr_login.html')


@app.route('/teacher/trdash')
def teacher_dashboard():
    authority_id = session.get('authority_id')
    if not authority_id:
        flash("Please log in first!", "warning")
        return redirect(url_for('teacher_login'))

    db = None
    cursor = None
    profile_image = None
    fullname = None
    exams = []  # List to store exam details

    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor(dictionary=True)

        # Fetch full name from users table
        cursor.execute("SELECT fullname FROM exam_authority WHERE authority_id = %s", (authority_id,))
        authority_info = cursor.fetchone()
        if authority_info:
            fullname = authority_info['fullname']

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM teacher_profiles WHERE id = %s", (authority_id,))
        result = cursor.fetchone()
        if result and result['profile_image']:
            profile_image = base64.b64encode(result['profile_image']).decode('utf-8')  # Convert binary to base64 for HTML

        # Fetch all exams created by the teacher
        cursor.execute("""
            SELECT exam_id, exam_title, exam_date, exam_time, exam_link 
            FROM exam_info 
            WHERE authority_id = %s
            ORDER BY created_at DESC
        """, (authority_id,))
        exams = cursor.fetchall()  # Fetch all exams

    except mysql.connector.Error as err:
        flash(f"Error: {err}", "error")
        return redirect(url_for('teacher_login'))

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return render_template('teacher/trdash.html', fullname=fullname, profile_image=profile_image, exams=exams)


@app.route('/delete-exam/<int:exam_id>', methods=['DELETE'])
def delete_exam(exam_id):
    authority_id = session.get('authority_id')
    if not authority_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    db = None
    cursor = None
    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor()

        # Delete the exam only if it belongs to the current teacher
        cursor.execute("""
            DELETE FROM exam_info 
            WHERE exam_id = %s AND authority_id = %s
        """, (exam_id, authority_id))
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Exam not found or unauthorized'}), 404

        db.commit()
        return jsonify({'success': True})

    except mysql.connector.Error as err:
        if db:
            db.rollback()
        return jsonify({'success': False, 'error': str(err)}), 500

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

            

@app.route('/teacher/tr_createxm', methods=['GET', 'POST'])
def teacher_createxm():
    authority_id = session.get('authority_id')
    if not authority_id:
        flash("Please log in first!", "warning")
        return redirect(url_for('teacher_login'))

    # Initialize variables for teacher display
    profile_image = None
    fullname = None

    # Fetch teacher details for display
    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor()

        cursor.execute("SELECT fullname FROM exam_authority WHERE authority_id = %s", (authority_id,))
        authority_info = cursor.fetchone()
        if authority_info:
            fullname = authority_info[0]

        cursor.execute("SELECT profile_image FROM teacher_profiles WHERE id = %s", (authority_id,))
        result = cursor.fetchone()
        if result and result[0]:
            profile_image = base64.b64encode(result[0]).decode('utf-8')
    except mysql.connector.Error as err:
        flash(f"Error: {err}", "error")
        return redirect(url_for('teacher_login'))
    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    if request.method == 'POST':
        exam_title = request.form.get('exam-title')
        exam_type = request.form.get('exam-type')
        
        try:
            db = mysql.connector.connect(**db_config)
            cursor = db.cursor()

            exam_id = int(uuid4().int & (1 << 31) - 1)

            cursor.execute(
                """INSERT INTO exam_info (exam_id, authority_id, exam_title)
                   VALUES (%s, %s, %s)""",
                (exam_id, authority_id, exam_title)
            )

            if exam_type == 'objective':
                questions = request.form.getlist('questions[]')
                obj_marks = request.form.getlist('obj-marks[]')
                options = request.form.getlist('options[]')

                for i, question in enumerate(questions):
                    try:
                        # Convert marks to integer, default to 0 if conversion fails
                        mark = int(obj_marks[i]) if i < len(obj_marks) and obj_marks[i] else 0
                    except (ValueError, IndexError):
                        mark = 0

                    question_image = request.files.get(f'upload-image-obj-{i+1}')
                    image_data = question_image.read() if question_image and question_image.filename else None

                    cursor.execute(
                        """INSERT INTO exam_questions 
                        (authority_id, exam_id, exam_title, exam_type, question_text, question_image, marks, options) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (authority_id, exam_id, exam_title, exam_type, question, image_data, mark, 
                         options[i] if i < len(options) else None)
                    )

            elif exam_type == 'subjective':
                subj_questions = request.form.getlist('subj-questions[]')
                subj_marks = request.form.getlist('subj-marks[]')

                for i, question in enumerate(subj_questions):
                    try:
                        # Convert marks to integer, default to 0 if conversion fails
                        mark = int(subj_marks[i]) if i < len(subj_marks) and subj_marks[i] else 0
                    except (ValueError, IndexError):
                        mark = 0

                    question_image = request.files.get(f'upload-image-subj-{i+1}')
                    image_data = question_image.read() if question_image and question_image.filename else None

                    cursor.execute(
                        """INSERT INTO exam_questions 
                        (authority_id, exam_id, exam_title, exam_type, question_text, question_image, marks) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (authority_id, exam_id, exam_title, exam_type, question, image_data, mark)
                    )
            
            db.commit()
            flash("Exam created successfully!", "success")
            return redirect(url_for('teacher_instruction', exam_id=exam_id))

        except mysql.connector.Error as err:
            flash(f"Error: {err}", "error")
            return redirect(url_for('teacher_login'))
        finally:
            if cursor:
                cursor.close()
            if db and db.is_connected():
                db.close()

    return render_template('teacher/tr_createxm.html', fullname=fullname, profile_image=profile_image)



@app.route('/instruction/<int:exam_id>', methods=['GET', 'POST'])
def teacher_instruction(exam_id):
    if request.method == 'POST':
        exam_duration = request.form['exam-duration']
        exam_rules = request.form['exam-rules']
        exam_date = request.form['exam-date']
        exam_time = request.form['exam-time']

        try:
            db = mysql.connector.connect(**db_config)
            cursor = db.cursor()

            # Update exam_info with additional exam-level details
            cursor.execute('''UPDATE exam_info 
                              SET exam_duration = %s, exam_rules = %s, exam_date = %s, exam_time = %s 
                              WHERE exam_id = %s''', 
                           (exam_duration, exam_rules, exam_date, exam_time, exam_id))
            db.commit()
            flash("Exam details updated successfully!", "success")
            return redirect(url_for('show_exam', exam_id=exam_id))
        except mysql.connector.Error as err:
            flash(f"Error: {err}", "error")
            return redirect(url_for('teacher_dashboard'))
        finally:
            if cursor:
                cursor.close()
            if db and db.is_connected():
                db.close()

    return render_template('teacher/tr_instruction.html', exam_id=exam_id)



@app.route('/teacher/show/<int:exam_id>')
def show_exam(exam_id):
    authority_id = session.get('authority_id')
    if not authority_id:
        flash("Please log in first!", "warning")
        return redirect(url_for('teacher_login'))

    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor(dictionary=True)

        # Get exam-level info from exam_info (including exam_title)
        cursor.execute("""
            SELECT exam_title, exam_duration, exam_rules, exam_date, exam_time, exam_link 
            FROM exam_info 
            WHERE authority_id = %s AND exam_id = %s LIMIT 1
        """, (authority_id, exam_id))
        exam_info = cursor.fetchone()

        if not exam_info:
            flash("Exam not found!", "error")
            return redirect(url_for('teacher_dashboard'))

        # Fetch all questions for the exam from exam_questions
        cursor.execute("""
            SELECT question_text, question_image, marks, options, exam_type 
            FROM exam_questions 
            WHERE authority_id = %s AND exam_id = %s
        """, (authority_id, exam_id))
        questions = cursor.fetchall()

        # Convert any binary images to base64 strings for display in HTML
        for q in questions:
            if q['question_image']:
                q['question_image'] = base64.b64encode(q['question_image']).decode('utf-8')
            else:
                q['question_image'] = None

        # If no exam link exists, generate one and update exam_info
        exam_link = exam_info.get('exam_link')
        if not exam_link:
            exam_link = str(uuid.uuid4())
            cursor.execute("""
                UPDATE exam_info 
                SET exam_link = %s 
                WHERE exam_id = %s
            """, (exam_link, exam_id))
            db.commit()
            exam_info['exam_link'] = exam_link

        return render_template('teacher/show.html', 
                               exam_title=exam_info['exam_title'], 
                               exam_duration=exam_info['exam_duration'], 
                               exam_rules=exam_info['exam_rules'], 
                               exam_date=exam_info['exam_date'], 
                               exam_time=exam_info['exam_time'], 
                               exam_link=exam_info['exam_link'], 
                               questions=questions)
    except mysql.connector.Error as err:
        flash(f"Error: {err}", "error")
        return redirect(url_for('teacher_dashboard'))
    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()



@app.route('/exam_link/<unique_id>')
def exam_link(unique_id):
    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor(dictionary=True, buffered=True)

        # Look up the exam in exam_info by its exam_link
        cursor.execute("SELECT * FROM exam_info WHERE exam_link = %s", (unique_id,))
        exam_info = cursor.fetchone()

        if not exam_info:
            flash("Exam not found!", "error")
            return redirect(url_for('teacher_dashboard'))

        return render_template('teacher/exam_link.html', exam_link=unique_id)
    except mysql.connector.Error as err:
        flash(f"Error: {err}", "error")
        return redirect(url_for('teacher_dashboard'))
    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()



@app.route('/teacher/tr_result')
def teacher_result():
    authority_id = session.get('authority_id')
    if not authority_id:
        flash("Please log in first!", "warning")
        return redirect(url_for('teacher_login'))

    db = None
    cursor = None
    profile_image = None
    fullname = None
    results_data = []

    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor(dictionary=True)  # Use dictionary cursor

        # Fetch teacher's full name
        cursor.execute("SELECT fullname FROM exam_authority WHERE authority_id = %s", (authority_id,))
        authority_info = cursor.fetchone()
        fullname = authority_info['fullname'] if authority_info else None

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM teacher_profiles WHERE id = %s", (authority_id,))
        profile_result = cursor.fetchone()
        if profile_result and profile_result['profile_image']:
            profile_image = base64.b64encode(profile_result['profile_image']).decode('utf-8')

        # Fetch student results for exams created by this teacher
        cursor.execute("""
            SELECT sa.answer_id, sa.user_id, sa.exam_id, sa.fullname, 
                sa.submitted_at, sa.exam_title, sa.score, sa.status 
            FROM student_result sa
            JOIN exam_info ei ON sa.exam_id = ei.exam_id
            WHERE ei.authority_id = %s
            ORDER BY sa.submitted_at DESC
        """, (authority_id,))
        results_data = cursor.fetchall()

    except mysql.connector.Error as err:
        flash(f"Error: {err}", "error")
        return redirect(url_for('teacher_login'))

    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()

    return render_template(
        'teacher/tr_result.html',
        profile_image=profile_image,
        fullname=fullname,
        results=results_data
    )



@app.route('/submit_teacher_complaint', methods=['POST'])
def submit_teacher_complaint():
    if request.method == 'POST':
        complaint_text = request.form['complaint_text']
        authority_id = session.get('authority_id')  # Get user_id from session

        if not authority_id:
            flash("User ID not found. Please log in again.", "error")
            return redirect(url_for('teacher_login'))

        connection = None
        try:
            connection = mysql.connector.connect(**db_config)
            cursor = connection.cursor()

            # Insert the complaint into the complaints table
            query = '''INSERT INTO complaints (authority_id, complaint_text, status)
                       VALUES (%s, %s, %s)'''
            cursor.execute(query, (authority_id, complaint_text, 'Pending'))
            connection.commit()

            flash("Complaint submitted successfully!", "success")
            return redirect(url_for('teacher_complaint'))

        except mysql.connector.Error as err:
            flash(f"Error: {err}", "error")
            return redirect(url_for('teacher_complaint'))

        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    return redirect(url_for('teacher_complaint'))



@app.route('/teacher/tr_complaint')
def teacher_complaint():
    authority_id = session.get('authority_id')  # Get user ID from session

    if not authority_id:
        flash("User ID not found. Please log in again.", "error")
        return redirect(url_for('teacher_login'))
    
    connection = None
    profile_image = None
    complaints = []
    fullname = None  # Add a variable for the full name

    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)

        # Fetch full name from exam_authority table
        cursor.execute("SELECT fullname FROM exam_authority WHERE authority_id = %s", (authority_id,))
        authority_info = cursor.fetchone()
        if authority_info:
            fullname = authority_info['fullname']

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM teacher_profiles WHERE id = %s", (authority_id,))
        result = cursor.fetchone()

        if result and result['profile_image']:
            profile_image = base64.b64encode(result['profile_image']).decode('utf-8')

        # Retrieve complaints of the logged-in teacher
        query = "SELECT complaint_text, reply_text, status FROM complaints WHERE authority_id = %s ORDER BY complaint_id DESC"
        cursor.execute(query, (authority_id,))
        complaints = cursor.fetchall()  # Fetch all complaints

    except mysql.connector.Error as err:
        flash(f"Error retrieving complaints: {err}", "error")

    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

    return render_template('teacher/tr_complaint.html', complaints=complaints, profile_image=profile_image, fullname=fullname)



@app.route('/teacher/tr_profile')
def teacher_profile():
    connection = None
    cursor = None

    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Fetch authority_id from session
        authority_id = session.get('authority_id')

        if not authority_id:
            flash("Authority ID not found. Please log in again.", "error")
            return redirect(url_for('teacher_login'))
        

        # Fetch profile image and latest personal details
        cursor.execute('''SELECT full_name, email, phone, address 
                          FROM teacher_personal_info 
                          WHERE authority_id = %s''', (authority_id,))
        result = cursor.fetchone()

        teacher_data = {}
        if result:
            teacher_data = {
                'full_name': result[0],
                'email': result[1],
                'phone': result[2],
                'address': result[3]
            }
        else:
            # Fallback to exam_authority if no personal info exists
            cursor.execute('''SELECT fullname, email, contact 
                              FROM exam_authority 
                              WHERE authority_id = %s''', (authority_id,))
            
            result = cursor.fetchone()
            if result:
                teacher_data = {
                    'full_name': result[0],
                    'email': result[1],
                    'phone': result[2],
                    'address': ''  # Address not available in exam_authority
                }

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM teacher_profiles WHERE id = %s", (authority_id,))
        image_result = cursor.fetchone()

        profile_image = None
        if image_result and image_result[0]:
            profile_image = base64.b64encode(image_result[0]).decode('utf-8')  # Convert binary to base64 for HTML


        # Fetch academic information
        cursor.execute('''SELECT degree, specialization, year 
                          FROM teacher_academic_info 
                          WHERE authority_id = %s''', (authority_id,))
        academic_result = cursor.fetchone()

        academic_data = {}
        if academic_result:
            academic_data = {
                'degree': academic_result[0],
                'specialization': academic_result[1],
                'year': academic_result[2]
            }

        # Fetch subjects taught
        cursor.execute('''SELECT sub_taught FROM teacher_achieve 
                          WHERE authority_id = %s AND sub_taught IS NOT NULL''', (authority_id,))
        subjects = [row[0] for row in cursor.fetchall()]

        # Fetch achievements
        cursor.execute('''SELECT achieve FROM teacher_achieve 
                          WHERE authority_id = %s AND achieve IS NOT NULL''', (authority_id,))
        achievements = [row[0] for row in cursor.fetchall()]

        return render_template('teacher/tr_profile.html', 
                               profile_image=profile_image,
                               teacher_data=teacher_data,
                               academic_data=academic_data,
                               subjects=subjects,
                               achievements=achievements)

    except mysql.connector.Error as err:
        flash(f"Error: {err}", "error")
        return redirect(url_for('teacher_profile'))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    

@app.route('/teacher/edit_profile', methods=['GET', 'POST'])
def teacher_edit_profile():
    authority_id = session.get('authority_id')
    if not authority_id:
        return redirect(url_for('teacher_login'))

    connection = None
    cursor = None
    profile_image = None
    fullname = None

    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Fetch teacher's fullname from authorities table
        cursor.execute("SELECT fullname FROM exam_authority WHERE id = %s", (authority_id,))
        authority_info = cursor.fetchone()
        if authority_info:
            fullname = authority_info[0]

        # Fetch profile image
        cursor.execute("SELECT profile_image FROM teacher_profiles WHERE id = %s", (authority_id,))
        result = cursor.fetchone()
        if result and result[0]:
            profile_image = base64.b64encode(result[0]).decode('utf-8')

        if request.method == 'POST':
            # Handle image removal
            if 'remove-image' in request.form:
                cursor.execute("""
                    UPDATE teacher_profiles 
                    SET profile_image = NULL 
                    WHERE id = %s
                """, (authority_id,))
                connection.commit()
                return redirect(url_for('teacher_profile'))  # Fixed redirect

            # Handle image upload
            if 'profile-picture' in request.files:
                file = request.files['profile-picture']
                if file.filename != '' and allowed_file(file.filename):
                    image_data = file.read()
                    # Use INSERT ... ON DUPLICATE KEY UPDATE to handle new/existing profiles
                    cursor.execute("""
                        INSERT INTO teacher_profiles (id, profile_image)
                        VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE profile_image = %s
                    """, (authority_id, image_data, image_data))
                    connection.commit()
                    return redirect(url_for('teacher_profile'))

    except mysql.connector.Error as err:
        if connection:
            connection.rollback()
        flash(f"Database error: {str(err)}", "error")
        return redirect(url_for('teacher_dashboard'))
    
    except Exception as e:
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for('teacher_dashboard'))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return render_template('teacher/edit_profile.html', 
                         profile_image=profile_image, 
                         fullname=fullname)




@app.route('/teacher/edit_personal_info', methods=['GET', 'POST'])
def teacher_personal():
    connection = None
    cursor = None
    teacher_data = {}

    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        authority_id = session.get('authority_id')
        if not authority_id:
            flash("Authority ID not found. Please log in again.", "error")
            return redirect(url_for('teacher_login'))

        if request.method == 'GET':
            # Check existing personal info in teacher_personal_info
            cursor.execute('''
                SELECT full_name, email, phone, address
                FROM teacher_personal_info
                WHERE authority_id = %s
            ''', (authority_id,))
            result = cursor.fetchone()

            if result:
                teacher_data = {
                    'full_name': result[0],
                    'email': result[1],
                    'phone': result[2],
                    'address': result[3]
                }
            else:
                # Fallback to exam_authority
                cursor.execute('''
                    SELECT fullname, email, contact
                    FROM exam_authority
                    WHERE authority_id = %s
                ''', (authority_id,))
                result = cursor.fetchone()

                if result:
                    teacher_data = {
                        'full_name': result[0],  # Corrected key from 'fullname' to 'full_name'
                        'email': result[1],
                        'phone': result[2],
                        'address': ''  # exam_authority doesn't have address
                    }

            return render_template('teacher/edit_personal_info.html', teacher_data=teacher_data)

        elif request.method == 'POST':
            # Process form data and update both tables
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            phone = request.form.get('phone')
            address = request.form.get('address')

            # Update teacher_personal_info
            cursor.execute('''
                INSERT INTO teacher_personal_info (authority_id, full_name, email, phone, address)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    full_name = VALUES(full_name),
                    email = VALUES(email),
                    phone = VALUES(phone),
                    address = VALUES(address)
            ''', (authority_id, full_name, email, phone, address))

            # Update exam_authority
            cursor.execute('''
                UPDATE exam_authority
                SET fullname = %s, email = %s, contact = %s
                WHERE authority_id = %s
            ''', (full_name, email, phone, authority_id))

            connection.commit()
            flash("Personal Information updated successfully!", "success")
            return redirect(url_for('teacher_profile'))

    except mysql.connector.Error as err:
        flash(f"Database Error: {err}", "error")
        return redirect(url_for('teacher_personal'))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route('/teacher/academic', methods=['GET', 'POST'])
def teacher_academic():
    if 'authority_id' not in session:
        return redirect(url_for('teacher_login'))

    authority_id = session['authority_id']
    
    if request.method == 'POST':
        connection = None
        cursor = None
        try:
            degree = request.form['degree']
            specialization = request.form['specialization']
            year = request.form['year']

            connection = mysql.connector.connect(**db_config)
            cursor = connection.cursor()

            # Upsert query
            query = """INSERT INTO teacher_academic_info 
                       (authority_id, degree, specialization, year)
                       VALUES (%s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                       degree = VALUES(degree),
                       specialization = VALUES(specialization),
                       year = VALUES(year)"""
            
            cursor.execute(query, (authority_id, degree, specialization, year))
            connection.commit()
            
            flash("Academic information updated successfully!", "success")
            return redirect(url_for('teacher_profile'))

        except mysql.connector.Error as err:
            flash(f"Database error: {err}", "error")
            return redirect(url_for('teacher_academic'))
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()
    
    else:  # GET request
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(**db_config)
            cursor = connection.cursor(dictionary=True)

            cursor.execute('''SELECT degree, specialization, year 
                            FROM teacher_academic_info 
                            WHERE authority_id = %s''', (authority_id,))
            academic_data = cursor.fetchone()

            return render_template('teacher/edit_academic_info.html', 
                                 academic_data=academic_data or {})

        except mysql.connector.Error as err:
            flash(f"Database error: {err}", "error")
            return redirect(url_for('teacher_profile'))
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()
            

@app.route('/teacher/edit_subjects', methods=['GET', 'POST'])
def edit_subjects():
    if 'authority_id' not in session:
        return redirect(url_for('teacher_login'))

    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()

    if request.method == 'POST':
        # Delete existing subjects
        cursor.execute("DELETE FROM teacher_achieve WHERE authority_id = %s AND sub_taught IS NOT NULL", 
                      (session['authority_id'],))
        
        # Insert new subjects
        subjects = request.form.getlist('subjects[]')
        for subject in subjects:
            if subject.strip():
                cursor.execute("INSERT INTO teacher_achieve (authority_id, sub_taught) VALUES (%s, %s)",
                              (session['authority_id'], subject.strip()))
        connection.commit()
        flash("Subjects updated successfully!", "success")
        return redirect(url_for('teacher_profile'))

    # GET existing subjects
    cursor.execute("SELECT sub_taught FROM teacher_achieve WHERE authority_id = %s AND sub_taught IS NOT NULL",
                  (session['authority_id'],))
    subjects = [row[0] for row in cursor.fetchall()]
    
    cursor.close()
    connection.close()
    return render_template('teacher/edit_sub_tght.html', subjects=subjects)


@app.route('/teacher/edit_achievements', methods=['GET', 'POST'])
def edit_achievements():
    if 'authority_id' not in session:
        return redirect(url_for('teacher_login'))

    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()

    if request.method == 'POST':
        # Delete existing achievements
        cursor.execute("DELETE FROM teacher_achieve WHERE authority_id = %s AND achieve IS NOT NULL", 
                      (session['authority_id'],))
        
        # Insert new achievements
        achievements = request.form.getlist('achievements[]')
        for achievement in achievements:
            if achievement.strip():
                cursor.execute("INSERT INTO teacher_achieve (authority_id, achieve) VALUES (%s, %s)",
                              (session['authority_id'], achievement.strip()))
        connection.commit()
        flash("Achievements updated successfully!", "success")
        return redirect(url_for('teacher_profile'))

    # GET existing achievements
    cursor.execute("SELECT achieve FROM teacher_achieve WHERE authority_id = %s AND achieve IS NOT NULL",
                  (session['authority_id'],))
    achievements = [row[0] for row in cursor.fetchall()]
    
    cursor.close()
    connection.close()
    return render_template('teacher/edit_achievements.html', achievements=achievements)


@app.route('/teacher/student_answers')
def student_answers():
    authority_id = session.get('authority_id')
    if not authority_id:
        flash("Please log in first!", "warning")
        return redirect(url_for('teacher_login'))

    answer_id = request.args.get('answer_id')
    if not answer_id:
        flash("Invalid request.", "error")
        return redirect(url_for('teacher_result'))

    db = None
    cursor = None
    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor(dictionary=True)

        # Verify the submission belongs to the teacher's exam
        cursor.execute("""
            SELECT sa.fullname, sa.exam_title, ei.authority_id 
            FROM student_result sa
            JOIN exam_info ei ON sa.exam_id = ei.exam_id
            WHERE sa.answer_id = %s
        """, (answer_id,))
        submission_info = cursor.fetchone()

        if not submission_info or submission_info['authority_id'] != authority_id:
            flash("Unauthorized access.", "error")
            return redirect(url_for('teacher_result'))

        # Fetch the student's answers for this submission
        cursor.execute("""
            SELECT eq.question_id, eq.question_text, eq.options, sad.answer, eq.marks, eq.question_image 
            FROM student_answers sad
            JOIN exam_questions eq ON sad.question_id = eq.question_id
            WHERE sad.answer_id = %s
        """, (answer_id,))
        answers = cursor.fetchall()

        # Convert question images to base64
        for answer in answers:
            if answer['question_image']:
                answer['question_image'] = base64.b64encode(answer['question_image']).decode('utf-8')
            else:
                answer['question_image'] = None

        return render_template(
            'teacher/student_answers.html',
            fullname=submission_info['fullname'],
            exam_title=submission_info['exam_title'],
            answers=answers,
            answer_id=answer_id  # Pass answer_id to the template
        )

    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")
        return redirect(url_for('teacher_result'))
    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()


# app.py
@app.route('/teacher/submit_marks', methods=['POST'])
def submit_marks():
    authority_id = session.get('authority_id')
    if not authority_id:
        flash("Please log in first!", "warning")
        return redirect(url_for('teacher_login'))

    answer_id = request.form.get('answer_id')
    overall_mark = request.form.get('overall-mark')
    overall_status = request.form.get('overall-status')

    if not answer_id or not overall_mark or not overall_status:
        flash("All fields are required.", "error")
        return redirect(url_for('student_answers', answer_id=answer_id))

    db = None
    cursor = None
    try:
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor()

        # Verify the teacher's authority over this exam
        cursor.execute("""
            SELECT ei.authority_id 
            FROM student_result sa
            JOIN exam_info ei ON sa.exam_id = ei.exam_id
            WHERE sa.answer_id = %s
        """, (answer_id,))
        result = cursor.fetchone()

        if not result or result[0] != authority_id:
            flash("Unauthorized action.", "error")
            return redirect(url_for('teacher_result'))

        # Update the student's results
        cursor.execute("""
            UPDATE student_result 
            SET score = %s, status = %s 
            WHERE answer_id = %s
        """, (int(overall_mark), overall_status, answer_id))
        db.commit()

        flash("Marks and status updated successfully!", "success")
        return redirect(url_for('teacher_result'))

    except mysql.connector.Error as err:
        if db:
            db.rollback()
        flash(f"Database error: {err}", "error")
        return redirect(url_for('student_answers', answer_id=answer_id))
    except ValueError:
        flash("Invalid marks entered.", "error")
        return redirect(url_for('student_answers', answer_id=answer_id))
    finally:
        if cursor:
            cursor.close()
        if db and db.is_connected():
            db.close()






@app.route('/teacher/monitor')
def teacher_monitor():
    exam_id = request.args.get('exam_id')
    if not exam_id:
        flash("Exam ID is missing!", "danger")
        return redirect(url_for('teacher_dashboard'))

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        # Fetch exam title
        cursor.execute("SELECT exam_title FROM exam_info WHERE exam_id = %s", (exam_id,))
        exam = cursor.fetchone()
        
        # Rest of the violations query remains the same
        cursor.execute("""
            SELECT v.*, u.fullname AS student_name, u.email 
            FROM exam_violations v
            JOIN users u ON v.user_id = u.user_id
            WHERE v.exam_id = %s
            ORDER BY v.timestamp DESC
        """, (exam_id,))
        violations = cursor.fetchall()

        return render_template(
            'teacher/monitor.html',
            exam_title=exam['exam_title'],
            exam_id=exam_id,
            violations=violations  # Removed exam_start_time
        )

    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "danger")
        return redirect(url_for('teacher_dashboard'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

















@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        # You can add additional server-side validation here if needed
        pass
    return render_template('admin/ad_login.html')


# Custom filter for datetime formatting
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M:%S'):
    return value.strftime(format)

@app.route('/admin/adash')
def admin_dashboard():
    connection = None
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)

        # Retrieve only unresolved complaints (where reply_text is NULL or status is 'Pending')
        query = """SELECT * FROM complaints 
                   WHERE reply_text IS NULL OR status = 'Pending' 
                   ORDER BY complaint_id DESC"""
        cursor.execute(query)
        complaints = cursor.fetchall()

        # Format submission_time for display
        for complaint in complaints:
            complaint['submission_time'] = complaint['submission_time'].strftime('%Y-%m-%d %H:%M:%S')

    except mysql.connector.Error as err:
        flash(f"Error retrieving complaints: {err}", "error")
        complaints = []  # Set complaints to empty if an error occurs

    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

    return render_template('admin/adash.html', complaints=complaints)

@app.route('/send_reply', methods=['POST'])
def send_reply():
    if request.method == 'POST':
        reply_text = request.form['reply_text']
        complaint_id = request.form['complaint_id']

        connection = None
        try:
            connection = mysql.connector.connect(**db_config)
            cursor = connection.cursor()

            # Update the complaint with the reply and set status to 'Resolved'
            query = """UPDATE complaints 
                       SET reply_text = %s, status = 'Resolved'
                       WHERE complaint_id = %s"""
            cursor.execute(query, (reply_text, complaint_id))
            connection.commit()

            flash("Reply sent successfully!", "success")
            return redirect(url_for('admin_dashboard'))

        except mysql.connector.Error as err:
            flash(f"Error: {err}", "error")
            return redirect(url_for('admin_dashboard'))

        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

    return redirect(url_for('admin_dashboard'))





@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    
    if user_id:
        try:
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            
            # Clear the session_id in the database
            cursor.execute("UPDATE users SET session_id = NULL WHERE user_id = %s", (user_id,))
            conn.commit()
            
        except mysql.connector.Error as err:
            flash(f"Database error: {err}", "danger")
        
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    # Clear session
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('authority_id', None)
    # Clear cookie
    response = make_response(redirect(url_for('home')))
    response.set_cookie('session_id', '', expires=0)
    
    return response

if __name__ == '__main__':
    app.run(debug=True)
