import os
import time
from distribution.base import BaseUploader
from distribution.models import UploadJob, UploadResult, UploadStatus
from distribution.naver_clip.browser import NaverBrowserSession
from distribution.naver_clip.selectors import NaverClipSelectors
from distribution.naver_clip.resolver import NaverClipResolver

class NaverClipUploader(BaseUploader):
    """
    네이버 크리에이터 스튜디오(tv.naver.com)를 통한 클립 업로드 구현체.
    playwright persistent context를 사용하여 로그인을 유지하며,
    실제 사용자의 DOM 인터랙션 흐름을 모방합니다.
    """

    def __init__(self):
        super().__init__()
        self.platform_name = "naver_clip"

    def upload(self, job: UploadJob) -> UploadResult:
        with NaverBrowserSession(headless=False) as context:
            page = context.pages[0] if context.pages else context.new_page()
            
            try:
                # 1. 로그인 확인 및 업로드 화면 접근
                page.goto("https://studio.tv.naver.com/")
                page.wait_for_load_state("domcontentloaded")
                
                try:
                    page.wait_for_selector(NaverClipSelectors.BTN_CREATE, timeout=15000)
                except:
                    return UploadResult(
                        job_id=job.job_id,
                        platform=self.platform_name,
                        status=UploadStatus.FAILED,
                        error_message="로그인이 필요하거나 크리에이터 스튜디오 접속에 실패했습니다."
                    )
                
                page.locator(NaverClipSelectors.BTN_CREATE).first.click()
                
                # '클립 업로드' 클릭
                buttons = page.locator(NaverClipSelectors.BTN_CLIP_UPLOAD).all()
                if len(buttons) > 1:
                    buttons[1].click() # 보통 두 번째가 클립 업로드
                elif buttons:
                    buttons[0].click()
                else:
                    return UploadResult(job_id=job.job_id, platform=self.platform_name, status=UploadStatus.FAILED, error_message="클립 업로드 버튼을 찾을 수 없습니다.")

                # 2. 파일 업로드
                page.wait_for_selector(NaverClipSelectors.INPUT_FILE, state="attached", timeout=10000)
                
                abs_video_path = os.path.abspath(job.video_path)
                if not os.path.exists(abs_video_path):
                    return UploadResult(job_id=job.job_id, platform=self.platform_name, status=UploadStatus.FAILED, error_message=f"영상 파일을 찾을 수 없습니다: {abs_video_path}")
                
                page.set_input_files(NaverClipSelectors.INPUT_FILE, abs_video_path)
                
                # 3. 폼 렌더링 대기
                page.wait_for_selector(NaverClipSelectors.TEXTAREA_DESC, timeout=30000)
                time.sleep(2) # 안정화
                
                # 4. 제목 및 본문/해시태그 입력
                # 제목 입력란 (maxlength 이슈 방지)
                safe_title = job.title[:24] if job.title else "Naver Clip Video"
                page.fill(NaverClipSelectors.INPUT_TITLE, safe_title)
                
                # 본문 입력란 (본문 + 해시태그 조합)
                full_desc = f"{job.description}\n\n{' '.join(job.hashtags)}"
                page.fill(NaverClipSelectors.TEXTAREA_DESC, full_desc)
                
                # 5. 필수 카테고리 지정 (임의로 첫 번째나 '엔터/일상' 선택)
                try:
                    cat1_btn = page.locator(NaverClipSelectors.BTN_CATEGORY_1).first
                    if cat1_btn.is_visible():
                        cat1_btn.click()
                        time.sleep(0.5)
                        # '엔터' 또는 '일상기록' 등 무난한 카테고리 시도
                        target_cat = page.locator(NaverClipSelectors.BTN_CATEGORY_ITEM + ":has-text('엔터')").first
                        if not target_cat.is_visible():
                            target_cat = page.locator(NaverClipSelectors.BTN_CATEGORY_ITEM).first # 첫 번째 카테고리 fallback
                        target_cat.click()
                        time.sleep(0.5)
                        
                        # 2차 카테고리도 활성화되면 선택
                        cat2_btn = page.locator(NaverClipSelectors.BTN_CATEGORY_2).first
                        if cat2_btn.is_visible() and not cat2_btn.is_disabled():
                            cat2_btn.click()
                            time.sleep(0.5)
                            page.locator(NaverClipSelectors.BTN_CATEGORY_ITEM).first.click()
                            time.sleep(0.5)
                except Exception as e:
                    print(f"[Warning] 카테고리 선택 실패 (필수가 아닐 수도 있음): {e}")

                # 6. 게시/저장 클릭
                save_btn = page.locator(NaverClipSelectors.BTN_SAVE).first
                if save_btn.is_disabled():
                    print("[Warning] 저장 버튼이 비활성화 되어 있습니다. 영상 처리 중이거나 필수 항목이 누락되었습니다.")
                    # 혹시 영상 처리 대기가 필요할 수 있으므로 최대 30초 대기
                    for _ in range(30):
                        if not save_btn.is_disabled():
                            break
                        time.sleep(1)
                        
                    if save_btn.is_disabled():
                        return UploadResult(job_id=job.job_id, platform=self.platform_name, status=UploadStatus.FAILED, error_message="저장 버튼이 활성화되지 않습니다.")

                save_btn.click()
                print("게시(저장) 버튼 클릭 완료!")
                
                # 저장 완료 후 약간 대기
                time.sleep(5)
                
                # 7. Resolver를 통한 URL 획득 검증
                resolver = NaverClipResolver(page)
                published_url = resolver.resolve_url(job)
                
                if published_url:
                    return UploadResult(
                        job_id=job.job_id,
                        platform=self.platform_name,
                        status=UploadStatus.SUCCESS,
                        published_url=published_url
                    )
                else:
                    return UploadResult(
                        job_id=job.job_id,
                        platform=self.platform_name,
                        status=UploadStatus.FAILED,
                        error_message="게시는 완료된 것 같으나, 실제 URL을 검증(Resolve)하지 못하여 실패 처리합니다."
                    )

            except Exception as e:
                import traceback
                traceback.print_exc()
                return UploadResult(
                    job_id=job.job_id,
                    platform=self.platform_name,
                    status=UploadStatus.FAILED,
                    error_message=f"업로드 진행 중 오류 발생: {str(e)}"
                )
