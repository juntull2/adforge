"""웹 검색을 실행하는 브라우저 작업자와 기존 광고 분석기의 어댑터."""
import json
import os
import queue
import subprocess
import sys
import threading
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

from meta_ad_library import AdCollection, AdLibraryBlocked


class BrowserAdLibraryClient:
    def __init__(self, country="KR"):
        self.country = country
        self.collection_mode = "browser"
        self.request_count = 0
        self.failed_queries = []
        self.last_error = {}
        self._process = None
        self._cache = {}
        self._page_names = {}
        self._responses = queue.Queue()

    def _start(self):
        if self._process is not None:
            return
        self._responses = queue.Queue()
        worker = Path(__file__).with_name("meta_browser_worker.py")
        self._process = subprocess.Popen(
            [sys.executable, str(worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        process = self._process
        responses = self._responses
        def read_results():
            try:
                for line in process.stdout:
                    try:
                        responses.put(json.loads(line))
                    except ValueError:
                        continue
            except (OSError, ValueError):
                pass
            finally:
                responses.put({"error": "브라우저 작업자가 종료됐습니다. Playwright와 Chrome 설치 상태를 확인하세요."})
        threading.Thread(target=read_results, daemon=True).start()

    def _collect(self, request):
        key = json.dumps(request, sort_keys=True)
        if key in self._cache:
            return deepcopy(self._cache[key])
        try:
            self._start()
            self._process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
            result = self._responses.get(timeout=100 + 8 * request["max_pages"])
        except queue.Empty:
            self.close()
            result = {"error": "브라우저 검색 응답 시간이 초과됐습니다."}
        except (OSError, ValueError):
            self.close()
            result = {"error": "검색 브라우저를 시작하거나 연결하지 못했습니다. Chrome 설치 상태를 확인하세요."}
        self.request_count += result.get("requests", 0)
        if result.get("error"):
            label = f"page:{request['page_id']}" if request.get("page_id") else request["query"]
            self.failed_queries.append(label)
            self.last_error = {"source": "browser", "message": result["error"]}
            raise AdLibraryBlocked(result["error"])
        ads = AdCollection()
        self.last_error = {}
        if result.get("warning"):
            self.last_error = {"source": "browser", "message": result["warning"]}
        cutoff = request.get("started_before")
        for ad in result["ads"]:
            self.remember_page(ad.get("page_id"), ad.get("page_name"))
            if cutoff:
                value = ad.get("start_date")
                try:
                    started = datetime.fromtimestamp(int(value)).date() if str(value).isdigit() else date.fromisoformat(str(value)[:10])
                except (ValueError, TypeError, OSError, OverflowError):
                    # 일자 미상 광고는 기존 분석기의 기간 검사에서 제외합니다.
                    started = None
                if started and started > date.fromisoformat(cutoff):
                    continue
            ads.append(ad)
        for field in ("pages_collected", "has_next_page", "stop_reason"):
            setattr(ads, field, result[field])
        if ads.stop_reason in ("", "page_limit"):
            self._cache[key] = deepcopy(ads)
        return ads

    def search(self, query, *, search_type="keyword_unordered", active_status="active", started_before=None, max_pages=3):
        cutoff = started_before.isoformat() if hasattr(started_before, "isoformat") else started_before
        return self._collect(dict(query=query, country=self.country, search_type=search_type,
                                  active_status=active_status, started_before=cutoff, max_pages=max(1, int(max_pages))))

    def page_ads(self, page_id, *, active_status="active", max_pages=1):
        found = self._collect(dict(query="", country=self.country, search_type="page", page_id=str(page_id),
                                   active_status=active_status, max_pages=max(1, int(max_pages))))
        name = self._page_names.get(str(page_id))
        if found or not name:
            return found
        # 프로필 주소의 ID로 직접 조회하면 0개가 나오는 계정이 있습니다.
        # 계정명을 검색하고 동일 계정의 광고만 남기되, 전체 조회 완료로 취급하지 않습니다.
        searched = self.search(name, active_status=active_status, max_pages=max_pages)
        matched = deepcopy(searched)
        matched[:] = [ad for ad in searched if str(ad.get("page_id")) == str(page_id)]
        matched.has_next_page = True
        matched.stop_reason = "account_name_fallback"
        return matched

    def remember_page(self, page_id, name):
        if page_id and name:
            self._page_names[str(page_id)] = str(name)

    def close(self):
        process = self._process
        if process is None:
            return
        try:
            process.stdin.write('{"close":true}\n')
            process.stdin.flush()
            process.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            process.kill()
            process.wait(timeout=5)
        finally:
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except OSError:
                    pass
            self._process = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
