# -*- coding: utf-8 -*-
"""notebook7e8d723b43-2.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1zwjCKYDFMS6jSmKukucoSg3788l_7G-u
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import SimpleITK as sitk
import PIL
import cv2
import os
import shutil
import tempfile
from pathlib import Path

# This Python 3 environment comes with many helpful analytics libraries installed
# It is defined by the kaggle/python Docker image: https://github.com/kaggle/docker-python
# For example, here's several helpful packages to load

import numpy as np # linear algebra
import pandas as pd # data processing, CSV file I/O (e.g. pd.read_csv)

# Input data files are available in the read-only "../input/" directory
# For example, running this (by clicking run or pressing Shift+Enter) will list all files under the input directory

import os
for dirname, _, filenames in os.walk('/kaggle/input'):
    for filename in filenames:
        print(os.path.join(dirname, filename))

# You can write up to 20GB to the current directory (/kaggle/working/) that gets preserved as output when you create a version using "Save & Run All"
# You can also write temporary files to /kaggle/temp/, but they won't be saved outside of the current session

# Commented out IPython magic to ensure Python compatibility.
# %env DATA_DIRECTORY = /kaggle/input

directory = os.environ.get("DATA_DIRECTORY")
ROOT_DIR = Path(tempfile.mkdtemp()) if directory is None else Path(directory)
print(ROOT_DIR)

ECHONET_DATA_DIR = 'heartdatabase/EchoNet-Dynamic'
import pprint
pp = pprint.PrettyPrinter()
DATA_DIR = ROOT_DIR.joinpath(ECHONET_DATA_DIR)

INFO_FILE = DATA_DIR.joinpath('FileList.csv')
VOL_TRACE_FILE = DATA_DIR.joinpath('VolumeTracings.csv')

INFO_DF = pd.read_csv(INFO_FILE)
VOL_TRACE_DF = pd.read_csv(VOL_TRACE_FILE)
INFO_DF.head()

INFO_DF.Split.value_counts()

def extractEDandESframes(image_file, ED_frame_number, ES_frame_number):
    video = cv2.VideoCapture(str(image_file))
    frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    ## Retrieve the ED frame
    for i in range(ED_frame_number-1):
        ret, frame = video.read()
    res, ED_frame = video.read()
    ## Retrieve the ES frame
    diff = ES_frame_number - ED_frame_number
    for i in range(diff):
        ret, frame = video.read()
    res1, ES_frame = video.read()
    if not res:
        print("issue ED")
    if not res1:
        print("issue ES")
    if res&res1:
        return ED_frame, ES_frame
    else:
        return None, None

def saveEDandESimages(data_dir, output_dir, info_df, trace_df):
    patient_list = [x for x in data_dir.iterdir()]

    for i, file in enumerate(patient_list):
        patient_id = file.name.split('.')[0]
        frame_df = trace_df.query(f"FileName == '{file.name}'")
        try:
            ed_number, es_number = frame_df.Frame.unique()
        except:
            print(f"This {file} generated an error")
            continue
        split_value = info_df.query(f"FileName == '{patient_id}'").Split
        #print(ed_number, es_number)
        ED_frame, ES_frame = extractEDandESframes(file, ed_number, es_number)
        if ED_frame is not None or ES_frame is not None:
            ## Write the ED and ES frames as images
            iED_path = output_dir.joinpath(f"{patient_id}_ED.png")
            iES_path = output_dir.joinpath(f"{patient_id}_ES.png")
            cv2.imwrite(str(iED_path), ED_frame)
            cv2.imwrite(str(iES_path), ES_frame)
            ## Write the trac points into a csv file
            ED_info = frame_df.query(f'FileName =="{file.name}" and Frame == {ed_number}').reset_index(drop=True)
            ES_info = frame_df.query(f'FileName =="{file.name}" and Frame == {es_number}').reset_index(drop=True)
            ES_info = frame_df.query(f'FileName =="{file.name}" and Frame == {es_number}').reset_index(drop=True)
            ED_stack = np.hstack(ED_info[['X1', 'Y1', 'X2', 'Y2']].values).tolist()
            ES_stack = np.hstack(ES_info[['X1', 'Y1', 'X2', 'Y2']].values).tolist()
            keypoint_df = pd.DataFrame([ED_stack, ES_stack])
            keypoint_df['Image'] = [f"{patient_id}_ED.png", f"{patient_id}_ES.png"]
            keypoint_df['Split'] = [split_value.iloc[0], split_value.iloc[0]]
            keypoint_df.to_csv(output_dir.joinpath(f"{patient_id}.csv"), index=False)
        else:
            print(f"There was an issue with processing {file}")

VIDEO_DIR = DATA_DIR.joinpath('Videos')
OUTPUT_DIR = Path('/kaggle/working/Output')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
saveEDandESimages(VIDEO_DIR, OUTPUT_DIR, INFO_DF, VOL_TRACE_DF)

NUM_KEYPOINTS = 84
trace_df = pd.read_csv(OUTPUT_DIR.joinpath('0XB5CECBD29920B7B.csv'))
arr = PIL.Image.open(str(OUTPUT_DIR.joinpath('0XB5CECBD29920B7B_ED.png')))
plt.imshow(arr)
df = trace_df.query('Image == "0XB5CECBD29920B7B_ED.png"')
print(df.iloc[0][0])
for i in range(0, NUM_KEYPOINTS, 4):
    x1, y1 = df.iloc[0][i], df.iloc[0][i+1]
    x2, y2 = df.iloc[0][i+2], df.iloc[0][i+3]
    plt.plot([x1, x2], [y1, y2], color='red', linewidth=3)
plt.show()

import tensorflow as tf
print("TensorFlow version:", tf.__version__)

from keras.models import Model
from tensorflow.keras.applications.mobilenet_v2 import MobileNetV2
from keras.layers import Input, Dropout, SeparableConv2D, Dense, Flatten
import tensorflow

NUM_KEYPOINTS=84
IMAGE_SIZE = 112
OUTPUT_DIR = Path('/kaggle/working/Output')
EPOCHS=50

## Load all the images and the keypoints
def LoadData(input_dir, type='TRAIN'):
    all_images = []
    all_points = []
    all_ids = []
    for j, p in enumerate(input_dir.glob(f"*.csv")):
        df = pd.read_csv(p)
        try:
            df_type = df.Split.unique()[0]
        except AttributeError:
            print(df)
            break
        if df_type == type:
            for i, x in enumerate(df.Image):
                img = PIL.Image.open(input_dir.joinpath(x))
                #plt.imshow(img)
                #plt.show()
                v = df.iloc[i][:NUM_KEYPOINTS]
                if len(v) != 84:
                    continue
                all_points.append(v)
                img = cv2.resize(np.asarray(img), (IMAGE_SIZE, IMAGE_SIZE))
                all_images.append(img)
                all_ids.append(p.name.split('.')[0])
    all_images = np.asarray(all_images)
    all_points = np.asarray(all_points)
    all_points = all_points.reshape(-1, 1, 1, NUM_KEYPOINTS) / IMAGE_SIZE
    all_ids = np.asarray(all_ids)
    return all_images, all_points, all_ids

train_images, train_keypoints, train_ids = LoadData(OUTPUT_DIR)
pp.pprint(train_images.shape)
pp.pprint(train_keypoints.shape)
train_keypoints_conv = train_keypoints.astype('float32')

def VisualizeSampleImages(image, kps, col='red'):
    plt.imshow(image)
    for i in range(0, NUM_KEYPOINTS, 4):
        x1, y1 = kps[0][i], kps[0][i+1]
        x2, y2 = kps[0][i+2], kps[0][i+3]
        plt.plot([x1, x2], [y1, y2], color=col, linewidth=2)

plt.subplots(4, 4, figsize=(10,10))
num_total = train_images.shape[0]
for i, k in enumerate(np.random.randint(num_total, size=16)):
    kps = train_keypoints_conv[k].reshape(-1, NUM_KEYPOINTS) * IMAGE_SIZE
    image = train_images[k]
    plt.subplot(4, 4, i+1)
    plt.gca().set_yticklabels([])
    plt.gca().set_xticklabels([])
    plt.gca().set_xticks([])
    plt.gca().set_yticks([])
    VisualizeSampleImages(image, kps)
    plt.xlabel(train_ids[k])

def VisualizeInstanceData(data_images, data_keypoints, data_ids, ED_index, ES_index):
    print(f"Data id {data_ids[ED_index]}")
    plt.subplots(1, 2, figsize=(8, 8))
    plt.subplot(1, 2, 1)
    img = data_images[ED_index]
    kps = data_keypoints[ED_index].reshape(-1,NUM_KEYPOINTS) * IMAGE_SIZE
    plt.gca().set_yticklabels([])
    plt.gca().set_xticklabels([])
    plt.gca().set_xticks([])
    plt.gca().set_yticks([])
    VisualizeSampleImages(img, kps)
    plt.xlabel("ED image")
    plt.subplot(1, 2, 2)
    img = data_images[ES_index]
    kps = data_keypoints[ES_index].reshape(-1,NUM_KEYPOINTS) * IMAGE_SIZE
    plt.gca().set_yticklabels([])
    plt.gca().set_xticklabels([])
    plt.gca().set_xticks([])
    plt.gca().set_yticks([])
    VisualizeSampleImages(img, kps)
    plt.xlabel("ES image")

train_error_list = ['0X354B37A25C64276F','0X973E4A9DAADDF9F','0X37F9E9981E207C04','0X766B7B0ABDB07CD5',
'0X5B6FCBB75BF8FCB7','0X36C5A15AC7FC6AAA','0X4BBA9C8FB485C9AB','0X49EC1927F5747B19','0X5D38D994C2490EAE',
'0X53C185263415AA4F','0X65E605F203321860','0X753AA26EA352BBB']

x = [np.where(train_ids == inst)[0].tolist() for inst in train_error_list]

flat_list = list(np.concatenate(x).flat)
train_keypoints_conv = np.delete(train_keypoints_conv, flat_list, 0)
train_images = np.delete(train_images, flat_list, 0)
train_ids = np.delete(train_ids, flat_list, 0)

IMAGE_SIZE=112
backbone = MobileNetV2(input_shape=(IMAGE_SIZE, IMAGE_SIZE, 3), weights= '/kaggle/input/mobilenet-v2-weights/mobilenet_v2_weights_tf_dim_ordering_tf_kernels_1.0_224_no_top.h5', include_top=False)
backbone.trainable = False

MODEL_NAME = 'LV_Cavity_Volume_Trace'
#InputLayer
inputs = Input(shape=(IMAGE_SIZE, IMAGE_SIZE, 3), name="InputLayer")
# Preprocess Input
x = mobilenet_v2.preprocess_input(inputs)
# MobileNetV2 Backbone
x = backbone(x)
# Regularization
x = Dropout(0.3, name="DropOut")(x)
# Separable Convolutional Operation
x = SeparableConv2D(NUM_KEYPOINTS, kernel_size=3, activation='relu', data_format='channels_last', name="ConvPass")(x)
# Outputs
outputs = SeparableConv2D(NUM_KEYPOINTS, kernel_size=2, activation='sigmoid', data_format='channels_last', name="OutputLayer")(x)
#Model
model_1 = Model(inputs, outputs, name=MODEL_NAME)
model_1.summary()

val_images, val_keypoints, val_ids = LoadData(OUTPUT_DIR, type='VAL')
pp.pprint(val_images.shape)
pp.pprint(val_keypoints.shape)
val_keypoints_conv = val_keypoints.astype('float32')

# Callbacks
from keras.callbacks import EarlyStopping, ModelCheckpoint, Callback

# Optimizer
from tensorflow.keras.optimizers import Adam

class ShowProgress(Callback):

    def on_epoch_end(self, epoch, logs=None):
        if epoch % 20 == 0:
            plt.subplots(1, 4, figsize=(10, 10))
            for i, k in enumerate(np.random.randint(num_total, size=2)):
                img = train_images[k]
                img = img.reshape(-1, IMAGE_SIZE, IMAGE_SIZE, 3)
                pred_kps = self.model.predict(img)
                pred_kps = pred_kps.reshape(-1,NUM_KEYPOINTS) * IMAGE_SIZE
                kps = train_keypoints_conv[k].reshape(-1,NUM_KEYPOINTS) * IMAGE_SIZE
                plt.subplot(1, 4, 2*i+1)
                plt.gca().set_yticklabels([])
                plt.gca().set_xticklabels([])
                plt.gca().set_xticks([])
                plt.gca().set_yticks([])
                VisualizeSampleImages(img[0], pred_kps, col='#16a085')
                plt.xlabel(f"Predicted")
                plt.subplot(1, 4, 2*i+2)
                plt.gca().set_yticklabels([])
                plt.gca().set_xticklabels([])
                plt.gca().set_xticks([])
                plt.gca().set_yticks([])
                VisualizeSampleImages(img[0], kps)
                plt.xlabel(f"GT:{train_ids[k]}")
            plt.show()

WEIGHT_DIR = Path('/kaggle/working/Weights')
WEIGHT_DIR.mkdir(parents=True, exist_ok=True)

EPOCHS=100
# Compile
model_1.compile(loss='mae', optimizer=Adam(learning_rate=1e-4)) # Lower the Learning Rate better the results.
checkpoint_path = str(WEIGHT_DIR)+MODEL_NAME+"-{epoch:04d}.ckpt"
# Model Training
callbacks = [
#     EarlyStopping(patience=7, restore_best_weights=True), # keep the patience low.
    ModelCheckpoint(checkpoint_path, save_best_only=True, save_weights_only=True),
    ShowProgress()
]
history = model_1.fit(train_images, train_keypoints_conv,
                      validation_data=(val_images, val_keypoints_conv),
                      epochs=EPOCHS,
                      callbacks=callbacks)

lc = pd.DataFrame(history.history)
lc.plot(figsize=(10,8))
plt.title("Learning Curve", fontsize=25)
plt.grid()
plt.legend(fontsize=12)
plt.show()



from tensorflow.train import latest_checkpoint
latest = latest_checkpoint('/kaggle/working')
latest

test_images, test_keypoints, test_ids = LoadData(OUTPUT_DIR, type='TEST')
pp.pprint(test_images.shape)
pp.pprint(test_keypoints.shape)
test_keypoints_conv = test_keypoints.astype('float32')

def evaluate_model(model, data_images, data_keypoints):
    loss = model.evaluate(data_images, data_keypoints, verbose=2)
    return loss

model_2 = Model(inputs, outputs, name=MODEL_NAME)
model_2.compile(loss='mae', optimizer=Adam(learning_rate=1e-4))
model_2.load_weights(latest)

print(f"Loss for training images : {evaluate_model(model_2, train_images, train_keypoints_conv)}")
print(f"Loss for validation images : {evaluate_model(model_2, val_images, val_keypoints_conv)}")
print(f"Loss for testing images : {evaluate_model(model_2, test_images, test_keypoints_conv)}")

test_total = test_images.shape[0]
plt.subplots(1, 4, figsize=(10, 10))
for i, k in enumerate(np.random.randint(test_total, size=2)):
    img = test_images[k]
    img = img.reshape(-1, IMAGE_SIZE, IMAGE_SIZE, 3)
    pred_kps = model_2.predict(img)
    pred_kps = pred_kps.reshape(-1,NUM_KEYPOINTS) * IMAGE_SIZE
    kps = test_keypoints[k].reshape(-1,NUM_KEYPOINTS) * IMAGE_SIZE
    plt.subplot(1, 4, 2*i+1)
    plt.gca().set_yticklabels([])
    plt.gca().set_xticklabels([])
    plt.gca().set_xticks([])
    plt.gca().set_yticks([])
    VisualizeSampleImages(img[0], pred_kps, col='#16a085')
    plt.xlabel(f"Predicted")
    plt.subplot(1, 4, 2*i+2)
    plt.gca().set_yticklabels([])
    plt.gca().set_xticklabels([])
    plt.gca().set_xticks([])
    plt.gca().set_yticks([])
    VisualizeSampleImages(img[0], kps)
    plt.xlabel(f"GT:{train_ids[k]}")



import math
def calculate_disk_area(x1, y1, x2, y2):
    dist = np.linalg.norm(np.array((x1, y1)) - np.array((x2, y2)))
    r = dist/2
    area = np.pi * r * r
    return area

def calculate_volume(keypoints):
    '''
        keypoints: shape is [1, NUM_KEYPOINTS]
    '''
    ## first 4 is the long axis points
    x1, y1, x2, y2 = keypoints[0][0], keypoints[0][1], keypoints[0][2], keypoints[0][3]
    distance = np.linalg.norm(np.array((x1, y1)) - np.array((x2, y2)))
    height_of_disk = distance/20
    accumalated_areas = []
    for i in range(4, NUM_KEYPOINTS, 4):
        accumalated_areas.append(calculate_disk_area(keypoints[0][i], keypoints[0][i+1],
                                                     keypoints[0][i+2], keypoints[0][i+3]))

    xa, ya, xb, yb = keypoints[0][4], keypoints[0][5], keypoints[0][6], keypoints[0][7]
    xc, yc, xd, yd = keypoints[0][8], keypoints[0][9], keypoints[0][10], keypoints[0][11]
    ## Calculate the distance between the 2 adjacent parallel lines. This will be alternate height of
    ## the disk
    m = (yb-ya)/(xb-xa)
    c1 = yb - m*xb
    c2 = yd - m*xd
    alt_height_of_disk = abs(c1-c2)/math.sqrt(1+m*m)
    volume = sum(accumalated_areas)*height_of_disk
    return volume

# Commented out IPython magic to ensure Python compatibility.
# %matplotlib inline

def calculate_EF(ED_keypoints, ES_keypoints):
    '''
        ED_keypoints: shape [1, NUM_KEYPOINTS]
        ES_keypoints: shape [1, NUM_KEYPOINTS]
    '''
    ED_volume = calculate_volume(ED_keypoints)
    ES_volume = calculate_volume(ES_keypoints)
    EF = ((ED_volume - ES_volume) / ED_volume) * 100
    return EF

def calculate_EFs(data_keypoints):
    '''
    data_keypoints: shape [None, 1, 1, NUM_KEYPOINTS]
    '''
    total = data_keypoints.shape[0]
    data_EFs = []
    for i in range(0, total, 2):
        ED_kps = data_keypoints[i].reshape(-1, NUM_KEYPOINTS) * IMAGE_SIZE
        ES_kps = data_keypoints[i+1].reshape(-1, NUM_KEYPOINTS) * IMAGE_SIZE
        EF = calculate_EF(ED_kps, ES_kps)
        data_EFs.append(EF)
    return data_EFs

def build_dataframe_EFs(calculated_kps, predicted_kps):
    '''
        calculated_kps: shape [None, 1, 1, NUM_KEYPOINTS]
        predicted_kps: shape [None, 1, 1, NUM_KEYPOINTS]
    '''
    cal_efs = calculate_EFs(calculated_kps)
    pred_efs = calculate_EFs(predicted_kps)
    d = {'Actual_EF': cal_efs, 'Pred_EF': pred_efs}
    df = pd.DataFrame(data=d)
    act_lvef_class = []
    for i in df.Actual_EF:
        if i >= 70:
            act_lvef_class.append('Hyperdynamic')
        elif 69 >= i >= 55:
            act_lvef_class.append('Normal')
        elif 54 >= i >= 45:
            act_lvef_class.append('Mildly Reduced')
        elif 44 >= i >= 30:
            act_lvef_class.append('Moderately Reduced')
        else:
            act_lvef_class.append('Severely Reduced')
    act_lvef_class = pd.Series(act_lvef_class, name='Actual_HFClass')
    act_lvef_class = act_lvef_class.astype('category')
    act_lvef_class = act_lvef_class.cat.set_categories(["Hyperdynamic", "Normal", "Mildly Reduced", "Moderately Reduced", "Severely Reduced"], ordered=True)
    df['Actual_HFClass'] = act_lvef_class
    pred_lvef_class = []
    for i in df.Pred_EF:
        if i >= 70:
            pred_lvef_class.append('Hyperdynamic')
        elif 69 >= i >= 55:
            pred_lvef_class.append('Normal')
        elif 54 >= i >= 45:
            pred_lvef_class.append('Mildly Reduced')
        elif 44 >= i >= 30:
            pred_lvef_class.append('Moderately Reduced')
        else:
            pred_lvef_class.append('Severely Reduced')
    pred_lvef_class = pd.Series(pred_lvef_class, name='Actual_HFClass')
    pred_lvef_class = pred_lvef_class.astype('category')
    pred_lvef_class = pred_lvef_class.cat.set_categories(["Hyperdynamic", "Normal", "Mildly Reduced", "Moderately Reduced", "Severely Reduced"], ordered=True)
    df['Pred_HFClass'] = pred_lvef_class
    df['Diff_EFs'] = np.abs(df.Actual_EF - df.Pred_EF)
    return df

def get_predicted_points(data_images, model):
    '''
    data_images: shape [None, 112, 112, 3]
    '''
    data_kps = model.predict(data_images)
    return data_kps

predicted_train_kps = get_predicted_points(train_images, model_2)
predicted_val_kps = get_predicted_points(val_images, model_2)
predicted_test_kps = get_predicted_points(test_images, model_2)

training_output_df = build_dataframe_EFs(train_keypoints_conv, predicted_train_kps)
val_output_df = build_dataframe_EFs(val_keypoints_conv, predicted_val_kps)
test_output_df = build_dataframe_EFs(test_keypoints_conv, predicted_test_kps)

def VisualizeSingleData(data_images, data_keypoints, pred_keypoints, data_ids, index):
    print(f"Data id {data_ids[2*index]}")
    plt.subplots(1, 4, figsize=(12, 12))
    img = data_images[2*index]
    pred_kps = pred_keypoints[2*index].reshape(-1,NUM_KEYPOINTS) * IMAGE_SIZE
    kps = data_keypoints[2*index].reshape(-1,NUM_KEYPOINTS) * IMAGE_SIZE
    plt.subplot(1, 4, 1)
    plt.gca().set_yticklabels([])
    plt.gca().set_xticklabels([])
    plt.gca().set_xticks([])
    plt.gca().set_yticks([])
    VisualizeSampleImages(img, pred_kps, col='#16a085')
    plt.xlabel(f"Predicted")
    plt.subplot(1, 4, 2)
    plt.gca().set_yticklabels([])
    plt.gca().set_xticklabels([])
    plt.gca().set_xticks([])
    plt.gca().set_yticks([])
    VisualizeSampleImages(img, kps)
    img = data_images[2*index+1]
    pred_kps = pred_keypoints[2*index+1].reshape(-1,NUM_KEYPOINTS) * IMAGE_SIZE
    kps = data_keypoints[2*index+1].reshape(-1,NUM_KEYPOINTS) * IMAGE_SIZE
    plt.xlabel(f"GT:{data_ids[2*index+1]}")
    plt.subplot(1, 4, 3)
    plt.gca().set_yticklabels([])
    plt.gca().set_xticklabels([])
    plt.gca().set_xticks([])
    plt.gca().set_yticks([])
    VisualizeSampleImages(img, pred_kps, col='#16a085')
    plt.xlabel(f"Predicted")
    plt.subplot(1, 4, 4)
    plt.gca().set_yticklabels([])
    plt.gca().set_xticklabels([])
    plt.gca().set_xticks([])
    plt.gca().set_yticks([])
    VisualizeSampleImages(img, kps)
    plt.xlabel(f"GT:{data_ids[2*index+1]}")

error_list = training_output_df.query('Actual_EF < 0').index.tolist()
## Errors in training data
for i, err in enumerate(error_list):
    VisualizeSingleData(train_images, train_keypoints_conv, predicted_train_kps, train_ids, err)
    plt.show()

error_list_val = val_output_df.query('Actual_EF < 0').index.tolist()
## Errors in validation data
for err in error_list_val:
    VisualizeSingleData(val_images, val_keypoints_conv, predicted_val_kps, val_ids, err)
    plt.show()

from sklearn.metrics import accuracy_score
def Accuracy_ConfusionMatrix(actual, predicted, categories):
    print(f"Accuracy of model: {accuracy_score(actual, predicted)}")
    confusion_matrix = pd.crosstab(actual, predicted, rownames=['Actual'], colnames=['Predicted'])
    print(confusion_matrix)
    print("Sensitivity of model for individual classes")
    class_sum = np.sum(confusion_matrix, axis=1)
    for c,i in enumerate(categories):
        print(f"Class {i} : {confusion_matrix.iloc[c][c]/class_sum[c]}")

from sklearn.metrics import accuracy_score
def Accuracy_ConfusionMatrix(actual, predicted, categories):
    print(f"Accuracy of model: {accuracy_score(actual, predicted)}")
    confusion_matrix = pd.crosstab(actual, predicted, rownames=['Actual'], colnames=['Predicted'])
    print(confusion_matrix)
    print("Sensitivity of model for individual classes")
    class_sum = np.sum(confusion_matrix, axis=1)
    for c,i in enumerate(categories):
        print(f"Class {i} : {confusion_matrix.iloc[c][c]/class_sum[c]}")

print('Confusion Matrix for Training Data')
Accuracy_ConfusionMatrix(training_output_df.Actual_HFClass,
                         training_output_df.Pred_HFClass,
                         training_output_df.Actual_HFClass.cat.categories)

import matplotlib.pyplot as plt
from sklearn.datasets import make_classification
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay

cm = confusion_matrix(training_output_df.Actual_HFClass, training_output_df.Pred_HFClass, labels=training_output_df.Actual_HFClass.cat.categories)
disp = ConfusionMatrixDisplay(confusion_matrix=cm,display_labels=training_output_df.Actual_HFClass.cat.categories)
disp.plot()

plt.show()

print('Confusion Matrix for Validation Data')
Accuracy_ConfusionMatrix(val_output_df.Actual_HFClass,
                         val_output_df.Pred_HFClass,
                         val_output_df.Actual_HFClass.cat.categories)

import matplotlib.pyplot as plt
from sklearn.datasets import make_classification
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay

cm = confusion_matrix(val_output_df.Actual_HFClass, val_output_df.Pred_HFClass, labels=val_output_df.Actual_HFClass.cat.categories)
disp = ConfusionMatrixDisplay(confusion_matrix=cm,display_labels=val_output_df.Actual_HFClass.cat.categories)
disp.plot()

plt.show()

print('Confusion Matrix for Testing Data')
Accuracy_ConfusionMatrix(test_output_df.Actual_HFClass,
                         test_output_df.Pred_HFClass,
                         test_output_df.Actual_HFClass.cat.categories)

import matplotlib.pyplot as plt
from sklearn.datasets import make_classification
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay

cm = confusion_matrix(test_output_df.Actual_HFClass, test_output_df.Pred_HFClass, labels=test_output_df.Actual_HFClass.cat.categories)
disp = ConfusionMatrixDisplay(confusion_matrix=cm,display_labels=test_output_df.Actual_HFClass.cat.categories)
disp.plot()

plt.show()

VisualizeSingleData(train_images, train_keypoints_conv, predicted_train_kps, train_ids, 531)

training_output_df.boxplot(column='Diff_EFs', by='Actual_HFClass', showfliers=False)

history.history.keys()

import keras
from matplotlib import pyplot as plt
plt.plot(history.history['loss'])
plt.plot(history.history['val_loss'])
plt.title('Model Loss')
plt.ylabel('Loss')
plt.xlabel('Epoch')
plt.legend(['train', 'validation'], loc='upper left')
plt.show