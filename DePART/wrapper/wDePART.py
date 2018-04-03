# -*- coding: utf-8 -*-
"""
Created on Tue Apr  3 18:55:35 2018

@author: Hanjo
"""
def depart(train_loc, pred_loc, reader="MaxQuant", min_obs=1, 
           store_features=True, nfolds=5, cv=False, chrom="hSAX", 
           predict_proba=False, use_mods=False, epochs=100, batch_size=512):
    """
    DePART.
    
    Parameters:
    ----------------------
    train_loc: str, file location of the input data for training
    
    pred_loc: str, file location of the input data for training    
            
    reader: str, Can be MaxQuant or CSV, depending in which format the
    
    data is given. MaxQuant files are the evidence files from a normal run.
    
    min_obs: int, minimum number of peptides per fraction. Fractions with less
    observations are excluded from the data.
    
    store_features: bool, if True feature matrix is stored.
    
    target: str, Either "hSAX" or "regression". In princicap the "hSAX"
    set-up can be used for any classification / fractionation experiment.
    
    predict_proba: bool, if True probabilities are return in the final 
    dataframe and not class labels
    
    """    
    import os
    from DePART.learning import processing as LP
    import DePART.preprocessing.PrepFactory as PF
    import DePART.learning.models as LM
    
    from keras.utils import np_utils
    #from keras.models import load_model
    import numpy as np
    import pandas as pd
    
    from sklearn.preprocessing import LabelEncoder
    from sklearn.metrics import mean_squared_error, accuracy_score
    from sys import platform   
    np.random.seed(42)
    
    #some path work
    basepath = os.path.abspath(os.path.dirname(train_loc))
    basename = os.path.basename(pred_loc)
    
    #only prep train data if needed

    meta_train, full_train, features_train = PF.preprocess_df(train_loc, min_obs=min_obs)
    meta_pred, full_pred, features_pred = PF.preprocess_df(pred_loc, min_obs=min_obs)    
    
    #select y column                
    if chrom.lower() == "regression":
        #use same infrastructure but different variable content
        features_train["Fraction"] = meta_train["Retention time"]

    # make sure that the training and test data have the same features.
    train_features = set(features_train.columns)
    pred_features = set(features_pred.columns)
    common_features = list(train_features & pred_features)
    
    #training data
    X_train_full, Seqs_train_full, y_train_full = LP.process_df(features_train[common_features])
    X_valid_full, Seqs_valid_full, y_valid_full = LP.process_df(features_pred[common_features])
    
    #select neural network model
    if chrom.lower() == "regression":
        ytrain_fnn = y_train_full
        model = LM.FNN_Regressor(input_dim=X_train_full.shape[1], loss="mse")
    
    elif chrom.lower() == "hsax":
        encoder = LabelEncoder()
        encoder.fit(y_train_full)            
        ytrain_fnn = np_utils.to_categorical(encoder.transform(y_train_full))
        model = LM.SAX_Model(input_dim=X_train_full.shape[1],
                             output_dim=len(encoder.classes_))
    else:
        #does it make sense?
        ytrain_fnn = y_train_full
        model = LM.FNN_Classifier(input_dim=X_train_full.shape[1])
        
    #fit the model
    model.fit(X_train_full, ytrain_fnn, epochs=epochs, batch_size=batch_size, 
              verbose=0)
                
    # now the model is fit,let's predict  
    if predict_proba:
        pred_preds_proba = pd.DataFrame(model.predict(X_valid_full))
        train_preds_proba = pd.DataFrame(model.predict(X_train_full))
    else:
        pred_preds_class = pd.DataFrame(model.predict(X_valid_full).argmax(1)+1)
        train_preds_class = pd.DataFrame(model.predict(X_train_full).argmax(1)+1)
    
    
    #perform cross-validation
    if cv:
        if platform == "linux" or platform == "linux2":
            use_joblib=True
        elif platform == "darwin":
            use_joblib=True
        elif platform == "win32":
            use_joblib=False
            
        train_df, valid_df = np.split(features_train.sample(frac=1, random_state=42), 
                              [int(.75*len(features_train))])
        CV_res = LP.cross_validation(train_df, valid_df, name="FNN", nkfold=nfolds, 
                                 n_jobs=5, use_joblib=use_joblib, epochs=100, 
                                 batch_size=512)
        print ("Cross-Validation Accuracy esimate: (mean + standard error of the mean)")
        print (CV_res["Accuracy"])
    #%% store results
    res_pred_df = pd.DataFrame()
    res_pred_df["Sequences"] = Seqs_valid_full
    res_pred_df = pd.concat([res_pred_df, pred_preds_class], axis=1)
    res_pred_df.columns = ["Sequences", "Prediction"]
    res_pred_df["Measured"] = features_pred["Fraction"]
    
    res_train_df = pd.DataFrame()
    res_train_df["Sequences"] = Seqs_train_full
    res_train_df = pd.concat([res_train_df, train_preds_class], axis=1)
    res_train_df.columns = ["Sequences", "Prediction"]
    res_train_df["Measured"] = features_train["Fraction"]
    
    print("______________________________________")
    if chrom.lower() == "regression":
        print ("Train MSE: {:.2f}".format(mean_squared_error(res_train_df["Measured"],
               res_train_df["Prediction"])))
    else:
        print ("Train Acc: {:.2f}".format(accuracy_score(res_train_df["Measured"],
               res_train_df["Prediction"])))
        print ("Test Acc: {:.2f}".format(accuracy_score(res_pred_df["Measured"],
               res_pred_df["Prediction"])))
    #%%store results
    res_train_df.to_csv(basepath+"//pred_traindata"+basename, index=False)
    res_pred_df.to_csv(basepath+"//pred_preddata"+basename, index=False)
    
    #store trained model
    model.save(basepath+"//model_fullmodel"+basename+".h5")
    json_string = model.to_json()
    model.save_weights(basepath+"//model_weights"+basename+".h5")
    
    with open(basepath+"//model_architecture"+basename+".json","w") as koutmodel:
        koutmodel.write(json_string)
    
    if store_features:
        X_valid_full.to_csv(basepath+"//features_valid_"+basename, index=False)
        X_train_full.to_csv(basepath+"//features_train_"+basename, index=False)
    print ("Done. Thanks for using DePART.")
    return(model, res_pred_df, res_train_df)