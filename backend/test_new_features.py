"""Test all new module imports and functionality."""
import sys
sys.path.insert(0, '.')

print('=== Testing Module Imports ===')
from app.core.detect import detect_base_url, suggest_relays, fetch_models, KNOWN_RELAYS
print('✓ detect module imported')
print(f'  Known relays: {len(KNOWN_RELAYS)}')

from app.utils.ranking_aggregator import aggregate_audits, AuditEntry, generate_ranking_json, get_top_contributors
print('✓ ranking_aggregator module imported')

from app.utils.badge_generator import generate_contributor_badge, generate_stat_badge, generate_profile_readme_section
print('✓ badge_generator module imported')

from app.models import AuditMode, AuditRequest
print('✓ models module with AuditMode imported')

# Test detect functionality
print('\n=== Testing Detect Functionality ===')
result = detect_base_url('sk-test123')
print(f'detect_base_url(sk-test123): {result}')

suggestions = suggest_relays('sk-test123')
print(f'suggest_relays(sk-test123): {len(suggestions)} suggestions')
for s in suggestions[:3]:
    print(f'  - {s["name"]}: {s["base_url"]} ({s["confidence"]*100:.0f}%)')

# Test ranking aggregator
print('\n=== Testing Ranking Aggregator ===')
entries = [
    AuditEntry(relay='wolfai.top', model='gpt-4o-mini', base_url='https://wolfai.top/v1',
               overall_score=55.7, trust_level='critical', token_inflation_pct=76.1,
               avg_latency_ms=1856, contributor='@dafahaha', tested_at='2026-09-14'),
    AuditEntry(relay='wolfai.top', model='gpt-4o', base_url='https://wolfai.top/v1',
               overall_score=57.5, trust_level='critical', token_inflation_pct=76.1,
               avg_latency_ms=1161, contributor='@dafahaha', tested_at='2026-09-14'),
]
aggregated = aggregate_audits(entries)
ranking = generate_ranking_json(aggregated)
print(f'Aggregated: {len(aggregated)} entries')
print(f'Total audits: {ranking["total_audits"]}')
print(f'Total relays: {ranking["total_relays"]}')

contributors = get_top_contributors(entries)
print(f'Top contributors: {len(contributors)}')
for c in contributors:
    print(f'  #{c["rank"]} {c["contributor"]}: {c["audit_count"]} audits')

# Test badge generator
print('\n=== Testing Badge Generator ===')
badge = generate_contributor_badge('dafahaha', 5, 2)
print(f'Contributor badge generated: {len(badge)} chars')
stat = generate_stat_badge('Audits', '12', '#16a34a')
print(f'Stat badge generated: {len(stat)} chars')
readme = generate_profile_readme_section('dafahaha', 5, 2, 1, 56.6)
print(f'Profile README section generated: {len(readme)} chars')

print('\n=== All Tests Passed! ===')
