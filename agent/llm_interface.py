"""
LLM接口模块

该模块负责：
- 与多模态大语言模型交互
- 构建提示词
- 处理图像编码
- 解析模型响应
"""

import base64
import io
import json
from typing import Dict, List, Optional, Any
from PIL import Image
import numpy as np


class LLMInterface:
    """多模态LLM接口"""

    def __init__(self, config: Dict):
        """
        初始化LLM接口

        Args:
            config: LLM配置字典，包含：
                - provider: 'openai' 或 'anthropic'
                - model: 模型名称
                - api_key: API密钥
                - max_tokens: 最大生成token数
                - temperature: 温度参数
        """
        self.provider = config.get('provider', 'openai')
        self.model = config.get('model', 'gpt-4-vision-preview')
        self.api_key = config.get('api_key', '')
        self.max_tokens = config.get('max_tokens', 2000)
        self.temperature = config.get('temperature', 0.7)

        # 加载系统提示词
        self.system_prompt = self._load_system_prompt()

        # 初始化API客户端
        self._init_client()

    def _load_system_prompt(self) -> str:
        """加载系统提示词"""
        try:
            with open('prompts/system_prompt.txt', 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            # 如果文件不存在，返回默认提示词
            return "你是一个路侧交通安全助手，负责分析交通场景并提供驾驶建议。"

    def _init_client(self):
        """初始化API客户端"""
        if self.provider == 'openai':
            try:
                from openai import OpenAI
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
                )
            except ImportError:
                raise ImportError("请安装openai库: pip install openai")
        elif self.provider == 'anthropic':
            try:
                from anthropic import Anthropic
                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("请安装anthropic库: pip install anthropic")
        else:
            raise ValueError(f"不支持的provider: {self.provider}")

    def _encode_image(self, image: np.ndarray) -> str:
        """
        将numpy图像编码为base64字符串

        Args:
            image: numpy图像数组 (H, W, 3)

        Returns:
            base64编码的图像字符串
        """
        # 转换为PIL Image
        pil_image = Image.fromarray(image)

        # 压缩图像以减少token消耗
        max_size = 1024
        if max(pil_image.size) > max_size:
            ratio = max_size / max(pil_image.size)
            new_size = tuple(int(dim * ratio) for dim in pil_image.size)
            pil_image = pil_image.resize(new_size, Image.LANCZOS)

        # 编码为base64
        buffer = io.BytesIO()
        pil_image.save(buffer, format='JPEG', quality=85)
        image_bytes = buffer.getvalue()
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        return base64_image

    def _build_user_prompt(self, camera_coverage: Dict, vehicle_info: Dict,
                          traffic_command: Optional[Dict]) -> str:
        """
        构建用户提示词

        Args:
            camera_coverage: 摄像头覆盖信息
            vehicle_info: 车辆信息
            traffic_command: 交通指令（可选）

        Returns:
            用户提示词文本
        """
        prompt_parts = []

        # 1. 摄像头覆盖状态
        prompt_parts.append(f"## 摄像头空间关系：{camera_coverage['relationships']}")
        prompt_parts.append("## 摄像头覆盖状态\n")
        if camera_coverage['in_blind_spot']:
            blind_spot_info = camera_coverage['blind_spot_info']
            prompt_parts.append(f"**车辆不在任何摄像头视野内（监控死角）**\n")
            prompt_parts.append(f"{blind_spot_info['description']}\n")
        else:
            visible_cameras = camera_coverage['visible_cameras']
            camera_names = [camera_coverage['projections'][cid]['camera_name']
                          for cid in visible_cameras]
            prompt_parts.append(f"**车辆在以下摄像头视野内**: {', '.join(camera_names)}\n")
            prompt_parts.append(f"当前分析使用的摄像头: {camera_names[0]}\n")

        # 2. 车辆信息
        prompt_parts.append("\n## 车辆信息\n")
        prompt_parts.append(f"- **类型**: {vehicle_info['type']}\n")
        prompt_parts.append(f"- **颜色**: {vehicle_info['color']}\n")
        prompt_parts.append(f"- **车牌**: {vehicle_info['plate']}\n")
        if vehicle_info.get('description'):
            prompt_parts.append(f"- **描述**: {vehicle_info['description']}\n")
        prompt_parts.append(f"- **驾驶意图**: {vehicle_info['intention']}\n")
        prompt_parts.append(f"- **当前速度**: {vehicle_info['velocity']:.1f} km/h\n")
        prompt_parts.append(f"- **加速度**: {vehicle_info['acceleration']:.2f} m/s²\n")

        # 3. 交通指令
        if traffic_command:
            prompt_parts.append("\n## 交通指挥指令\n")
            prompt_parts.append(f"**指令内容**: {traffic_command['command']}\n")
            prompt_parts.append("**注意**: 交通指挥指令具有最高优先级，请优先执行该指令。\n")

        # 4. 分析要求
        prompt_parts.append("\n## 分析要求\n")
        prompt_parts.append("请按照系统提示词中的7步推理流程进行分析：\n")
        prompt_parts.append("1. 摄像头覆盖分析\n")
        prompt_parts.append("2. 观察分析\n")
        prompt_parts.append("3. 场景识别\n")
        prompt_parts.append("4. 盲区识别\n")
        prompt_parts.append("5. 风险评估\n")
        prompt_parts.append("6. 意图匹配\n")
        prompt_parts.append("7. 建议生成\n")
        prompt_parts.append("\n请提供完整的推理过程和最终的驾驶建议。\n")

        return ''.join(prompt_parts)

    def analyze_scene(self, camera_coverage: Dict, vehicle_info: Dict,
                     traffic_command: Optional[Dict] = None) -> Dict:
        """
        调用LLM分析场景并生成建议

        Args:
            camera_coverage: 摄像头覆盖信息（包含图像）
            vehicle_info: 车辆信息
            traffic_command: 交通指令（可选）

        Returns:
            分析结果字典：
            {
                "reasoning": "完整的推理过程",
                "advice": "驾驶建议",
                "risk_level": "low/medium/high",
                "raw_response": "原始LLM响应"
            }
        """
        # 构建用户提示词
        user_prompt = self._build_user_prompt(camera_coverage, vehicle_info, traffic_command)

        # 准备消息
        messages = []

        if self.provider == 'openai':
            # OpenAI格式
            messages.append({
                "role": "system",
                "content": self.system_prompt
            })

            # 如果车辆可见，添加图像
            if not camera_coverage['in_blind_spot']:
                # 获取第一个可见摄像头的图像
                first_camera = camera_coverage['visible_cameras'][0]
                image_with_bbox = camera_coverage['projections'][first_camera]['image_with_bbox']

                if image_with_bbox is not None:
                    base64_image = self._encode_image(image_with_bbox)

                    messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": user_prompt
                    })
            else:
                # 监控死角，只发送文本
                messages.append({
                    "role": "user",
                    "content": user_prompt
                })

            # 调用OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )

            raw_response = response.choices[0].message.content

        elif self.provider == 'anthropic':
            # Anthropic格式
            content_parts = [{"type": "text", "text": user_prompt}]

            # 如果车辆可见，添加图像
            if not camera_coverage['in_blind_spot']:
                first_camera = camera_coverage['visible_cameras'][0]
                image_with_bbox = camera_coverage['projections'][first_camera]['image_with_bbox']

                if image_with_bbox is not None:
                    base64_image = self._encode_image(image_with_bbox)
                    content_parts.insert(0, {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64_image
                        }
                    })

            # 调用Anthropic API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self.system_prompt,
                messages=[{
                    "role": "user",
                    "content": content_parts
                }]
            )

            raw_response = response.content[0].text

        # 解析响应
        result = self._parse_response(raw_response)
        result['raw_response'] = raw_response

        return result

    def _parse_response(self, response: str) -> Dict:
        """
        解析LLM响应，提取推理过程和建议

        Args:
            response: LLM原始响应文本

        Returns:
            解析后的结果字典
        """
        # 尝试分离推理过程和建议
        parts = response.split('## 驾驶建议')

        if len(parts) == 2:
            reasoning = parts[0].strip()
            advice = parts[1].strip()
        else:
            # 如果没有明确分隔，尝试其他方式
            if '---' in response:
                parts = response.split('---')
                reasoning = parts[0].strip()
                advice = parts[-1].strip()
            else:
                # 默认将整个响应作为推理过程
                reasoning = response
                advice = "请参考上述分析。"

        # 尝试提取风险等级
        risk_level = 'medium'  # 默认中等风险
        if '高风险' in response or '危险' in response or '紧急' in response:
            risk_level = 'high'
        elif '低风险' in response or '安全' in response:
            risk_level = 'low'

        return {
            'reasoning': reasoning,
            'advice': advice,
            'risk_level': risk_level
        }
