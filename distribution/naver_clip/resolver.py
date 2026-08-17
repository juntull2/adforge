import time
from typing import Optional
from distribution.models import UploadJob
from distribution.naver_clip.browser import NaverBrowserSession
from distribution.naver_clip.selectors import NaverClipSelectors

class NaverClipResolver:
    def __init__(self, page):
        self.page = page

    def resolve_url(self, job: UploadJob) -> Optional[str]:
        """
        다중 검증 방식을 통해 방금 업로드된 클립의 실제 시청 URL을 가져옵니다.
        1. 업로드 후 '콘텐츠' 목록으로 이동
        2. 첫 번째 항목의 제목 일치 확인
        3. 최신성 검증
        4. 링크 복사 또는 직접 URL 추출
        """
        try:
            # 1. 콘텐츠 -> 클립 탭으로 이동 (채널명 부분을 알아내기 위해 대시보드에서 네비게이션)
            # 보통 저장 후 자동으로 목록으로 이동할 수 있지만 명시적으로 접근
            print("업로드 완료 확인 후 콘텐츠 목록으로 이동하여 URL을 추출합니다...")
            self.page.goto("https://studio.tv.naver.com/")
            self.page.wait_for_load_state("domcontentloaded")
            
            # 좌측 메뉴에서 '콘텐츠' 클릭
            self.page.locator("a[href*='/content/']").first.click()
            self.page.wait_for_load_state("networkidle")
            
            # (만약 비디오 탭이라면 클립 탭으로 이동)
            # "클립" 텍스트를 가진 탭 또는 버튼을 찾아 클릭
            try:
                clip_tab = self.page.locator("a:has-text('클립'), button:has-text('클립')").first
                if clip_tab.is_visible():
                    clip_tab.click()
                    self.page.wait_for_load_state("networkidle")
                    time.sleep(2)
            except:
                pass # 이미 클립 탭이거나 탭 구분이 없을 수 있음
            
            # 2. 목록의 첫 번째 항목 찾기
            # Naver Studio는 대개 최신순 정렬임
            # 리스트 렌더링 대기
            self.page.wait_for_selector("table, ul, div[role='rowgroup']", timeout=10000)
            
            # 첫 번째 항목의 텍스트들을 전부 가져와서 우리가 올린 제목과 비교
            # 클립의 경우 제목 입력 글자수가 잘리거나 '...' 처리될 수 있으므로 부분 일치 검사
            first_item = self.page.locator("tr, div[role='row']").nth(1) # 보통 첫 번째(0)는 헤더, 1이 실제 첫 아이템
            item_text = first_item.inner_text()
            
            # 3. 일치 검증
            target_title_prefix = job.title[:10] # 첫 10글자로 일치 확인
            
            if target_title_prefix not in item_text:
                print(f"[Resolver Error] 최신 항목에서 제목을 찾을 수 없습니다. (찾는 제목: {target_title_prefix})")
                return None
                
            # 4. 링크 추출
            # 해당 행에 있는 메뉴(...) 버튼 클릭
            more_btn = first_item.locator("button:has-text('더보기'), button._dropdown_button, button:has-text('...')").first
            if not more_btn.is_visible():
                # 메뉴 버튼이 없으면, 썸네일이나 제목의 링크 확인
                link = first_item.locator("a[href*='tv.naver.com/v/']").first
                if link.is_visible():
                    return link.get_attribute("href")
            
            # 메뉴 버튼 클릭
            more_btn.click()
            time.sleep(1)
            
            # "네이버TV 바로가기" 버튼이 있으면 a 태그일 수 있음
            goto_btn = self.page.locator("button:has-text('네이버TV 바로가기'), a:has-text('네이버TV 바로가기')").first
            if goto_btn.is_visible() and goto_btn.evaluate("el => el.tagName") == "A":
                return goto_btn.get_attribute("href")
            
            # 클립보드 인터셉트를 통한 '링크 복사'
            # JS 환경에서 navigator.clipboard.writeText를 오버라이드하여 링크 캡처
            self.page.evaluate('''() => {
                window._interceptedLink = null;
                navigator.clipboard.writeText = (text) => {
                    window._interceptedLink = text;
                    return Promise.resolve();
                };
            }''')
            
            copy_btn = self.page.locator("button:has-text('링크 복사')").first
            if copy_btn.is_visible():
                copy_btn.click()
                time.sleep(1)
                
                # 인터셉트된 링크 가져오기
                link = self.page.evaluate("() => window._interceptedLink")
                if link and "naver.com" in link:
                    return link

            print("[Resolver Error] 링크 복사 버튼을 찾을 수 없거나 링크를 추출하지 못했습니다.")
            return None

        except Exception as e:
            print(f"[Resolver Exception] URL 해결 중 오류 발생: {e}")
            return None
