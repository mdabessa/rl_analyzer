import os
import sys

sys.path.append(os.path.join(os.path.dirname(sys.path[0])))

from joblib import dump
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn import metrics
import numpy as np

from src.db import database
from src.pre_processing import extract_players


playlist = "ranked_doubles"
collection = database.get_collection(f'{playlist}-train')

replays = collection.find({})

players = extract_players(replays)

if players.shape[0] == 0:
    print("No replays found")
    exit()

print("Shape of data:", players.shape)

X = players.drop(["tier"], axis=1)
y = players.tier

random_state = 0 # Set random state for reproducibility
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=random_state)

print("Training model...")
model = RandomForestRegressor()
model.fit(X_train, y_train)

print("Saving model...")
dump(model, f"./src/ml_models/{playlist}.joblib")

print("Evaluating model...")
pred = model.predict(X_test)
print("Mean Absolute Error (MAE):", metrics.mean_absolute_error(y_test, pred))
print("Mean Squared Error (MSE):", metrics.mean_squared_error(y_test, pred))
mape = np.mean(np.abs((y_test - pred) / np.abs(y_test)))
print("Mean Absolute Percentage Error (MAPE):", round(mape * 100, 2))
print("Accuracy:", round(100 * (1 - mape), 2))
