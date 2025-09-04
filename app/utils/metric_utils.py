# modelwhiz-backend/app/utils/metric_utils.py

# Removed top-level imports: pandas, joblib, sklearn.metrics

def evaluate_model_metrics(model_path: str, test_csv_path: str):
    # --- ML Library Imports moved inside the function ---
    import pandas as pd
    import joblib
    from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
    # --- End ML Library Imports ---

    model = joblib.load(model_path)
    df = pd.read_csv(test_csv_path)

    # Auto-detect target column
    # Ensure there's at least one column to drop and one for target
    if df.empty:
        raise ValueError("Input DataFrame is empty.")
    if df.shape[1] < 2:
        raise ValueError("Input DataFrame must have at least two columns for features and target.")
    
    target_col = df.columns[-1]
    X = df.drop(columns=[target_col])
    y = df[target_col]

    y_pred = model.predict(X)

    metrics = {
        "accuracy": round(accuracy_score(y, y_pred), 4),
        "f1_score": round(f1_score(y, y_pred, average='weighted'), 4),
        "auc": None
    }

    # Try AUC only for binary or probability-supporting classifiers
    try:
        if hasattr(model, "predict_proba"):
            # Check if y is binary for roc_auc_score
            if len(y.unique()) == 2:
                y_proba = model.predict_proba(X)[:, 1]
                metrics["auc"] = round(roc_auc_score(y, y_proba), 4)
            else:
                print("Skipping AUC calculation: target is not binary.")
    except Exception as e:
        print(f"Error calculating AUC: {e}")
        pass # AUC remains None if calculation fails

    return metrics