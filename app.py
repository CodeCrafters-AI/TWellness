import re
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import os
import requests
import datetime

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = 'your_jwt_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///health_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
jwt = JWTManager(app)

# Environment variable for Gemini API key
GEMINI_API_KEY = "AIzaSyC0dvbkfvsGRGb8kgui7AoToWrOdNV3AAw"  # Replace with actual API key in real use
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(80), unique=True, nullable=False)
    fullname = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'adolescent', 'guardian', or 'healthcare_provider'


class HealthData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sleep_hours = db.Column(db.Float)
    exercise_minutes = db.Column(db.Integer)
    water_intake_liters = db.Column(db.Float)
    mood = db.Column(db.String(50))

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    type = db.Column(db.String(50))

# Initialize the database
@app.before_request
def create_tables():
    db.create_all()

# Function to convert markdown-like syntax to HTML
def convert_to_html(response_text):
    html_text = response_text.replace("\n\n", "<br><br>").replace("\n", "<br>")
    html_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html_text)
    html_text = re.sub(r'\* (.*?)<br>', r'<ul><li>\1</li></ul><br>', html_text)
    html_text = re.sub(r'"(.*?)"', r'<em>\1</em>', html_text)
    return html_text

# Helper function for Gemini API
def gemini_ai_response(prompt):
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }
    params = {"key": GEMINI_API_KEY}
    response = requests.post(GEMINI_API_URL, headers=headers, json=data, params=params)
    if response.status_code == 200:
        return convert_to_html(response.json()['candidates'][0]['content']['parts'][0]['text'])
    else:
        return f"Error: {response.status_code}, {response.text}"

# User Management Endpoints
@app.route('/',methods=['GET','POST'])
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user_data = request.form
        username = user_data.get('username')
        password = user_data.get('password')
        role = user_data.get('role', 'adolescent')

        if User.query.filter_by(username=username).first():
            return jsonify({"msg": "User already exists"}), 409

        new_user = User(username=username, password=password, role=role)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_data = request.form
        username = user_data.get('username')
        password = user_data.get('password')
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            access_token = create_access_token(identity={"user_id": user.id, "role": user.role})
            return jsonify(access_token=access_token), 200
        return jsonify({"msg": "Invalid credentials"}), 401
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
@jwt_required()  # Enable JWT authentication
def logout():
    return jsonify({"msg": "Logout successful"}), 200

# Health Dashboard Endpoints
@app.route('/dashboard', methods=['GET', 'POST'])
@jwt_required()  # Enable JWT authentication
def dashboard():
    user_id = get_jwt_identity().get("user_id")
    if request.method == 'POST':
        data = request.form
        health_data = HealthData.query.filter_by(user_id=user_id).first()
        if health_data:
            health_data.sleep_hours = data.get('sleep_hours')
            health_data.exercise_minutes = data.get('exercise_minutes')
            health_data.water_intake_liters = data.get('water_intake_liters')
            health_data.mood = data.get('mood')
        else:
            health_data = HealthData(
                user_id=user_id,
                sleep_hours=data.get('sleep_hours'),
                exercise_minutes=data.get('exercise_minutes'),
                water_intake_liters=data.get('water_intake_liters'),
                mood=data.get('mood')
            )
            db.session.add(health_data)
        db.session.commit()
    health_data = HealthData.query.filter_by(user_id=user_id).first()
    return render_template('dashboard.html', health_data=health_data)

# Symptom Checker Endpoint
@app.route('/symptoms/check', methods=['POST'])
@jwt_required()  # Enable JWT authentication
def check_symptoms():
    symptoms = request.form.get('symptoms')
    advice = gemini_ai_response(f"Assume you are a physician. This response is for a small college project. "
                                f"Assume I have {symptoms}. What could it be? Answer as a professional.")
    return jsonify({"advice": advice}), 200

# Mental Health Support Endpoints
@app.route('/mentalhealth/resources', methods=['GET'])
@jwt_required()  # Enable JWT authentication
def mental_health_resources():
    return render_template('mental_health.html')

@app.route('/mentalhealth/self-assessment', methods=['POST'])
@jwt_required()  # Enable JWT authentication
def mental_health_assessment():
    responses = request.form
    feedback = gemini_ai_response(f"Mental health self-assessment feedback {responses}")
    return jsonify({"feedback": feedback}), 200

@app.route('/mentalhealth/book-session', methods=['POST'])
@jwt_required()  # Enable JWT authentication
def book_mental_health_session():
    user_id = get_jwt_identity().get("user_id")
    date_str = request.json.get('date')
    date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    new_session = Appointment(user_id=user_id, date=date, type="therapy")
    db.session.add(new_session)
    db.session.commit()
    return jsonify({"msg": "Therapy session booked"}), 201

# Reproductive Health Endpoints
@app.route('/reproductive-health/articles', methods=['GET'])
@jwt_required()  # Enable JWT authentication
def reproductive_health_articles():
    return render_template('reproductive_health.html')

@app.route('/reproductive-health/ask-question', methods=['POST'])
@jwt_required()  # Enable JWT authentication
def ask_reproductive_health_question():
    question = request.form.get('question')
    response = gemini_ai_response(question)
    return jsonify({"answer": response}), 200

# Appointments and Reminders Endpoints
@app.route('/appointments/book', methods=['POST'])
@jwt_required()  # Enable JWT authentication
def book_appointment():
    user_id = get_jwt_identity().get("user_id")
    appointment_data = request.form
    appointment_date = datetime.datetime.strptime(appointment_data.get('date'), '%Y-%m-%d')
    new_appointment = Appointment(user_id=user_id, date=appointment_date, type=appointment_data.get('type'))
    db.session.add(new_appointment)
    db.session.commit()
    return jsonify({"msg": "Appointment booked successfully"}), 201

@app.route('/appointments/reminders', methods=['GET'])
@jwt_required()  # Enable JWT authentication
def get_appointment_reminders():
    user_id = get_jwt_identity().get("user_id")
    reminders = Appointment.query.filter_by(user_id=user_id).all()
    return render_template('appointments.html', reminders=reminders)

# Health Dashboard - Separate Update Endpoint
@app.route('/dashboard', methods=['GET'])
@jwt_required()  # Enable JWT authentication
def get_dashboard():
    user_id = get_jwt_identity().get("user_id")
    health_data = HealthData.query.filter_by(user_id=user_id).first()
    return render_template('dashboard.html', health_data=health_data)

@app.route('/dashboard/update', methods=['POST'])
@jwt_required()  # Enable JWT authentication
def update_dashboard():
    user_id = get_jwt_identity().get("user_id")
    data = request.form
    health_data = HealthData.query.filter_by(user_id=user_id).first()
    if not health_data:
        health_data = HealthData(user_id=user_id)
        db.session.add(health_data)
    health_data.sleep_hours = data.get('sleep_hours')
    health_data.exercise_minutes = data.get('exercise_minutes')
    health_data.water_intake_liters = data.get('water_intake_liters')
    health_data.mood = data.get('mood')
    db.session.commit()
    return jsonify({"msg": "Health data updated successfully"}), 200

if __name__ == '__main__':
    app.run(debug=True)
