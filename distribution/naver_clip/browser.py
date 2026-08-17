import os
from playwright.sync_api import sync_playwright, BrowserContext

class NaverBrowserSession:
    def __init__(self, headless=False):
        self.headless = headless
        self.profile_dir = os.path.abspath(os.path.join("storage", "browser_profiles", "naver_clip"))
        self._playwright = None
        self.context: BrowserContext = None

    def start(self):
        os.makedirs(self.profile_dir, exist_ok=True)
        self._playwright = sync_playwright().start()
        self.context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"]
        )
        return self.context

    def stop(self):
        if self.context:
            self.context.close()
        if self._playwright:
            self._playwright.stop()

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
