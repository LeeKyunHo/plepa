#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
N 시리즈 포즈 명칭 업데이트 통합 테스트
"""
import sys
import os
sys.path.insert(0, r'c:\Users\rbsgh\plepa')

from plepa_engine.services.pose_service import PoseService
from plepa_engine.prompt_builder import assemble_flux_prompt, assemble_sdxl_prompt
from plepa_engine.models import CharacterConfig, CharacterAppearance, LoraConfig

# Test data mapping
TEST_POSES = {
    "N46": ("상대를씻겨줌", "씻겨주기"),
    "N47": ("씻겨짐", "씻겨받기"),
    "N48": ("에로마사지앞", "앞면에로마사지"),
    "N49": ("에로마사지뒤", "뒷면에로마사지"),
    "N57": ("뒤에서가슴잡힘", "착의뒤가슴잡힘"),
    "N59": ("야외은밀자극", "착의야외은밀자극"),
    "N60": ("야외쾌감참는중", "착의야외쾌감참기"),
    "N61": ("야외주저앉아절정", "착의야외주저앉아절정"),
    "N63": ("강제입맞춤", "착의강제입맞춤"),
    "N66": ("측위삽입약", "측위약삽입"),
    "N67": ("측위삽입강", "측위강삽입"),
    "N68": ("프론본삽입약", "프론본약삽입"),
    "N69": ("프론본삽입강", "프론본강삽입"),
}

SAMPLE_POSES_FOR_PROMPT = ["N46", "N59", "N63", "N66", "N69"]

class IntegrationTestRunner:
    def __init__(self):
        self.results = {
            "test1": [],
            "test2": [],
            "test3": None,
        }
        self.service = PoseService()
        
    def run_test1(self):
        """Test 1: 포즈 로드 검증 (SDXL + FLUX 양쪽)"""
        print("\n=== Test 1: 포즈 로드 검증 ===")
        
        for code, (old_label, expected_label) in TEST_POSES.items():
            result = {
                "code": code,
                "old_label": old_label,
                "expected_label": expected_label,
                "flux_label": None,
                "sdxl_label": None,
                "flux_prompt": None,
                "sdxl_prompt": None,
                "status": "FAIL",
            }
            
            try:
                # Load from both engines
                flux_db = self.service.load_pose_db(engine="flux")
                sdxl_db = self.service.load_pose_db(engine="sdxl")
                
                # Get details
                details = self.service.get_pose_details(code)
                
                result["flux_label"] = details.get("label", "N/A")
                result["sdxl_label"] = details.get("label", "N/A")
                result["flux_prompt"] = details.get("flux_prompt", "")
                result["sdxl_prompt"] = details.get("sdxl_prompt", "")
                
                # Validate
                label_match = details.get("label") == expected_label
                label_not_old = details.get("label") != old_label
                flux_prompt_exists = bool(details.get("flux_prompt", "").strip())
                sdxl_prompt_exists = bool(details.get("sdxl_prompt", "").strip())
                
                if label_match and label_not_old and flux_prompt_exists and sdxl_prompt_exists:
                    result["status"] = "PASS"
                else:
                    result["status"] = "FAIL"
                    if not label_match:
                        print(f"  {code}: Label mismatch - expected '{expected_label}', got '{result['flux_label']}'")
                    if not label_not_old:
                        print(f"  {code}: Label still matches old name '{old_label}'")
                    if not flux_prompt_exists:
                        print(f"  {code}: Missing FLUX prompt")
                    if not sdxl_prompt_exists:
                        print(f"  {code}: Missing SDXL prompt")
                        
            except Exception as e:
                result["status"] = "FAIL"
                print(f"  {code}: Exception - {str(e)}")
            
            self.results["test1"].append(result)
            print(f"  {code}: {result['status']}")
    
    def run_test2(self):
        """Test 2: 프롬프트 빌더 5종 샘플 테스트"""
        print("\n=== Test 2: 프롬프트 빌더 샘플 테스트 ===")
        
        # Create minimal character config
        char = CharacterConfig(
            prefix="test",
            name="테스트캐릭터",
            gender="female",
            appearance=CharacterAppearance(
                face_and_hair="long black hair, brown eyes",
                physique="slender, average height",
                outfit="school uniform"
            ),
            sdxl_positive="1girl, solo, beautiful face, detailed eyes",
            sdxl_nude_positive="1girl, solo, beautiful face, detailed eyes",
            sdxl_negative="lowres, worst quality, bad quality",
            lora=LoraConfig(name=None, weight=0.8),
            style_keywords="masterpiece, best quality"
        )
        
        for code in SAMPLE_POSES_FOR_PROMPT:
            for engine in ["flux", "sdxl"]:
                result = {
                    "code": code,
                    "engine": engine,
                    "prompt_preview": None,
                    "status": "FAIL",
                }
                
                try:
                    details = self.service.get_pose_details(code)
                    
                    # Create PoseEntry from details
                    from plepa_engine.models import PoseEntry
                    pose = PoseEntry(
                        code=details["code"],
                        section=details["section"],
                        label=details["label"],
                        prompt=details.get(f"{engine}_prompt", ""),
                        description=details.get("description", ""),
                    )
                    
                    if engine == "flux":
                        prompt, nude = assemble_flux_prompt(char, pose, "")
                    else:  # sdxl
                        pos_prompt, neg_prompt, nude = assemble_sdxl_prompt(char, pose, "")
                        prompt = pos_prompt
                    
                    if prompt and prompt.strip():
                        result["prompt_preview"] = prompt[:50] + "..." if len(prompt) > 50 else prompt
                        result["status"] = "PASS"
                    else:
                        result["status"] = "FAIL"
                        print(f"  {code} ({engine}): Empty prompt returned")
                        
                except Exception as e:
                    result["status"] = "FAIL"
                    print(f"  {code} ({engine}): Exception - {str(e)}")
                
                self.results["test2"].append(result)
                print(f"  {code} ({engine}): {result['status']}")
    
    def run_test3(self):
        """Test 3: GUI 코드 레이블 노출 확인"""
        print("\n=== Test 3: GUI 레이블 확인 ===")
        
        gui_file = r'c:\Users\rbsgh\plepa\plepa_gui\pages\poses.py'
        result = {
            "file_exists": False,
            "status": "SKIP",
            "details": ""
        }
        
        if os.path.exists(gui_file):
            result["file_exists"] = True
            try:
                with open(gui_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check for PoseService or label references
                uses_pose_service = "PoseService" in content
                uses_get_pose = "get_pose" in content
                uses_load_db = "load_pose_db" in content
                
                # Check for any hardcoded pose labels from our test set
                hardcoded_labels = []
                for code, (old_label, new_label) in TEST_POSES.items():
                    if f'"{new_label}"' in content or f"'{new_label}'" in content:
                        hardcoded_labels.append(new_label)
                    if f'"{old_label}"' in content or f"'{old_label}'" in content:
                        hardcoded_labels.append(old_label)
                
                if uses_pose_service or uses_get_pose or uses_load_db:
                    result["status"] = "PASS"
                    result["details"] = "GUI는 PoseService를 통해 레이블을 동적으로 참조함"
                    print("  PASS: GUI는 PoseService를 통해 동적 참조")
                elif hardcoded_labels:
                    result["status"] = "PARTIAL"
                    result["details"] = f"GUI에 하드코딩된 명칭 발견: {', '.join(set(hardcoded_labels[:3]))}"
                    print(f"  PARTIAL: 하드코딩된 명칭 발견 - {result['details']}")
                else:
                    result["status"] = "SKIP"
                    result["details"] = "GUI에서 해당 포즈 라벨 참조 없음"
                    print("  SKIP: 해당 포즈 라벨 참조 없음")
                    
            except Exception as e:
                result["status"] = "FAIL"
                result["details"] = f"파일 읽기 오류: {str(e)}"
                print(f"  FAIL: {result['details']}")
        else:
            result["details"] = f"파일 없음: {gui_file}"
            print(f"  SKIP: {result['details']}")
        
        self.results["test3"] = result
    
    def get_summary(self):
        """테스트 결과 요약"""
        test1_pass = sum(1 for r in self.results["test1"] if r["status"] == "PASS")
        test1_total = len(self.results["test1"])
        
        test2_pass = sum(1 for r in self.results["test2"] if r["status"] == "PASS")
        test2_total = len(self.results["test2"])
        
        test3_status = self.results["test3"]["status"]
        
        overall = "PASS" if (test1_pass == test1_total and test2_pass == test2_total) else "FAIL"
        
        return {
            "overall": overall,
            "test1": f"{test1_pass}/{test1_total}",
            "test2": f"{test2_pass}/{test2_total}",
            "test3": test3_status,
        }

def main():
    runner = IntegrationTestRunner()
    
    print("=" * 60)
    print("N 시리즈 포즈 명칭 업데이트 통합 테스트 시작")
    print("=" * 60)
    
    runner.run_test1()
    runner.run_test2()
    runner.run_test3()
    
    summary = runner.get_summary()
    
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)
    print(f"전체 결과: {summary['overall']}")
    print(f"Test 1 (포즈 로드): {summary['test1']}")
    print(f"Test 2 (프롬프트 빌더): {summary['test2']}")
    print(f"Test 3 (GUI): {summary['test3']}")
    
    # Save results to JSON for report generation
    import json
    results_file = r'c:\Users\rbsgh\plepa\.agents\tasks\test_results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump({
            "summary": summary,
            "details": runner.results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n테스트 결과 저장: {results_file}")
    
    return 0 if summary["overall"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
