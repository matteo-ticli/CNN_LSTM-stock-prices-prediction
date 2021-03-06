"""
We are going to focus at first on the Nasdaq100. We are going to scrape each trading day in the past 20 years.
    The scope is to create a strategy which is able to beat the market. We are going to base our analisys on:
        1. Technical indicators
        2. Differrent stocks for the correlation
        3. Dilated timeframe for each day

    PROCEDURE:
        1. Get data using Yahoo Finance
        2. Store data in a df
        3. Build technical indicators
        4. Calculate the "images"
        5. For each day label the image: SELL (0), BUY (1), HOLD (2)
        6. Data scaling
        7. Connect AWS
        8. Create the CNN
        9. Connects it to LSTM
        10. Test multiple models
        11. Conclusions
"""


import os
import numpy as np
import pandas as pd
import pandas_datareader.data as web
import datetime as dt
import technical_indicators as ti
import time


def get_data(directory, tickers, tickers_name, start_date='2000-01-01', end_date='2021-01-01'):
    if not os.path.exists(directory):
        os.makedirs(directory)
    for idx, ticker in enumerate(tickers):
        try:
            df_ticker = web.DataReader(ticker, 'yahoo', start_date, end_date).drop(labels=['Open', 'Volume', 'Adj Close'], axis=1)
            df_ticker = df_ticker.reset_index().dropna()
            df_ticker.to_csv(directory + '/' + tickers_name[idx] + '.csv', index=False)
            print(directory + '/' + tickers_name[idx])
        except:
            print(idx)
            continue


def create_csv(directory):
    for filename in os.listdir(directory):
        path = os.path.join(directory, filename)
        df = pd.read_csv(path)

        ti.simple_moving_average(df)
        ti.weighted_moving_average(df)
        ti.momentum(df)
        ti.stochastic_k(df)
        ti.stochastic_d(df)
        ti.moving_average_convergence_divergence(df)
        ti.relative_strength_index(df)
        ti.williams_r(df)
        ti.commodity_channel_index(df)
        ti.accumulation_distribution_oscillator(df)

        df.to_csv(path, index=False)


def load_assets_dfs(directory, main_asset):
    dfs_dict = dict()
    dfs_dict[main_asset] = pd.read_csv(os.path.join(directory, main_asset + '.csv'))

    for filename in os.listdir(directory):
        if filename == main_asset + '.csv':
            continue
        filename_split = filename.split('.', 1)
        dfs_dict[filename_split[0]] = pd.read_csv(os.path.join(directory, filename))

    ## clean rows that do not share same date
    start_date = dt.date(year=2000, month=1, day=1)
    end_date = dt.date(year=2021, month=1, day=1)
    current_date = start_date

    while current_date <= end_date:

        idx_list = list()
        for asset in dfs_dict.keys():
            df = dfs_dict[asset]
            idx = df.index[df['Date'] == current_date.isoformat()].to_list()
            if len(idx) != 0:
                idx_list.append(idx)

        if len(idx_list) != len(dfs_dict) and len(idx_list) != 0:
            for asset in dfs_dict.keys():
                df = dfs_dict[asset]
                idx = df.index[df['Date'] == current_date.isoformat()].to_list()
                if len(idx) != 0:
                    dfs_dict[asset].drop(labels=idx[0], axis=0, inplace=True)
                    dfs_dict[asset].reset_index(drop=True, inplace=True)

        current_date += dt.timedelta(days=1)

    return dfs_dict


def calculate_returns(dfs_dict):
    for i, asset in enumerate(dfs_dict):
        dfs_dict[asset]['Return'] = dfs_dict[asset]['Close'].diff() / dfs_dict[asset]['Close']
    return dfs_dict


def order_correlated_assets(dfs_dict, day, time_delta):
    arr = np.zeros((time_delta, len(dfs_dict)))
    list_asset = list()
    for i, asset in enumerate(list(dfs_dict.keys())):
        arr[:, i] = dfs_dict[asset].loc[day - time_delta + 1 :day, 'Return']
        list_asset.append(asset)
    df = pd.DataFrame(data=arr, columns=list_asset)
    corr_matrix = df.corr()
    corr_matrix_ordered = corr_matrix.sort_values(by=[main_asset])
    ordered_indexes = list(corr_matrix_ordered.index)
    ordered_indexes.reverse()
    return ordered_indexes


def label_tensor(dfs_dict, main_asset, day):
    if dfs_dict[main_asset].loc[day, 'Close'] < dfs_dict[main_asset].loc[day + 1, 'Close']:
        label = 1
    else:
        label = 0
    return label


def create_tensor(dfs_dict, main_asset, time_delta, tech_indicators, start_date_num=50, end_date_num=100):

    t, z, y, x = end_date_num-start_date_num, time_delta, tech_indicators, len(dfs_dict)
    tensor = np.zeros((t, z, y, x))
    labels = np.zeros((t, ))

    for idx, day in enumerate(range(start_date_num, end_date_num)):

        label = label_tensor(dfs_dict, main_asset, day)
        ordered_indexes = order_correlated_assets(dfs_dict, day, time_delta)

        for i, subday in enumerate(range(day - time_delta, day)):

            for j, asset in enumerate(ordered_indexes):

                # SMA
                if dfs_dict[asset].loc[subday, 'Close'] > dfs_dict[asset].loc[subday, 'SMA']:
                    tensor[idx, i, 0, j] = 1
                if dfs_dict[asset].loc[subday, 'Close'] <= dfs_dict[asset].loc[subday, 'SMA']:
                    tensor[idx, i, 0, j] = 0

                # WMA
                if dfs_dict[asset].loc[subday, 'Close'] > dfs_dict[asset].loc[subday, 'WMA']:
                    tensor[idx, i, 1, j] = 1
                if dfs_dict[asset].loc[subday, 'Close'] <= dfs_dict[asset].loc[subday, 'WMA']:
                    tensor[idx, i, 1, j] = 0

                # Mom
                if dfs_dict[asset].loc[subday, 'MOM'] > 0:
                    tensor[idx, i, 2, j] = 1
                if dfs_dict[asset].loc[subday, 'MOM'] <= 0:
                    tensor[idx, i, 2, j] = 0

                # K%
                if dfs_dict[asset].loc[subday, 'K %'] > dfs_dict[asset].loc[subday - 1, 'K %']:
                    tensor[idx, i, 3, j] = 1
                if dfs_dict[asset].loc[subday, 'K %'] <= dfs_dict[asset].loc[subday - 1, 'K %']:
                    tensor[idx, i, 3, j] = 0

                # D%
                if dfs_dict[asset].loc[subday, 'D %'] > dfs_dict[asset].loc[subday - 1, 'D %']:
                    tensor[idx, i, 4, j] = 1
                if dfs_dict[asset].loc[subday, 'D %'] <= dfs_dict[asset].loc[subday - 1, 'D %']:
                    tensor[idx, i, 4, j] = 0

                # MACD
                if dfs_dict[asset].loc[subday, 'MACD'] > dfs_dict[asset].loc[subday - 1, 'MACD']:
                    tensor[idx, i, 5, j] = 1
                if dfs_dict[asset].loc[subday, 'MACD'] <= dfs_dict[asset].loc[subday - 1, 'MACD']:
                    tensor[idx, i, 5, j] = 0

                # RSI
                if dfs_dict[asset].loc[subday, 'RSI'] <= 30 or dfs_dict[asset].loc[subday, 'RSI'] > dfs_dict[asset].loc[
                    subday - 1, 'RSI']:
                    tensor[idx, i, 6, j] = 1
                if dfs_dict[asset].loc[subday, 'RSI'] >= 70 or dfs_dict[asset].loc[subday, 'RSI'] <= \
                        dfs_dict[asset].loc[subday - 1, 'RSI']:
                    tensor[idx, i, 6, j] = 0

                # W %R
                if dfs_dict[asset].loc[subday, 'W %R'] > dfs_dict[asset].loc[subday - 1, 'W %R']:
                    tensor[idx, i, 7, j] = 1
                if dfs_dict[asset].loc[subday, 'W %R'] <= dfs_dict[asset].loc[subday - 1, 'W %R']:
                    tensor[idx, i, 7, j] = 0

                # CCI
                if dfs_dict[asset].loc[subday, 'CCI'] < -200 or dfs_dict[asset].loc[subday, 'CCI'] > \
                        dfs_dict[asset].loc[subday - 1, 'CCI']:
                    tensor[idx, i, 8, j] = 1
                if dfs_dict[asset].loc[subday, 'CCI'] > 200 or dfs_dict[asset].loc[subday, 'RSI'] <= \
                        dfs_dict[asset].loc[subday - 1, 'RSI']:
                    tensor[idx, i, 8, j] = 0

                # AD
                if dfs_dict[asset].loc[subday, 'AD'] > dfs_dict[asset].loc[subday - 1, 'AD']:
                    tensor[idx, i, 9, j] = 1
                if dfs_dict[asset].loc[subday, 'AD'] <= dfs_dict[asset].loc[subday - 1, 'AD']:
                    tensor[idx, i, 9, j] = 0

        labels[idx] = label

    return tensor, labels


def execute_data_prep(directory, time_delta, tech_indicators, tickers, tickers_name, main_asset,
                      start_date, end_date, start_tensor, end_tensor, tensor_name, labels_name):

    t0 = time.time()

    get_data(directory, tickers, tickers_name, start_date=start_date, end_date=end_date)
    create_csv(directory)
    dfs_dict = load_assets_dfs(directory, main_asset)
    dfs_dict = calculate_returns(dfs_dict)
    tensor, labels = create_tensor(dfs_dict, main_asset, time_delta, tech_indicators, start_date_num=start_tensor, end_date_num=end_tensor)

    np.save(tensor_name, tensor)
    np.save(labels_name, labels)

    t1 = time.time()
    delta_t = t1 - t0
    print(f"The data preparation process lasted: {delta_t} seconds")

    return tensor, labels


### execute this code with these parameters ###

directory = os.getcwd() + '/data'

tickers = ['^NDX', '^GSPC', '^DJI', '^RUT', '^NYA', '^GDAXI', '^N225', '^FCHI', '^HSI', '000001.SS']
tickers_name = ['NASDAQ', 'SP500', 'DJI', 'RUSSEL', 'NYSE', 'DAX', 'NIKKEI 225', 'CAC 40', 'HANG SENG', 'SSE']
main_asset = 'NASDAQ'
time_delta = 10
tech_indicators = 10

start_date = '2000-01-01'
end_date = '2021-01-01'
start_date_num = 50
end_date_num = 5200

tensor_name = directory + '/' + main_asset + '/tensor.npy'
labels_name = directory + '/' + main_asset + '/labels.npy'

tensor, labels = execute_data_prep(directory, time_delta, tech_indicators, tickers, tickers_name, main_asset,
                                   start_date, end_date, start_date_num, end_date_num, tensor_name, labels_name)