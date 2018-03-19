import keras
import pydot_ng as pydot
from keras import Model
from keras.models import Sequential
from keras.layers import Dense, Dropout, CuDNNLSTM, TimeDistributed, Bidirectional, LSTM, RepeatVector, LeakyReLU, CuDNNGRU, Conv1D
import numpy as np
from sklearn.metrics import confusion_matrix
import re
import converter as cvt
import math
from keras.utils import plot_model
from keras.utils.vis_utils import plot_model
import json
import glob
import os
from pathlib2 import Path
from keras import backend as K
import matplotlib.pyplot as plt
from sklearn.preprocessing import MinMaxScaler



'''
    weighted_categorical_crossentropy implementation by Mike Clark https://gist.github.com/wassname
'''
def weighted_categorical_crossentropy(weights):
    """
    A weighted version of keras.objectives.categorical_crossentropy

    Variables:
        weights: numpy array of shape (C,) where C is the number of classes

    Usage:
        weights = np.array([0.5,2,10]) # Class one at 0.5, class 2 twice the normal weights, class 3 10x.
        loss = weighted_categorical_crossentropy(weights)
        model.compile(loss=loss,optimizer='adam')
    """

    weights = K.variable(weights)

    def loss(y_true, y_pred):
        # scale predictions so that the class probas of each sample sum to 1
        y_pred /= K.sum(y_pred, axis=-1, keepdims=True)
        # clip to prevent NaN's and Inf's
        y_pred = K.clip(y_pred, K.epsilon(), 1 - K.epsilon())
        # calc
        loss = y_true * K.log(y_pred) * weights
        loss = -K.sum(loss, -1)
        return loss
    return loss

# turns trace into binary vector
def mask_trace(value, trace):
    output_trace = []
    for i in range(len(trace)):
        val = trace[i]
        if val == value:
            output_trace.append(1)
        else:
            output_trace.append(0)
    return output_trace

def uniform_sample_trace(sample_gap, trace):
    output_trace = []
    for i in range(len(trace)):
        if i%sample_gap == 1:
            output_trace.append(trace[i])
    return output_trace

# output two vectors: one for X and the other for Y
def regression_trace(trace):
    X = []
    Y = []
    group_lists= []
    group = []
    group_state = trace[0];

    for i in range(1,len(trace)):
        val = trace[i]
        if group_state == val:
            group.append(val)
        else:
            if len(group) > 0:
                group_lists.append(group)
            group = [val]
            group_state = val
    if len(group) > 0:
        group_lists.append(group)

    for i in range(len(group_lists)):
        group = group_lists[i]
        print("group len: " + str(len(group)))
        group_state = group[0]
        if group_state == 0:
            group_state = -1
        for j in range(len(group)):
            X.append((-j*group_state))
            Y.append(-group_state*(len(group) - j))

    scaler = MinMaxScaler(feature_range=(0, 1))
    X_scaled = scaler.fit_transform(np.reshape(X,(len(X),1)))
    Y_scaled = scaler.fit_transform(np.reshape(Y,(len(Y),1)))

    # plt.plot(X[10000:10250])
    # plt.plot(Y[10000:10250])
    # plt.ylabel("some stuff")
    # plt.show()

    return X_scaled, Y_scaled


def save_result(fileName, data_dict):
    with open(fileName, "w") as file:
        file.write(json.dumps(data_dict, indent=4, sort_keys=True))
    return

def score_display(fold_scores):
    fold_count = len(fold_scores)
    avg = []
    for i in range(fold_count):
        print("fold " + str(i) + ":", end="")
        fold_avg = []
        for j in range(fold_count-1):
            fold_avg.append(fold_scores[i][j][1])
            print("\t"+str(fold_scores[i][j][1]), end="")
        avg.append(np.mean(fold_avg))
        print("\tfold_avg: "+str(avg[i]))
    total_avg = np.mean(avg)
    print("total_avg: " + str(total_avg))
    return total_avg


def create_model(cell_count, shape, stateful, batch, output_dim, loss="mse", drop_out = True, layers=1, timesteps = 100):
    model = Sequential()
    # model.add(TimeDistributed(Dense(cell_count, activation='linear', name="scale_stuff"), batch_size=batch, input_shape=shape))
    # model.add(TimeDistributed(Dense(cell_count, activation='tanh', name="scale_stuff"), batch_size=batch, input_shape=shape))
    # model.add(Conv1D(10, math.floor(timesteps/10), use_bias=True))
    model.add(CuDNNGRU(cell_count,
          stateful=stateful,
          return_sequences=True, name="lstm_1", batch_size=batch, input_shape=(timesteps, 6), bias_initializer='ones'))
    model.add(Conv1D(math.floor(timesteps/10), timesteps, use_bias=True, bias_initializer='random_uniform'))
    # model.add(RepeatVector(shape[0]))
    model.add(CuDNNGRU(math.ceil(cell_count),
                   stateful=stateful,
                   return_sequences=True, name="lstm_2", bias_initializer='ones')
              )
    model.add(CuDNNGRU(math.ceil(cell_count),
                       stateful=stateful,
                       return_sequences=True, name="lstm_3", batch_size=batch, bias_initializer='ones')
              )
    model.add(TimeDistributed(Dense(cell_count, activation='tanh', name="dense_middle_2", bias_initializer='random_uniform')))
    model.add(TimeDistributed(Dense(cell_count, activation='linear', name="dense_middle_3", bias_initializer='random_uniform')))
    model.add(TimeDistributed(Dense(output_dim, activation='linear', name="output_layer", bias_initializer='random_uniform')))
    model.compile(loss=loss, optimizer="Nadam", metrics=['accuracy'])
    return model


def manual_verification(model, test_x, test_y, batch_size=100):
    model.reset_states()
    pred_y = model.predict(test_x, batch_size=batch_size)

    label_card = len(pred_y[0][0])

    for l in range(label_card):
        predictions = []
        true_value = []
        for i in range(len(pred_y)):
            pred_chunk = pred_y[i][0][l]
            true_chunk = test_y[i][0][l]
            predictions.append(pred_chunk)
            true_value.append(true_chunk)
        plt.plot(predictions[1000:2000])
        plt.plot(true_value[1000:2000])
        plt.ylabel("some stuff")
        plt.show()
        plt.gcf().clear()
    return

def self_predict(model, test_dataset, prediction_length, label_card, batch_size=1):
    return


def save_matrix(matrix, filename):
    with open(filename, "w") as file:
        for i in range(len(matrix)):
            for j in range(len(matrix[0])):
                file.write(str(matrix[i][j]))
                if j != len(matrix[0])-1:
                    file.write(",")
            if i != len(matrix)-1:
                file.write("\n")
    return

def tasksize_extractor(name):
    splits = re.split('(\d+)', name)
    return int(splits[1])
def rep_extractor(name):
    splits = re.split('(\d+)', name)
    return int(splits[3])
def file_exists(fileName):
    theFile = Path(fileName)
    if theFile.is_file():
        return True
    return False


def run_instance(data_name, cell_size = 32, layers = 1, epoch = 50, batch_size = 32, prediction_len = 1, offset = 0, validation = True, timesteps = 10, target_task = 0):
    # TODO:
    label_name = tasksize_extractor(data_name)
    rep_number = rep_extractor(data_name)
    label_card = label_name+1

    result_path = "./result/" + str(label_name) + "_" + str(rep_number) + "/"
    modelname = result_path + str(cell_size) + "_" + str(layers) + "_" + str(epoch) + "_" + str(batch_size) + "_t" + str(
        timesteps) + "_" + str(offset) + "_" + str(target_task) + ".model"
    statname = result_path + str(cell_size) + "_" + str(layers) + "_" + str(epoch) + "_" + str(batch_size) + "_" + str(
        prediction_len) + "_" + str(offset) + "_" + str(target_task) +".json"

    if not os.path.exists(result_path):
        os.makedirs(result_path)

    original_trace = cvt.newText_to_list(data_name)


    masked_trx = []
    masked_try = []
    masked_tex = []
    masked_tey = []
    for t in range(label_card):
        print("processing task " + str(t))
        trace = mask_trace(t,original_trace)
        trace = uniform_sample_trace(5, trace)
        trace = trace[100:1000000]
        print(trace)
        trace_X, trace_Y = regression_trace(trace)



        example = cvt.list_to_example_regression(trace_X, trace_Y, timesteps= timesteps, offset=offset + timesteps, pred_len=prediction_len, seed=data_name)

        dataset1 = cvt.chunk_examples(example[0], example[1], 0, len(example[0]))
        print(np.asarray(dataset1[0]))

        train_x, train_y, test_x, test_y = cvt.split_train_test(0.80, example, timesteps=timesteps)
        masked_trx.append(train_x)
        masked_try.append(train_y)
        masked_tex.append(test_x)
        masked_tey.append(test_y)


    masked_trx = np.stack(masked_trx, axis=-1)
    masked_try = np.stack(masked_try, axis=-1)
    masked_tex = np.stack(masked_tex, axis=-1)
    masked_tey = np.stack(masked_tey, axis=-1)



    total_len = len(masked_trx)
    print(total_len)
    total_len -= total_len % batch_size

    masked_trx = masked_trx[:total_len]
    masked_try = masked_try[:total_len]

    train_x = np.reshape(masked_trx, (total_len, timesteps, label_card))
    train_y = np.reshape(masked_try, (total_len, 1, label_card))

    validation_ratio = None

    if validation:
        validation_len = (total_len * 0.1)
        validation_ratio = (validation_len - (validation_len % (batch_size * timesteps))) / total_len


    total_len = len(masked_tex)
    total_len -= total_len % batch_size
    masked_tex = masked_tex[:total_len]
    masked_tey = masked_tey[:total_len]

    test_x = np.reshape(masked_tex, (total_len, timesteps, label_card))
    test_y = np.reshape(masked_tey, (total_len, 1, label_card))

    if file_exists(modelname):
        model = keras.models.load_model(modelname)
        y_pred, y_true = manual_verification(model, test_x, test_y, batch_size=batch_size)
        return

    print(train_x.shape)


    model = create_model(cell_size, (timesteps,  label_card), stateful=True,
                         batch=batch_size,
                         output_dim=label_card,
                         layers=layers,
                         timesteps=timesteps,
                         loss="mean_squared_error")

    for i in range(1):
        model.fit(train_x, train_y, epochs=epoch, batch_size=batch_size, verbose=2, validation_split=validation_ratio)
        model.reset_states()
        print("Current epoch: " + str(i))

    # TODO:
    model.save(modelname)

    scores = model.evaluate(test_x, test_y, batch_size=batch_size, verbose=2)
    model.reset_states()
    y_pred, y_true = manual_verification(model, test_x, test_y, batch_size=batch_size)

    # statJSON = {}
    # statJSON["accuracy"] = scores[1]
    # statJSON["normalized_matrix"] = {}
    # for i in range(label_card):
    #     statJSON["normalized_matrix"][i] = normal[i].tolist()
    # statJSON["matrix"] = {}
    # for i in range(label_card):
    #     statJSON["matrix"][i] = confusion.astype("float")[i].tolist()
    #
    # save_result(statname, statJSON)

    return scores, y_pred, y_true, model


if __name__ == "__main__":



    layer_set = set([4])
    cell_set = set([64])
    offset_set = set([0])

    fileNames = glob.glob('./data/*.data')

    for filename in fileNames:
        for layer in layer_set:
            for cell in cell_set:
                for offset in offset_set:

                    info = run_instance(filename, cell_size=cell, layers=layer, epoch=48, batch_size=100, prediction_len=1, offset=10000, timesteps=150, target_task=3)

                    if info is None:
                        continue
                    normal_mat = info[2]
                    scores = info[0]
                    print(normal_mat)
                    print(scores)