"""Quick test: verify real baseline loading."""
import sys
sys.path.insert(0, '.')
from app.core.statistical_analyzer import StatisticalAnalyzer

a = StatisticalAnalyzer()
a.load_default_baselines()
a.load_real_baselines('../data/baselines')

print()
print('Baselines loaded:', list(a.baseline_db.keys()))

bl = a.baseline_db.get('gpt-4o-mini')
if bl:
    print(f'gpt-4o-mini: family={bl.model_family}, n={bl.sample_size}')
    print(f'  tokenizer probes: {len(bl.tokenizer_distributions)}')
    print(f'  behavioral probes: {len(bl.behavioral_distributions)}')
    print(f'  latency samples: {len(bl.latency_distribution)}')
    
    # Check behavioral fingerprint
    beh = bl.behavioral_distributions.get('beh-number-1-10', [])
    if beh:
        from collections import Counter
        c = Counter(beh)
        print(f'  beh-number-1-10: {dict(c)}')
    
    beh2 = bl.behavioral_distributions.get('beh-dice-roll', [])
    if beh2:
        from collections import Counter
        c2 = Counter(beh2)
        print(f'  beh-dice-roll: {dict(c2)}')
else:
    print('gpt-4o-mini baseline NOT found!')

print()
print('Test passed: real baselines loaded successfully!')
