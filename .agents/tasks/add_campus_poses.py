import json

# SDXL 포즈 DB 로드
with open(r'c:\Users\rbsgh\plepa\data\sdxl_pose_database.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 캠퍼스 전용 포즈 추가 (200-205번)
campus_poses = {
    '200': {
        'label': '캠퍼스 클립보드',
        'description': '캠퍼스 프로젝트 전용: 클립보드를 들고 있는 포즈',
        'prompt': '1girl, solo, standing, holding clipboard, looking at viewer, light blush, campus setting',
        'required_outfit': 'default'
    },
    '201': {
        'label': '캠퍼스 카페',
        'description': '캠퍼스 프로젝트 전용: 카페에서 커피를 마시는 포즈',
        'prompt': '1girl, solo, sitting at cafe table, holding coffee cup, looking at viewer, warm lighting, campus setting',
        'required_outfit': 'default'
    },
    '202': {
        'label': '캠퍼스 도서관',
        'description': '캠퍼스 프로젝트 전용: 도서관에서 책을 읽는 포즈',
        'prompt': '1girl, solo, sitting, reading book in library, looking at viewer, calm expression, campus setting',
        'required_outfit': 'default'
    },
    '203': {
        'label': '캠퍼스 벤치',
        'description': '캠퍼스 프로젝트 전용: 캠퍼스 벤치에 앉아있는 포즈',
        'prompt': '1girl, solo, sitting on outdoor bench, relaxed pose, looking at viewer, soft smile, campus setting',
        'required_outfit': 'default'
    },
    '204': {
        'label': '캠퍼스 강의실',
        'description': '캠퍼스 프로젝트 전용: 강의실에서의 포즈',
        'prompt': '1girl, solo, standing in classroom, hand raised, attentive expression, looking at viewer, campus setting',
        'required_outfit': 'default'
    },
    '205': {
        'label': '캠퍼스 축제',
        'description': '캠퍼스 프로젝트 전용: 캠퍼스 축제에서의 포즈',
        'prompt': '1girl, solo, at campus festival, cheerful expression, looking at viewer, festival decorations, campus setting',
        'required_outfit': 'default'
    }
}

# h_scenes 섹션에 추가
if 'h_scenes' not in data:
    data['h_scenes'] = {}

data['h_scenes'].update(campus_poses)

# 저장
with open(r'c:\Users\rbsgh\plepa\data\sdxl_pose_database.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('✓ 캠퍼스 전용 포즈 추가 완료!')
print('추가된 포즈: 200-205번 (6개)')
print('포즈 목록:')
for code, pose in sorted(campus_poses.items()):
    label = pose['label']
    print(f'  {code}: {label}')
