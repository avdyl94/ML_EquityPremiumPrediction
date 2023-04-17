# -*- coding: utf-8 -*-
# creat_time: 2023/3/9 22:10

# -*- coding: utf-8 -*-
# creat_time: 2021/12/5 22:02

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.linear_model import Lasso, ElasticNet
from sklearn.cross_decomposition import PLSRegression
from sklearn.decomposition import PCA
from sklearn.preprocessing import minmax_scale
import torch
from NN_models import Net3
from tqdm import tqdm
#
from sklearn.svm import SVR
from sklearn.neighbors import KNeighborsRegressor
from sklearn.ensemble import AdaBoostRegressor
from xgboost import XGBRegressor
#
from sklearn.metrics import mean_squared_error
from Perform_CW_test import CW_test
from Perform_PT_test import PT_test
from data_cleaning import ogap_detrend
import warnings
warnings.filterwarnings('ignore')
# set seed
torch.manual_seed(1)
np.random.seed(1)
#


predictor_df = pd.read_csv('result_predictor.csv')
predictor_df.head()


newly = pd.read_csv("NewlyIdentifiedVariables.csv")
#newly.isna().sum()
newly.drop(columns=['Month'], inplace=True)
newly.head()   # range from 1990:01 to 2020:12

start_month = predictor_df.index[predictor_df['month'] == 199001][0]
predictor_df = predictor_df.iloc[start_month:, :]
predictor_df.reset_index(inplace=True, drop=True)
predictor_df.head()
#

predictor0 = pd.concat([predictor_df.loc[:, ['log_equity_premium']],
                        predictor_df.iloc[:, 3:]],axis=1)
predictor0.head()


# set the log equity premium 1-month ahead
predictor_old = np.concatenate([predictor0['log_equity_premium'][1:].values.reshape(-1, 1),
                            predictor0.iloc[0:(predictor0.shape[0] - 1), 1:].values], axis=1)
predictor_old
predictor_old = predictor_old.astype(np.float64)
N = predictor_old.shape[0]
#

# Actual one-month ahead log equity premium
actual = predictor_old[:, [0]]

# Historical average forecasting
y_pred_HA = predictor0['log_equity_premium'].values[0:(predictor0.shape[0] - 1), ].cumsum() / np.arange(1, N + 1)
y_pred_HA = y_pred_HA.reshape(-1, 1)


## Out-of-sample: 2000:01-2020:12
in_out_2000 = predictor_df.index[predictor_df['month'] == 200001][0]
actual_2000 = actual[in_out_2000:, ]
y_pred_HA_2000 = y_pred_HA[in_out_2000:, ]
MSFE_HA_2000 = mean_squared_error(y_pred_HA_2000, actual_2000)

# Machine Learning methods used in GKX (2020)
y_pred_OLS_2000, y_pred_PLS_2000, y_pred_PCR_2000,  y_pred_LASSO_2000 = [], [], [], []
y_pred_ENet_2000, y_pred_GBRT_2000, y_pred_RF_2000, y_pred_NN3_2000 = [], [], [], []

## Other commonly used machine learning method
y_pred_SVR_2000, y_pred_KNR_2000, y_pred_AdaBoost_2000, y_pred_XGBoost_2000 = [], [], [], []
y_pred_combination_2000 = []


year_index = 1   # control the update of model each year
for t in tqdm(range(in_out_2000, N)):
    newly_df = newly.iloc[:(t + 1), ]
    newly_df['ogap'] = ogap_detrend(newly_df['ogap'])
    #
    predictor = np.concatenate([predictor_old[:(t + 1), ], newly_df.to_numpy(), y_pred_HA[:(t + 1)]], axis=1)
    n_cols = predictor.shape[1]
    #
    X_train_all = predictor[:t, 1:n_cols]
    y_train_all = predictor[:t, 0]
    #
    X_train = X_train_all[0:int(len(X_train_all) * 0.85), :]
    X_validation = X_train_all[int(len(X_train_all) * 0.85):t, :]
    y_train = y_train_all[0:int(len(X_train_all) * 0.85)]
    y_validation = y_train_all[int(len(X_train_all) * 0.85):t]
    #
    if year_index % 12 == 1:
        year_index += 1
        # OLS
        OLS = LinearRegression()
        OLS.fit(X_train_all, y_train_all)
        y_pred_OLS_2000.append(OLS.predict(predictor[[t], 1:n_cols]))

        # PLS
        PLS_param = [1, 2, 3, 4, 5, 6, 7, 8]
        PLS_result = {}
        for k in PLS_param:
            PLS = PLSRegression(n_components=k)
            PLS.fit(X_train, y_train)
            mse = mean_squared_error(PLS.predict(X_validation), y_validation)
            PLS_result[mse] = k
        PLS_best_param = PLS_result[min(PLS_result.keys())]
        PLS_model = PLSRegression(n_components=PLS_best_param)
        PLS_model.fit(X_train_all, y_train_all)
        y_pred_PLS_2000.append(PLS_model.predict(predictor[[t], 1:n_cols]))

        # PCR
        PCR_param = [1, 2, 3, 4, 5, 6, 7, 8]
        PCR_result = {}
        for k in PCR_param:
            pca = PCA(n_components=k)
            pca.fit(X_train)
            comps = pca.transform(X_train)
            forecast = LinearRegression()
            forecast.fit(comps, y_train)
            mse = mean_squared_error(forecast.predict(pca.transform(X_validation)), y_validation)
            PCR_result[mse] = k
        PCR_best_param = PCR_result[min(PCR_result.keys())]
        PCR_model = PCA(n_components=PCR_best_param)
        PCR_model.fit(X_train_all)
        PCR_comps = PCR_model.transform(X_train_all)
        PCR_forecast = LinearRegression()
        PCR_forecast.fit(PCR_comps, y_train_all)
        y_pred_PCR_2000.append(PCR_forecast.predict(PCR_model.transform(predictor[[t], 1:n_cols])))

        # LASSO
        LASSO_param = 10 ** np.arange(-4, -1 + 0.001, 0.1)
        LASSO_result = {}
        for alpha in LASSO_param:
            LASSO = Lasso(alpha=alpha)
            LASSO.fit(X_train, y_train)
            mse = mean_squared_error(LASSO.predict(X_validation), y_validation)
            LASSO_result[mse] = alpha
        LASSO_best_param = LASSO_result[min(LASSO_result.keys())]
        LASSO_model = Lasso(alpha=LASSO_best_param)
        LASSO_model.fit(X_train_all, y_train_all)
        y_pred_LASSO_2000.append(LASSO_model.predict(predictor[[t], 1:n_cols]))

        # ENet
        ENet_param = 10 ** np.arange(-4, -1 + 0.001, 0.1)
        ENet_result = {}
        for alpha in ENet_param:
            ENet = ElasticNet(alpha=alpha, l1_ratio=0.5)
            ENet.fit(X_train, y_train)
            mse = mean_squared_error(ENet.predict(X_validation), y_validation)
            ENet_result[mse] = alpha
        ENet_best_param = ENet_result[min(ENet_result.keys())]
        ENet_model = ElasticNet(alpha=ENet_best_param, l1_ratio=0.5)
        ENet_model.fit(X_train_all, y_train_all)
        y_pred_ENet_2000.append(ENet_model.predict(predictor[[t], 1:n_cols]))

        # GBRT
        GBRT_param = [1, 2, 3, 4, 5, 6, 7, 8]
        GBRT_result = {}
        for depth in GBRT_param:
            GBRT = GradientBoostingRegressor(max_depth=depth)
            GBRT.fit(X_train, y_train)
            mse = mean_squared_error(GBRT.predict(X_validation), y_validation)
            GBRT_result[mse] = depth
        GBRT_best_param = GBRT_result[min(GBRT_result.keys())]
        GBRT_model = GradientBoostingRegressor(max_depth=GBRT_best_param)
        GBRT_model.fit(X_train_all, y_train_all)
        y_pred_GBRT_2000.append(GBRT_model.predict(predictor[[t], 1:n_cols]))

        # RF
        RF_param =[1, 2, 3, 4, 5, 6, 7, 8]
        RF_result = {}
        for depth in RF_param:
            RF = RandomForestRegressor(max_depth=depth)
            RF.fit(X_train, y_train)
            mse = mean_squared_error(RF.predict(X_validation), y_validation)
            RF_result[mse] = depth
        RF_best_param = RF_result[min(RF_result.keys())]
        RF_model = RandomForestRegressor(max_depth=RF_best_param)
        RF_model.fit(X_train_all, y_train_all)
        y_pred_RF_2000.append(RF_model.predict(predictor[[t], 1:n_cols]))


        # NN3
        X_train_tensor = torch.tensor(X_train, dtype=torch.float)
        y_train_tensor = torch.tensor(y_train.reshape(-1, 1), dtype=torch.float)
        X_validation_tensor = torch.tensor(X_validation, dtype=torch.float)
        y_validation_tensor = torch.tensor(y_validation, dtype=torch.float)
        NN3_l2_param = 10 ** np.arange(-5, -3 + 0.0001, 0.1)
        NN3_result = {}
        NN3 = Net3(n_cols - 1, 32, 16, 8, 1)
        #
        for l2 in NN3_l2_param:
            # break
            optimizer = torch.optim.SGD(NN3.parameters(), lr=0.01, weight_decay=l2)
            loss_func = torch.nn.MSELoss()
            for i in range(100):
                out = NN3(X_train_tensor)
                loss = loss_func(out, y_train_tensor)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            NN3(X_train_tensor)
            mse = mean_squared_error(NN3(X_validation_tensor).detach().numpy(), y_validation)

            NN3_result[mse] = l2
        NN3_best_param = NN3_result[min(NN3_result.keys())]
        NN3_optimizer = torch.optim.SGD(NN3.parameters(), lr=0.01, weight_decay=NN3_best_param)
        NN3_loss_func = torch.nn.MSELoss()
        X_train_all_tensor = torch.tensor(X_train_all, dtype=torch.float)
        y_train_all_tensor = torch.tensor(y_train_all.reshape(-1, 1), dtype=torch.float)
        for i in range(100):
            NN3_out = NN3(X_train_all_tensor)
            NN3_loss = NN3_loss_func(NN3_out, y_train_all_tensor)
            NN3_optimizer.zero_grad()
            NN3_loss.backward()
            NN3_optimizer.step()
        y_pred_NN3_2000.append(NN3(torch.tensor(predictor[[t], 1:n_cols],
                                                dtype=torch.float)).detach().numpy()[0])
        ## Other commmonly used ML methods
        # SVR
        SVR_param = ['linear', 'poly', 'rbf', 'sigmoid']
        SVR_result = {}
        for kernel in SVR_param:
            SVR_tmp = SVR(kernel=kernel)
            SVR_tmp.fit(X_train, y_train)
            mse = mean_squared_error(SVR_tmp.predict(X_validation), y_validation)
            SVR_result[mse] = kernel
        SVR_best_param = SVR_result[min(SVR_result.keys())]
        SVR_model = SVR(kernel=SVR_best_param)
        SVR_model.fit(X_train_all, y_train_all)
        y_pred_SVR_2000.append(SVR_model.predict(predictor[[t], 1:n_cols]))

        # KNR
        KNR = KNeighborsRegressor()
        KNR_param = [5, 10, 20, 25, 30, 40, 50, 60, 70]
        KNR_result = {}
        for n_neighbors in KNR_param:
            KNR = KNeighborsRegressor(n_neighbors=n_neighbors)
            KNR.fit(X_train, y_train)
            mse = mean_squared_error(KNR.predict(X_validation), y_validation)
            KNR_result[mse] = n_neighbors
        KNR_best_param = KNR_result[min(KNR_result.keys())]
        KNR_model = KNeighborsRegressor(n_neighbors=KNR_best_param)
        KNR_model.fit(X_train_all, y_train_all)
        y_pred_KNR_2000.append(KNR_model.predict(predictor[[t], 1:n_cols]))

        # AdaBoost
        AdaBoost_param = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        AdaBoost_result = {}
        for n_estimators in AdaBoost_param:
            AdaBoost = AdaBoostRegressor(n_estimators=n_estimators)
            AdaBoost.fit(X_train, y_train)
            mse = mean_squared_error(AdaBoost.predict(X_validation), y_validation)
            AdaBoost_result[mse] = n_estimators
        AdaBoost_best_param = AdaBoost_result[min(AdaBoost_result.keys())]
        AdaBoost_model = AdaBoostRegressor(n_estimators=AdaBoost_best_param)
        AdaBoost_model.fit(X_train_all, y_train_all)
        y_pred_AdaBoost_2000.append(AdaBoost_model.predict(predictor[[t], 1:n_cols]))

        # XGBoost
        XGBoost_param = [1, 2, 3, 4, 5, 6, 7, 8]
        XGBoost_result = {}
        for max_depth in XGBoost_param:
            XGBoost = XGBRegressor(max_depth=max_depth)
            XGBoost.fit(X_train, y_train)
            mse = mean_squared_error(XGBoost.predict(X_validation), y_validation)
            XGBoost_result[mse] = max_depth
        XGB_best_param = XGBoost_result[min(XGBoost_result.keys())]
        XGB_model = XGBRegressor(max_depth=XGB_best_param)
        XGB_model.fit(X_train_all, y_train_all)
        y_pred_XGBoost_2000.append(XGB_model.predict(predictor[[t], 1:n_cols]))
    else:
        year_index += 1
        y_pred_OLS_2000.append(OLS.predict(predictor[[t], 1:n_cols]))
        y_pred_PLS_2000.append(PLS_model.predict(predictor[[t], 1:n_cols]))
        y_pred_PCR_2000.append(PCR_forecast.predict(PCR_model.transform(predictor[[t], 1:n_cols])))
        y_pred_LASSO_2000.append(LASSO_model.predict(predictor[[t], 1:n_cols]))
        y_pred_ENet_2000.append(ENet_model.predict(predictor[[t], 1:n_cols]))
        y_pred_GBRT_2000.append(GBRT_model.predict(predictor[[t], 1:n_cols]))
        y_pred_RF_2000.append(RF_model.predict(predictor[[t], 1:n_cols]))
        y_pred_NN3_2000.append(NN3(torch.tensor(predictor[[t], 1:n_cols], dtype=torch.float)).detach().numpy()[0])
        # Other commmonly used ML methods
        y_pred_SVR_2000.append(SVR_model.predict(predictor[[t], 1:n_cols]))
        y_pred_KNR_2000.append(KNR_model.predict(predictor[[t], 1:n_cols]))
        y_pred_AdaBoost_2000.append(AdaBoost_model.predict(predictor[[t], 1:n_cols]))
        y_pred_XGBoost_2000.append(XGB_model.predict(predictor[[t], 1:n_cols]))


# Performance compared with HA
# OLS
y_pred_OLS_2000 = np.array(y_pred_OLS_2000).reshape(-1, 1)
MSFE_OLS_2000 = mean_squared_error(y_pred_OLS_2000, actual_2000)
OOS_R_OLS_2000 = 1 - MSFE_OLS_2000 / MSFE_HA_2000
MSFE_adjusted_OLS_2000, p_OLS_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_OLS_2000)
success_ratio_OLS_2000, PT_OLS_2000, p2_OLS_2000 = PT_test(actual_2000, y_pred_OLS_2000)
# PLS
y_pred_PLS_2000 = np.array(y_pred_PLS_2000).reshape(-1, 1)
MSFE_PLS_2000 = mean_squared_error(y_pred_PLS_2000, actual_2000)
OOS_R_PLS_2000 = 1 - MSFE_PLS_2000 / MSFE_HA_2000
MSFE_adjusted_PLS_2000, p_PLS_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_PLS_2000)
success_ratio_PLS_2000, PT_PLS_2000, p2_PLS_2000 = PT_test(actual_2000, y_pred_PLS_2000)
# PCR
y_pred_PCR_2000 = np.array(y_pred_PCR_2000).reshape(-1, 1)
MSFE_PCR_2000 = mean_squared_error(y_pred_PCR_2000, actual_2000)
OOS_R_PCR_2000 = 1 - MSFE_PCR_2000 / MSFE_HA_2000
MSFE_adjusted_PCR_2000, p_PCR_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_PCR_2000)
success_ratio_PCR_2000, PT_PCR_2000, p2_PCR_2000 = PT_test(actual_2000, y_pred_PCR_2000)
# LASSO
y_pred_LASSO_2000 = np.array(y_pred_LASSO_2000).reshape(-1, 1)
MSFE_LASSO_2000 = mean_squared_error(y_pred_LASSO_2000, actual_2000)
OOS_R_LASSO_2000 = 1 - MSFE_LASSO_2000 / MSFE_HA_2000
MSFE_adjusted_LASSO_2000, p_LASSO_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_LASSO_2000)
success_ratio_LASSO_2000, PT_LASSO_2000, p2_LASSO_2000 = PT_test(actual_2000, y_pred_LASSO_2000)
# ENet
y_pred_ENet_2000 = np.array(y_pred_ENet_2000).reshape(-1, 1)
MSFE_ENet_2000 = mean_squared_error(y_pred_ENet_2000, actual_2000)
OOS_R_ENet_2000 = 1 - MSFE_ENet_2000 / MSFE_HA_2000
MSFE_adjusted_ENet_2000, p_ENet_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_ENet_2000)
success_ratio_ENet_2000, PT_ENet_2000, p2_ENet_2000 = PT_test(actual_2000, y_pred_ENet_2000)
# GBRT
y_pred_GBRT_2000 = np.array(y_pred_GBRT_2000).reshape(-1, 1)
MSFE_GBRT_2000 = mean_squared_error(y_pred_GBRT_2000, actual_2000)
OOS_R_GBRT_2000 = 1 - MSFE_GBRT_2000 / MSFE_HA_2000
MSFE_adjusted_GBRT_2000, p_GBRT_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_GBRT_2000)
success_ratio_GBRT_2000, PT_GBRT_2000, p2_GBRT_2000 = PT_test(actual_2000, y_pred_GBRT_2000)
# RF
y_pred_RF_2000 = np.array(y_pred_RF_2000).reshape(-1, 1)
MSFE_RF_2000 = mean_squared_error(y_pred_RF_2000, actual_2000)
OOS_R_RF_2000 = 1 - MSFE_RF_2000 / MSFE_HA_2000
MSFE_adjusted_RF_2000, p_RF_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_RF_2000)
success_ratio_RF_2000, PT_RF_2000, p2_RF_2000 = PT_test(actual_2000, y_pred_RF_2000)
# NN3
y_pred_NN3_2000 = np.array(y_pred_NN3_2000).reshape(-1, 1)
MSFE_NN3_2000 = mean_squared_error(y_pred_NN3_2000, actual_2000)
OOS_R_NN3_2000 = 1 - MSFE_NN3_2000 / MSFE_HA_2000
MSFE_adjusted_NN3_2000, p_NN3_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_NN3_2000)
success_ratio_NN3_2000, PT_NN3_2000, p2_NN3_2000 = PT_test(actual_2000, y_pred_NN3_2000)
# SVR
y_pred_SVR_2000 = np.array(y_pred_SVR_2000).reshape(-1, 1)
MSFE_SVR_2000 = mean_squared_error(y_pred_SVR_2000, actual_2000)
OOS_R_SVR_2000 = 1 - MSFE_SVR_2000 / MSFE_HA_2000
MSFE_adjusted_SVR_2000, p_SVR_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_SVR_2000)
success_ratio_SVR_2000, PT_SVR_2000, p2_SVR_2000 = PT_test(actual_2000, y_pred_SVR_2000)
# KNR
y_pred_KNR_2000 = np.array(y_pred_KNR_2000).reshape(-1, 1)
MSFE_KNR_2000 = mean_squared_error(y_pred_KNR_2000, actual_2000)
OOS_R_KNR_2000 = 1 - MSFE_KNR_2000 / MSFE_HA_2000
MSFE_adjusted_KNR_2000, p_KNR_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_KNR_2000)
success_ratio_KNR_2000, PT_KNR_2000, p2_KNR_2000 = PT_test(actual_2000, y_pred_KNR_2000)
# AdaBoost
y_pred_AdaBoost_2000 = np.array(y_pred_AdaBoost_2000).reshape(-1, 1)
MSFE_AdaBoost_2000 = mean_squared_error(y_pred_AdaBoost_2000, actual_2000)
OOS_R_AdaBoost_2000 = 1 - MSFE_AdaBoost_2000 / MSFE_HA_2000
MSFE_adjusted_AdaBoost_2000, p_AdaBoost_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_AdaBoost_2000)
success_ratio_AdaBoost_2000, PT_AdaBoost_2000, p2_AdaBoost_2000 = PT_test(actual_2000, y_pred_AdaBoost_2000)
# XGBoost
y_pred_XGBoost_2000 = np.array(y_pred_XGBoost_2000).reshape(-1, 1)
MSFE_XGBoost_2000 = mean_squared_error(y_pred_XGBoost_2000, actual_2000)
OOS_R_XGBoost_2000 = 1 - MSFE_XGBoost_2000 / MSFE_HA_2000
MSFE_adjusted_XGBoost_2000, p_XGBoost_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_XGBoost_2000)
success_ratio_XGBoost_2000, PT_XGBoost_2000, p2_XGBoost_2000 = PT_test(actual_2000, y_pred_XGBoost_2000)
# Combination
y_pred_combination_2000 = np.concatenate([y_pred_OLS_2000, y_pred_PLS_2000, y_pred_PCR_2000, y_pred_LASSO_2000,
                                          y_pred_ENet_2000, y_pred_GBRT_2000, y_pred_RF_2000, y_pred_NN3_2000,
                                          y_pred_SVR_2000, y_pred_KNR_2000, y_pred_AdaBoost_2000,
                                          y_pred_XGBoost_2000], axis=1).mean(axis=1).reshape(-1, 1)
MSFE_combination_2000 = mean_squared_error(y_pred_combination_2000, actual_2000)
OOS_R_combination_2000 = 1 - MSFE_combination_2000 / MSFE_HA_2000
MSFE_adjusted_combination_2000, p_combination_2000 = CW_test(actual_2000, y_pred_HA_2000, y_pred_combination_2000)
success_ratio_combination_2000, PT_combination_2000, p2_combination_2000 = PT_test(actual_2000, y_pred_combination_2000)
# success ratio of HA
success_ratio_HA_2000, PT_HA_2000, p2_HA_2000 = PT_test(actual_2000, y_pred_HA_2000)

# output results
results_OOS_sample_forecast1 = np.array([
    [np.nan, np.nan, np.nan, success_ratio_HA_2000, PT_HA_2000, p2_HA_2000],
    [OOS_R_OLS_2000, MSFE_adjusted_OLS_2000, p_OLS_2000, success_ratio_OLS_2000, PT_OLS_2000, p2_OLS_2000],
    [OOS_R_PLS_2000, MSFE_adjusted_PLS_2000, p_PLS_2000, success_ratio_PLS_2000, PT_PLS_2000, p2_PLS_2000],
    [OOS_R_PCR_2000, MSFE_adjusted_PCR_2000, p_PCR_2000, success_ratio_PCR_2000, PT_PCR_2000, p2_PCR_2000],
    [OOS_R_LASSO_2000, MSFE_adjusted_LASSO_2000, p_LASSO_2000, success_ratio_LASSO_2000, PT_LASSO_2000, p2_LASSO_2000],
    [OOS_R_ENet_2000, MSFE_adjusted_ENet_2000, p_ENet_2000, success_ratio_ENet_2000, PT_ENet_2000, p2_ENet_2000],
    [OOS_R_GBRT_2000, MSFE_adjusted_GBRT_2000, p_GBRT_2000, success_ratio_GBRT_2000, PT_GBRT_2000, p2_GBRT_2000],
    [OOS_R_RF_2000, MSFE_adjusted_RF_2000, p_RF_2000, success_ratio_RF_2000, PT_RF_2000, p2_RF_2000],
    [OOS_R_NN3_2000, MSFE_adjusted_NN3_2000, p_NN3_2000, success_ratio_NN3_2000, PT_NN3_2000, p2_NN3_2000]
])
results_OOS_sample_forecast1 = pd.DataFrame(results_OOS_sample_forecast1)
results_OOS_sample_forecast1.insert(0, "Forecasting models",  ["HA", "OLS", "PLS", "PCR", "LASSO",
                                                               "ENet", "GBRT", "RF", "NN3"])
results_OOS_sample_forecast1.to_csv("results_OOS_sample_forecast1_newly_identified_variables.csv", index=False)
#

results_OOS_sample_forecast2 = np.array([
    [np.nan, np.nan, np.nan, success_ratio_HA_2000, PT_HA_2000, p2_HA_2000],
    [OOS_R_SVR_2000, MSFE_adjusted_SVR_2000, p_SVR_2000, success_ratio_SVR_2000, PT_SVR_2000, p2_SVR_2000],
    [OOS_R_KNR_2000, MSFE_adjusted_KNR_2000, p_KNR_2000, success_ratio_KNR_2000, PT_KNR_2000, p2_KNR_2000],
    [OOS_R_AdaBoost_2000, MSFE_adjusted_AdaBoost_2000, p_AdaBoost_2000, success_ratio_AdaBoost_2000, PT_AdaBoost_2000, p2_AdaBoost_2000],
    [OOS_R_XGBoost_2000, MSFE_adjusted_XGBoost_2000, p_XGBoost_2000, success_ratio_XGBoost_2000, PT_XGBoost_2000, p2_XGBoost_2000],
    [OOS_R_combination_2000, MSFE_adjusted_combination_2000, p_combination_2000, success_ratio_combination_2000, PT_combination_2000, p2_combination_2000]
])
#
results_OOS_sample_forecast2 = pd.DataFrame(results_OOS_sample_forecast2)
results_OOS_sample_forecast2.insert(0, "Forecasting models",
                                   ["HA", "SVR", "KNR", "AdaBoost", "XGBoost", "Combination"])
results_OOS_sample_forecast2.to_csv("results_OOS_sample_forecast2_newly_identified_variables.csv", index=False)
#

