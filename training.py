import requests
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, accuracy_score, classification_report
import joblib


DATABASE_URL = "https://aquariumdata-3d6fa-default-rtdb.asia-southeast1.firebasedatabase.app"
NODE_PATH = "/UsersData.json"
URL = f"{DATABASE_URL}{NODE_PATH}"

response = requests.get(URL)
if response.status_code != 200:
    print("Failed to retrieve data")
    exit()

data = response.json()

records = []
for user_id, user_data in data.items():
    readings = user_data.get("readings", {})
    for reading_id, reading in readings.items():
        records.append(reading)

df = pd.DataFrame(records)


df["Po"] = pd.to_numeric(df["Po"], errors='coerce')
df["tdsValue"] = pd.to_numeric(df["tdsValue"], errors='coerce')
df["temperatureC"] = pd.to_numeric(df["temperatureC"], errors='coerce')
df["timestamp"] = pd.to_datetime(df["timestamp"], unit='s', errors='coerce')

df.dropna(subset=["Po", "tdsValue", "temperatureC"], inplace=True)


def label_condition(row):
    return (
        24 <= row["temperatureC"] <= 30 and
        200 <= row["tdsValue"] <= 500 and
        6.5 <= row["Po"] <= 8.5
    )

df["is_ok"] = df.apply(label_condition, axis=1)


X = df[["temperatureC", "tdsValue", "Po"]]
y = df["is_ok"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

print(X_test[:5])


y_pred = model.predict(X_test)

print("Confusion Matrix:\n", confusion_matrix(y_test, y_pred))
print(f"\nAccuracy: {accuracy_score(y_test, y_pred):.4f}")
print("\nClassification Report:\n", classification_report(y_test, y_pred))


joblib.dump(["temperatureC", "tdsValue", "Po"], 'features.pkl')

print("\nModel and features saved successfully.")
