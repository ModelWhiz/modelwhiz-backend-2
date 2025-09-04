# modelwhiz-backend/app/utils/evaluation.py

# Removed top-level imports: pandas, numpy, joblib, sklearn.metrics, datetime
# from sqlalchemy.orm import Session # This can stay at top-level as it's not a heavy ML lib
# from app.models.model import MLModel # This can stay at top-level
# from app.models.metric import Metric # This can stay at top-level

def evaluate_and_store_metrics(model_path: str, test_csv_path: str, db, model_id: int):
    # --- ML Library Imports moved inside the function ---
    import pandas as pd
    import numpy as np # Although numpy is not directly used, pandas depends on it heavily
    import joblib
    from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
    from datetime import datetime # datetime is lightweight, but can be moved for consistency
    from ..models.model import MLModel
    from ..models.metric import Metric
    # --- End ML Library Imports ---

    try:
        # Load model
        model = joblib.load(model_path)

        # Load test data
        df = pd.read_csv(test_csv_path)

        if 'target' not in df.columns:
            raise ValueError("Test CSV must contain a 'target' column.")

        X_test = df.drop(columns=['target'])
        y_test = df['target']

        # Predict
        y_pred = model.predict(X_test)

        # Try predicting probabilities if possible
        if hasattr(model, "predict_proba"):
            y_probs = model.predict_proba(X_test)
            try:
                auc = roc_auc_score(y_test, y_probs[:, 1])
            except:
                auc = None
        else:
            auc = None

        # Calculate metrics
        accuracy = float(accuracy_score(y_test, y_pred))
        f1 = float(f1_score(y_test, y_pred, average='weighted'))  # Handle multiclass
        auc = float(auc) if auc is not None else None

        # Save new metric row
        metric = Metric(
            model_id=model_id,
            accuracy=accuracy,
            f1_score=f1,
            auc=auc,
            timestamp=datetime.utcnow()
        )
        db.add(metric)

        # Update latest values in ml_models table
        ml_model = db.query(MLModel).filter(MLModel.id == model_id).first()
        if ml_model:
            ml_model.accuracy = accuracy
            ml_model.f1_score = f1
            ml_model.auc = auc # Ensure AUC is updated for the model as well

        db.commit()
        db.refresh(metric)
        db.refresh(ml_model)

        print("🎯 Final metrics:", accuracy, f1, auc)
        
        return {
            "accuracy": accuracy,
            "f1_score": f1,
            "auc": auc
        }

    except Exception as e:
        db.rollback()
        raise e