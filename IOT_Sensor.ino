#define BLYNK_TEMPLATE_ID "TMPL66oPLY30w"
#define BLYNK_TEMPLATE_NAME "Aquarium IoT"
#define BLYNK_AUTH_TOKEN "JPIxxVh25IwQk161zPHqpFk6-Yk1Fr-b"
#define BLYNK_PRINT Serial

#define TdsSensorPin 32
#define VREF 3.3
#define SCOUNT 30
#define RELAY_PIN 18

#include <OneWire.h>
#include <DallasTemperature.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <BlynkSimpleEsp32.h>
#include <Firebase_ESP_Client.h>

#include "addons/TokenHelper.h"

#include "addons/RTDBHelper.h"


#define API_KEY "AIzaSyBEKnbWHQ304mnGyMvoUCmWWO13ct1MRYg"
#define USER_EMAIL "neodanish123@gmail.com"
#define USER_PASSWORD "Danish123"
#define DATABASE_URL "https://aquariumdata-3d6fa-default-rtdb.asia-southeast1.firebasedatabase.app/"


FirebaseData fbdo;
FirebaseAuth auth;
FirebaseConfig config;

char ssid[] = "TP-Link_D1F2";
char pass[] = "18947809";

BlynkTimer timer;

int analogBuffer[SCOUNT];
int analogBufferTemp[SCOUNT];
int analogBufferIndex = 0;

float averageVoltage = 0;
float tdsValue;
float temperature = 25;
float temperatureC;

const int oneWireBus = 27;
OneWire oneWire(oneWireBus);
DallasTemperature sensors(&oneWire);

const int ph_Pin = 34;
float Po;
float PH_step;
int PH_analog_val;
double VoltPh;
float PH4 = 3.3;
float PH7 = 2.6;


String uid;


String databasePath;

String temperatureCPath = "/temperatureC";
String PoPath = "/Po";
String tdsValuePath = "/tdsValue";
String dtPath = "/dateTime";
String timePath = "/timestamp";


String parentPath;

int timestamp;
FirebaseJson json;
const char* ntpServer = "pool.ntp.org";


unsigned long getTime(char* buffer, size_t bufferSize) {
  time_t now;
  struct tm timeinfo;


  if (!getLocalTime(&timeinfo)) {
    Serial.println("Failed to obtain time");
    return 0;
  }

  
  strftime(buffer, bufferSize, "%Y-%m-%d %H:%M:%S", &timeinfo);


  time(&now);
  return now;
}

BLYNK_WRITE(V3) {
  int relayState = param.asInt();  
  digitalWrite(RELAY_PIN, relayState);
  Serial.print("Relay is now: ");
  Serial.println(relayState ? "ON" : "OFF");
}


int getMedianNum(int bArray[], int iFilterLen) {
  int bTab[iFilterLen];
  for (byte i = 0; i < iFilterLen; i++)
    bTab[i] = bArray[i];
  int i, j, bTemp;
  for (j = 0; j < iFilterLen - 1; j++) {
    for (i = 0; i < iFilterLen - j - 1; i++) {
      if (bTab[i] > bTab[i + 1]) {
        bTemp = bTab[i];
        bTab[i] = bTab[i + 1];
        bTab[i + 1] = bTemp;
      }
    }
  }
  if ((iFilterLen & 1) > 0)
    return bTab[(iFilterLen - 1) / 2];
  else
    return (bTab[iFilterLen / 2] + bTab[iFilterLen / 2 - 1]) / 2;
}

void readAndSendData() {
  sensors.requestTemperatures();
  temperatureC = sensors.getTempCByIndex(0);
  Serial.print("Temperature: ");
  Serial.print(temperatureC);
  Serial.println("ºC");


  PH_analog_val = analogRead(ph_Pin);
  VoltPh = 3.3 / 4095.0 * PH_analog_val;
  PH_step = (PH4 - PH7) / 3;
  Po = 7.00 + ((PH7 - VoltPh) / PH_step);

  Serial.print("PH Value: ");
  Serial.println(Po, 2);

  // TDS Reading
  for (int i = 0; i < SCOUNT; i++) {
    analogBuffer[i] = analogRead(TdsSensorPin);
    delay(10);
  }

  for (int i = 0; i < SCOUNT; i++) {
    analogBufferTemp[i] = analogBuffer[i];
  }

  averageVoltage = getMedianNum(analogBufferTemp, SCOUNT) * (float)VREF / 4096.0;
  float compensationCoefficient = 1.0 + 0.02 * (temperatureC - 25.0);
  float compensationVoltage = averageVoltage / compensationCoefficient;
  tdsValue = (133.42 * compensationVoltage * compensationVoltage * compensationVoltage - 255.86 * compensationVoltage * compensationVoltage + 857.39 * compensationVoltage) * 0.5;

  Serial.print("TDS Value: ");
  Serial.print(tdsValue, 0);
  Serial.println(" ppm");


  Blynk.virtualWrite(V0, temperatureC);
  Blynk.virtualWrite(V1, Po);
  Blynk.virtualWrite(V2, tdsValue);

  if (temperatureC <= 24) {
    Blynk.logEvent("temp_alert", "Temperature below Optimal range please heat up the tank");
    Serial.println("Send Notification - Temperature below Optimal range");
  } else if (temperatureC >= 30) {
    Blynk.logEvent("temp_alert", "Temperature above Optimal range please cool down the tank");
    Serial.println("Send Notification - Temperature above Optimal range");
  }

  if (Po <= 6.5) {
    Blynk.logEvent("ph_alert", "pH level is too low (acidic)! Current reading: " + String(Po) + ". Immediate attention may be required to stabilize water.");
    Serial.println("Send Notification - pH level is too low");
  } else if (Po >= 9.0) {
    Blynk.logEvent("ph_alert", "pH level is too high (alkaline)! Current reading: " + String(Po) + ". Please adjust water accordingly.");
    Serial.println("Send Notification - pH level is too high");
  }

  if (tdsValue <= 200) {
    Blynk.logEvent("tds_alert", "TDS level is below recommended threshold! Current reading: " + String(tdsValue) + " ppm. This may indicate low mineral content.");
    Serial.println("Send Notification - TDS level is below recommended threshold");
  } else if (tdsValue >= 500) {
    Blynk.logEvent("tds_alert", "TDS level is above safe limit! Current reading:  " + String(tdsValue) + " ppm. Check for overfeeding or water contamination.");
    Serial.println("Send Notification - TDS level is above safe limit!");
  }


  sendFirebase(temperatureC, Po, tdsValue);
}

void setup() {
  Serial.begin(115200);
  pinMode(TdsSensorPin, INPUT);
  pinMode(RELAY_PIN, OUTPUT);
  sensors.begin();

  Blynk.begin(BLYNK_AUTH_TOKEN, ssid, pass);


  configTime(28800, 0, ntpServer);

  config.api_key = API_KEY;


  auth.user.email = USER_EMAIL;
  auth.user.password = USER_PASSWORD;

  config.database_url = DATABASE_URL;

  Firebase.reconnectWiFi(true);
  fbdo.setResponseSize(4096);


  config.token_status_callback = tokenStatusCallback; 
  
  config.max_token_generation_retry = 5;

  Firebase.begin(&config, &auth);


  Serial.println("Getting User UID");
  while ((auth.token.uid) == "") {
    Serial.print('.');
    delay(1000);
  }

  uid = auth.token.uid.c_str();
  Serial.print("User UID: ");
  Serial.println(uid);

  
  databasePath = "/UsersData/" + uid + "/readings";

  timer.setInterval(300000L, readAndSendData);  
}

void loop() {
  Blynk.run();
  timer.run();
}

void sendFirebase(float temperatureC, float Po, float tdsValue) {
  char dateTimeString[25];
  unsigned long timestamp = getTime(dateTimeString, sizeof(dateTimeString));

  if (timestamp == 0) {
    Serial.println("Failed to obtain time");
    return;
  }

  
  String parentPath = databasePath + "/" + String(timestamp);


  json.set(temperatureCPath.c_str(), String(temperatureC));
  json.set(PoPath.c_str(), String(Po));
  json.set(tdsValuePath.c_str(), String(tdsValue));
  json.set(dtPath.c_str(), String(dateTimeString));
  json.set(timePath, String(timestamp));


  Serial.printf("Set JSON... %s\n", Firebase.RTDB.setJSON(&fbdo, parentPath.c_str(), &json) ? "ok" : fbdo.errorReason().c_str());

  delay(1000);
}
