"""
路侧摄像头客户端

发送摄像头图片到服务端
"""

import argparse
import requests


def send_image(server_url: str, camera_id: str, image_path: str):
    """发送图片到服务端"""
    url = f"{server_url}/camera/upload"

    with open(image_path, 'rb') as f:
        files = {'image': (image_path, f, 'image/jpeg')}
        data = {'camera_id': camera_id}

        response = requests.post(url, files=files, data=data)

    if response.status_code == 200:
        print(f"图片上传成功: {response.json()}")
    else:
        print(f"图片上传失败: {response.status_code} - {response.text}")

    return response


def main():
    parser = argparse.ArgumentParser(description='路侧摄像头客户端')
    parser.add_argument('--server', default='http://localhost:5000', help='服务端地址')
    parser.add_argument('--camera', required=True, help='摄像头ID (如 camera_1)')
    parser.add_argument('--image', required=True, help='图片路径')

    args = parser.parse_args()
    send_image(args.server, args.camera, args.image)


if __name__ == '__main__':
    main()
