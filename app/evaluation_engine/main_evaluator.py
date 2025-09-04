# FILE: app/evaluation_engine/main_evaluator.py (Fixing paths and cleanup)

from typing import Optional
import os
import zipfile
from datetime import datetime
import asyncio
import shutil # Added for potential cleanup of job_dir if evaluation fails critically

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select

from ..models.model import MLModel
from ..models.metric import Metric
from ..models.evaluation_job import EvaluationJob, JobStatus
from .insight_generator import generate_insights
from .auto_preprocessor import build_auto_preprocessor

def find_file_in_dir(directory, filenames):
    for root, dirs, files in os.walk(directory):
        for filename in filenames:
            if filename in files: return os.path.join(root, filename)
    return None

# Context manager for temporary file handling
class TemporaryFileHandler:
    def __init__(self, file_path):
        self.file_path = file_path
        
    def __enter__(self):
        return self.file_path
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if os.path.exists(self.file_path):
            try:
                os.remove(self.file_path)
            except OSError:
                pass

async def run_evaluation_task(
    job_id: int, 
    model_id: int, 
    zip_path: str, # Original path of the uploaded zip
    csv_path: str, # Original path of the uploaded CSV
    target_column: str, 
    split_data: bool, 
    async_db_session_factory: async_sessionmaker[AsyncSession]
):
    import joblib
    import pandas as pd
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (
        accuracy_score, f1_score, roc_auc_score, 
        mean_squared_error, r2_score, ConfusionMatrixDisplay
    )
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    
    db_session = None
    job_dir = f"uploads/eval_jobs/{job_id}" # This is the PERMANENT storage for job artifacts

    try:
        async with async_db_session_factory() as db_session:
            job_result = await db_session.execute(select(EvaluationJob).where(EvaluationJob.id == job_id))
            job = job_result.scalar_one_or_none()
            if not job:
                print(f"Job {job_id} not found in DB. Exiting evaluation task.")
                return

            job.status = JobStatus.PROCESSING
            await db_session.commit()

            os.makedirs(job_dir, exist_ok=True) # Ensure permanent job artifact directory exists
            
            # --- Synchronous file operations (extract zip) in a thread pool ---
            def extract_zip_sync():
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(job_dir)
            await asyncio.to_thread(extract_zip_sync)
            # --- End synchronous file operations ---
                
            # Now, model_path and preprocessor_path refer to files *inside* the job_dir
            model_file_in_job_dir = find_file_in_dir(job_dir, ['model.pkl', 'model.joblib'])
            preprocessor_file_in_job_dir = find_file_in_dir(job_dir, ['preprocessor.pkl'])
            
            if not model_file_in_job_dir: 
                raise FileNotFoundError(f"Model file not found in extracted job directory {job_dir}.")
            
            # --- Synchronous loading of model/data (also in thread pool) ---
            def load_model_and_data_sync():
                model_obj = joblib.load(model_file_in_job_dir)
                df_obj = pd.read_csv(csv_path) # CSV is still in UPLOAD_DIR/temp
                return model_obj, df_obj
            
            model, df = await asyncio.to_thread(load_model_and_data_sync)
            # --- End synchronous loading ---
            
            # Memory management: Clear large arrays after use
            def clear_memory():
                import gc
                gc.collect()
            
            await asyncio.to_thread(clear_memory)

            if target_column not in df.columns:
                raise ValueError(f"Target column '{target_column}' not found in the dataset.")

            X = df.drop(columns=[target_column])
            y = df[target_column]

            if split_data:
                n_unique_classes = len(y.unique())
                stratify = y if n_unique_classes < 30 and (y.dtype == 'object' or y.dtype == 'int64') else None 
                X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=stratify)
            else:
                X_train, X_test, y_train, y_test = X, X, y, y 

            insights_from_preprocessing = []
            preprocessor = None

            if preprocessor_file_in_job_dir:
                def load_preprocessor_sync():
                    return joblib.load(preprocessor_file_in_job_dir)
                preprocessor = await asyncio.to_thread(load_preprocessor_sync)
            else:
                preprocessor = build_auto_preprocessor(X_train)
                if preprocessor:
                    insights_from_preprocessing.append("✅ An Auto-Preprocessor was built and fitted on your data.")
                else:
                    insights_from_preprocessing.append("ℹ️ No preprocessing was needed for this dataset.")

            # --- Synchronous preprocessor fit/transform ---
            def fit_transform_preprocessor_sync(preprocessor_obj, X_train_data, X_test_data):
                if preprocessor_obj:
                    if hasattr(preprocessor_obj, 'fit') and hasattr(preprocessor_obj, 'transform'):
                         preprocessor_obj.fit(X_train_data)
                         return preprocessor_obj.transform(X_train_data), preprocessor_obj.transform(X_test_data)
                    else:
                        return X_train_data, X_test_data
                return X_train_data, X_test_data
            
            X_train_processed, X_test_processed = await asyncio.to_thread(
                fit_transform_preprocessor_sync, preprocessor, X_train, X_test
            )
            # --- End synchronous preprocessor fit/transform ---

            # --- Synchronous model fit/predict ---
            def fit_predict_model_sync(model_obj, X_train_p, y_train_p, X_test_p):
                if split_data:
                    model_obj.fit(X_train_p, y_train_p) 
                
                y_pred = model_obj.predict(X_test_p)
                y_proba = None
                if hasattr(model_obj, "predict_proba"):
                    y_proba = model_obj.predict_proba(X_test_p)
                return y_pred, y_proba
            
            y_pred, y_proba = await asyncio.to_thread(fit_predict_model_sync, model, X_train_processed, y_train, X_test_processed)
            # --- End synchronous model fit/predict ---
            
            metrics = {}
            artifacts = {}
            
            is_classification = (getattr(model, '_estimator_type', None) == 'classifier')
            if not is_classification and getattr(model, '_estimator_type', None) == 'regressor':
                is_classification = False
            elif not is_classification:
                is_classification = len(y.unique()) < 30 and (y.dtype == 'object' or y.dtype == 'int64')
            
            if is_classification:
                metrics['accuracy'] = float(accuracy_score(y_test, y_pred))
                metrics['f1_score'] = float(f1_score(y_test, y_pred, average='weighted'))
                
                if y_proba is not None:
                    try:
                        if len(y_test.unique()) == 2 and y_proba.shape[1] == 2:
                            metrics['auc'] = float(roc_auc_score(y_test, y_proba[:, 1]))
                        elif y_proba.shape[1] > 2:
                             metrics['auc'] = float(roc_auc_score(y_test, y_proba, multi_class='ovr', labels=model.classes_))
                        else:
                            print("AUC skipped: not binary target or probabilities shape mismatch.")
                            metrics['auc'] = None
                    except Exception as e:
                        print(f"Could not calculate AUC: {e}")
                        metrics['auc'] = None
                else:
                    metrics['auc'] = None

                # Plotting Confusion Matrix (synchronous, move to thread pool)
                def generate_confusion_matrix_plot_sync():
                    fig, ax = plt.subplots(figsize=(8, 6))
                    ConfusionMatrixDisplay.from_predictions(y_test, y_pred, ax=ax, normalize='true', cmap='Blues', values_format='.2%')
                    ax.set_title('Confusion Matrix')
                    artifact_filename = "confusion_matrix.png"
                    artifact_path = os.path.join(job_dir, artifact_filename)
                    plt.savefig(artifact_path)
                    plt.close(fig)
                    # --- CRITICAL FIX: Include /uploads/ prefix for StaticFiles mapping ---
                    return f"/uploads/eval_jobs/{job_id}/{artifact_filename}" 

                try:
                    artifacts['plot_url'] = await asyncio.to_thread(generate_confusion_matrix_plot_sync)
                except Exception as plot_error:
                    print(f"Could not generate confusion matrix plot: {plot_error}")
                    artifacts['plot_url'] = None
                
            else: # Regression
                metrics['rmse'] = float(mean_squared_error(y_test, y_pred, squared=False))
                metrics['r2_score'] = float(r2_score(y_test, y_pred))
                
                # Plotting Regression Plot (synchronous, move to thread pool)
                def generate_regression_plot_sync():
                    fig, ax = plt.subplots(figsize=(8, 6))
                    ax.scatter(y_test, y_pred, edgecolors=(0, 0, 0, 0.5), alpha=0.8)
                    ax.plot([y_test.min(), y_test.max()], [y_test.min(), y_test.max()], 'r--', lw=2)
                    ax.set_xlabel('Actual Values')
                    ax.set_ylabel('Predicted Values')
                    ax.set_title('Predicted vs. Actual Values')
                    artifact_filename = "regression_plot.png"
                    artifact_path = os.path.join(job_dir, artifact_filename)
                    plt.savefig(artifact_path)
                    plt.close(fig)
                    # --- CRITICAL FIX: Include /uploads/ prefix for StaticFiles mapping ---
                    return f"/uploads/eval_jobs/{job_id}/{artifact_filename}"
                
                try:
                    artifacts['plot_url'] = await asyncio.to_thread(generate_regression_plot_sync)
                except Exception as plot_error:
                    print(f"Could not generate regression plot: {plot_error}")
                    artifacts['plot_url'] = None

            final_metrics = {k: round(v, 4) for k, v in metrics.items() if v is not None}
            
            job.status = JobStatus.COMPLETED
            job.results = final_metrics
            job.results['insights'] = insights_from_preprocessing + generate_insights(final_metrics)
            job.artifacts = artifacts
            job.completed_at = datetime.utcnow()

            ml_model_result = await db_session.execute(select(MLModel).where(MLModel.id == model_id))
            ml_model = ml_model_result.scalar_one_or_none()
            if ml_model:
                ml_model.latest_metrics = final_metrics
                ml_model.task_type = 'classification' if is_classification else 'regression'

            new_metric_record = Metric(model_id=model_id, values=final_metrics, timestamp=datetime.utcnow())
            db_session.add(new_metric_record)

            await db_session.commit()
            
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        if job:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            try:
                await db_session.commit()
            except Exception as commit_error:
                print(f"Error committing failed job status: {commit_error}")
        # If the evaluation fails, and job_dir was created, it should also be cleaned up.
        # This prevents leftover partial artifacts from failed runs.
        if os.path.exists(job_dir):
            try:
                shutil.rmtree(job_dir)
            except OSError as e:
                print(f"Error removing failed job directory {job_dir} during error cleanup: {e}")
    finally:
        # Cleanup original uploaded temporary files (zip and csv)
        # The permanent job_dir contents should NOT be deleted here.
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except OSError as e:
                print(f"Error removing original uploaded zip file {zip_path}: {e}")
        
        if os.path.exists(csv_path):
            try:
                os.remove(csv_path)
            except OSError as e:
                print(f"Error removing original uploaded csv file {csv_path}: {e}")

        # The job_dir itself (e.g., uploads/eval_jobs/{job_id}) and its contents
        # are considered permanent artifacts IF THE JOB COMPLETED.
        # If the job failed, job_dir is now cleaned up in the except block.