import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import pandas as pd
import joblib
import time
import json
from datetime import datetime
from typing import Dict, Any, Optional
import warnings
import os
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import threading


warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  
pd.options.mode.chained_assignment = None  

app = Flask(__name__)
app.config['SECRET_KEY'] = 'aquarium_monitor_secret'
socketio = SocketIO(app, cors_allowed_origins="*")

class AquariumPredictor:
    def __init__(self, model_path='model.pkl', features_path='features.pkl'):
        """Initialize the predictor with saved model and features"""
        try:
            self.model = joblib.load(model_path)
            self.features = joblib.load(features_path)
            self.status = "Model loaded successfully"
        except FileNotFoundError as e:
            self.status = f"Model files not found: {e}"
            self.model = None
            self.features = None
        
        self.database_url = "https://aquariumdata-3d6fa-default-rtdb.asia-southeast1.firebasedatabase.app"
        self.node_path = "/UsersData.json"
        self.processed_readings = set()
        self.is_monitoring = False
        self.latest_results = []
        self.stats = {
            'total_predictions': 0,
            'correct_predictions': 0,
            'accuracy': 0,
            'last_update': None
        }
    
    def fetch_latest_data(self) -> Dict[str, Any]:
        """Fetch the latest data from Firebase"""
        url = f"{self.database_url}{self.node_path}"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except:
            return {}
    
    def extract_new_records(self, data: Dict[str, Any]) -> list:
        """Extract new records that haven't been processed yet"""
        new_records = []
        
        for user_id, user_data in data.items():
            readings = user_data.get("readings", {})
            for reading_id, reading in readings.items():
                unique_id = f"{user_id}_{reading_id}"
                
                if unique_id not in self.processed_readings:
                    reading['user_id'] = user_id
                    reading['reading_id'] = reading_id
                    reading['unique_id'] = unique_id
                    new_records.append(reading)
                    self.processed_readings.add(unique_id)
        
        return new_records
    
    def clean_record(self, record: Dict[str, Any]) -> Optional[pd.Series]:
        """Clean and validate a single record"""
        try:
            po = pd.to_numeric(record.get("Po"), errors='coerce')
            tds = pd.to_numeric(record.get("tdsValue"), errors='coerce')
            temp = pd.to_numeric(record.get("temperatureC"), errors='coerce')
            
            # Handle timestamp conversion
            timestamp_raw = record.get("timestamp")
            try:
                if isinstance(timestamp_raw, str):
                    timestamp_numeric = float(timestamp_raw)
                else:
                    timestamp_numeric = float(timestamp_raw) if timestamp_raw else 0
                timestamp = pd.to_datetime(timestamp_numeric, unit='s', errors='coerce')
            except:
                timestamp = pd.Timestamp.now()
            
            if pd.isna([po, tds, temp]).any():
                return None
            
            cleaned = pd.Series({
                'Po': po,
                'tdsValue': tds,
                'temperatureC': temp,
                'timestamp': timestamp,
                'user_id': record.get('user_id'),
                'reading_id': record.get('reading_id'),
                'unique_id': record.get('unique_id')
            })
            
            return cleaned
            
        except:
            return None
    
    def predict_condition(self, record: pd.Series) -> Dict[str, Any]:
        """Make prediction for a single record"""
        if self.model is None:
            return None
            
        try:
            features_data = record[self.features].values.reshape(1, -1)
            prediction = self.model.predict(features_data)[0]
            probability = self.model.predict_proba(features_data)[0]
            
            actual_condition = (
                24 <= record["temperatureC"] <= 30 and
                200 <= record["tdsValue"] <= 500 and
                6.5 <= record["Po"] <= 8.5
            )

            is_correct = bool(prediction) == actual_condition
            
            result = {
                'prediction': bool(prediction),
                'actual_condition': actual_condition,
                'is_correct': is_correct,
                'confidence': float(max(probability)),
                'probabilities': {
                    'not_ok': float(probability[0]),
                    'ok': float(probability[1])
                },
                'values': {
                    'temperature': float(record["temperatureC"]),
                    'tds': float(record["tdsValue"]),
                    'po': float(record["Po"])
                },
                'timestamp': record["timestamp"].strftime('%Y-%m-%d %H:%M:%S'),
                'user_id': record["user_id"],
                'reading_id': record["reading_id"]
            }

            if not prediction:
                self.send_email_notification(result)
                
            return result
            
        except:
            return None

    
    def update_stats(self, result: Dict[str, Any]):
        """Update prediction statistics"""
        self.stats['total_predictions'] += 1
        if result['is_correct']:
            self.stats['correct_predictions'] += 1
        
        if self.stats['total_predictions'] > 0:
            self.stats['accuracy'] = (self.stats['correct_predictions'] / self.stats['total_predictions']) * 100
        
        self.stats['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def send_email_notification(self, prediction_result):
        """Send HTML formatted email notification via Mailhog"""
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            sender_email = "aquarium@monitor.com"
            receiver_email = "neodanish123@gmail.com"
            smtp_server = "localhost"
            smtp_port = 1025  # Default Mailhog port
            
            message = MIMEMultipart("alternative")
            message["From"] = sender_email
            message["To"] = receiver_email
            message["Subject"] = "Monitoring Alert: Water Quality Issue Detected"

            status = "OK" if prediction_result['prediction'] else "BELOW SATISFACTORY LEVEL"
            confidence_pct = prediction_result['confidence'] * 100

            html = f"""
            <html>
            <head>
            <style>
                body {{
                font-family: Arial, sans-serif;
                background-color: #f4f7f8;
                color: #333333;
                padding: 20px;
                }}
                .container {{
                background-color: #ffffff;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                max-width: 600px;
                margin: auto;
                }}
                h2 {{
                color: #d9534f;
                }}
                .status {{
                font-weight: bold;
                font-size: 1.2em;
                color: {'#5cb85c' if prediction_result['prediction'] else '#d9534f'};
                }}
                .parameters {{
                margin-top: 20px;
                border-collapse: collapse;
                width: 100%;
                }}
                .parameters th, .parameters td {{
                text-align: left;
                padding: 8px;
                border-bottom: 1px solid #ddd;
                }}
                .footer {{
                margin-top: 30px;
                font-size: 0.9em;
                color: #777777;
                }}
            </style>
            </head>
            <body>
            <div class="container">
                <h2>Water Quality Alert</h2>
                <p>Dear User,</p>
                <p>This is an automated alert from your <strong>Monitoring System</strong>.</p>
                <p><strong>Water Quality Status:</strong> <span class="status">{status}</span></p>
                <p><strong>Confidence Level:</strong> {confidence_pct:.1f}%</p>

                <table class="parameters">
                <thead>
                    <tr><th>Parameter</th><th>Value</th></tr>
                </thead>
                <tbody>
                    <tr><td>Temperature</td><td>{prediction_result['values']['temperature']:.1f} °C</td></tr>
                    <tr><td>Total Dissolved Solids (TDS)</td><td>{prediction_result['values']['tds']:.0f} ppm</td></tr>
                    <tr><td>pH Level</td><td>{prediction_result['values']['po']:.1f}</td></tr>
                    <tr><td>Timestamp</td><td>{prediction_result['timestamp']}</td></tr>
                    <tr><td>User ID</td><td>{prediction_result['user_id']}</td></tr>
                    <tr><td>Reading ID</td><td>{prediction_result['reading_id']}</td></tr>
                </tbody>
                </table>

                

                <p</p>
            </div>
            </body>
            </html>
            """

            part = MIMEText(html, "html")
            message.attach(part)

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.sendmail(sender_email, receiver_email, message.as_string())

        except Exception as e:
            print(f"Failed to send email: {e}")

    
    def monitor_continuous(self, check_interval: int = 5):
        """Monitor Firebase continuously"""
        self.is_monitoring = True
        
        while self.is_monitoring:
            try:
                data = self.fetch_latest_data()
                if data:
                    new_records = self.extract_new_records(data)
                    
                    for record in new_records:
                        cleaned_record = self.clean_record(record)
                        if cleaned_record is not None:
                            result = self.predict_condition(cleaned_record)
                            if result:
                                self.update_stats(result)
                                self.latest_results.append(result)
                                
                                # Keep only last 50 results
                                if len(self.latest_results) > 50:
                                    self.latest_results.pop(0)
                                
                                # Emit to frontend
                                socketio.emit('new_prediction', result)
                                socketio.emit('stats_update', self.stats)
                
                time.sleep(check_interval)
                
            except Exception as e:
                # Silently continue on errors
                time.sleep(check_interval)
    
    def stop_monitoring(self):
        """Stop the monitoring process"""
        self.is_monitoring = False

predictor = AquariumPredictor()


@app.route('/api/historical_data')
def get_historical_data():
    data = predictor.fetch_latest_data()
    if not data:
        return jsonify([])
    
    all_records = []
    for user_id, user_data in data.items():
        readings = user_data.get("readings", {})
        for reading_id, reading in readings.items():
            reading['user_id'] = user_id
            reading['reading_id'] = reading_id
            all_records.append(reading)
    
    sorted_records = sorted(all_records, 
                          key=lambda x: float(x.get('timestamp', 0)), 
                          reverse=True)[:50]
    
    processed = []
    for record in sorted_records:
        cleaned = predictor.clean_record(record)
        if cleaned is not None:
            result = predictor.predict_condition(cleaned)
            if result:
                processed.append({
                    k: v.item() if hasattr(v, 'item') and callable(v.item) else v
                    for k, v in result.items()
                })
    print(processed)
    return jsonify(processed)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    return jsonify({
        'status': predictor.status,
        'is_monitoring': predictor.is_monitoring,
        'model_loaded': predictor.model is not None
    })

@app.route('/api/stats')
def get_stats():
    return jsonify(predictor.stats)

@app.route('/check-latest')
def check_latest():
    print(jsonify(predictor.latest_results[-10:]))
    return jsonify(predictor.latest_results[-10:])  

@socketio.on('start_monitoring')
def start_monitoring():
    if not predictor.is_monitoring and predictor.model is not None:
        monitor_thread = threading.Thread(target=predictor.monitor_continuous)
        monitor_thread.daemon = True
        monitor_thread.start()
        emit('monitoring_status', {'status': 'started'})

@socketio.on('stop_monitoring')
def stop_monitoring():
    predictor.stop_monitoring()
    emit('monitoring_status', {'status': 'stopped'})

@socketio.on('connect')
def handle_connect():
    emit('stats_update', predictor.stats)
    emit('latest_results', predictor.latest_results[-10:])

if __name__ == '__main__':
    print("Starting Aquarium Monitoring Dashboard...")
    print("Access the dashboard at: http://localhost:5000")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)