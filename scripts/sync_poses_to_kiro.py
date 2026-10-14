"""
플에파 → 키로 포즈 동기화 스크립트
Phase 1 리팩토링에서 변경된 포즈를 키로 프로젝트로 동기화합니다.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Phase 1에서 변경된 포즈 코드 목록
CHANGED_POSES = {
    # 이름 변경된 포즈
    "014": "유혹 (가슴유혹에서 변경)",
    "023": "의심 (도도한팔짱에서 변경)",
    "028": "안고엉덩이애무 (밀착포옹에서 변경)",
    "029": "엎드려유혹 (도기유혹에서 변경)",
    "030": "전라스탠딩 (알몸스탠딩에서 변경)",
    "031": "뒤에서가슴애무 (후방가슴애무에서 변경)",
    "033": "몰래애무 (신규 포즈, 턱들기 대체)",
    "034": "가슴에얼굴묻기 (가슴파묻힘에서 변경)",
    "035": "덮치기 (침대덮침에서 변경)",
    "037": "붓카케 (애프터피크에서 변경)",
    "040": "덮쳐짐 (상대방덮치기에서 변경)",
    "041": "능동적 역전 (042와 교환)",
    "042": "수동적 역전 (041과 교환)",
    "047": "쓰다듬기 (탄산음료사귀기에서 변경)",
    "052": "누워절정여운 (수평사후에서 변경)",
    "053": "엎드려절정여운 (엎드려사후에서 변경)",
    "065": "남근핥기 (립잡대딸에서 변경, 067과 교환)",
    "067": "립잡대딸 (남근핥기에서 변경, 065와 교환)",
}

# 추가 개선사항 (선택적 적용)
IMPROVEMENTS = {
    "1girl_1boy": "110개 파트너 포즈에 1girl, 1boy 태그 추가",
    "구도_개선": ["056", "067", "069", "081", "082", "087", "089"],
    "역할_명확화": ["033", "034", "065"],
}


def load_json(path: Path) -> dict:
    """JSON 파일 로드"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path: Path, data: dict):
    """JSON 파일 저장 (포맷팅 유지)"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def backup_file(path: Path) -> Path:
    """파일 백업 생성"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_suffix(f'.backup_{timestamp}.json')
    
    if path.exists():
        with open(path, 'r', encoding='utf-8') as src:
            with open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(src.read())
        print(f"📦 백업 생성: {backup_path.name}")
    
    return backup_path


def sync_pose(plepa_db: dict, kiro_db: dict, pose_code: str, section: str = "h_scenes") -> bool:
    """특정 포즈를 플에파에서 키로로 동기화"""
    if section not in plepa_db:
        print(f"⚠️  플에파에 '{section}' 섹션이 없습니다.")
        return False
    
    if section not in kiro_db:
        print(f"⚠️  키로에 '{section}' 섹션이 없습니다.")
        return False
    
    if pose_code not in plepa_db[section]:
        print(f"⚠️  {pose_code}: 플에파에서 찾을 수 없음")
        return False
    
    # 동기화
    kiro_db[section][pose_code] = plepa_db[section][pose_code].copy()
    
    pose_name = plepa_db[section][pose_code].get("label", "이름없음")
    print(f"✅ {pose_code}: {pose_name} 동기화 완료")
    
    return True


def compare_pose(plepa_db: dict, kiro_db: dict, pose_code: str, section: str = "h_scenes") -> dict:
    """두 포즈의 차이점 분석"""
    diff = {
        "code": pose_code,
        "exists_in_plepa": pose_code in plepa_db.get(section, {}),
        "exists_in_kiro": pose_code in kiro_db.get(section, {}),
        "differences": []
    }
    
    if not diff["exists_in_plepa"] or not diff["exists_in_kiro"]:
        return diff
    
    plepa_pose = plepa_db[section][pose_code]
    kiro_pose = kiro_db[section][pose_code]
    
    # 라벨 비교
    if plepa_pose.get("label") != kiro_pose.get("label"):
        diff["differences"].append({
            "field": "label",
            "plepa": plepa_pose.get("label"),
            "kiro": kiro_pose.get("label")
        })
    
    # 설명 비교
    if plepa_pose.get("description") != kiro_pose.get("description"):
        diff["differences"].append({
            "field": "description",
            "plepa": plepa_pose.get("description"),
            "kiro": kiro_pose.get("description")
        })
    
    # 프롬프트 비교 (길이만 비교)
    plepa_prompt_len = len(plepa_pose.get("prompt", ""))
    kiro_prompt_len = len(kiro_pose.get("prompt", ""))
    if abs(plepa_prompt_len - kiro_prompt_len) > 50:  # 50자 이상 차이나면
        diff["differences"].append({
            "field": "prompt",
            "plepa_length": plepa_prompt_len,
            "kiro_length": kiro_prompt_len
        })
    
    return diff


def generate_diff_report(plepa_path: Path, kiro_path: Path) -> list:
    """변경점 리포트 생성"""
    print("\n📊 변경점 분석 중...")
    
    plepa_db = load_json(plepa_path)
    kiro_db = load_json(kiro_path)
    
    report = []
    for pose_code, description in CHANGED_POSES.items():
        diff = compare_pose(plepa_db, kiro_db, pose_code)
        if diff["differences"]:
            report.append({
                "code": pose_code,
                "description": description,
                "changes": diff["differences"]
            })
    
    return report


def main():
    print("=" * 60)
    print("🔄 플에파 → 키로 포즈 동기화 스크립트")
    print("=" * 60)
    
    # 플에파 경로 (현재 스크립트 기준)
    script_dir = Path(__file__).parent
    plepa_root = script_dir.parent
    plepa_path = plepa_root / "data" / "sdxl_pose_database.json"
    
    if not plepa_path.exists():
        print(f"❌ 플에파 포즈 DB를 찾을 수 없습니다: {plepa_path}")
        sys.exit(1)
    
    # 키로 경로 입력
    print(f"\n📁 플에파 경로: {plepa_path}")
    kiro_root = input("\n📁 키로 프로젝트 루트 경로를 입력하세요: ").strip()
    
    if not kiro_root:
        print("❌ 경로를 입력하지 않았습니다.")
        sys.exit(1)
    
    kiro_root = Path(kiro_root)
    if not kiro_root.exists():
        print(f"❌ 키로 프로젝트를 찾을 수 없습니다: {kiro_root}")
        sys.exit(1)
    
    # 키로 포즈 DB 찾기
    possible_paths = [
        kiro_root / "data" / "sd_pose_database.json",
        kiro_root / "data" / "sdxl_pose_database.json",
        kiro_root / "pose_database.json",
    ]
    
    kiro_path = None
    for path in possible_paths:
        if path.exists():
            kiro_path = path
            break
    
    if not kiro_path:
        print(f"❌ 키로 포즈 DB를 찾을 수 없습니다. 다음 경로를 확인했습니다:")
        for path in possible_paths:
            print(f"  - {path}")
        sys.exit(1)
    
    print(f"📁 키로 포즈 DB: {kiro_path}")
    
    # 모드 선택
    print("\n" + "=" * 60)
    print("모드를 선택하세요:")
    print("  1. 차이점 리포트만 생성 (안전)")
    print("  2. 선택된 포즈만 동기화")
    print("  3. 전체 포즈 동기화 (백업 자동 생성)")
    print("=" * 60)
    
    mode = input("\n선택 (1/2/3): ").strip()
    
    if mode == "1":
        # 리포트만 생성
        report = generate_diff_report(plepa_path, kiro_path)
        
        if not report:
            print("\n✨ 변경점이 없습니다!")
        else:
            print(f"\n📋 변경점 {len(report)}개 발견:")
            for item in report:
                print(f"\n  {item['code']}: {item['description']}")
                for change in item['changes']:
                    print(f"    - {change['field']}: 차이 있음")
        
        # 리포트 파일로 저장
        report_path = plepa_root / "docs" / f"pose_sync_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        save_json(report_path, report)
        print(f"\n📄 리포트 저장됨: {report_path}")
    
    elif mode in ["2", "3"]:
        # 백업 생성
        backup_path = backup_file(kiro_path)
        
        # 로드
        plepa_db = load_json(plepa_path)
        kiro_db = load_json(kiro_path)
        
        if mode == "2":
            # 선택 동기화
            print(f"\n동기화할 포즈 ({len(CHANGED_POSES)}개):")
            for code, desc in CHANGED_POSES.items():
                print(f"  {code}: {desc}")
            
            confirm = input("\n이 포즈들을 동기화하시겠습니까? (y/n): ").strip().lower()
            if confirm != 'y':
                print("❌ 취소되었습니다.")
                sys.exit(0)
            
            poses_to_sync = CHANGED_POSES.keys()
        
        else:  # mode == "3"
            confirm = input(f"\n⚠️  전체 {len(CHANGED_POSES)}개 포즈를 동기화하시겠습니까? (y/n): ").strip().lower()
            if confirm != 'y':
                print("❌ 취소되었습니다.")
                sys.exit(0)
            
            poses_to_sync = CHANGED_POSES.keys()
        
        # 동기화 실행
        print("\n🔄 동기화 시작...\n")
        success_count = 0
        
        for pose_code in poses_to_sync:
            if sync_pose(plepa_db, kiro_db, pose_code):
                success_count += 1
        
        # 저장
        save_json(kiro_path, kiro_db)
        
        print("\n" + "=" * 60)
        print(f"✅ 동기화 완료! {success_count}/{len(poses_to_sync)}개 포즈 업데이트됨")
        print(f"📦 백업 파일: {backup_path}")
        print(f"💾 업데이트된 파일: {kiro_path}")
        print("=" * 60)
        
        # 검증 제안
        print("\n💡 다음 단계:")
        print("  1. 키로 프로젝트에서 테스트 생성 실행")
        print(f"     cd {kiro_root}")
        print("     python sd_batch_generator.py -r [roster] -c [char] -p 065,067,033")
        print("  2. 문제가 있다면 백업으로 복원:")
        print(f"     cp {backup_path} {kiro_path}")
    
    else:
        print("❌ 잘못된 선택입니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()
