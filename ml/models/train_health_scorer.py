"""Train and save the account health LightGBM model."""

import pickle
import json
import numpy as np
import lightgbm as lgb
from datetime import datetime
from pathlib import Path

# Generate synthetic training data
def generate_synthetic_data(n_samples=1000):
    """Generate synthetic customer health data for training."""
    np.random.seed(42)
    
    X = np.random.randn(n_samples, 15)
    
    # Scale features to reasonable ranges
    # recency_days: 0-365
    X[:, 0] = np.abs(X[:, 0]) * 50 + np.random.uniform(0, 365, n_samples)
    # frequency: 1-100
    X[:, 1] = np.abs(X[:, 1]) * 10 + 1
    # monetary_value: 0-50000
    X[:, 2] = np.abs(X[:, 2]) * 5000
    # support_contact_count: 0-50
    X[:, 3] = np.abs(X[:, 3]) * 5
    # avg_resolution_days: 0-10
    X[:, 4] = np.abs(X[:, 4])
    # failed_payments_90d: 0-10
    X[:, 5] = np.maximum(0, X[:, 5] * 2)
    # chargeback_count: 0-5
    X[:, 6] = np.maximum(0, X[:, 6])
    # subscription_age_days: 0-1000
    X[:, 7] = np.abs(X[:, 7]) * 100 + np.random.uniform(0, 1000, n_samples)
    # subscription_status_active: 0 or 1
    X[:, 8] = np.random.randint(0, 2, n_samples)
    # plan_value_usd: 0-500
    X[:, 9] = np.abs(X[:, 9]) * 50
    # account_age_days: 0-2000
    X[:, 10] = np.abs(X[:, 10]) * 200 + np.random.uniform(0, 2000, n_samples)
    # total_order_count: 0-100
    X[:, 11] = np.abs(X[:, 11]) * 10
    # high_value_order_count: 0-20
    X[:, 12] = np.abs(X[:, 12]) * 2
    # return_rate: 0-1
    X[:, 13] = np.clip(np.random.rand(n_samples), 0, 1)
    # sentiment_negative_ratio: 0-1
    X[:, 14] = np.clip(np.random.rand(n_samples), 0, 1)
    
    # Generate labels based on churn risk heuristic
    # High risk factors: high recency, low frequency, failed payments, inactive subscription, negative sentiment
    churn_scores = np.zeros(n_samples)
    churn_scores += np.where(X[:, 0] > 90, 0.2, 0)  # recency > 90 days
    churn_scores += np.where(X[:, 1] < 5, 0.2, 0)   # low frequency
    churn_scores += X[:, 5] * 0.05                    # failed payments
    churn_scores += np.where(X[:, 8] == 0, 0.2, 0)   # inactive subscription
    churn_scores += X[:, 14] * 0.1                    # negative sentiment
    
    # Add some noise
    churn_scores += np.random.normal(0, 0.1, n_samples)
    churn_scores = np.clip(churn_scores, 0, 1)
    
    # Threshold at 0.65 to create labels
    y = (churn_scores >= 0.65).astype(int)
    
    return X, y

# Train the model
print("Generating synthetic training data...")
X_train, y_train = generate_synthetic_data(n_samples=1000)

print("Training LightGBM model...")
train_data = lgb.Dataset(X_train, label=y_train)

params = {
    'objective': 'binary',
    'metric': 'binary_logloss',
    'boosting_type': 'gbdt',
    'num_leaves': 31,
    'learning_rate': 0.05,
    'feature_fraction': 0.8,
    'bagging_fraction': 0.8,
    'bagging_freq': 5,
    'verbose': -1,
}

model = lgb.train(
    params,
    train_data,
    num_boost_round=100,
    valid_sets=[train_data],
)

# Save the model
model_path = Path(__file__).parent / 'account_health_lgb.pkl'
print(f"Saving model to {model_path}...")

with open(model_path, 'wb') as f:
    pickle.dump(model, f)

# Save version metadata
version_info = {
    "version": "v1.0.0",
    "timestamp": datetime.utcnow().isoformat(),
    "training_samples": 1000,
    "num_features": 15,
    "feature_names": [
        "recency_days", "frequency", "monetary_value",
        "support_contact_count", "avg_resolution_days",
        "failed_payments_90d", "chargeback_count",
        "subscription_age_days", "subscription_status_active",
        "plan_value_usd", "account_age_days",
        "total_order_count", "high_value_order_count",
        "return_rate", "sentiment_negative_ratio"
    ],
    "model_type": "LightGBM",
    "threshold": 0.65,
}

version_path = Path(__file__).parent / 'account_health_lgb_v1.0.0.json'
print(f"Saving version metadata to {version_path}...")

with open(version_path, 'w') as f:
    json.dump(version_info, f, indent=2)

print("Model training complete!")
print(f"Model saved to: {model_path}")
print(f"Version info saved to: {version_path}")
