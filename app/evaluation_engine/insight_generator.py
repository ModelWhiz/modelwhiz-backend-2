# modelwhiz-backend/app/evaluation_engine/insight_generator.py

def generate_insights(metrics: dict) -> list[str]:
    """
    Generates a list of simple, rule-based insights from a metrics dictionary.
    This function is now task-aware (handles regression and classification).
    """
    insights = []
    
    # --- vvv NEW: Task-Aware Logic vvv ---
    is_regression = 'rmse' in metrics

    if is_regression:
        rmse = metrics.get('rmse')
        r2 = metrics.get('r2_score')

        if r2 is not None:
            if r2 < 0.5:
                insights.append(f"📉 Low R² Score ({r2:.2f}): The model explains less than 50% of the variance in the target variable. Consider adding more predictive features.")
            elif r2 > 0.85:
                insights.append(f"✅ Strong R² Score ({r2:.2f}): The model explains a large portion of the variance in the target.")
        
        if rmse is not None and rmse > 1.0: # This threshold is arbitrary and should be context-dependent
             insights.append(f"⚠️ High RMSE ({rmse:.2f}): The model's predictions are, on average, far from the actual values. Check for outliers or consider feature scaling.")

    else: # Classification Insights
        f1 = metrics.get('f1_score')
        auc = metrics.get('auc')
        accuracy = metrics.get('accuracy')

        if f1 is not None and f1 < 0.7:
            insights.append("⚠️ F1 Score is low. This may indicate a class imbalance. Review precision and recall for each class.")
        
        if auc is not None and auc < 0.7:
            insights.append("📉 AUC score is modest. The model has limited ability to distinguish between classes.")
        
        if auc is not None and auc > 0.9 and f1 is not None and f1 < 0.8:
            insights.append("🔍 High AUC but moderate F1 Score. This can happen with an unoptimized classification threshold or imbalanced classes.")

        if accuracy is not None and accuracy < 0.6:
            insights.append("📉 Accuracy is low. The model is performing slightly better than random chance.")
    # --- ^^^ END OF NEW LOGIC ^^^ ---
    
    if not insights:
        insights.append("✅ Solid performance metrics. The model appears to be well-calibrated for this dataset.")

    return insights