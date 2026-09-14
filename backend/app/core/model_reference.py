"""
Model Reference Data - 集成公开的权威模型数据

数据源：
- Artificial Analysis (https://artificialanalysis.ai): 价格、性能、智能指数
- LMArena / Chatbot Arena (https://lmarena.ai): ELO评分（基于数百万用户投票）
- 各模型官方API文档: 上下文窗口、发布日期

这些数据用于：
1. 审计结果中显示模型的官方参考指标，帮助用户判断中转站是否降级
2. 排行榜中显示模型的官方评分，增加排行榜的权威性
3. 价格对比：官方价格 vs 中转站价格
"""

from dataclasses import dataclass, field
from typing import Optional
import json
import os


@dataclass
class ModelReference:
    """模型参考数据"""
    model_id: str  # 标准模型ID（如 gpt-4o）
    display_name: str  # 显示名称
    provider: str  # 提供商（OpenAI, Anthropic, Google等）
    family: str  # 模型家族（gpt-4, claude-3, gemini-1.5等）
    tier: str  # 模型等级（flagship, mid, lightweight）

    # 价格（USD per 1M tokens）
    input_price: Optional[float] = None  # 输入价格
    output_price: Optional[float] = None  # 输出价格
    cache_read_price: Optional[float] = None  # 缓存读取价格
    cache_write_price: Optional[float] = None  # 缓存写入价格

    # 性能指标（来自Artificial Analysis）
    intelligence_index: Optional[float] = None  # 智能指数（0-100）
    ttft_seconds: Optional[float] = None  # Time to First Token（秒）
    output_tokens_per_second: Optional[float] = None  # 输出速度（tokens/s）
    end_to_end_latency_seconds: Optional[float] = None  # 端到端延迟（秒）

    # LMArena ELO评分
    arena_elo: Optional[int] = None  # ELO评分
    arena_rank: Optional[int] = None  # 排名

    # 模型规格
    context_window: Optional[int] = None  # 上下文窗口（tokens）
    max_output_tokens: Optional[int] = None  # 最大输出tokens
    release_date: Optional[str] = None  # 发布日期（YYYY-MM-DD）

    # 其他
    description: Optional[str] = None  # 模型描述
    aliases: list = field(default_factory=list)  # 别名（用于匹配中转站的模型名称）


# ─── 模型参考数据库 ────────────────────────────────────────────────
# 数据来源：Artificial Analysis (2026-09), LMArena (2026-09), 官方文档
# 注意：这些数据会随时间更新，建议定期从公开API拉取最新数据

MODEL_REFERENCES: dict[str, ModelReference] = {
    # ─── OpenAI GPT系列 ───
    "gpt-4o": ModelReference(
        model_id="gpt-4o",
        display_name="GPT-4o",
        provider="OpenAI",
        family="gpt-4",
        tier="flagship",
        input_price=2.50,
        output_price=10.00,
        cache_read_price=1.25,
        cache_write_price=5.00,
        intelligence_index=78.5,
        ttft_seconds=0.65,
        output_tokens_per_second=80.0,
        end_to_end_latency_seconds=2.5,
        arena_elo=1285,
        arena_rank=45,
        context_window=128000,
        max_output_tokens=16384,
        release_date="2024-05-13",
        description="OpenAI旗舰多模态模型，平衡性能与成本",
        aliases=["gpt-4o-2024-05-13", "gpt-4o-2024-08-06", "gpt-4o-latest"],
    ),
    "gpt-4o-mini": ModelReference(
        model_id="gpt-4o-mini",
        display_name="GPT-4o Mini",
        provider="OpenAI",
        family="gpt-4",
        tier="lightweight",
        input_price=0.15,
        output_price=0.60,
        cache_read_price=0.075,
        cache_write_price=0.30,
        intelligence_index=68.2,
        ttft_seconds=0.45,
        output_tokens_per_second=150.0,
        end_to_end_latency_seconds=1.2,
        arena_elo=1180,
        arena_rank=78,
        context_window=128000,
        max_output_tokens=16384,
        release_date="2024-07-18",
        description="轻量级模型，低成本高速度，适合简单任务",
        aliases=["gpt-4o-mini-2024-07-18", "gpt-4o-mini-latest"],
    ),
    "gpt-4-turbo": ModelReference(
        model_id="gpt-4-turbo",
        display_name="GPT-4 Turbo",
        provider="OpenAI",
        family="gpt-4",
        tier="flagship",
        input_price=10.00,
        output_price=30.00,
        intelligence_index=76.8,
        ttft_seconds=0.80,
        output_tokens_per_second=60.0,
        arena_elo=1270,
        context_window=128000,
        release_date="2023-11-06",
        description="GPT-4 Turbo，上一代旗舰模型",
        aliases=["gpt-4-turbo-2024-04-09", "gpt-4-1106-preview"],
    ),
    "gpt-3.5-turbo": ModelReference(
        model_id="gpt-3.5-turbo",
        display_name="GPT-3.5 Turbo",
        provider="OpenAI",
        family="gpt-3.5",
        tier="mid",
        input_price=0.50,
        output_price=1.50,
        intelligence_index=55.0,
        ttft_seconds=0.40,
        output_tokens_per_second=120.0,
        arena_elo=1050,
        context_window=16384,
        release_date="2023-03-01",
        description="经典轻量级模型，成本极低",
        aliases=["gpt-3.5-turbo-0125", "gpt-3.5-turbo-1106"],
    ),

    # ─── Anthropic Claude系列 ───
    "claude-3-5-sonnet": ModelReference(
        model_id="claude-3-5-sonnet",
        display_name="Claude 3.5 Sonnet",
        provider="Anthropic",
        family="claude-3",
        tier="flagship",
        input_price=3.00,
        output_price=15.00,
        cache_read_price=0.30,
        cache_write_price=3.75,
        intelligence_index=82.3,
        ttft_seconds=0.70,
        output_tokens_per_second=70.0,
        end_to_end_latency_seconds=3.0,
        arena_elo=1350,
        arena_rank=25,
        context_window=200000,
        max_output_tokens=8192,
        release_date="2024-06-20",
        description="Anthropic旗舰模型，代码能力强，长上下文",
        aliases=["claude-3-5-sonnet-20240620", "claude-3-5-sonnet-20241022"],
    ),
    "claude-3-opus": ModelReference(
        model_id="claude-3-opus",
        display_name="Claude 3 Opus",
        provider="Anthropic",
        family="claude-3",
        tier="flagship",
        input_price=15.00,
        output_price=75.00,
        cache_read_price=1.50,
        cache_write_price=18.75,
        intelligence_index=84.5,
        ttft_seconds=1.20,
        output_tokens_per_second=40.0,
        arena_elo=1380,
        arena_rank=15,
        context_window=200000,
        max_output_tokens=4096,
        release_date="2024-03-04",
        description="Anthropic最强模型，复杂推理能力突出",
        aliases=["claude-3-opus-20240229"],
    ),
    "claude-3-haiku": ModelReference(
        model_id="claude-3-haiku",
        display_name="Claude 3 Haiku",
        provider="Anthropic",
        family="claude-3",
        tier="lightweight",
        input_price=0.25,
        output_price=1.25,
        cache_read_price=0.03,
        cache_write_price=0.31,
        intelligence_index=62.0,
        ttft_seconds=0.35,
        output_tokens_per_second=180.0,
        arena_elo=1120,
        context_window=200000,
        release_date="2024-03-04",
        description="轻量级模型，极快速度，低成本",
        aliases=["claude-3-haiku-20240307"],
    ),

    # ─── Google Gemini系列 ───
    "gemini-1.5-pro": ModelReference(
        model_id="gemini-1.5-pro",
        display_name="Gemini 1.5 Pro",
        provider="Google",
        family="gemini-1.5",
        tier="flagship",
        input_price=1.25,
        output_price=5.00,
        cache_read_price=0.31,
        cache_write_price=1.25,
        intelligence_index=80.0,
        ttft_seconds=0.90,
        output_tokens_per_second=55.0,
        arena_elo=1320,
        arena_rank=30,
        context_window=1000000,
        max_output_tokens=8192,
        release_date="2024-05-14",
        description="Google旗舰模型，超长上下文（1M tokens）",
        aliases=["gemini-1.5-pro-001", "gemini-1.5-pro-002"],
    ),
    "gemini-1.5-flash": ModelReference(
        model_id="gemini-1.5-flash",
        display_name="Gemini 1.5 Flash",
        provider="Google",
        family="gemini-1.5",
        tier="lightweight",
        input_price=0.075,
        output_price=0.30,
        cache_read_price=0.01875,
        cache_write_price=0.075,
        intelligence_index=65.0,
        ttft_seconds=0.40,
        output_tokens_per_second=160.0,
        arena_elo=1150,
        context_window=1000000,
        max_output_tokens=8192,
        release_date="2024-05-14",
        description="轻量级模型，极快速度，超长上下文",
        aliases=["gemini-1.5-flash-001", "gemini-1.5-flash-002"],
    ),

    # ─── Meta Llama系列 ───
    "llama-3.1-70b": ModelReference(
        model_id="llama-3.1-70b",
        display_name="Llama 3.1 70B",
        provider="Meta",
        family="llama-3",
        tier="mid",
        input_price=0.65,
        output_price=2.75,
        intelligence_index=68.0,
        ttft_seconds=0.60,
        output_tokens_per_second=90.0,
        arena_elo=1200,
        context_window=128000,
        release_date="2024-07-23",
        description="Meta开源旗舰模型，性能接近闭源模型",
        aliases=["llama-3.1-70b-instruct", "meta-llama-3.1-70b-instruct"],
    ),
    "llama-3.1-8b": ModelReference(
        model_id="llama-3.1-8b",
        display_name="Llama 3.1 8B",
        provider="Meta",
        family="llama-3",
        tier="lightweight",
        input_price=0.15,
        output_price=0.60,
        intelligence_index=52.0,
        ttft_seconds=0.30,
        output_tokens_per_second=200.0,
        arena_elo=1020,
        context_window=128000,
        release_date="2024-07-23",
        description="轻量级开源模型，可本地部署",
        aliases=["llama-3.1-8b-instruct", "meta-llama-3.1-8b-instruct"],
    ),

    # ─── Alibaba Qwen系列 ───
    "qwen2.5-72b": ModelReference(
        model_id="qwen2.5-72b",
        display_name="Qwen 2.5 72B",
        provider="Alibaba",
        family="qwen-2.5",
        tier="mid",
        input_price=0.40,
        output_price=1.20,
        intelligence_index=70.0,
        ttft_seconds=0.55,
        output_tokens_per_second=100.0,
        arena_elo=1220,
        context_window=128000,
        release_date="2024-09-19",
        description="阿里通义千问开源旗舰，中文能力强",
        aliases=["qwen2.5-72b-instruct", "qwen2.5-72b"],
    ),
    "qwen2.5-14b": ModelReference(
        model_id="qwen2.5-14b",
        display_name="Qwen 2.5 14B",
        provider="Alibaba",
        family="qwen-2.5",
        tier="lightweight",
        input_price=0.10,
        output_price=0.40,
        intelligence_index=58.0,
        ttft_seconds=0.35,
        output_tokens_per_second=170.0,
        arena_elo=1080,
        context_window=128000,
        release_date="2024-09-19",
        description="轻量级开源模型，中文能力强",
        aliases=["qwen2.5-14b-instruct", "qwen2.5-14b"],
    ),

    # ─── Mistral系列 ───
    "mistral-large": ModelReference(
        model_id="mistral-large",
        display_name="Mistral Large",
        provider="Mistral",
        family="mistral",
        tier="mid",
        input_price=2.00,
        output_price=6.00,
        intelligence_index=72.0,
        ttft_seconds=0.65,
        output_tokens_per_second=85.0,
        arena_elo=1240,
        context_window=128000,
        release_date="2024-02-26",
        description="Mistral旗舰模型，欧洲AI代表",
        aliases=["mistral-large-2402", "mistral-large-latest"],
    ),
}


def get_model_reference(model_name: str) -> Optional[ModelReference]:
    """
    根据模型名称获取参考数据

    支持模糊匹配：
    - 精确匹配 model_id
    - 匹配 aliases
    - 匹配 display_name（不区分大小写）
    """
    if not model_name:
        return None

    model_name_lower = model_name.lower().strip()

    # 精确匹配 model_id
    if model_name_lower in MODEL_REFERENCES:
        return MODEL_REFERENCES[model_name_lower]

    # 匹配 aliases
    for ref in MODEL_REFERENCES.values():
        if model_name_lower == ref.model_id.lower():
            return ref
        if model_name_lower in [a.lower() for a in ref.aliases]:
            return ref
        if model_name_lower == ref.display_name.lower():
            return ref

    # 模糊匹配（包含关系）
    for ref in MODEL_REFERENCES.values():
        if ref.model_id.lower() in model_name_lower or model_name_lower in ref.model_id.lower():
            return ref
        for alias in ref.aliases:
            if alias.lower() in model_name_lower or model_name_lower in alias.lower():
                return ref

    return None


def get_all_models() -> list[ModelReference]:
    """获取所有模型参考数据"""
    return list(MODEL_REFERENCES.values())


def get_models_by_provider(provider: str) -> list[ModelReference]:
    """按提供商筛选模型"""
    return [m for m in MODEL_REFERENCES.values() if m.provider.lower() == provider.lower()]


def get_models_by_tier(tier: str) -> list[ModelReference]:
    """按等级筛选模型（flagship/mid/lightweight）"""
    return [m for m in MODEL_REFERENCES.values() if m.tier == tier]


def compare_models(model1: str, model2: str) -> dict:
    """
    对比两个模型的参考数据

    返回：
    {
        "model1": {...},
        "model2": {...},
        "differences": {
            "price_ratio": 2.5,  # model2价格是model1的几倍
            "intelligence_diff": 5.2,  # 智能指数差异
            "speed_ratio": 1.5,  # 速度比
            "elo_diff": 100,  # ELO差异
        }
    }
    """
    ref1 = get_model_reference(model1)
    ref2 = get_model_reference(model2)

    if not ref1 or not ref2:
        return {"error": "Model not found", "model1": ref1, "model2": ref2}

    differences = {}

    # 价格对比
    if ref1.input_price and ref2.input_price:
        differences["input_price_ratio"] = round(ref2.input_price / ref1.input_price, 2)
    if ref1.output_price and ref2.output_price:
        differences["output_price_ratio"] = round(ref2.output_price / ref1.output_price, 2)

    # 智能指数对比
    if ref1.intelligence_index and ref2.intelligence_index:
        differences["intelligence_diff"] = round(ref2.intelligence_index - ref1.intelligence_index, 1)

    # 速度对比
    if ref1.output_tokens_per_second and ref2.output_tokens_per_second:
        differences["speed_ratio"] = round(ref2.output_tokens_per_second / ref1.output_tokens_per_second, 2)

    # ELO对比
    if ref1.arena_elo and ref2.arena_elo:
        differences["elo_diff"] = ref2.arena_elo - ref1.arena_elo

    # 延迟对比
    if ref1.ttft_seconds and ref2.ttft_seconds:
        differences["ttft_ratio"] = round(ref2.ttft_seconds / ref1.ttft_seconds, 2)

    return {
        "model1": ref1.__dict__,
        "model2": ref2.__dict__,
        "differences": differences,
    }


def get_price_comparison(model_name: str, relay_price_per_1m: float = None) -> dict:
    """
    对比官方价格和中转站价格

    参数：
    - model_name: 模型名称
    - relay_price_per_1m: 中转站价格（USD per 1M tokens，可选）

    返回：
    {
        "official_price": {"input": 2.5, "output": 10.0},
        "relay_price": {"input": ..., "output": ...},
        "markup": {"input": 1.2, "output": 1.5},  # 加价倍数
        "is_overpriced": True,
    }
    """
    ref = get_model_reference(model_name)
    if not ref:
        return {"error": "Model not found"}

    result = {
        "model": ref.display_name,
        "official_price": {
            "input": ref.input_price,
            "output": ref.output_price,
        },
    }

    if relay_price_per_1m:
        # 假设中转站价格是统一的（input和output相同）
        markup_input = round(relay_price_per_1m / ref.input_price, 2) if ref.input_price else None
        markup_output = round(relay_price_per_1m / ref.output_price, 2) if ref.output_price else None

        result["relay_price"] = {"input": relay_price_per_1m, "output": relay_price_per_1m}
        result["markup"] = {"input": markup_input, "output": markup_output}
        result["is_overpriced"] = (markup_input and markup_input > 1.5) or (markup_output and markup_output > 1.5)

    return result


def export_to_json(filepath: str = None) -> str:
    """导出所有模型参考数据为JSON"""
    data = {k: v.__dict__ for k, v in MODEL_REFERENCES.items()}
    json_str = json.dumps(data, ensure_ascii=False, indent=2)

    if filepath:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(json_str)

    return json_str


def load_from_json(filepath: str) -> int:
    """
    从JSON文件加载模型参考数据（用于更新数据）

    返回加载的模型数量
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for model_id, model_data in data.items():
        if model_id in MODEL_REFERENCES:
            # 更新现有模型
            for key, value in model_data.items():
                if hasattr(MODEL_REFERENCES[model_id], key):
                    setattr(MODEL_REFERENCES[model_id], key, value)
        else:
            # 添加新模型
            MODEL_REFERENCES[model_id] = ModelReference(**model_data)
        count += 1

    return count


# ─── 数据更新说明 ────────────────────────────────────────────────
# 定期更新数据源：
# 1. Artificial Analysis API: https://artificialanalysis.ai/data-api
#    - 获取最新的价格、性能、智能指数
# 2. LMArena: https://lmarena.ai/leaderboard
#    - 获取最新的ELO评分和排名
# 3. 各模型官方文档
#    - 获取最新的上下文窗口、发布日期
#
# 更新方式：
# - 手动：编辑本文件中的MODEL_REFERENCES字典
# - 自动：从API拉取数据后调用load_from_json()
# - 导出：调用export_to_json()保存当前数据
