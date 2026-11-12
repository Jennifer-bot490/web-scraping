# SiteScout

Enter a website address and get its pages, services, purpose and contact info.

## Run in VS Code

1. Open the `sitescout` folder in VS Code (File > Open Folder).
2. Open the terminal (Ctrl+`) and create a virtual environment:
   - Windows: `python -m venv venv` then `venv\Scripts\activate`
   - Mac/Linux: `python3 -m venv venv` then `source venv/bin/activate`
3. Install packages: `pip install -r requirements.txt`
4. Start the server: `python app.py`
5. Open http://127.0.0.1:5000 in your browser.

## Structure

- `app.py` - Flask backend: crawls the site (same domain only) and extracts data
- `static/index.html`, `style.css`, `script.js` - the frontend

## Notes

- Only scans pages on the same domain, up to 30 pages.
- Sites that load content with JavaScript, or block bots, may return little data.
- Only scan sites you have permission to scan, and respect their terms and robots.txt.
