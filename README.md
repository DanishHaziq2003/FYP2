# FYP2
# 🐠 IoT-Based Smart Aquarium Monitoring System

This project is an AI-powered, IoT-based smart aquarium monitoring dashboard. It continuously monitors **temperature**, **pH**, and **TDS** levels using sensors connected to an **ESP32**, stores the data in **Firebase**, and provides **real-time predictions and alert notifications** via a web dashboard and email (Mailhog).

---

## 🔧 Features

- 🌡️ **Sensor Integration**  
  Real-time data from temperature (DS18B20), pH (PH-4502C), and TDS sensors.

- 🔁 **ESP32 + Firebase**  
  ESP32 reads sensor values and pushes data to Firebase Realtime Database.

- 📊 **ML Prediction Model**  
  Predicts aquarium water quality using a trained classification model (joblib `.pkl`).

- 📬 **Alert Notification System**  
  Automatically sends email alerts via **Mailhog** when water quality drops.

- 💻 **Live Dashboard** (Flask + Socket.IO)  
  - Start/Stop Monitoring  
  - Real-time prediction updates  
  - Dashboard status and statistics

- 📈 **Historical View**  
  Fetches and analyzes past readings to detect patterns or track anomalies.

---

## 📂 Project Structure

```bash
├── main.py                 # Flask app with ML logic and Socket.IO integration
├── templates/
│   └── index.html          # Real-time dashboard frontend
├── model.pkl               # Trained classification model (joblib)
├── features.pkl            # Feature list used by the model
├── test.py                 # Script to test model with manual data
├── static/                 # CSS, JS (optional)
└── README.md               # You're here!
