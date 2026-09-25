# Project notes for Claude

## Organizational X-Ray (main app)

The whole app is one file: `organizational_xray/app.py` (Streamlit).

When the user asks to run / start / open the app (e.g. "شغّل البرنامج", "run", "اعمل run"):

1. From the repo root, run it as a **background** process (it is a long-running server; do not wait for it to exit):
   ```bash
   cd organizational_xray && python app.py
   ```
   On Windows use `py -3 app.py` if `python` is not found; on macOS/Linux use `python3` if needed.
   On first run `app.py` installs any missing packages itself (streamlit, pandas, numpy, plotly,
   networkx, openpyxl, Faker), then relaunches through Streamlit.
2. Wait until the output shows `Local URL: http://localhost:8501`, then tell the user to open
   http://localhost:8501 (Streamlit usually opens the browser automatically).
3. If port 8501 is busy: `python app.py --server.port 8502`.
4. To stop the app, stop that background process (Ctrl+C in its terminal).

Other commands (run from `organizational_xray/`):
- Tests: `python -m pytest -q` (install with `pip install -r requirements.txt` first).
- Regenerate the sample dataset + report: `python app.py --generate`.

Requires Python 3.11+ (developed on 3.12). No database or external API is needed.

## Legacy HR dashboard

`data_generator.py` at the repo root (run with `python data_generator.py`), and a static
`hr_dashboard.html` that opens directly in a browser.
