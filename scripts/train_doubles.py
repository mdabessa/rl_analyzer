import os
import sys

sys.path.append(os.path.join(os.path.dirname(sys.path[0])))

from joblib import dump
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn import metrics
import numpy as np

from src.db import ranked_doubles
from src.preprocessing import extract_players


replays = ranked_doubles.find({})

players = extract_players(replays)
print("Shape of data:", players.shape)

X = players.drop(["tier"], axis=1)
y = players.tier

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

print("Training model...")
model = RandomForestRegressor()
model.fit(X_train, y_train)

print("Saving model...")
dump(model, "./src/ml_models/ranked_doubles.joblib", compress=3)

print("Evaluating model...")
pred = model.predict(X_test)
print("Mean Absolute Error (MAE):", metrics.mean_absolute_error(y_test, pred))
print("Mean Squared Error (MSE):", metrics.mean_squared_error(y_test, pred))
print(
    "Root Mean Squared Error (RMSE):", np.sqrt(metrics.mean_squared_error(y_test, pred))
)
mape = np.mean(np.abs((y_test - pred) / np.abs(y_test)))
print("Mean Absolute Percentage Error (MAPE):", round(mape * 100, 2))
print("Accuracy:", round(100 * (1 - mape), 2))
