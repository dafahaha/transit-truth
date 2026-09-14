"""Randomized probe generator.

Generates randomized probe prompts for each audit run to prevent
relay services from detecting and defending against fixed probe patterns.

Key principle: preserve the *characteristic* of each probe (e.g.,
"long digit run" for tokenizer probes, "random number question" for
behavioral probes) while randomizing the *specific content*.

This makes it impossible for a relay to whitelist specific probe strings
while still allowing us to measure the same underlying characteristics.
"""
import random
import string
from dataclasses import dataclass
from typing import Optional

from .probes import Probe


# Character pools for randomization
CJK_CHARS = "的一是不了人我在有他这为之大来以个中上们到说国和地也子时道出而要于就下得可你年生自那后能对着事其景"
EMOJIS = ["🤖", "🧠", "🚀", "💻", "🎯", "🔥", "✨", "🌟", "💡", "🎨", "🐱", "🐶", "🌍", "⚡", "🎵", "📚", "🔧", "🎮", "🌸", "🍕"]
COLORS = ["red", "blue", "green", "yellow", "purple", "orange", "pink", "brown", "black", "white", "gray", "cyan", "magenta", "lime", "teal"]
ANIMALS = ["cat", "dog", "elephant", "tiger", "lion", "bear", "wolf", "fox", "rabbit", "mouse", "bird", "fish", "snake", "monkey", "horse", "cow", "pig", "sheep", "chicken", "duck"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
LETTERS = list(string.ascii_uppercase)


@dataclass
class RandomizedProbe(Probe):
    """A probe with randomized content."""
    original_id: str = ""
    random_seed: int = 0


class ProbeRandomizer:
    """Generates randomized versions of probes."""

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.seed = seed or random.randint(0, 2**31 - 1)

    def randomize_all(self, probes: list[Probe]) -> list[RandomizedProbe]:
        """Randomize a list of probes."""
        return [self._randomize_probe(p) for p in probes]

    def _randomize_probe(self, probe: Probe) -> RandomizedProbe:
        """Randomize a single probe based on its category and ID."""
        if probe.category == "tokenizer":
            prompt = self._randomize_tokenizer_probe(probe.id)
        elif probe.category == "behavioral":
            prompt = self._randomize_behavioral_probe(probe.id)
        elif probe.category == "capability":
            prompt, expected = self._randomize_capability_probe(probe.id)
        else:
            prompt = probe.prompt

        return RandomizedProbe(
            id=f"{probe.id}_r{self.seed}",
            original_id=probe.id,
            category=probe.category,
            prompt=prompt,
            description=probe.description,
            expected_tokens_range=probe.expected_tokens_range,
            max_tokens=probe.max_tokens,
            temperature=probe.temperature,
            random_seed=self.seed,
        )

    # ─── Tokenizer Probe Randomization ────────────────────────────────
    # Preserve character type, randomize specific content

    def _randomize_tokenizer_probe(self, probe_id: str) -> str:
        if probe_id == "tok-digits":
            digits = "".join(self.rng.choice(string.digits) for _ in range(30))
            return f"Repeat this string exactly: {digits}"
        elif probe_id == "tok-cjk":
            cjk = "".join(self.rng.choice(CJK_CHARS) for _ in range(20))
            return f"Repeat this string exactly: {cjk}"
        elif probe_id == "tok-emoji":
            emojis = "".join(self.rng.sample(EMOJIS, min(10, len(EMOJIS))))
            return f"Repeat this string exactly: {emojis}"
        elif probe_id == "tok-whitespace":
            chars = self.rng.sample(string.ascii_lowercase, 8)
            return f"Repeat this string exactly: {'    '.join(chars)}"
        elif probe_id == "tok-code":
            var_name = "".join(self.rng.choice(string.ascii_lowercase) for _ in range(self.rng.randint(3, 8)))
            num1 = self.rng.randint(1, 10)
            num2 = self.rng.randint(1, 10)
            return f"Repeat this string exactly: def {var_name}(x): return x*{num1}+{num2}  # test"
        elif probe_id == "tok-url":
            domain = "".join(self.rng.choice(string.ascii_lowercase) for _ in range(self.rng.randint(5, 12)))
            path = "".join(self.rng.choice(string.ascii_lowercase) for _ in range(self.rng.randint(3, 10)))
            model = f"model-{self.rng.randint(1, 9)}.{self.rng.choice(['0', '1', '5'])}"
            return f"Repeat this string exactly: https://api.{domain}.com/v1/{path}/completions?model={model}"
        elif probe_id == "tok-mixed-unicode":
            accented = self.rng.sample(["café", "résumé", "naïve", "über", "façade", "jalapeño", "señor", "piñata"], 3)
            cjk = "".join(self.rng.choice(CJK_CHARS) for _ in range(4))
            korean = "".join(self.rng.choice("가나다라마바사아자차카타파하") for _ in range(3))
            arabic = "".join(self.rng.choice("مرحباالسلامعليكم") for _ in range(4))
            return f"Repeat this string exactly: {' '.join(accented)} {cjk} {korean} {arabic}"
        elif probe_id == "tok-repeated-chars":
            char = self.rng.choice(string.ascii_lowercase)
            count = self.rng.randint(24, 40)
            return f"Repeat this string exactly: {char * count}"
        else:
            return f"Repeat this string: {self.rng.randint(1000, 9999)}"

    # ─── Behavioral Probe Randomization ───────────────────────────────
    # Preserve question type, randomize wording and parameters

    def _randomize_behavioral_probe(self, probe_id: str) -> str:
        templates = {
            "beh-random-100": [
                "Pick a random number between 1 and 100. Reply with ONLY the number.",
                "Choose any integer from 1 to 100 at random. Output just the number.",
                "Generate a random whole number in the range [1, 100]. Reply with ONLY the number.",
                "Select a random number between one and one hundred. Output only the number.",
            ],
            "beh-random-color": [
                "Name a random color. Reply with ONLY the color name.",
                "Pick any color at random. Output just the color name.",
                "Choose a random color from the spectrum. Reply with ONLY the name.",
                "Think of a random color. Output only its name.",
            ],
            "beh-coin-flip": [
                "Flip a coin. Reply with ONLY heads or tails.",
                "Toss a fair coin. Output just heads or tails.",
                "Imagine flipping a coin. Reply with ONLY the result (heads or tails).",
                "Randomly choose heads or tails. Output only your choice.",
            ],
            "beh-random-letter": [
                "Pick a random letter from A to Z. Reply with ONLY the letter.",
                "Choose any letter of the alphabet at random. Output just the letter.",
                "Select a random uppercase letter from A through Z. Reply with ONLY it.",
                "Think of a random letter in the English alphabet. Output only it.",
            ],
            "beh-dice-roll": [
                "Roll a six-sided die. Reply with ONLY the number 1-6.",
                "Throw a standard die. Output just the result (1-6).",
                "Imagine rolling a D6. Reply with ONLY the number.",
                "Randomly pick a number from 1 to 6 as if rolling a die. Output only it.",
            ],
            "beh-random-animal": [
                "Name a random animal. Reply with ONLY the animal name.",
                "Pick any animal at random. Output just its name.",
                "Choose a random creature. Reply with ONLY the name.",
                "Think of a random animal. Output only its name.",
            ],
            "beh-random-day": [
                "Pick a random day of the week. Reply with ONLY the day name.",
                "Choose any day from Monday to Sunday at random. Output just it.",
                "Select a random day of the week. Reply with ONLY the name.",
                "Think of a random day. Output only its name.",
            ],
            "beh-number-1-10": [
                "Pick a random number between 1 and 10. Reply with ONLY the number.",
                "Choose any integer from 1 to 10 at random. Output just the number.",
                "Generate a random whole number in [1, 10]. Reply with ONLY it.",
                "Select a random number from one to ten. Output only it.",
            ],
        }
        options = templates.get(probe_id, ["Reply with a random answer."])
        return self.rng.choice(options)

    # ─── Capability Probe Randomization ───────────────────────────────
    # Preserve problem type, randomize specific numbers/content

    def _randomize_capability_probe(self, probe_id: str) -> tuple[str, set]:
        if probe_id == "cap-simple-math":
            a = self.rng.randint(10, 99)
            b = self.rng.randint(10, 99)
            return f"What is {a} * {b}? Reply with ONLY the number.", {str(a * b)}
        elif probe_id == "cap-logic":
            # Keep the classic logic problem, randomize wording
            templates = [
                "If all cats are animals and some animals are black, can we conclude some cats are black? Answer yes or no only.",
                "All roses are flowers. Some flowers fade quickly. Can we conclude some roses fade quickly? Answer yes or no only.",
                "All dogs are mammals. Some mammals are large. Can we conclude some dogs are large? Answer yes or no only.",
            ]
            return self.rng.choice(templates), {"no"}
        elif probe_id == "cap-code-syntax":
            func_name = "".join(self.rng.choice(string.ascii_lowercase) for _ in range(self.rng.randint(3, 6)))
            return (f"Write a Python one-liner that returns the sum of even numbers in a list called {func_name}. "
                    f"Reply with ONLY the code.", set())
        elif probe_id == "cap-following-instructions":
            start = self.rng.randint(1, 3)
            end = self.rng.randint(6, 9)
            skip = self.rng.randint(start + 1, end - 1)
            expected = ",".join(str(i) for i in range(start, end + 1) if i != skip)
            return (f"Count from {start} to {end}, but skip {skip}. "
                    f"Reply with ONLY the numbers separated by commas.",
                    {expected, expected.replace(",", ", ")})
        else:
            return "What is 2 + 2? Reply with ONLY the number.", {"4"}


def generate_randomized_probes(seed: Optional[int] = None) -> tuple[list[RandomizedProbe], int]:
    """Generate a full set of randomized probes.

    Returns:
        Tuple of (randomized_probes, seed_used)
    """
    from .probes import TOKENIZER_PROBES, BEHAVIORAL_PROBES, CAPABILITY_PROBES

    randomizer = ProbeRandomizer(seed)
    all_probes = TOKENIZER_PROBES + BEHAVIORAL_PROBES + CAPABILITY_PROBES
    randomized = randomizer.randomize_all(all_probes)
    return randomized, randomizer.seed
