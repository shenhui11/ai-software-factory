#!/usr/bin/env python3
"""
generate_spec.py - 根据自然语言需求生成特征规格说明
"""

import json
import os
import sys
from datetime import datetime
from openai import OpenAI
from pathlib import Path

def validate_environment():
    """检查必要的环境变量"""
    required_vars = ['OPENAI_API_KEY', 'FEATURE_ID', 'RAW_REQUIREMENT']
    missing = [var for var in required_vars if not os.environ.get(var)]
    
    if missing:
        print(f"错误: 缺少必要的环境变量: {', '.join(missing)}")
        sys.exit(1)
    
    # 验证 OpenAI API 密钥格式
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key.startswith('sk-'):
        print("警告: OPENAI_API_KEY 格式可能不正确，应以 'sk-' 开头")

def load_schema():
    """加载 JSON Schema"""
    schema_path = Path(__file__).parent.parent / 'specs' / 'schema' / 'feature-spec.schema.json'
    
    if not schema_path.exists():
        print(f"警告: Schema 文件不存在: {schema_path}")
        return None
    
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"错误: 无法加载 Schema: {e}")
        return None

def call_openai(prompt, schema=None):
    """调用 OpenAI API"""
    try:
        # 获取 API 配置
        api_key = os.environ.get('OPENAI_API_KEY')
        base_url = os.environ.get('OPENAI_BASE_URL')
        
        # 创建客户端
        client_params = {"api_key": api_key}
        if base_url:
            client_params["base_url"] = base_url
            print(f"使用自定义端点: {base_url}")
        
        client = OpenAI(**client_params)
        
        # 构建系统提示词
        system_prompt = """你是一个专业的产品经理，擅长将用户需求转化为结构化的特征规格说明。
        请根据用户的需求描述，生成一个符合 JSON Schema 的特征规格说明文档。"""
        
        # 如果有 Schema，添加到提示词中
        user_prompt = prompt
        if schema:
            user_prompt += f"\n\n请严格按照以下 JSON Schema 格式输出，不要包含任何解释性文字：\n{json.dumps(schema, indent=2, ensure_ascii=False)}"
        
        # 调用 API
        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "qwen3.6-plus"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,  # 低温度确保输出稳定
            max_tokens=2000
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"调用 OpenAI API 失败: {e}")
        raise

def parse_json_response(response_text):
    """解析 API 返回的 JSON"""
    # 尝试提取 JSON（可能被 markdown 代码块包围）
    text = response_text.strip()
    
    # 移除可能的 markdown 代码块标记
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    if text.endswith("```"):
        text = text[:-3]
    
    text = text.strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
        print(f"原始响应: {text}")
        return None

def save_spec(spec_data, feature_id):
    """保存生成的 spec 文件"""
    # 确保 spec 包含 feature_id
    if 'feature_id' not in spec_data:
        spec_data['feature_id'] = feature_id
    
    # 设置时间戳
    spec_data['created_at'] = datetime.now().isoformat()
    spec_data['updated_at'] = spec_data['created_at']
    
    # 保存到文件
    output_dir = Path(__file__).parent.parent / 'specs' / 'intake'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / f"{feature_id}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(spec_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Spec 已生成: {output_path}")
    return output_path

def main():
    """主函数"""
    print("=" * 60)
    print("开始生成特征规格说明...")
    print("=" * 60)
    
    # 1. 验证环境变量
    validate_environment()
    
    # 2. 获取输入
    feature_id = os.environ.get('FEATURE_ID')
    raw_requirement = os.environ.get('RAW_REQUIREMENT')
    
    print(f"特征ID: {feature_id}")
    print(f"原始需求: {raw_requirement}")
    print("-" * 60)
    
    # 3. 加载 Schema
    schema = load_schema()
    
    # 4. 构建提示词
    prompt = f"""
    请根据以下需求生成一个完整的产品特征规格说明：

    特征ID: {feature_id}
    需求描述: {raw_requirement}

    请生成一个详细的特征规格说明，包含以下关键信息：
    1. 特征标题
    2. 简要描述
    3. 涉及的角色
    4. 商业目标
    5. 范围（包括范围内和范围外）
    6. 验收标准
    7. 非功能性需求（安全性、性能、可靠性、可观测性）
    8. 技术约束
    9. 交付物
    """
    
    # 5. 调用 OpenAI API
    print("正在调用 OpenAI API 生成规格说明...")
    try:
        response = call_openai(prompt, schema)
        print("✅ API 调用成功")
    except Exception as e:
        print(f"❌ 生成失败: {e}")
        sys.exit(1)
    
    # 6. 解析响应
    print("正在解析响应...")
    spec_data = parse_json_response(response)
    
    if not spec_data:
        print("❌ 无法解析有效的 JSON 响应")
        sys.exit(1)
    
    # 7. 保存文件
    output_path = save_spec(spec_data, feature_id)
    
    # 8. 输出摘要
    print("\n" + "=" * 60)
    print("生成完成！摘要信息：")
    print("=" * 60)
    print(f"特征ID: {spec_data.get('feature_id', 'N/A')}")
    print(f"标题: {spec_data.get('title', 'N/A')}")
    print(f"描述: {spec_data.get('summary', 'N/A')[:100]}...")
    
    if 'actors' in spec_data:
        print(f"涉及角色: {', '.join(spec_data['actors'])}")
    
    if 'acceptance_criteria' in spec_data:
        print(f"验收标准数量: {len(spec_data['acceptance_criteria'])}")
    
    print(f"文件位置: {output_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
