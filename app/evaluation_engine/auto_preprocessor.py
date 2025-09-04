# modelwhiz-backend/app/evaluation_engine/auto_preprocessor.py

def build_auto_preprocessor(df) : # Removed type hint for pd.DataFrame as pandas is now imported inside
    """
    Analyzes a DataFrame and builds a scikit-learn pipeline to handle
    common preprocessing tasks like imputation, scaling, and encoding.
    """
    # --- ML Library Imports moved inside the function ---
    import pandas as pd
    import numpy as np
    from sklearn.preprocessing import StandardScaler, OneHotEncoder
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    # --- End ML Library Imports ---

    if df.empty:
        print("Input DataFrame is empty, cannot build preprocessor.")
        return None
        
    numeric_features = df.select_dtypes(include=np.number).columns.tolist()
    categorical_features = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    # Don't try to process if there's nothing to do
    if not numeric_features and not categorical_features:
        print("No numeric or categorical features found for preprocessing.")
        return None

    print(f"Auto-detection found {len(numeric_features)} numeric and {len(categorical_features)} categorical features.")

    # Create a pipeline for numeric columns: fill missing with median, then scale
    numeric_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())
    ])

    # Create a pipeline for categorical columns: fill missing with a constant, then one-hot encode
    categorical_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='constant', fill_value='missing')),
        ('onehot', OneHotEncoder(handle_unknown='ignore'))
    ])

    # Create a ColumnTransformer to apply the correct pipeline to the correct columns
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_features),
            ('cat', categorical_transformer, categorical_features)
        ],
        remainder='passthrough' # Keep any other columns (like dates)
    )
    
    return preprocessor