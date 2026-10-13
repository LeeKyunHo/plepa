#!/usr/bin/env python3
import json
import os
from pathlib import Path

with open(r'c:\Users\rbsgh\plepa\data\sdxl_pose_database.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Get all reference images for N01-N45
ref_dir = Path(r'c:\Users\rbsgh\plepa\projects\spy\assets\chl')
n01_45 = sorted([k for k in data['adult'].keys() if k.startswith('N') and int(k[1:]) <= 45])

print("N01-N45 Validation Check:")
print("=" * 80)

for n_id in n01_45:
    info = data['adult'][n_id]
    label = info.get('label', 'N/A')
    
    # Look for matching image files
    pattern = f"chl_{n_id}_*"
    matching = list(ref_dir.glob(pattern))
    
    if not matching:
        print(f"{n_id}: {label:20} | NO_REF - Missing reference image")
    else:
        files = [m.name for m in matching]
        print(f"{n_id}: {label:20} | {len(matching)} image(s): {files[0]}")

print("\n" + "=" * 80)
print(f"Total: {len(n01_45)} poses")
print(f"Poses with missing reference images need NO_REF mark")
