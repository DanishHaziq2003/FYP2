import pandas as pd
import requests
import time
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestRegressor
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


DATABASE_URL = "https://aquariumdata-3d6fa-default-rtdb.asia-southeast1.firebasedatabase.app"
NODE_PATH = "/UsersData.json"
FIREBASE_URL = f"{DATABASE_URL}{NODE_PATH}"


EMAIL_FROM = "aquarium-monitor@localhost"
EMAIL_TO = "neodanish123@gmail.com"
SMTP_SERVER = "localhost"
SMTP_PORT = 1025


ACCEPTABLE_RANGES = {
    "temperatureC": (24, 30),
    "tdsValue": (200, 500),
    "Po": (6.5, 8.5)
}


last_timestamp_seen = None

def get_firebase_data():
    """Fetching data from Firebase"""
    try:
        logger.info(f"Fetching data from Firebase...")
        response = requests.get(FIREBASE_URL, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"HTTP Error: {response.status_code}")
            return None
            
        data = response.json()
        
        if not data:
            logger.warning("No data returned")
            return pd.DataFrame()
     
        records = []
        for user_id, user_data in data.items():
            if isinstance(user_data, dict):
                readings = user_data.get("readings", {})
                for reading_id, reading in readings.items():
                    if isinstance(reading, dict):
                        records.append(reading)
        
        logger.info(f"Retrieved {len(records)} total records")
        df = pd.DataFrame(records)
        
        return df
        
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return None

def preprocess_data(df):
    """Clean and prepare data"""
    try:
        if df.empty:
            logger.warning("Empty DataFrame")
            return df
        
   
        required_cols = ["temperatureC", "tdsValue", "Po", "timestamp"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            logger.error(f"Missing columns: {missing_cols}")
            return pd.DataFrame()
        
        df["temperatureC"] = pd.to_numeric(df["temperatureC"], errors='coerce')
        df["tdsValue"] = pd.to_numeric(df["tdsValue"], errors='coerce')
        df["Po"] = pd.to_numeric(df["Po"], errors='coerce')
        
      
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors='coerce')


        if df["timestamp"].max() > 4000000000:  
            df["timestamp"] = df["timestamp"] / 1000
        
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit='s', errors='coerce')
        
      
        initial_count = len(df)
        df = df.dropna(subset=["timestamp", "temperatureC", "tdsValue", "Po"])
        logger.info(f"Cleaned data: {len(df)} valid records (removed {initial_count - len(df)} invalid)")
        
        if df.empty:
            logger.error("No valid data after cleaning")
            return df
        
        df = df.sort_values("timestamp")
        
        
        df["temp_lag1"] = df["temperatureC"].shift(1)
        df["tds_lag1"] = df["tdsValue"].shift(1)
        df["ph_lag1"] = df["Po"].shift(1)
        df["hour"] = df["timestamp"].dt.hour
        df["dayofweek"] = df["timestamp"].dt.dayofweek
        
       
        df = df.dropna()
        
        logger.info(f"Final preprocessed data: {len(df)} rows")
        
        return df
        
    except Exception as e:
        logger.error(f"Preprocessing error: {e}")
        return pd.DataFrame()

def train_and_predict(df):
    """Train models and make predictions"""
    try:
        if len(df) < 3:
            logger.error(f"Need at least 3 records, have {len(df)}")
            return None, None
        
        logger.info("Training models...")
        
     
        temp_features = df[['temp_lag1', 'hour', 'dayofweek']]
        tds_features = df[['tds_lag1', 'hour', 'dayofweek']]
        ph_features = df[['ph_lag1', 'hour', 'dayofweek']]
        
    
        temp_model = RandomForestRegressor(n_estimators=50, random_state=42)
        tds_model = RandomForestRegressor(n_estimators=50, random_state=42)
        ph_model = RandomForestRegressor(n_estimators=50, random_state=42)
        
        temp_model.fit(temp_features, df['temperatureC'])
        tds_model.fit(tds_features, df['tdsValue'])
        ph_model.fit(ph_features, df['Po'])
        
        logger.info("Models trained successfully!")
        
     
        last_row = df.iloc[-1]
        current_temp = last_row['temperatureC']
        current_tds = last_row['tdsValue']
        current_ph = last_row['Po']
        current_time = last_row['timestamp']
        
        last_reading = {
            'timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S'),
            'temperature': round(current_temp, 1),
            'tds': round(current_tds, 0),
            'ph': round(current_ph, 1)
        }
        
        logger.info(f"Last reading: Temp={last_reading['temperature']}°C, TDS={last_reading['tds']}, pH={last_reading['ph']}")
        
     
        predictions = []
        
        for hour in range(1, 9):
            future_time = current_time + timedelta(hours=hour)
            hour_of_day = future_time.hour
            dayofweek = future_time.dayofweek
            
            
            temp_pred = temp_model.predict([[current_temp, hour_of_day, dayofweek]])[0]
            tds_pred = tds_model.predict([[current_tds, hour_of_day, dayofweek]])[0]
            ph_pred = ph_model.predict([[current_ph, hour_of_day, dayofweek]])[0]
            
            prediction = {
                'hour': hour,
                'time': future_time.strftime('%Y-%m-%d %H:%M'),
                'temperature': round(temp_pred, 1),
                'tds': round(tds_pred, 0),
                'ph': round(ph_pred, 1)
            }
            
            predictions.append(prediction)
            
           
            current_temp = temp_pred
            current_tds = tds_pred
            current_ph = ph_pred
        
        logger.info(f"Generated predictions for {len(predictions)} hours")
        return predictions, last_reading
        
    except Exception as e:
        logger.error(f"Training/prediction error: {e}")
        return None, None

def check_alerts(predictions):
    """Check predictions for values outside acceptable ranges"""
    alerts = []
    
    for pred in predictions:
        issues = []
    
        if pred['temperature'] < ACCEPTABLE_RANGES['temperatureC'][0]:
            issues.append(f"Temperature too low ({pred['temperature']}°C)")
        elif pred['temperature'] > ACCEPTABLE_RANGES['temperatureC'][1]:
            issues.append(f"Temperature too high ({pred['temperature']}°C)")
        
        if pred['tds'] < ACCEPTABLE_RANGES['tdsValue'][0]:
            issues.append(f"TDS too low ({pred['tds']})")
        elif pred['tds'] > ACCEPTABLE_RANGES['tdsValue'][1]:
            issues.append(f"TDS too high ({pred['tds']})")
        
  
        if pred['ph'] < ACCEPTABLE_RANGES['Po'][0]:
            issues.append(f"pH too low ({pred['ph']})")
        elif pred['ph'] > ACCEPTABLE_RANGES['Po'][1]:
            issues.append(f"pH too high ({pred['ph']})")
        
        if issues:
            alerts.append({
                'time': pred['time'],
                'hour': pred['hour'],
                'issues': issues,
                'values': pred
            })
    
    return alerts

def create_html_email(predictions, last_reading, alerts):
    """Create HTML email content"""
    

    if alerts:
        status_color = "#ff6b6b"  
        status_message = f" {len(alerts)} Alert(s) Detected"
        status_icon = ""
    else:
        status_color = "#51cf66"  
        status_message = " All Values Normal"
        status_icon = "✅"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Aquarium Monitoring Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f7fa; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 28px; }}
            .header p {{ margin: 10px 0 0 0; opacity: 0.9; }}
            .status {{ background: {status_color}; color: white; padding: 15px; text-align: center; font-weight: bold; font-size: 18px; }}
            .section {{ padding: 30px; }}
            .section h2 {{ color: #333; border-bottom: 2px solid #e9ecef; padding-bottom: 10px; margin-bottom: 20px; }}
            .last-reading {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 30px; }}
            .reading-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; }}
            .reading-item {{ text-align: center; padding: 15px; border: 2px solid #e9ecef; border-radius: 8px; }}
            .reading-value {{ font-size: 24px; font-weight: bold; color: #495057; }}
            .reading-label {{ font-size: 12px; color: #6c757d; margin-top: 5px; }}
            .predictions-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            .predictions-table th {{ background: #495057; color: white; padding: 12px; text-align: left; }}
            .predictions-table td {{ padding: 12px; border-bottom: 1px solid #e9ecef; }}
            .predictions-table tr:nth-child(even) {{ background: #f8f9fa; }}
            .alert-section {{ background: #fff5f5; border: 1px solid #fed7d7; border-radius: 8px; padding: 20px; margin: 20px 0; }}
            .alert-item {{ background: white; border-left: 4px solid #e53e3e; padding: 15px; margin: 10px 0; border-radius: 0 8px 8px 0; }}
            .safe-section {{ background: #f0fff4; border: 1px solid #9ae6b4; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center; }}
            .footer {{ background: #f8f9fa; padding: 20px; text-align: center; color: #6c757d; border-radius: 0 0 10px 10px; }}
            .temp {{ color: #e74c3c; }}
            .tds {{ color: #3498db; }}
            .ph {{ color: #2ecc71; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Aquarium Monitoring Report</h1>
                <p>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
            </div>
            
            <div class="status">
                {status_icon} {status_message}
            </div>
            
            <div class="section">
                <h2>Current Reading</h2>
                <div class="last-reading">
                    <p><strong>Last Updated:</strong> {last_reading['timestamp']}</p>
                    <div class="reading-grid">
                        <div class="reading-item">
                            <div class="reading-value temp">{last_reading['temperature']}°C</div>
                            <div class="reading-label">Temperature</div>
                        </div>
                        <div class="reading-item">
                            <div class="reading-value tds">{last_reading['tds']}</div>
                            <div class="reading-label">TDS</div>
                        </div>
                        <div class="reading-item">
                            <div class="reading-value ph">{last_reading['ph']}</div>
                            <div class="reading-label">pH Level</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>8-Hour Forecast</h2>
                <table class="predictions-table">
                    <thead>
                        <tr>
                            <th>Hour</th>
                            <th>Time</th>
                            <th>Temperature (°C)</th>
                            <th>TDS</th>
                            <th>pH</th>
                        </tr>
                    </thead>
                    <tbody>
    """
    

    for pred in predictions:
        
        temp_class = ""
        tds_class = ""
        ph_class = ""
        
        if pred['temperature'] < ACCEPTABLE_RANGES['temperatureC'][0] or pred['temperature'] > ACCEPTABLE_RANGES['temperatureC'][1]:
            temp_class = 'style="background-color: #ffebee; font-weight: bold;"'
        if pred['tds'] < ACCEPTABLE_RANGES['tdsValue'][0] or pred['tds'] > ACCEPTABLE_RANGES['tdsValue'][1]:
            tds_class = 'style="background-color: #ffebee; font-weight: bold;"'
        if pred['ph'] < ACCEPTABLE_RANGES['Po'][0] or pred['ph'] > ACCEPTABLE_RANGES['Po'][1]:
            ph_class = 'style="background-color: #ffebee; font-weight: bold;"'
        
        html += f"""
                        <tr>
                            <td>+{pred['hour']}h</td>
                            <td>{pred['time']}</td>
                            <td {temp_class}>{pred['temperature']}</td>
                            <td {tds_class}>{pred['tds']}</td>
                            <td {ph_class}>{pred['ph']}</td>
                        </tr>
        """
    
    html += """
                    </tbody>
                </table>
            </div>
    """
    
 
    if alerts:
        html += """
            <div class="section">
                <h2>Alerts</h2>
                <div class="alert-section">
        """
        for alert in alerts:
            html += f"""
                    <div class="alert-item">
                        <strong>+{alert['hour']}h ({alert['time']}):</strong><br>
                        {'<br>'.join(alert['issues'])}
                    </div>
            """
        html += """
                </div>
            </div>
        """
    else:
        html += """
            <div class="section">
                <div class="safe-section">
                    <h3>All Clear!</h3>
                    <p>All predicted values for the next 8 hours are within safe ranges.</p>
                </div>
            </div>
        """
    
 
    html += f"""
            <div class="section">
                <h2>Acceptable Ranges</h2>
                <div class="reading-grid">
                    <div class="reading-item">
                        <div class="reading-value temp">{ACCEPTABLE_RANGES['temperatureC'][0]}-{ACCEPTABLE_RANGES['temperatureC'][1]}°C</div>
                        <div class="reading-label">Temperature</div>
                    </div>
                    <div class="reading-item">
                        <div class="reading-value tds">{ACCEPTABLE_RANGES['tdsValue'][0]}-{ACCEPTABLE_RANGES['tdsValue'][1]}</div>
                        <div class="reading-label">TDS</div>
                    </div>
                    <div class="reading-item">
                        <div class="reading-value ph">{ACCEPTABLE_RANGES['Po'][0]}-{ACCEPTABLE_RANGES['Po'][1]}</div>
                        <div class="reading-label">pH Level</div>
                    </div>
                </div>
            </div>
            
            <div class="footer">
                <p>This report was automatically generated by your Aquarium Monitoring System</p>
                <p>Next check scheduled in 30 minutes</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

def send_email(predictions, last_reading, alerts):
    """Send HTML email via MailHog"""
    try:
        logger.info("Preparing to send email...")
        

        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        msg['Subject'] = f"Aquarium Report - {datetime.now().strftime('%Y-%m-%d')} ({' Alerts' if alerts else ' Normal'})"
        

        html_content = create_html_email(predictions, last_reading, alerts)
        

        text_content = f"""
        Aquarium Monitoring Report
        Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        Last Reading ({last_reading['timestamp']}):
        Temperature: {last_reading['temperature']}°C
        TDS: {last_reading['tds']}
        pH: {last_reading['ph']}
        
        8-Hour Forecast:
        """
        
        for pred in predictions:
            text_content += f"\n+{pred['hour']}h ({pred['time']}): Temp={pred['temperature']}°C, TDS={pred['tds']}, pH={pred['ph']}"
        
        if alerts:
            text_content += f"\n\nALERTS ({len(alerts)} issues detected):\n"
            for alert in alerts:
                text_content += f"\n{alert['time']}: {', '.join(alert['issues'])}"
        else:
            text_content += "\n\nAll predicted values are within safe ranges."
        

        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        server.quit()
        
        logger.info(f"Email sent successfully to {EMAIL_TO}")
        
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

def analyze_and_predict(df):
    """Main analysis function"""
    try:

        processed_df = preprocess_data(df)
        if processed_df.empty:
            logger.error("No valid data after preprocessing")
            return False
        

        predictions, last_reading = train_and_predict(processed_df)
        if predictions is None:
            logger.error("Failed to generate predictions")
            return False

        alerts = check_alerts(predictions)
        

        logger.info("\n8-Hour Forecast:")
        for pred in predictions:
            logger.info(f"  +{pred['hour']}h ({pred['time']}): Temp={pred['temperature']}°C, TDS={pred['tds']}, pH={pred['ph']}")
        
        if alerts:
            logger.warning(f"  {len(alerts)} alert(s) detected")
        else:
            logger.info(" All values within safe ranges")
        
     
        send_email(predictions, last_reading, alerts)
        
        return True
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return False

def initial_analysis():
    """Perform initial analysis at startup"""
    logger.info("=" * 70)
    logger.info(" STARTING AQUARIUM MONITORING SYSTEM")
    logger.info("=" * 70)
    
    df = get_firebase_data()
    if df is None or df.empty:
        logger.error(" No data available for initial analysis")
        return False
    
    logger.info("Performing initial analysis and sending first report...")
    success = analyze_and_predict(df)
    
    if success:
        logger.info(" Initial analysis completed successfully")
    else:
        logger.error(" Initial analysis failed")
    
    return success

def monitor_loop():
    """Main monitoring loop"""
    global last_timestamp_seen
    
 
    initial_success = initial_analysis()
    if not initial_success:
        logger.warning("  Initial analysis failed, but continuing with monitoring...")
    

    df = get_firebase_data()
    if df is not None and not df.empty:
        processed_df = preprocess_data(df)
        if not processed_df.empty:
            last_timestamp_seen = processed_df['timestamp'].max()
            logger.info(f" Monitoring from: {last_timestamp_seen}")
    
    logger.info("\n" + "=" * 70)
    logger.info("  STARTING REAL-TIME MONITORING")
    logger.info(" Checking for new data every 60 seconds")
    logger.info("=" * 70)
    
    while True:
        try:
            df = get_firebase_data()
            if df is None or df.empty:
                logger.info("No data available")
                time.sleep(60)
                continue
            
         
            df_temp = df.copy()
            df_temp["timestamp"] = pd.to_numeric(df_temp["timestamp"], errors='coerce')
            if df_temp["timestamp"].max() > 4000000000:
                df_temp["timestamp"] = df_temp["timestamp"] / 1000
            df_temp["timestamp"] = pd.to_datetime(df_temp["timestamp"], unit='s', errors='coerce')
            
          
            if last_timestamp_seen is not None:
                new_data = df_temp[df_temp['timestamp'] > last_timestamp_seen]
                
                if not new_data.empty:
                    logger.info(f"New data detected! {len(new_data)} new records")
                    logger.info("Running analysis and sending updated report...")
                    
                    if analyze_and_predict(df):
                     
                        processed_df = preprocess_data(df)
                        if not processed_df.empty:
                            last_timestamp_seen = processed_df['timestamp'].max()
                        logger.info(" Analysis completed and email sent")
                    else:
                        logger.error(" Analysis failed")
                else:
                    logger.info(f" No new data at {datetime.now().strftime('%H:%M:%S')}")
            else:
                logger.info("First run - analyzing all available data...")
                analyze_and_predict(df)
                processed_df = preprocess_data(df)
                if not processed_df.empty:
                    last_timestamp_seen = processed_df['timestamp'].max()
            
        except Exception as e:
            logger.error(f" Error in monitoring loop: {e}")

        time.sleep(1800)  

if __name__ == "__main__":
    try:
        monitor_loop()
    except KeyboardInterrupt:
        logger.info("\n Monitoring stopped by user")
    except Exception as e:
        logger.error(f" Fatal error: {e}")