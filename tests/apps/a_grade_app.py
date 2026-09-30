"""AppTest용 최소 앱: A급 탭만 그립니다."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from a_grade_view import render_a_grade_view  # noqa: E402

render_a_grade_view()
