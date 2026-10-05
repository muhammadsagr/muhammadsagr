"""ميزان — منصة تحليل المخاطر.

التشغيل من مجلد المشروع:
    python mizan/app.py
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

# عند التشغيل بـ python مباشرة: أعد تشغيل الملف عبر Streamlit ليفتح في المتصفح
if not st.runtime.exists():
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", __file__]))

st.set_page_config(page_title="ميزان — تحليل المخاطر", page_icon="⚖️", layout="wide")
st.markdown("<style>.main, .stMarkdown, .stCaption {direction: rtl; text-align: right;}</style>",
            unsafe_allow_html=True)

views = Path(__file__).parent / "views"
st.navigation([
    st.Page(views / "prices.py", title="الأسعار والعوائد", icon="📈", default=True),
    st.Page(views / "fraud_sim.py", title="محاكاة التهرب والاحتيال", icon="🕵️", url_path="fraud"),
]).run()
