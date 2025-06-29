import pandas as pd
from datetime import datetime
from main import AquariumPredictor

predictor = AquariumPredictor()
bad_data = pd.Series({
    "Po": 4.0,         
    "temperatureC": 35, 
    "tdsValue": 800,     
    "timestamp": datetime.now(),
    "user_id": "test_user_123",
    "reading_id": "bad_test_001"
})

good_data = pd.Series({
    "Po": 6.79,         
    "temperatureC": 28.94, 
    "tdsValue": 221.32,     
    "timestamp": datetime.now(),
    "user_id": "test_user_123",
    "reading_id": "good_test_001"
})

features = ["Po", "tdsValue", "temperatureC"]
result = predictor.predict_condition(bad_data)

print("Prediction Result:")
print(result)

if result and not result['prediction']:
    print("\nEmail notification sis sent")
else:
    print("\nNo email notification sent")