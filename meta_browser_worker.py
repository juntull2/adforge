"""AdForge용 격리 브라우저 작업자. 실제 검색 페이지가 받은 광고만 반환합니다."""
import json
import sys
import re
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright


def connections(value):
    if isinstance(value, dict):
        main = value.get("ad_library_main")
        if isinstance(main, dict) and isinstance(main.get("search_results_connection"), dict):
            yield main["search_results_connection"]
        for child in value.values():
            yield from connections(child)
    elif isinstance(value, list):
        for child in value:
            yield from connections(child)


def collect(page, request):
    ads, page_info = {}, {}
    counts = {"requests": 0}
    pages = 0
    extract_cards = Path(__file__).with_name("meta_browser_cards.js").read_text(encoding="utf-8")
    def read_cards():
        for ad in page.evaluate(extract_cards):
            ads.setdefault(str(ad["ad_archive_id"]), ad)
    def receive(response):
        if "/api/graphql" not in response.url:
            return
        counts["requests"] += 1
        try:
            for line in response.text().removeprefix("for (;;);").splitlines():
                if not line.strip():
                    continue
                for conn in connections(json.loads(line)):
                    page_info.update(conn.get("page_info") or {})
                    for edge in conn.get("edges") or []:
                        node = (edge or {}).get("node") or {}
                        for ad in node.get("collated_results") or ([node] if node.get("ad_archive_id") else []):
                            if ad.get("ad_archive_id"):
                                ads[str(ad["ad_archive_id"])] = ad
        except Exception:
            pass
    page.on("response", receive)
    try:
        params = {"active_status": request.get("active_status", "active"), "ad_type": "all",
                  "country": request.get("country", "KR"), "media_type": "all",
                  "search_type": request.get("search_type", "keyword_unordered")}
        if request.get("page_id"):
            params["view_all_page_id"] = request["page_id"]
        else:
            params["q"] = request["query"]
        url = "https://www.facebook.com/ads/library/?" + urlencode(params)
        response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        # 최초 문서가 403이어도 페이지의 접속 확인 JavaScript 뒤에 검색이
        # 정상 렌더링될 수 있으므로, 최초 상태 코드만으로 중단하지 않습니다.
        # 브라우저가 페이지의 JavaScript를 실행하고 실제 검색을 끝낼 때까지 기다립니다.
        page.get_by_text(re.compile(r"라이브러리 ID:|Library ID:|결과.*개|results|검색 결과가 없습니다|No ads found")).first.wait_for(timeout=45000)
        page.wait_for_timeout(1500)
        read_cards()
        completed = False
        stop_reason = "page_limit"
        pages = 1
        for _ in range(max(1, request.get("max_pages", 3)) - 1):
            before = len(ads)
            if page_info.get("has_next_page") is False:
                completed = True
                break
            more = page.get_by_role("button", name=re.compile(r"^(더 보기|See more|Load more)$"))
            if more.count() and more.last.is_visible():
                more.last.click(timeout=5000)
            else:
                page.evaluate("window.scrollTo(0, document.scrollingElement.scrollHeight)")
            # 추가 로딩이 5초 이상 걸릴 수 있습니다. 실제 새 카드가 나타날 때까지
            # 기다리고, 아래쪽 로딩 지점이 다시 화면에 들어오게 합니다.
            for _wait in range(30):
                page.wait_for_timeout(500)
                read_cards()
                if len(ads) > before or page_info.get("has_next_page") is False:
                    break
                if _wait in (9, 19):
                    page.evaluate("window.scrollTo(0, Math.max(0, document.scrollingElement.scrollHeight - innerHeight - 200))")
                    page.wait_for_timeout(200)
                    page.evaluate("window.scrollTo(0, document.scrollingElement.scrollHeight)")
            pages += 1
            if len(ads) == before:
                completed = page_info.get("has_next_page") is False
                if not completed:
                    stop_reason = "pagination_stalled"
                break
        if page_info.get("has_next_page") is False:
            completed = True
        body = page.locator("body").inner_text()
        if not ads:
            # 0개 정상 검색과 로그인·검증·로딩 실패를 구분합니다.
            if not re.search(r"결과\s*[~약]?\s*0개|0 results|No ads found|검색 결과가 없습니다|일치하는 광고가 없습니다", body, re.I):
                raise RuntimeError("메타 검색 화면에서 광고 데이터를 받지 못했습니다. 로그인 또는 접속 확인이 필요한지 확인하세요.")
            completed = True
        page.screenshot(path=str(Path(__file__).parent / "scratch" / "meta_browser_latest.png"))
        return {"ads": list(ads.values()), "requests": counts["requests"] + 1,
                "pages_collected": pages, "has_next_page": not completed,
                "stop_reason": "" if completed else stop_reason, "url": url}
    except Exception as exc:
        if not ads:
            raise
        return {"ads": list(ads.values()), "requests": counts["requests"] + 1,
                "pages_collected": max(1, pages), "has_next_page": True,
                "stop_reason": "browser_error", "warning": str(exc).split("Call log:")[0][:300]}
    finally:
        page.remove_listener("response", receive)


def main():
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="chrome", headless=False, args=["--start-minimized"])
        context = browser.new_context(locale="ko-KR", viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        try:
            for line in sys.stdin:
                request = json.loads(line)
                if request.get("close"):
                    break
                try:
                    result = collect(page, request)
                except Exception as exc:
                    try:
                        page.screenshot(path=str(Path(__file__).parent / "scratch" / "meta_browser_latest.png"))
                        (Path(__file__).parent / "scratch" / "meta_browser_visible_error.txt").write_text(page.locator("body").inner_text()[:2000], encoding="utf-8")
                    except Exception:
                        pass
                    result = {"error": str(exc).split("Call log:")[0][:500]}
                print(json.dumps(result, ensure_ascii=False), flush=True)
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
