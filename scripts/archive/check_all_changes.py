"""모든 Phase 1 변경사항 확인"""
import json

# 플에파와 키로 DB 로드
with open('c:/Users/rbsgh/plepa/data/sdxl_pose_database.json', 'r', encoding='utf-8') as f:
    plepa_db = json.load(f)

with open('C:/Users/rbsgh/kiro/pose_database.json', 'r', encoding='utf-8') as f:
    kiro_db = json.load(f)

# 개발일지에 기록된 모든 변경사항
all_changes = {
    'emotions': {
        '014': '유혹',
    },
    'poses': {
        '023': '의심',
        '028': '안고엉덩이애무',
        '029': '엎드려유혹',
        '030': '전라스탠딩',
        '031': '뒤에서가슴애무',
        '033': '몰래애무',
        '034': '가슴에얼굴묻기',
        '035': '덮치기',
        '037': '붓카케',
        '040': '덮쳐짐',
        '041': '능동',  # 키워드 포함 확인
        '042': '수동',  # 키워드 포함 확인
        '047': '쓰다듬기',
    },
    'h_scenes': {
        '052': '누워절정여운',
        '053': '엎드려절정여운',
        '065': '남근핥기',
        '067': '립잡대딸',
    }
}

print('=' * 80)
print('🔍 Phase 1 전체 변경사항 확인')
print('=' * 80)

total_ok = 0
total_diff = 0

for section, poses in all_changes.items():
    print(f'\n📂 [{section}] 섹션')
    print('-' * 80)
    
    for code, expected in poses.items():
        plepa_pose = plepa_db.get(section, {}).get(code, {})
        kiro_pose = kiro_db.get(section, {}).get(code, {})
        
        plepa_label = plepa_pose.get('label', '없음')
        kiro_label = kiro_pose.get('label', '없음')
        
        # 포즈가 존재하는지 확인
        if plepa_label == '없음':
            print(f'\n  {code}번: ❌ 플에파에 포즈 없음!')
            total_diff += 1
            continue
        
        # 예상 라벨이 포함되어 있는지 확인
        label_match = (expected in plepa_label) or (plepa_label == expected)
        sync_match = (plepa_label == kiro_label)
        
        if label_match and sync_match:
            print(f'  {code}번: ✅ OK - "{plepa_label}"')
            total_ok += 1
        else:
            print(f'\n  {code}번: ⚠️ 문제 발견')
            print(f'    예상: "{expected}"')
            print(f'    플에파: "{plepa_label}"', '✅' if label_match else '❌')
            print(f'    키로: "{kiro_label}"', '✅' if sync_match else '❌')
            
            if not label_match:
                print(f'    → 플에파에 "{expected}" 키워드 없음')
            if not sync_match:
                print(f'    → 키로 동기화 필요')
            
            total_diff += 1

print('\n' + '=' * 80)
print(f'📊 최종 결과: OK {total_ok}개 / 문제 {total_diff}개')
print('=' * 80)
