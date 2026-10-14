"""포즈 비교 스크립트"""
import json

# 플에파와 키로 DB 로드
with open('c:/Users/rbsgh/plepa/data/sdxl_pose_database.json', 'r', encoding='utf-8') as f:
    plepa_db = json.load(f)

with open('C:/Users/rbsgh/kiro/pose_database.json', 'r', encoding='utf-8') as f:
    kiro_db = json.load(f)

# Phase 1 변경 포즈 목록 (섹션별 분류)
changes = {
    'emotions': {
        '014': '유혹 (가슴유혹에서 변경)',
    },
    'poses': {
        '023': '의심 (도도한팔짱에서 변경)',
        '028': '안고엉덩이애무 (밀착포옹에서 변경)',
        '029': '엎드려유혹 (도기유혹에서 변경)',
        '030': '전라스탠딩 (알몸스탠딩에서 변경)',
        '031': '뒤에서가슴애무 (후방가슴애무에서 변경)',
        '033': '몰래애무 (턱들기에서 변경)',
        '034': '가슴에얼굴묻기 (가슴파묻힘에서 변경)',
        '035': '덮치기 (침대덮침에서 변경)',
        '037': '붓카케 (애프터피크에서 변경)',
    },
    'h_scenes': {
        '040': '덮쳐짐 (상대방덮치기에서 변경)',
        '041': '능동적 역전 (042와 교환)',
        '042': '수동적 역전 (041과 교환)',
        '047': '쓰다듬기 (탄산음료사귀기에서 변경)',
        '052': '누워절정여운 (수평사후에서 변경)',
        '053': '엎드려절정여운 (엎드려사후에서 변경)',
    }
}

print('=' * 80)
print('🔍 플에파 Phase 1 변경사항 vs 키로 현재 상태 비교')
print('=' * 80)

total_diff = 0
total_same = 0

for section, poses in changes.items():
    print(f'\n📂 [{section}] 섹션')
    print('-' * 80)
    
    for code, expected in poses.items():
        plepa_pose = plepa_db.get(section, {}).get(code, {})
        kiro_pose = kiro_db.get(section, {}).get(code, {})
        
        plepa_label = plepa_pose.get('label', '없음')
        kiro_label = kiro_pose.get('label', '없음')
        
        if plepa_label != kiro_label:
            print(f'\n  {code}번: ⚠️ 차이 있음')
            print(f'    키로:   "{kiro_label}"')
            print(f'    플에파: "{plepa_label}" ⬅ 변경필요')
            
            # 프롬프트 길이 비교
            plepa_prompt_len = len(plepa_pose.get('prompt', ''))
            kiro_prompt_len = len(kiro_pose.get('prompt', ''))
            if abs(plepa_prompt_len - kiro_prompt_len) > 50:
                print(f'    프롬프트: {kiro_prompt_len}자 → {plepa_prompt_len}자 (차이 {abs(plepa_prompt_len - kiro_prompt_len)}자)')
            
            total_diff += 1
        else:
            print(f'  {code}번: ✅ 동일 ("{plepa_label}")')
            total_same += 1

print('\n' + '=' * 80)
print(f'📊 요약: 동일 {total_same}개 / 차이 {total_diff}개')
print('=' * 80)
