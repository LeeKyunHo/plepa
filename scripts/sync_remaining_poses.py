"""나머지 Phase 1 포즈를 키로에 동기화"""
import json
from datetime import datetime

# 플에파와 키로 DB 로드
with open('c:/Users/rbsgh/plepa/data/sdxl_pose_database.json', 'r', encoding='utf-8') as f:
    plepa_db = json.load(f)

with open('C:/Users/rbsgh/kiro/pose_database.json', 'r', encoding='utf-8') as f:
    kiro_db = json.load(f)

# 동기화할 포즈 목록
sync_list = [
    ('emotions', '014'),
    ('poses', '023'),
    ('poses', '028'),
    ('poses', '029'),
    ('poses', '030'),
    ('poses', '031'),
    ('poses', '033'),
    ('poses', '034'),
    ('poses', '035'),
]

print('=' * 80)
print('🔄 플에파 → 키로 포즈 동기화')
print('=' * 80)

synced = 0

for section, code in sync_list:
    if code in plepa_db.get(section, {}) and code in kiro_db.get(section, {}):
        plepa_pose = plepa_db[section][code]
        old_label = kiro_db[section][code].get('label', '없음')
        new_label = plepa_pose.get('label', '없음')
        
        # 동기화
        kiro_db[section][code] = plepa_pose.copy()
        
        print(f'✅ {section}/{code}: "{old_label}" → "{new_label}"')
        synced += 1
    else:
        print(f'⚠️ {section}/{code}: 건너뜀 (포즈 없음)')

# 저장
with open('C:/Users/rbsgh/kiro/pose_database.json', 'w', encoding='utf-8') as f:
    json.dump(kiro_db, f, ensure_ascii=False, indent=2)

print('=' * 80)
print(f'✅ 완료! {synced}개 포즈 동기화됨')
print('=' * 80)
