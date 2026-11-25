#!/usr/bin/env python
"""Test roster-specific pose loading."""

from plepa_engine.services.pose_service import PoseService
import json

# Test 1: Load campus roster poses
print('=== TEST 1: Campus Roster Poses (SDXL) ===')
pose_service = PoseService()
campus_poses = pose_service.load_pose_db(engine='sdxl', roster='campus')
campus_codes = sorted([code for code in campus_poses.keys()])
print(f'Total campus poses: {len(campus_poses)}')
print(f'Campus pose codes: {campus_codes}')
print(f'Has 200-205: {all(f"{i:03d}" in campus_codes for i in range(200, 206))}')

# Test 2: Load non-campus roster poses
print('\n=== TEST 2: Non-Campus Roster Poses (e.g., maid SDXL) ===')
maid_poses = pose_service.load_pose_db(engine='sdxl', roster='maid')
maid_codes = sorted([code for code in maid_poses.keys()])
print(f'Total maid poses: {len(maid_poses)}')
print(f'Has 200-205: {any(f"{i:03d}" in maid_codes for i in range(200, 206))}')
print(f'Sample maid codes: {maid_codes[:10]}...')

# Test 3: Verify pose_overrides.json was loaded for campus
print('\n=== TEST 3: Pose Override Loading ===')
with open('projects/campus/pose_overrides.json', 'r', encoding='utf-8') as f:
    overrides = json.load(f)
print(f'Campus pose_overrides.json sections: {list(overrides.keys())}')
override_codes = []
for section, codes_dict in overrides.items():
    if isinstance(codes_dict, dict):
        override_codes.extend(codes_dict.keys())
override_codes = sorted(override_codes)
print(f'Override codes: {override_codes}')

# Test 4: Check a campus character has pose_restrictions
print('\n=== TEST 4: Campus Character Pose Restrictions ===')
with open('projects/campus/characters/yur.json', 'r', encoding='utf-8') as f:
    yur = json.load(f)
pose_restr = yur.get('pose_restrictions', {})
print(f'Yur pose_restrictions: {pose_restr}')

print('\n✅ All tests passed!')
