#!/usr/bin/env python
"""Test mock generation with campus roster."""

import sys
sys.path.insert(0, r'c:\Users\rbsgh\plepa')

from plepa_engine.services.generation_service import GenerationService, GenerationParams
from plepa_engine.services.config_service import ConfigService

# Create a mock generation test
config_service = ConfigService()
gen_service = GenerationService(config_service)

# Test campus generation with mock
print('=== TEST: Campus Generation (Mock Mode) ===')
params = GenerationParams(
    engine='sdxl',
    chars='yur,aya',
    poses='00,01,200,201',
    roster='campus',
    mock=True,
    dry_run=False,
    quiet=False
)

try:
    results = gen_service.run_batch(params)
    print(f'\n✅ Generated {len(results)} mock images')
    print('\nFirst 5 results:')
    for i, r in enumerate(results[:5]):
        print(f'  {i+1}. Pose {r.target.code}: {r.target.output_filename} (success={r.success})')
    
    # Verify campus poses are present
    pose_codes = set(r.target.code for r in results)
    print(f'\nGenerated pose codes: {sorted(pose_codes)}')
    has_campus = all(str(i) in pose_codes for i in [200, 201])
    print(f'Has campus poses (200, 201): {has_campus}')
    
except Exception as e:
    import traceback
    print(f'❌ Error: {e}')
    traceback.print_exc()
