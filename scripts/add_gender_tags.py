import json
import sys

def add_gender_tags_to_h_scenes():
    """H씬 포즈(048-099)에 1girl, 1boy 태그 추가"""
    
    # SDXL DB 처리
    with open('data/sdxl_pose_database.json', 'r', encoding='utf-8') as f:
        sdxl_db = json.load(f)
    
    modified_count = 0
    
    # H씬 범위 (048-099)
    for pose_id in range(48, 100):
        pose_key = f"{pose_id:03d}"
        
        if pose_key in sdxl_db.get('h_scenes', {}):
            pose = sdxl_db['h_scenes'][pose_key]
            prompt = pose.get('prompt', '')
            
            # 이미 1girl, 1boy가 있으면 스킵
            if '1girl' not in prompt and '1boy' not in prompt:
                # 프롬프트 맨 앞에 추가
                pose['prompt'] = f"1girl, 1boy, {prompt}"
                modified_count += 1
                print(f"✓ {pose_key}: {pose['label']}")
    
    # 저장
    with open('data/sdxl_pose_database.json', 'w', encoding='utf-8') as f:
        json.dump(sdxl_db, f, ensure_ascii=False, indent=2)
    
    print(f"\n총 {modified_count}개 포즈에 1girl, 1boy 추가 완료")
    return modified_count

def add_2boys_to_otokonoko():
    """오토코노코 H씬(148-199)에 2boys 태그 추가"""
    
    with open('data/sdxl_pose_database.json', 'r', encoding='utf-8') as f:
        sdxl_db = json.load(f)
    
    modified_count = 0
    
    # 오토코노코 범위 (148-199)
    for pose_id in range(148, 200):
        pose_key = f"{pose_id:03d}"
        
        if pose_key in sdxl_db.get('scenes_otokonoko', {}):
            pose = sdxl_db['scenes_otokonoko'][pose_key]
            prompt = pose.get('prompt', '')
            
            # 이미 2boys가 있으면 스킵
            if '2boys' not in prompt:
                # 프롬프트 맨 앞에 추가
                pose['prompt'] = f"2boys, {prompt}"
                modified_count += 1
                print(f"✓ {pose_key}: {pose['label']}")
    
    # 저장
    with open('data/sdxl_pose_database.json', 'w', encoding='utf-8') as f:
        json.dump(sdxl_db, f, ensure_ascii=False, indent=2)
    
    print(f"\n총 {modified_count}개 오토코노코 포즈에 2boys 추가 완료")
    return modified_count

if __name__ == "__main__":
    print("=" * 60)
    print("H씬 포즈에 성별 태그 추가")
    print("=" * 60)
    
    print("\n[1단계] H씬 (048-099)에 1girl, 1boy 추가")
    print("-" * 60)
    h_count = add_gender_tags_to_h_scenes()
    
    print("\n[2단계] 오토코노코 H씬 (148-199)에 2boys 추가")
    print("-" * 60)
    oto_count = add_2boys_to_otokonoko()
    
    print("\n" + "=" * 60)
    print(f"완료: H씬 {h_count}개, 오토코노코 {oto_count}개")
    print("=" * 60)
