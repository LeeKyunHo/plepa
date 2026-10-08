import json

with open('sdxl_pose_database.json', encoding='utf-8') as f:
    raw = json.load(f)

target_codes = ['037', '040', '036', '039', '038']

for section_name, section_data in raw.items():
    if section_name == '_schema':
        continue
    for code, data in section_data.items():
        if code in target_codes:
            label = data.get('label', '')
            pos = data.get('positive', data.get('prompt', ''))
            print(f"[{code}] {label} ({section_name})")
            print(f"  {pos[:200]}")
            print()
