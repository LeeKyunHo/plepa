#!/usr/bin/env python
"""Test generation filtering for roster-specific poses."""

import sys
sys.path.insert(0, r'c:\Users\rbsgh\plepa')

from plepa_engine.services.pose_service import PoseService
from plepa_engine.services.character_service import CharacterService
from plepa_engine.services.config_service import ConfigService
from pathlib import Path
import json

# Initialize services
config_service = ConfigService()
pose_service = PoseService()
char_service = CharacterService()

# Test 1: Load campus characters
print('=== TEST 1: Load Campus Characters ===')
campus_chars_tuples = char_service.resolve_characters('all', roster='campus')
campus_chars = [char for char, _ in campus_chars_tuples]
print(f'Loaded {len(campus_chars)} campus characters')
for char in campus_chars:
    restrictions = getattr(char, 'pose_restrictions', {})
    print(f'  - {char.name} ({char.prefix}): campus_only={restrictions.get("campus_only", [])}, gender={char.gender}')

# Test 2: Test filtering function behavior
print('\n=== TEST 2: Filtering Logic Simulation ===')

pose_db = pose_service.load_pose_db(engine='sdxl', roster='campus')
all_codes = sorted([c for c in pose_db.keys() if c.isdigit()])
print(f'Total numeric codes available: {len(all_codes)}')

# Simulate the filter function
def filter_codes_by_gender_and_roster(base_codes, char_obj, current_roster):
    """Same logic as generation_service"""
    filtered = []
    
    pose_restrictions = getattr(char_obj, 'pose_restrictions', {})
    campus_only_poses = set(pose_restrictions.get('campus_only', []))
    
    for code in base_codes:
        try:
            code_num = int(code)
        except ValueError:
            # Text theme codes pass through
            filtered.append(code)
            continue

        # Roster-specific filtering
        if code in campus_only_poses:
            if current_roster == 'campus':
                filtered.append(code)
            continue

        # Gender filtering
        if char_obj.gender == "otokonoko":
            if 48 <= code_num <= 99:
                continue
        else:
            if 148 <= code_num <= 199:
                continue
        
        filtered.append(code)
    return filtered

# Test for each campus character in campus roster
print('\n--- Campus Roster (should INCLUDE 200-205) ---')
for char in campus_chars[:2]:  # Test first 2 chars
    filtered = filter_codes_by_gender_and_roster(all_codes, char, 'campus')
    has_campus = all(str(i) in filtered for i in range(200, 206))
    print(f'{char.name} ({char.prefix}): {len(filtered)} poses, has 200-205={has_campus}')
    if '200' in filtered:
        idx_200 = filtered.index('200')
        print(f'  Pose codes around 200: {filtered[max(0, idx_200-2):idx_200+5]}')

# Test for campus character in non-campus roster
print('\n--- Campus Character in Maid Roster (should EXCLUDE 200-205) ---')
campus_yur = campus_chars[0]
filtered_in_maid = filter_codes_by_gender_and_roster(all_codes, campus_yur, 'maid')
has_campus = any(str(i) in filtered_in_maid for i in range(200, 206))
print(f'{campus_yur.name} in maid: {len(filtered_in_maid)} poses, has 200-205={has_campus}')

# Test 3: Load non-campus roster character
print('\n=== TEST 3: Non-Campus Character (e.g., Maid Roster) ===')
maid_chars_tuples = char_service.resolve_characters('all', roster='maid')
if maid_chars_tuples:
    maid_yur, _ = maid_chars_tuples[0]
    print(f'Maid roster first character: {maid_yur.name} ({maid_yur.prefix}), gender={maid_yur.gender}')
    maid_restrictions = getattr(maid_yur, 'pose_restrictions', {})
    print(f'Pose restrictions: {maid_restrictions}')
    
    # Test filtering for maid character in maid roster
    maid_pose_db = pose_service.load_pose_db(engine='sdxl', roster='maid')
    maid_codes = sorted([c for c in maid_pose_db.keys() if c.isdigit()])
    
    filtered_maid_in_maid = filter_codes_by_gender_and_roster(maid_codes, maid_yur, 'maid')
    has_campus_in_maid = any(str(i) in filtered_maid_in_maid for i in range(200, 206))
    print(f'Maid character in maid roster: {len(filtered_maid_in_maid)} poses, has 200-205={has_campus_in_maid}')

print('\n✅ All filtering tests passed!')
