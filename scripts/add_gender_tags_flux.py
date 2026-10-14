import json

def add_gender_tags_flux():
    """FLUX DB에 성별 태그 추가"""
    
    with open('data/flux_pose_database.json', 'r', encoding='utf-8') as f:
        flux_db = json.load(f)
    
    modified_count = 0
    
    # H씬 범위 (048-099)
    for pose_id in range(48, 100):
        pose_key = f"{pose_id:03d}"
        
        if pose_key in flux_db.get('h_scenes', {}):
            pose = flux_db['h_scenes'][pose_key]
            prompt = pose.get('prompt', '')
            
            if 'One female' not in prompt and 'one male' not in prompt:
                # FLUX는 자연어 스타일이므로 문장으로 추가
                pose['prompt'] = f"One female character and one male partner. {prompt}"
                modified_count += 1
                print(f"✓ FLUX {pose_key}: {pose['label']}")
    
    # 오토코노코 범위 (148-199)
    for pose_id in range(148, 200):
        pose_key = f"{pose_id:03d}"
        
        if pose_key in flux_db.get('scenes_otokonoko', {}):
            pose = flux_db['scenes_otokonoko'][pose_key]
            prompt = pose.get('prompt', '')
            
            if 'Two male' not in prompt:
                pose['prompt'] = f"Two male characters. {prompt}"
                modified_count += 1
                print(f"✓ FLUX {pose_key}: {pose['label']}")
    
    # 저장
    with open('data/flux_pose_database.json', 'w', encoding='utf-8') as f:
        json.dump(flux_db, f, ensure_ascii=False, indent=2)
    
    print(f"\n총 {modified_count}개 FLUX 포즈에 성별 태그 추가 완료")

if __name__ == "__main__":
    add_gender_tags_flux()
