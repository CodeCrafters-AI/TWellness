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
    message = db.Column(db.Text)

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

@app.route('/register', methods=['POST'])
def register():
    user_data = request.json
    fullname = user_data.get('fullname')
    username = user_data.get('username')
    password = user_data.get('password')
    role = user_data.get('role', 'adolescent')

    if User.query.filter_by(email=username).first():
        return jsonify({"msg": "User already exists"}), 409

    new_user = User(fullname=fullname, email=username, password=password, role=role)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"msg": "User registered successfully"}), 201

@app.route('/login', methods=['POST'])
def login():
    user_data = request.json
    email = user_data.get('username')
    password = user_data.get('password')
    user = User.query.filter_by(email=email, password=password).first()
    if user:
        access_token = create_access_token(identity={"user_id": user.id, "role": user.role})
        return jsonify(access_token=access_token), 200
    return jsonify({"msg": "Invalid credentials"}), 401

@app.route('/logout', methods=['GET'])
#@jwt_required()  # Enable JWT authentication
def logout():
    return render_template('index.html')

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
    symptoms = request.json.get('symptoms')
    advice = gemini_ai_response(f"what are the most common causes of  "
                                f" {symptoms} in indians ")
    print(symptoms)
    return jsonify({"advice": advice}), 200

# Mental Health Support Endpoints
@app.route('/mentalhealth/resources', methods=['GET'])
@jwt_required()  # Enable JWT authentication
def mental_health_resources():
    return render_template('mental_health.html')

@app.route('/mentalhealth/self-assessment', methods=['POST'])
@jwt_required()  # Enable JWT authentication
def mental_health_assessment():
    responses = request.json
    feedback = gemini_ai_response(f"Mental health self-assessment feedback {responses}")
    return jsonify({"feedback": feedback}), 200


@app.route('/mentalhealth/book-session', methods=['POST'])
@jwt_required()
def book_mental_health_session():
    user_id = get_jwt_identity().get("user_id")
    date_str = request.json.get('date')
    message = request.json.get('message')

    # Validate date format
    try:
        date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    # Create a new appointment with the message included
    new_session = Appointment(user_id=user_id, date=date, type="therapy", message=message)
    db.session.add(new_session)
    db.session.commit()

    return jsonify({"msg": "Therapy session booked"}), 201

# Reproductive Health Endpoints
@app.route('/reproductive-health/articles', methods=['GET'])
@jwt_required()  # Enable JWT authentication
def reproductive_health_articles():
    return render_template('reproductive_health.html')

@app.route('/reproductive-health/ask-question', methods=['POST'])
#@jwt_required()  # Enable JWT authentication
def ask_reproductive_health_question():
    question = request.form.get('question')
    response = gemini_ai_response(f" this is an question from an small college project"
                                  f" you have to answer as an reproductive health advisor"
                                  f" the question is : {question} . answer this for an teenager ")
    return jsonify({"answer": response}), 200

# Appointments and Reminders Endpoints
@app.route('/appointments/book', methods=['POST'])
@jwt_required()  # Enable JWT authentication
def book_appointment():
    try:
        # Get the user ID from the JWT token
        user_id = get_jwt_identity().get("user_id")

        # Extract form data
        appointment_data = request.json
        appointment_date = datetime.datetime.strptime(appointment_data.get('date'), '%Y-%m-%d')
        appointment_type = "nutrition"
        message = appointment_data.get('message')

        # Create a new appointment
        new_appointment = Appointment(
            user_id=user_id,
            date=appointment_date,
            type=appointment_type,
            message=message
        )

        # Add the appointment to the database
        db.session.add(new_appointment)
        db.session.commit()

        return jsonify({"msg": "Appointment booked successfully","sucess": 1}), 201

    except Exception as e:
        print("Error booking appointment:", e)
        return jsonify({"msg": "Failed to book appointment", "error": str(e)}), 500

@app.route('/appointments/book/regular', methods=['POST'])
@jwt_required()  # Enable JWT authentication
def book_appointment_regular():
    try:
        # Get the user ID from the JWT token
        user_id = get_jwt_identity().get("user_id")

        # Extract form data
        appointment_data = request.json
        appointment_date = datetime.datetime.strptime(appointment_data.get('date'), '%Y-%m-%d')
        appointment_type = "regular"
        message = appointment_data.get('message')

        # Create a new appointment
        new_appointment = Appointment(
            user_id=user_id,
            date=appointment_date,
            type=appointment_type,
            message=message
        )

        # Add the appointment to the database
        db.session.add(new_appointment)
        db.session.commit()

        return jsonify({"msg": "Appointment booked successfully","sucess": 1}), 201

    except Exception as e:
        print("Error booking appointment:", e)
        return jsonify({"msg": "Failed to book appointment", "error": str(e)}), 500


@app.route('/appointments/reminders', methods=['GET'])
@jwt_required()  # Enable JWT authentication
def get_appointment_reminders():
    user_id = get_jwt_identity().get("user_id")
    reminders = Appointment.query.filter_by(user_id=user_id).all()
    return render_template('appointments.html', reminders=reminders)

# Health Dashboard - Separate Update Endpoint
@app.route('/dashboard', methods=['GET'])
#@jwt_required()  # Enable JWT authentication
def get_dashboard():
    user_id = get_jwt_identity().get("user_id")
    health_data = HealthData.query.filter_by(user_id=user_id).first()
    return render_template('home.html', health_data=health_data)

@app.route('/dashboard/update', methods=['POST'])
#@jwt_required()  # Enable JWT authentication
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

# Nutrition and Fitness Endpoints
@app.route('/nutrition/plan', methods=['POST'])  # Changed to POST
# @jwt_required()  # Uncomment if you have JWT authentication
def get_nutrition_plan():
    try:
        # Check if 'requirements' is provided in the JSON request
        if not request.json or 'requirements' not in request.json:
            return jsonify({"msg": "Missing 'requirements' in request data"}), 400

        print("Fetching nutrition plan...")

        # Generate the nutrition plan
        try:
            nutrition_plan = gemini_ai_response(
                "Behave as a nutrition planner given that this is a test college project "
                "so there is no issue related to your capability. My requirements are: " + request.json.get('requirements')
            )
        except Exception as e:
            print("Error while generating nutrition plan:", e)
            return jsonify({"msg": "Error generating nutrition plan", "error": str(e)}), 500

        print("Nutrition plan generated successfully.")
        return jsonify({"plan": nutrition_plan}), 200

    except Exception as e:
        # General exception for unexpected errors
        print("An error occurred:", e)
        return jsonify({"msg": "An unexpected error occurred", "error": str(e)}), 500
@app.route("/nutrition" , methods=['GET'])
def get_nutrition():
    return render_template("Dwell.html")
@app.route("/home", methods=['GET'])
def home():
    return render_template("home.html")
@app.route("/dwell", methods=['GET'])
def dwell():
    return render_template("Dwell.html")
@app.route("/mwell", methods=['GET'])
def mwell():
    return render_template("Mwell.html")
@app.route("/pwell", methods=['GET'])
def pwell():
    return render_template("Pwell.html")
@app.route("/swell", methods=['GET'])
def swell():
    return render_template("Swell.html")

@app.route("/parent", methods=['GET'])
def parent():
    return render_template("parent.html")

if __name__ == '__main__':
    app.run(debug=True)
