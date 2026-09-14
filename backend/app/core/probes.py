"""Probe test sets for model fingerprinting.

Probes are carefully crafted inputs that elicit different responses
from different model families. We use three categories:
1. Tokenizer probes - strings that tokenize differently across families
2. Behavioral probes - questions with model-specific distribution patterns
3. Capability probes - tests that differentiate model tiers
"""
from dataclasses import dataclass
from typing import Literal


@dataclass
class Probe:
    """A single probe test."""
    id: str
    category: Literal["tokenizer", "behavioral", "capability"]
    prompt: str
    description: str
    expected_tokens_range: tuple[int, int] | None = None  # for tokenizer probes
    max_tokens: int = 64
    temperature: float = 1.0


# ─── Tokenizer Probes ───────────────────────────────────────────────
# These strings are crafted to produce different token counts
# across GPT (cl100k/o200k), Claude, and Gemini tokenizers.

TOKENIZER_PROBES: list[Probe] = [
    Probe(
        id="tok-digits",
        category="tokenizer",
        prompt="Repeat this string exactly: 123456789012345678901234567890",
        description="Long digit run - GPT tokenizes digits in pairs, Claude differently",
        expected_tokens_range=(15, 35),
    ),
    Probe(
        id="tok-cjk",
        category="tokenizer",
        prompt="Repeat this string exactly: 人工智能强化学习具身智能机器人视觉语言模型",
        description="CJK characters - different tokenizers handle Chinese differently",
        expected_tokens_range=(10, 40),
    ),
    Probe(
        id="tok-emoji",
        category="tokenizer",
        prompt="Repeat this string exactly: 🤖🧠🚀💻🎯🔥✨🌟💡🎨",
        description="Emoji sequence - tokenizers handle emoji very differently",
        expected_tokens_range=(10, 50),
    ),
    Probe(
        id="tok-whitespace",
        category="tokenizer",
        prompt="Repeat this string exactly: a    b    c    d    e    f    g    h",
        description="Multiple spaces - tokenizers handle whitespace runs differently",
        expected_tokens_range=(8, 25),
    ),
    Probe(
        id="tok-code",
        category="tokenizer",
        prompt="Repeat this string exactly: def foo(x): return x*2+1  # test",
        description="Code snippet - code tokenization varies across families",
        expected_tokens_range=(10, 30),
    ),
    Probe(
        id="tok-url",
        category="tokenizer",
        prompt="Repeat this string exactly: https://api.example.com/v1/chat/completions?model=gpt-4",
        description="URL with query params - URL tokenization varies",
        expected_tokens_range=(12, 35),
    ),
    Probe(
        id="tok-mixed-unicode",
        category="tokenizer",
        prompt="Repeat this string exactly: café résumé naïve über 日本語 한국어 العربية",
        description="Mixed accented + CJK + Arabic - unicode handling varies",
        expected_tokens_range=(15, 45),
    ),
    Probe(
        id="tok-repeated-chars",
        category="tokenizer",
        prompt="Repeat this string exactly: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        description="32 repeated 'a' chars - tokenizer compression behavior differs",
        expected_tokens_range=(3, 20),
    ),
]

# ─── Behavioral Probes ──────────────────────────────────────────────
# Questions that elicit model-specific distribution patterns.
# Based on research: different models have measurable biases in
# random number generation, color naming, coin flip outcomes, etc.

BEHAVIORAL_PROBES: list[Probe] = [
    Probe(
        id="beh-random-100",
        category="behavioral",
        prompt="Pick a random number between 1 and 100. Reply with ONLY the number.",
        description="Random number 1-100 - models show different distribution biases",
        max_tokens=8,
    ),
    Probe(
        id="beh-random-color",
        category="behavioral",
        prompt="Name a random color. Reply with ONLY the color name.",
        description="Random color - different models favor different colors",
        max_tokens=8,
    ),
    Probe(
        id="beh-coin-flip",
        category="behavioral",
        prompt="Flip a coin. Reply with ONLY heads or tails.",
        description="Coin flip - models show different heads/tails biases",
        max_tokens=4,
    ),
    Probe(
        id="beh-random-letter",
        category="behavioral",
        prompt="Pick a random letter from A to Z. Reply with ONLY the letter.",
        description="Random letter - letter preference distribution varies",
        max_tokens=4,
    ),
    Probe(
        id="beh-dice-roll",
        category="behavioral",
        prompt="Roll a six-sided die. Reply with ONLY the number 1-6.",
        description="Dice roll - distribution bias varies by model",
        max_tokens=4,
    ),
    Probe(
        id="beh-random-animal",
        category="behavioral",
        prompt="Name a random animal. Reply with ONLY the animal name.",
        description="Random animal - semantic preference varies",
        max_tokens=8,
    ),
    Probe(
        id="beh-random-day",
        category="behavioral",
        prompt="Pick a random day of the week. Reply with ONLY the day name.",
        description="Random day - day preference varies",
        max_tokens=8,
    ),
    Probe(
        id="beh-number-1-10",
        category="behavioral",
        prompt="Pick a random number between 1 and 10. Reply with ONLY the number.",
        description="Random number 1-10 - small range shows clearer biases",
        max_tokens=4,
    ),
    # ─── Chinese Behavioral Probes (文化偏好差异更大，区分度更高) ───
    Probe(
        id="beh-zh-number",
        category="behavioral",
        prompt="从一到十中选一个随机中文数字。只回复这个中文数字。",
        description="Chinese number 1-10 - cultural preference (8/6/9 lucky numbers) creates strong bias",
        max_tokens=4,
    ),
    Probe(
        id="beh-zh-color",
        category="behavioral",
        prompt="从红、橙、黄、绿、青、蓝、紫中选一个随机颜色。只回复这个颜色名称。",
        description="Chinese color - red/yellow cultural preference differs from English models",
        max_tokens=4,
    ),
    Probe(
        id="beh-zh-festival",
        category="behavioral",
        prompt="从春节、元宵、清明、端午、中秋、重阳中选一个随机中国传统节日。只回复节日名称。",
        description="Chinese festival - Spring Festival dominance creates extreme bias",
        max_tokens=8,
    ),
    Probe(
        id="beh-zh-surname",
        category="behavioral",
        prompt="从赵、钱、孙、李、周、吴、郑、王中选一个随机中文姓氏。只回复这个姓氏。",
        description="Chinese surname - Wang/Li dominance in training data creates strong bias",
        max_tokens=4,
    ),
    Probe(
        id="beh-zh-city",
        category="behavioral",
        prompt="从北京、上海、广州、深圳、杭州、成都中选一个随机中国城市。只回复城市名称。",
        description="Chinese city - Beijing/Shanghai dominance creates strong bias",
        max_tokens=8,
    ),
    Probe(
        id="beh-zh-food",
        category="behavioral",
        prompt="从麻婆豆腐、宫保鸡丁、红烧肉、糖醋排骨、鱼香肉丝中选一个随机中国菜。只回复菜名。",
        description="Chinese food - cultural familiarity creates distinct distribution patterns",
        max_tokens=8,
    ),
]

# ─── Capability Probes ───────────────────────────────────────────────
# Simple tests that differentiate model tiers (high vs mid vs low).
# These are not meant to be comprehensive benchmarks, just quick
# indicators that a claimed high-tier model might be downgraded.

CAPABILITY_PROBES: list[Probe] = [
    Probe(
        id="cap-simple-math",
        category="capability",
        prompt="What is 17 * 23? Reply with ONLY the number.",
        description="Simple multiplication - low-tier models may fail",
        max_tokens=8,
        temperature=0,
    ),
    Probe(
        id="cap-logic",
        category="capability",
        prompt="If all cats are animals and some animals are black, can we conclude some cats are black? Answer yes or no only.",
        description="Basic logic - tests reasoning capability",
        max_tokens=4,
        temperature=0,
    ),
    Probe(
        id="cap-code-syntax",
        category="capability",
        prompt="Write a Python one-liner that returns the sum of even numbers in a list called nums. Reply with ONLY the code.",
        description="Code generation - tests coding capability",
        max_tokens=64,
        temperature=0,
    ),
    Probe(
        id="cap-following-instructions",
        category="capability",
        prompt="Count from 1 to 5, but skip 3. Reply with ONLY the numbers separated by commas.",
        description="Instruction following - tests if model follows complex instructions",
        max_tokens=16,
        temperature=0,
    ),
    # ─── Advanced Capability Probes ────────────────────────────────
    # These probes are designed to differentiate model tiers more clearly.
    Probe(
        id="cap-knowledge-cutoff",
        category="capability",
        prompt="Who won the 2024 US Presidential Election? Reply with ONLY the person's name.",
        description="Knowledge cutoff test - models trained before 2024 may not know",
        max_tokens=16,
        temperature=0,
    ),
    Probe(
        id="cap-reasoning-chain",
        category="capability",
        prompt="A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost? Reply with ONLY the number of cents.",
        description="Cognitive reflection test - gpt-3.5 often says 10 cents, gpt-4 says 5 cents",
        max_tokens=8,
        temperature=0,
    ),
    Probe(
        id="cap-code-bug-fix",
        category="capability",
        prompt="Fix the bug in this Python code: def factorial(n): return n * factorial(n-1). Reply with ONLY the corrected function.",
        description="Bug fixing - tests code understanding and debugging",
        max_tokens=64,
        temperature=0,
    ),
    Probe(
        id="cap-multilingual",
        category="capability",
        prompt="Translate 'Hello, how are you?' to Japanese, Korean, and Arabic. Reply with ONLY the translations separated by commas.",
        description="Multilingual capability - low-tier models may struggle with Arabic",
        max_tokens=64,
        temperature=0,
    ),
    Probe(
        id="cap-context-length",
        category="capability",
        prompt="Repeat this exact sequence back to me: alpha-bravo-charlie-delta-echo-foxtrot-golf-hotel-india-juliet. Reply with ONLY the sequence.",
        description="Context retention - tests if model can retain and reproduce long sequences",
        max_tokens=64,
        temperature=0,
    ),
    Probe(
        id="cap-math-word-problem",
        category="capability",
        prompt="If a train travels 60 mph for 2.5 hours, then 80 mph for 1.5 hours, what is the average speed for the entire trip? Reply with ONLY the number.",
        description="Multi-step math word problem - tests quantitative reasoning",
        max_tokens=8,
        temperature=0,
    ),
]


def get_all_probes() -> list[Probe]:
    """Get all probes."""
    return TOKENIZER_PROBES + BEHAVIORAL_PROBES + CAPABILITY_PROBES


def get_probes_by_category(category: str) -> list[Probe]:
    """Get probes by category."""
    mapping = {
        "tokenizer": TOKENIZER_PROBES,
        "behavioral": BEHAVIORAL_PROBES,
        "capability": CAPABILITY_PROBES,
    }
    return mapping.get(category, [])
