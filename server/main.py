"""
路侧智能体服务端

接收来自路侧摄像头、车端和交通指挥者的数据，
调用Agent生成驾驶建议并推送到车端。
"""

import os
import sys
import io
import yaml
import requests
import numpy as np
import cv2
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.data_manager import DataManager
from agent.roadside_agent import RoadsideAgent

app = FastAPI(title="路侧智能体服务端", version="1.0.0")

# 全局变量
data_manager = DataManager()
agent: Optional[RoadsideAgent] = None
config: Dict = {}


def load_config(config_path: str = "config/server_config.yaml") -> Dict:
    """加载服务端配置"""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {
        "server": {"host": "0.0.0.0", "port": 5000},
        "vehicle": {"ip": "localhost", "port": 8000}
    }


def init_agent():
    """初始化Agent"""
    global agent
    agent = RoadsideAgent(
        agent_config_path='config/agent_config.yaml',
        camera_config_path='config/camera_config.yaml'
    )


# 请求模型
class VehicleInfoRequest(BaseModel):
    type: str
    color: str
    discription: Optional[str] = ""
    plate: str
    intention: str
    length: float
    width: float
    height: float
    location_x: float
    location_y: float
    location_z: float
    rotation_row: float
    rotation_pitch: float
    rotation_yaw: float
    velocity: float
    acceleration: float


class TrafficCommandRequest(BaseModel):
    command: str


# API端点
@app.on_event("startup")
async def startup_event():
    """服务启动时初始化"""
    global config
    config = load_config()
    init_agent()
    print("服务端启动完成")


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "cache_status": data_manager.get_status()}


@app.post("/camera/upload")
async def upload_camera_image(
    camera_id: str = Form(...),
    image: UploadFile = File(...)
):
    """接收摄像头图片"""
    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="无法解析图片")

        data_manager.set_image(camera_id, img)
        return {"status": "success", "camera_id": camera_id, "image_shape": img.shape}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/vehicle/info")
async def receive_vehicle_info(request: VehicleInfoRequest):
    """接收车辆信息并触发分析"""
    vehicle_info = request.model_dump()
    data_manager.set_vehicle_info(vehicle_info)

    # 获取缓存数据
    raw_images = data_manager.get_images()
    traffic_command = data_manager.get_traffic_command()

    if not raw_images:
        raise HTTPException(status_code=400, detail="没有可用的摄像头图片")

    # 调用Agent分析
    try:
        result = agent.analyze(
            raw_images=raw_images,
            vehicle_info=vehicle_info,
            traffic_command=traffic_command
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent分析失败: {str(e)}")

    # 发送驾驶建议到车端
    vehicle_ip = config.get("vehicle", {}).get("ip", "localhost")
    vehicle_port = config.get("vehicle", {}).get("port", 8000)

    try:
        resp = requests.post(
            f"http://{vehicle_ip}:{vehicle_port}/instruct",
            json={"instruction": result['advice']},
            timeout=5
        )
        send_status = "success" if resp.status_code == 200 else "failed"
    except Exception as e:
        send_status = f"failed: {str(e)}"

    # 清除已使用的交通指令
    data_manager.clear_traffic_command()

    return {
        "status": "success",
        "advice": result['advice'],
        "risk_level": result['risk_level'],
        "confidence": result['confidence'],
        "send_to_vehicle": send_status
    }


@app.post("/traffic/command")
async def receive_traffic_command(request: TrafficCommandRequest):
    """接收交通指挥指令"""
    data_manager.set_traffic_command(request.command)
    return {"status": "success", "command": request.command}


@app.get("/status")
async def get_status():
    """获取服务状态"""
    return {
        "agent_ready": agent is not None,
        "cache_status": data_manager.get_status(),
        "vehicle_target": f"{config.get('vehicle', {}).get('ip')}:{config.get('vehicle', {}).get('port')}"
    }


if __name__ == "__main__":
    import uvicorn
    config = load_config()
    init_agent()
    uvicorn.run(
        app,
        host=config.get("server", {}).get("host", "0.0.0.0"),
        port=config.get("server", {}).get("port", 5000)
    )
