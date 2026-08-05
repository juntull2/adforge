import pycapcut as cc

# 1. 사용자 시스템의 실제 CapCut 초안 폴더 경로
draft_folder_path = "C:/Users/5700G/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft"
draft_folder = cc.DraftFolder(draft_folder_path)

# 2. 기존 템플릿 초안을 복사하여 새 초안 만들기
# 예시: '0805' 초안을 복사하여 '새_초안_0805' 생성
# 원하시는 초안 이름(예: '0731', '0803', '0805' 등)으로 변경해 사용하세요.
template_name = "0805"
new_draft_name = "0805_copy"

script = draft_folder.duplicate_as_template(template_name, new_draft_name, allow_replace=True)

# 3. 자막/텍스트 변경 예시 (필요시 주석 해제하여 사용)
# script.replace_text("이전 텍스트", "새로운 텍스트")

# 4. 변경 사항 저장
script.save()

print(f"성공적으로 '{template_name}' 초안을 복사하여 '{new_draft_name}'(으)로 생성 및 저장했습니다.")
