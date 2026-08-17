"""
네이버 크리에이터 스튜디오 셀렉터 모음
실제 DOM 검사를 통해 확인된 안정적인 셀렉터들입니다.
nth-child 사용을 최대한 배제하고 역할, 클래스, 텍스트 기반으로 작성했습니다.
"""

class NaverClipSelectors:
    # 1. 업로드 진입
    BTN_CREATE = "button._uploadDropdown" # '만들기' 버튼
    BTN_CLIP_UPLOAD = "button.UploadBlocks_button___8gEk" # '클립 업로드' 버튼. 여러 개일 수 있으므로 텍스트나 인덱스로 접근 권장
    
    # 2. 파일 업로드
    INPUT_FILE = "input#uploadFiles" # 실제 파일 업로드용 hidden input
    
    # 3. 폼 입력창 (파일 업로드 후 나타남)
    INPUT_TITLE = "input.InputText_input_text__1Kzay" # 제목 입력 (maxlength 24)
    TEXTAREA_DESC = "textarea" # 본문/해시태그 설명 입력 (placeholder '영상에 대해 설명해 주세요')
    
    # 4. 카테고리 (저장 버튼 활성화를 위해 필수)
    BTN_CATEGORY_1 = "button:has-text('1차 카테고리')"
    BTN_CATEGORY_2 = "button:has-text('2차 카테고리')"
    BTN_CATEGORY_ITEM = "button.SelectGroup_button_item__WESRy" # 카테고리 드롭다운 항목들
    
    # 5. 저장 / 게시
    BTN_SAVE = "button.VideoDetailModal_button_save__gSwLV" # '저장' 버튼
    
    # 6. 완료 상태 및 URL 확인 (등록 후 뜨는 목록 등)
    # 목록에서 방금 올린 클립의 링크를 찾을 때
    LINK_LATEST_CLIP = "a.LatestVideoPerformance_link_wrap__W7cyV" # 대시보드 기준 가장 최근 클립 링크
