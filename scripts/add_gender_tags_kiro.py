import json

def add_gender_tags_kiro():
    """키로 DB에 성별 태그 추가"""
    
    with open('C:/Users/rbsgh/kiro/pose_database.json', 'r', encoding='utf-8') as f:
        kiro_db = json.load(f)
    
    modified_count = 0
    
    # H씬 범위 (048-099)
    for pose_id in range(48, 100):
        pose_key = f"{pose_id:03d}"
        
        if pose_key in kiro_db.get('h_scenes', {}):
            pose = kiro_db['h_scenes'][pose_key]
            prompt = pose.get('prompt', '')
            
            if not prompt.startswith('1girl, 1boy'):
                pose['prompt'] = f"1girl, 1boy, {prompt}"
                modified_count += 1
                print(f"✓ 키로 {pose_key}: {pose['label']}")
    
    # 오토코노코 범위 (148-199)
    for pose_id in range(148, 200):
        pose_key = f"{pose_id:03d}"
        
        if pose_key in kiro_db.get('scenes_otokonoko', {}):
            pose = kiro_db['scenes_otokonoko'][pose_key]
            prompt = pose.get('prompt', '')
            
            if not prompt.startswith('2boys'):
                pose['prompt'] = f"2boys, {prompt}"
                modified_count += 1
                print(f"✓ 키로 {pose_key}: {pose['label']}")
    
    # 저장
    with open('C:/Users/rbsgh/kiro/pose_database.json', 'w', encoding='utf-8') as f:
        json.dump(kiro_db, f, ensure_ascii=False, indent=2)
    
    print(f"\n총 {modified_count}개 키로 포즈에 성별 태그 추가 완료")

if __name__ == "__main__":
    add_gender_tags_kiro()
