"""
Simple util implementation for video conference
Including data capture, image compression and image overlap
Note that you can use your own implementation as well :)
"""

import base64
from io import BytesIO
import pyaudio
import cv2
import pyautogui
import numpy as np
from PIL import Image, ImageGrab
from config import *


# print warning if no available camera
cap = cv2.VideoCapture(0)
if cap.isOpened():
    can_capture_camera = True
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
else:
    can_capture_camera = False

my_screen_size = pyautogui.size()


def resize_image_to_fit_screen(image, my_screen_size):
    screen_width, screen_height = my_screen_size

    original_width, original_height = image.size

    aspect_ratio = original_width / original_height

    if screen_width / screen_height > aspect_ratio:
        # resize according to height
        new_height = screen_height
        new_width = int(new_height * aspect_ratio)
    else:
        # resize according to width
        new_width = screen_width
        new_height = int(new_width / aspect_ratio)

    # resize the image
    resized_image = image.resize((new_width, new_height), Image.LANCZOS)

    return resized_image


def overlay_camera_images(screen_image, camera_images):
    """
    screen_image: PIL.Image
    camera_images: list[PIL.Image]
    """
    if screen_image is None and camera_images is None:
        print("[Warn]: cannot display when screen and camera are both None")
        return None
    if screen_image is not None:
        screen_image = resize_image_to_fit_screen(screen_image, my_screen_size)

    if camera_images is not None:
        # make sure same camera images
        if not all(img.size == camera_images[0].size for img in camera_images):
            raise ValueError("All camera images must have the same size")

        screen_width, screen_height = (
            my_screen_size if screen_image is None else screen_image.size
        )
        camera_width, camera_height = camera_images[0].size

        # calculate num_cameras_per_row
        num_cameras_per_row = screen_width // camera_width

        # adjust camera_imgs
        if len(camera_images) > num_cameras_per_row:
            adjusted_camera_width = screen_width // len(camera_images)
            adjusted_camera_height = (
                adjusted_camera_width * camera_height
            ) // camera_width
            camera_images = [
                img.resize(
                    (adjusted_camera_width, adjusted_camera_height), Image.LANCZOS
                )
                for img in camera_images
            ]
            camera_width, camera_height = adjusted_camera_width, adjusted_camera_height
            num_cameras_per_row = len(camera_images)

        # if no screen_img, create a container
        if screen_image is None:
            display_image = Image.fromarray(
                np.zeros((camera_width, my_screen_size[1], 3), dtype=np.uint8)
            )
        else:
            display_image = screen_image
        # cover screen_img using camera_images
        for i, camera_image in enumerate(camera_images):
            row = i // num_cameras_per_row
            col = i % num_cameras_per_row
            x = col * camera_width
            y = row * camera_height
            display_image.paste(camera_image, (x, y))

        return display_image
    else:
        return screen_image


def capture_screen():
    # capture screen with the resolution of display
    # img = pyautogui.screenshot()
    img = ImageGrab.grab()
    return img


def capture_camera():
    # capture frame of camera
    ret, frame = cap.read()
    if not ret:
        raise Exception("Fail to capture frame from camera")
    return Image.fromarray(frame)


def compress_image(image, format="JPEG", quality=85):
    """
    compress image and output Bytes

    :param image: PIL.Image, input image
    :param format: str, output format ('JPEG', 'PNG', 'WEBP', ...)
    :param quality: int, compress quality (0-100), 85 default
    :return: bytes, compressed image data
    """
    img_byte_arr = BytesIO()
    image.save(img_byte_arr, format=format, quality=quality)
    img_byte_arr = img_byte_arr.getvalue()

    return img_byte_arr


def decompress_image(image_bytes):
    """
    decompress bytes to PIL.Image
    :param image_bytes: bytes, compressed data
    :return: PIL.Image
    """
    img_byte_arr = BytesIO(image_bytes)
    image = Image.open(img_byte_arr)

    return image


def get_base64_image(opencv_img):
    base64_str = base64.b64encode(opencv_img).decode("utf-8")
    base64_image = f"data:image/webp;base64,{base64_str}"
    return base64_image


def overlay_audio(*audio_data):
    # 将音频数据转换为 numpy 数组（假设音频格式是 int16）
    audio_arrays = [np.frombuffer(data, dtype=np.int16) for data in audio_data]

    # 获取最大音频长度
    max_length = max(len(arr) for arr in audio_arrays)

    # 补齐音频数组
    for i in range(len(audio_arrays)):
        if len(audio_arrays[i]) < max_length:
            audio_arrays[i] = np.pad(
                audio_arrays[i], (0, max_length - len(audio_arrays[i])), "constant"
            )

    # 将音频数组按帧逐个叠加
    combined_audio = np.zeros(max_length, dtype=np.int16)
    for arr in audio_arrays:
        combined_audio += arr

    # 将叠加后的音频数据转换为字节
    return combined_audio.tobytes()
