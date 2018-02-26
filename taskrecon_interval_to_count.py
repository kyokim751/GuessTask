import random
import math
import numpy as np
from keras.layers import Input, Convolution2D, MaxPooling2D, Dense, Dropout, Flatten
from keras.models import Sequential
import  keras.models as km


from keras.utils import plot_model
from os import listdir
from os.path import isfile, join

'''
    This python script creates a model to infer number of tasks from busy intervals.
    Data Representation:
        Approach 1:
            Dataset creation procedure: Convert the trace into (timesteps, state) where there are three states (rest, busy,
            swich) for each time slot. State is a one-hot vector
        Approach 2:
            Dataset creation procedure: Convert the trace into (interval_slot, state) where three states (rest, busy, switch)
            have real value similar to one-hot vector (e.g. only one of the state can be non-zero)

    Model:
        Approach 1:
            LSTM + CNN in that order. The idea is for the LSTM to encode the data so that it preserves the temportal features
            and the CNN to exploit the local features
        Approach 2:
            Stacked DNN. This is for comparing the performance.
'''
INT_STATE_COUNT = 2

class Converter:

    # returns 0 is state did not change
    # returns >0 if the state is still busy but switched
    # returns <0 if the state changed from busy to rest or rest to busy
    @staticmethod
    def state_changed(int_current, int_prev):
        # no change
        if int_current - int_prev == 0:
            return 0
        # context switch
        elif int_current > 0 and int_prev > 0:
            return 1
        # rest to busy
        elif int_current > 0 and int_prev == 0:
            return -1
        # busy to rest
        else:
            return -2

    # returns a list of intervals. (e.g. [(state, duration), (state, duration), (state, duration)])
    @staticmethod
    def vectorize(string_trace):
        # convert trace to intervals
        # state 0 = rest, 1 = busy, 2 = context switch
        vect = []
        int_interval_duration = 1
        int_prev_task = string_trace[0]
        for i in range(1, len(string_trace)):
            # int_interval_duration += 1
            int_current_task = 1 if string_trace[i] > 0 else 0
            int_change_flag = int_current_task - int_prev_task
            if int_change_flag > 0:
                vect.append((0, int_interval_duration))
                int_interval_duration = 0
            elif int_change_flag < 0:
                vect.append((1, int_interval_duration))
                int_interval_duration = 0
            # elif int_change_flag > 0:
            #     # write interval
            #     vect.append((1, int_interval_duration))
            #     # write the context switch change.
            #     int_interval_duration = 0
            int_interval_duration += 1
            int_prev_task = int_current_task

        if int_prev_task > 0:
            vect.append((1,int_interval_duration))
        else:
            vect.append((0, int_interval_duration))
        return vect

    # returns a randomly shifted convolution of data
    # i.e. a window which will be a data point will be randomly placed in the list of intervals
    # this will be used to multiply the dataset.
    # outputs
    @staticmethod
    def data_convolutor(vec_x, int_window_length, int_max_count, int_slide = None):
        if int_slide is None:
            int_slide = int_window_length

        vec_o_vec_output = []
        int_vec_len = len(vec_x)
        int_max_index = int_vec_len - int_window_length
        int_offset = 0
        int_current_count = 0
        while int_offset < int_max_index and int_current_count < int_max_count:
            vec_o_vec_output.append(vec_x[int_offset:int_offset+int_window_length])
            int_offset += int_slide
            int_current_count += 1
        return vec_o_vec_output

    # this function assigns labels by groups
    @staticmethod
    def assign_label(vec_o_vec_x, int_group_label):
        vec_o_tup_output = []
        for vec_i in vec_o_vec_x:
            vec_o_tup_output.append((vec_i, int_group_label))
        return vec_o_tup_output

    @staticmethod
    def vec_o_tup_to_mat(vec_o_tup_list):
        int_list_len = len(vec_o_tup_list)
        int_datum_len = len(vec_o_tup_list[0][0])
        mat_x = np.zeros((int_list_len, int_datum_len, INT_STATE_COUNT))
        mat_y = np.zeros((int_list_len, 1))
        int_insertion_index = 0
        for tup_i in vec_o_tup_list:

            for i in range(int_datum_len):

                mat_x[int_insertion_index][i][tup_i[0][i][0]]=tup_i[0][i][1]
            mat_y[int_insertion_index][0] = tup_i[1]
            int_insertion_index += 1

        return (mat_x, mat_y)


    # returns datapoint and its label (each data point is a list of vectorize() output from different dataset)
    @staticmethod
    def prep_train_test(vec_o_tup_x, float_train_ratio):
        #
        int_total_len = len(vec_o_tup_x)
        int_train_len = math.floor(int_total_len * float_train_ratio)
        int_test_len = int_total_len - int_train_len

        vec_o_tup_train = vec_o_tup_x[:int_train_len]
        vec_o_tup_test = vec_o_tup_x[-1 * int_test_len:]

        mat_train_x, mat_train_y = Converter.vec_o_tup_to_mat(vec_o_tup_train)
        mat_test_x, mat_test_y = Converter.vec_o_tup_to_mat(vec_o_tup_test)

        return  mat_train_x, mat_train_y, mat_test_x, mat_test_y

    # takes a vector of traces with corresponding labels
    # Inflates the data by convoluting window
    @staticmethod
    def data_prep(vec_o_vec_trace, int_window_len, int_conv_count, vec_labels, int_window_slide = None):
        vec_o_tup_samples = []
        for i in range(len(vec_o_vec_trace)):
            vec_o_vec_convoluted_bunch = Converter.data_convolutor(Converter.vectorize(vec_o_vec_trace[i]), int_window_len , int_conv_count, int_window_slide)
            vec_o_tup_samples += Converter.assign_label(vec_o_vec_convoluted_bunch, vec_labels[i])
        return Converter.vec_o_tup_to_mat(vec_o_tup_samples)

class Model:

    def __init__(self, int_cell_count):
        self._int_cell_count = int_cell_count
        self._model = None
        self.create_model()

    # each row is a data point
    # each column is a feature(i.e. single interval in this case)
    def create_model(self, int_rows, int_columns):
        self._model = Sequential()
        self._model.add(Dense(100, input_shape=(int_rows, int_columns), activation='relu'))
        self._model.add(Dense(50, activation='relu'))
        self._model.add(Dense(25, activation='relu'))
        self._model.add(Dense(1, activation='linear'))
        self._model.compile(loss="mse", optimizer='adam', metrics=["accuracy"])


def partition_train_test(data_dict, ratio):
    train_x = []
    train_y = []
    test_x = []
    test_y = []
    remapped_x= []
    remapped_y = []

    for label, vec_data in data_dict.items():
        data_len = len(vec_data)
        index_list = np.random.perumation(data_len)
        for i in range(math.floor(data_len * ratio)):
            train_x.append(vec_data[index_list[i]])
            train_y.append(label)
        for i in range(math.floor(data_len * ratio), data_len):
            test_x.append(vec_data[index_list[i]])
            test_y.append(label)

    index_list = np.random.permutation(len(train_x))
    for i in range(len(train_x)):
        remapped_x.append(train_x[index_list[i]])
        remapped_y.append(train_y[index_list[i]])
    train_x = remapped_x
    train_y = remapped_y

    remapped_x= []
    remapped_y= []
    index_list = np.random.permutation(len(test_x))
    for i in range(len(test_x)):
        remapped_x.append(test_x[index_list[i]])
        remapped_y.append(test_y[index_list[i]])
    test_x = remapped_x
    test_y = remapped_y

    return train_x, train_y, test_x, test_y




if __name__ == "__main__":
    # int_input_length = 4
    # vec_datum1 = [0,0,0,0,1,1,1,2,1,2,0,0,1,1,1,1,1,1,0,1,1,0,1,1,2,2,2,2,2,0,0,0,0,1,2,1]
    # vec_datum2 = [0,1,1,0,1,1,2,2,2,2,2,0,0,0,0,1,2,1, 0,0,0,0,1,1,1,2,1,2,0,0,1,1,1,1,1,1]
    # vec_datum3 = [1, 2, 1, 1, 1, 0, 2, 2, 2, 2, 2, 1, 1, 1, 0, 1, 2, 1]
    #
    # vec_data1 = Converter.assign_label(Converter.data_convolutor(Converter.vectorize(vec_datum1), int_input_length, 2), 2)
    # vec_data2 = Converter.assign_label(Converter.data_convolutor(Converter.vectorize(vec_datum2), int_input_length, 2), 2)
    # # vec_data1.append()
    #
    # vec_data1 += vec_data2
    # print(vec_data1)
    # train_x = Converter.vec_o_tup_to_mat(vec_data1)
    # print(train_x)
    #
    # print(Converter.data_prep([vec_datum1, vec_datum2], int_input_length, 2, [2,2]))


    # #
    # input_layer = Input(shape=(int_input_length, 2))
    # dense_layer_1 = Dense(math.floor(int_input_length/2), name="dense_1")(input_layer)
    # dense_layer_2 = Dense(math.floor(int_input_length/4), name="dense_2")(dense_layer_1)
    # # dense_layer_3 = Dense(math.floor(int_input_length/8))(dense_layer_2)
    # # dense_layer_4 = Dense(math.floor(int_input_length/16))(dense_layer_3)
    # flat_layer = Flatten()(dense_layer_2)
    # dense_layer_5 = Dense(1, name="dense_3")(flat_layer)
    #
    #
    # model = km.Model(inputs=input_layer, outputs=dense_layer_5)
    # model.compile(loss="mean_squared_error", optimizer='adam', metrics=['accuracy'])
    #
    # plot_model(model, to_file='model.png')
    #
    # model.fit(train_x[0], train_x[1])
    stop = 0
    onlyfiles = [f for f in listdir("./data/") if isfile(join("./data/", f))]

    data_dict = {}

    for filename in onlyfiles:
        label = int(filename.split("rep")[0].split("size")[1])
        rep_count = int(filename.split("rep")[1].split(".")[0])

        if label not in data_dict:
            data_dict[label] = []

        with open("./data/" + filename) as file:
            data = file.read()
            parsed_trace = [int(x) for x in data.split(", ")]
            data_dict[label].append(parsed_trace)
            file.close()


    train_x, train_y, test_x, test_y = partition_train_test(data_dict, 0.75)
    train_x, train_y = Converter.data_prep(train_x, 5000, 2, train_y)
    test_x, test_y = Converter.data_prep(test_x, 5000, 2, test_y)

    print(test_x)


    # mod = Model(100)
    # model = mod._model

