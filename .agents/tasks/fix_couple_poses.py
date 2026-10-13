"""
커플 씬 포즈에 1girl, 1boy 태그를 자동으로 추가하는 스크립트
"""
import json
from pathlib import Path

# 파트너가 포함된 씬을 감지하는 키워드 리스트
PARTNER_KEYWORDS = [
    'partner', 'male', 'faceless male', 'boy', '1boy',
    'missionary', 'doggystyle', 'cowgirl', 'sex', 'paizuri',
    'fellatio', 'handjob', 'footjob', 'titfuck', 'blowjob',
    'deepthroat', 'anal', 'vaginal', 'penetration', 'intercourse',
    'straddling', 'spooning', 'mating press', 'piledriver',
    'standing sex', 'shower sex', 'clothed sex', 'suspended sex',
    'nursing handjob', 'sumata', 'thigh sex', 'irrumatio',
    'hug from behind', 'back hug', 'princess carry', 'groping',
    'breast grab', 'ass grab'
]

# Solo 씬 키워드 (이런 게 있으면 파트너 씬이 아님)
SOLO_KEYWORDS = ['solo', 'solo focus', 'masturbation']

def needs_couple_tag(prompt: str, description: str) -> bool:
    """프롬프트와 설명을 보고 커플 태그가 필요한지 판단"""
    prompt_lower = prompt.lower()
    desc_lower = description.lower()
    
    # 이미 1girl, 1boy 태그가 있으면 불필요
    if '1girl' in prompt_lower and '1boy' in prompt_lower:
        return False
    
    # Solo 씬이면 불필요
    for solo_kw in SOLO_KEYWORDS:
        if solo_kw in prompt_lower:
            return False
    
    # 파트너 키워드가 있으면 필요
    for partner_kw in PARTNER_KEYWORDS:
        if partner_kw in prompt_lower or partner_kw in desc_lower:
            return True
    
    return False

def fix_pose_database(db_path: Path):
    """포즈 데이터베이스 파일을 읽어서 수정"""
    print(f"처리 중: {db_path}")
    
    with open(db_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    fixed_count = 0
    fixed_poses = []
    
    # 모든 섹션 순회
    for section_name in ['emotions', 'poses', 'genit_actions', 'h_scenes', 'scenes_otokonoko']:
        if section_name not in data:
            continue
        
        section = data[section_name]
        for code, pose in section.items():
            if 'prompt' not in pose:
                continue
            
            prompt = pose['prompt']
            description = pose.get('description', '')
            
            # 커플 태그가 필요한지 확인
            if needs_couple_tag(prompt, description):
                # 프롬프트 앞에 1girl, 1boy 추가
                if not prompt.startswith('1girl'):
                    new_prompt = f"1girl, 1boy, {prompt}"
                    pose['prompt'] = new_prompt
                    fixed_count += 1
                    fixed_poses.append(f"{code}: {pose['label']}")
                    print(f"  ✓ {code} ({pose['label']}): 1girl, 1boy 태그 추가")
    
    if fixed_count > 0:
        # 백업 생성
        backup_path = db_path.with_suffix('.json.bak')
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n백업 생성: {backup_path}")
        
        # 수정된 파일 저장
        with open(db_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"\n총 {fixed_count}개 포즈 수정 완료!")
        print("\n수정된 포즈 목록:")
        for pose_info in fixed_poses:
            print(f"  - {pose_info}")
    else:
        print("\n수정이 필요한 포즈가 없습니다.")
    
    return fixed_count

if __name__ == '__main__':
    # SDXL 포즈 데이터베이스 수정
    sdxl_db = Path(r'c:\Users\rbsgh\plepa\data\sdxl_pose_database.json')
    
    if sdxl_db.exists():
        fixed = fix_pose_database(sdxl_db)
        print(f"\n작업 완료: {fixed}개 포즈 수정됨")
    else:
        print(f"파일을 찾을 수 없습니다: {sdxl_db}")
