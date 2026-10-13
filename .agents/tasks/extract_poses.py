#!/usr/bin/env python3
import json
import sys

with open(r'c:\Users\rbsgh\plepa\data\sdxl_pose_database.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Get all N-series pose IDs (N01-N74)
adult_keys = sorted([k for k in data['adult'].keys() if k.startswith('N')])
print(f"Total N-series poses: {len(adult_keys)}")

n01_45 = [x for x in adult_keys if int(x[1:]) <= 45]
print(f"\nN01-N45 poses in database ({len(n01_45)} total):")
for k in n01_45:
    info = data['adult'][k]
    label = info.get('label', 'N/A')
    prompt_preview = info.get('prompt', '')[:60]
    print(f"  {k}: {label} | prompt: {prompt_preview}...")

print(f"\nChecking for N26-N29:")
for k in ['N26', 'N27', 'N28', 'N29']:
    if k in data['adult']:
        info = data['adult'][k]
        print(f"  {k}: {info.get('label', 'N/A')}")
