#!/usr/bin/env python3
import json

with open(r'c:\Users\rbsgh\plepa\data\sdxl_pose_database.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("N01-N45 Full Database Listing for Manual Visual Validation:")
print("=" * 100)

n01_45 = sorted([k for k in data['adult'].keys() if k.startswith('N') and int(k[1:]) <= 45])

for n_id in n01_45:
    info = data['adult'][n_id]
    label = info.get('label', 'N/A')
    desc = info.get('description', '')[:50]
    prompt = info.get('prompt', '')[:70]
    
    print(f"\n{n_id}: {label}")
    print(f"  Desc: {desc}...")
    print(f"  Prompt: {prompt}...")

print(f"\n{'='*100}\nTotal: {len(n01_45)} poses to validate")
