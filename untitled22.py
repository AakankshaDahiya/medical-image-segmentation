# -*- coding: utf-8 -*-
"""Untitled22.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1O9AMimSlujeNnD4l-PyivXGtYuO3s2Xx
"""

# ========== STEP 1: Mount Google Drive and Unzip ==========
from google.colab import drive
import zipfile, os

drive.mount('/content/drive')

zip_path = "/content/drive/MyDrive/Colab Notebooks/CVAI/covid19.zip"
extract_path = "/content/covid19_dataset"

with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(extract_path)

frames_path = os.path.join(extract_path, "frames")
masks_path = os.path.join(extract_path, "masks")

# ========== STEP 2: Data Prep ==========
import tensorflow as tf
from sklearn.model_selection import train_test_split
import matplotlib.pyplot as plt

img_size = (128, 128)
batch_size = 4

image_files = sorted([os.path.join(frames_path, f) for f in os.listdir(frames_path)])
mask_files = sorted([os.path.join(masks_path, f) for f in os.listdir(masks_path)])

train_images, val_images, train_masks, val_masks = train_test_split(
    image_files, mask_files, test_size=0.2, random_state=42
)

def load_image_mask(image_path, mask_path):
    image = tf.io.read_file(image_path)
    image = tf.image.decode_png(image, channels=3)
    image = tf.image.resize(image, img_size)
    image = tf.cast(image, tf.float32) / 255.0

    mask = tf.io.read_file(mask_path)
    mask = tf.image.decode_png(mask, channels=1)
    mask = tf.image.resize(mask, img_size)
    mask = tf.cast(mask, tf.float32) / 255.0

    return image, mask

def augment(image, mask):
    seed = tf.random.uniform([2], maxval=10000, dtype=tf.int32)
    image = tf.image.stateless_random_flip_left_right(image, seed)
    mask = tf.image.stateless_random_flip_left_right(mask, seed)
    return image, mask

def get_dataset(img_paths, mask_paths, training=False):
    ds = tf.data.Dataset.from_tensor_slices((img_paths, mask_paths))
    ds = ds.map(lambda x, y: load_image_mask(x, y), num_parallel_calls=tf.data.AUTOTUNE)
    if training:
        ds = ds.map(augment, num_parallel_calls=tf.data.AUTOTUNE)
        ds = ds.shuffle(100)
    ds = ds.batch(batch_size).cache().prefetch(tf.data.AUTOTUNE)
    ds = ds.apply(tf.data.experimental.ignore_errors())
    return ds

train_dataset = get_dataset(train_images, train_masks, training=True)
val_dataset = get_dataset(val_images, val_masks)

# ========== STEP 3: Simplified U-Net ==========
def small_unet(input_size=(128, 128, 3)):
    inputs = tf.keras.Input(shape=input_size)

    def conv_block(x, filters):
        x = tf.keras.layers.Conv2D(filters, 3, padding="same", activation="relu")(x)
        x = tf.keras.layers.Conv2D(filters, 3, padding="same", activation="relu")(x)
        return x

    def encoder(x, filters):
        f = conv_block(x, filters)
        p = tf.keras.layers.MaxPooling2D((2, 2))(f)
        return f, p

    def decoder(x, skip, filters):
        x = tf.keras.layers.Conv2DTranspose(filters, 2, strides=2, padding="same")(x)
        x = tf.keras.layers.Concatenate()([x, skip])
        x = conv_block(x, filters)
        return x

    f1, p1 = encoder(inputs, 32)
    f2, p2 = encoder(p1, 64)
    f3, p3 = encoder(p2, 128)

    bottleneck = conv_block(p3, 256)

    d1 = decoder(bottleneck, f3, 128)
    d2 = decoder(d1, f2, 64)
    d3 = decoder(d2, f1, 32)

    outputs = tf.keras.layers.Conv2D(1, 1, activation="sigmoid")(d3)

    return tf.keras.Model(inputs, outputs)

model = small_unet()
model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
model.summary()

# ========== STEP 4: Train ==========
callbacks = [
    tf.keras.callbacks.ModelCheckpoint("best_unet_model.h5", save_best_only=True, verbose=1),
    tf.keras.callbacks.EarlyStopping(patience=3, restore_best_weights=True)
]

history = model.fit(
    train_dataset,
    validation_data=val_dataset,
    epochs=20,  +
    callbacks=callbacks
)

# ========== STEP 5: Evaluate ==========
loss, acc = model.evaluate(val_dataset)
print(f"Validation Accuracy: {acc:.4f}")

import numpy as np
import tensorflow as tf

def dice_score(y_true, y_pred, smooth=1e-6):
    y_true = tf.cast(y_true, tf.float32)
    y_pred = tf.cast(y_pred > 0.5, tf.float32)  # Threshold predicted mask

    intersection = tf.reduce_sum(y_true * y_pred)
    union = tf.reduce_sum(y_true) + tf.reduce_sum(y_pred)

    dice = (2. * intersection + smooth) / (union + smooth)
    return dice.numpy()

dice_scores = []

for images, masks in val_dataset:
    preds = model.predict(images)
    for i in range(len(preds)):
        dice = dice_score(masks[i], preds[i])
        dice_scores.append(dice)

mean_dice = np.mean(dice_scores)
print(f"Mean Dice Score on Validation Set: {mean_dice:.4f}")

from sklearn.metrics import f1_score, accuracy_score, precision_score, recall_score, confusion_matrix
import numpy as np

def evaluate_segmentation_metrics(model, dataset):
    all_preds = []
    all_masks = []

    for images, masks in dataset:
        preds = model.predict(images)
        preds = (preds > 0.5).astype(np.uint8)

        # Flatten for metric calculation
        all_preds.extend(preds.flatten())
        all_masks.extend(masks.numpy().flatten())

    # Convert to binary
    all_preds = np.array(all_preds).astype(np.uint8)
    all_masks = np.array(all_masks).astype(np.uint8)

    # Compute metrics
    acc = accuracy_score(all_masks, all_preds)
    f1 = f1_score(all_masks, all_preds)
    precision = precision_score(all_masks, all_preds)
    recall = recall_score(all_masks, all_preds)
    cm = confusion_matrix(all_masks, all_preds)

    print(f"Accuracy  : {acc:.4f}")
    print(f"Precision : {precision:.4f}")
    print(f"Recall    : {recall:.4f}")
    print(f"F1 Score  : {f1:.4f}")
    print("\nConfusion Matrix:")
    print(cm)

# Run evaluation
evaluate_segmentation_metrics(model, val_dataset)

# ========== STEP 6: Visualize ==========
def visualize_predictions(dataset, model, num=3):
    for images, masks in dataset.take(1):
        preds = model.predict(images)
        for i in range(num):
            plt.figure(figsize=(12, 4))
            plt.subplot(1, 3, 1)
            plt.imshow(images[i])
            plt.title("Input")
            plt.axis("off")

            plt.subplot(1, 3, 2)
            plt.imshow(masks[i].numpy().squeeze(), cmap="gray")
            plt.title("Ground Truth")
            plt.axis("off")

            plt.subplot(1, 3, 3)
            plt.imshow(preds[i].squeeze() > 0.5, cmap="gray")
            plt.title("Predicted")
            plt.axis("off")
            plt.show()

visualize_predictions(val_dataset, model)

