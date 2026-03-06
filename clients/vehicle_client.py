"""
车端客户端

功能：
1. 发送车辆信息到服务端
2. 启动本地HTTP服务接收驾驶建议
"""

import argparse
import json
import requests
from flask import Flask, request, jsonify


def send_vehicle_info(server_url: str, vehicle_info: dict):
    """发送车辆信息到服务端"""
    url = f"{server_url}/vehicle/info"

    response = requests.post(url, json=vehicle_info)

    if response.status_code == 200:
        print(f"车辆信息发送成功: {response.json()}")
    else:
        print(f"车辆信息发送失败: {response.status_code} - {response.text}")

    return response


def start_receiver(port: int = 8000):
    """启动接收服务，监听驾驶建议"""
    app = Flask(__name__)

    @app.route('/instruct', methods=['POST'])
    def receive_instruction():
        data = request.get_json()
        instruction = data.get('instruction', '')
        print(f"\n{'='*50}")
        print(f"收到驾驶建议:")
        print(f"{instruction}")
        print(f"{'='*50}\n")
        return jsonify({"status": "received"})

    print(f"车端接收服务启动，监听端口 {port}...")
    app.run(host='0.0.0.0', port=port)


def main():
    parser = argparse.ArgumentParser(description='车端客户端')
    parser.add_argument('--mode', choices=['send', 'receive'], required=True,
                        help='模式: send=发送车辆信息, receive=接收驾驶建议')
    parser.add_argument('--server', default='http://localhost:5000', help='服务端地址')
    parser.add_argument('--port', type=int, default=8000, help='接收服务端口')
    parser.add_argument('--info', help='车辆信息JSON文件路径')

    args = parser.parse_args()

    if args.mode == 'receive':
        start_receiver(args.port)
    elif args.mode == 'send':
        if args.info:
            with open(args.info, 'r', encoding='utf-8') as f:
                vehicle_info = json.load(f)
        else:
            # 默认测试数据
            vehicle_info = {
                "type": "轿车",
                "color": "白色",
                "discription": "比亚迪秦Plus白色款",
                "plate": "京A12345",
                "intention": "直行通过路段",
                "length": 4.5,
                "width": 1.8,
                "height": 1.5,
                "location_x": 20.0,
                "location_y": 0.0,
                "location_z": 0.0,
                "rotation_row": 0.0,
                "rotation_pitch": 0.0,
                "rotation_yaw": 0.0,
                "velocity": 45.5,
                "acceleration": 0.2
            }
        send_vehicle_info(args.server, vehicle_info)


if __name__ == '__main__':
    main()
