import json

with open(r'c:\Users\rbsgh\plepa\data\sdxl_pose_database.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    
print('N30 (파일드라이버):')
print(f"  Label: {data['adult']['N30']['label']}")
print(f"  Prompt: {data['adult']['N30']['prompt'][:150]}...")
print()
print('N34 (수유대딸):')
print(f"  Label: {data['adult']['N34']['label']}")
print(f"  Prompt: {data['adult']['N34']['prompt'][:150]}...")
