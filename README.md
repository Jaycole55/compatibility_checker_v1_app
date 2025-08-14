# Compatibility Checker (v1)

A Streamlit app that checks product compatibility for common electrical categories.
Focus: **panel ↔ breaker**, **plug ↔ receptacle**, **enclosure NEMA rating**, and **EV charger ↔ circuit sizing**.
Designed for conversion: remove doubt, surface compatible families, and suggest next steps.

## What it does (v1)
- Parse pasted product info (or HTML) into a structured spec guess.
- Offer a *URL input* placeholder for future crawling (disabled by default).
- Run rule-based checks using a conservative dataset (brands/series).
- Generate a shareable compatibility report.
- Provide CTA links you can wire to your ecommerce PDPs later.

> **Important**: Data is intentionally conservative. Always validate with manufacturer docs and local codes.
> Expand `data/compatibility_rules.json` to add more brands/series and internal SKUs.

## Quickstart (local)
```bash
# 1) Create & activate a venv (macOS)
python3 -m venv .venv
source .venv/bin/activate

# 2) Install deps
pip install -r requirements.txt

# 3) Run the app
streamlit run app.py
```

App opens at: http://localhost:8501

## Deploy to GitHub
```bash
# from the project root
git init
git add .
git commit -m "compatibility-checker v1"
# create a new GitHub repo manually or via CLI, then:
git branch -M main
git remote add origin <YOUR_GITHUB_REPO_URL>
git push -u origin main
```

## Deploy to Streamlit Community Cloud
1. Go to https://share.streamlit.io
2. Connect your GitHub account.
3. Choose the repo and `main` branch.
4. Set the app file path to `app.py`.
5. Click Deploy.

## Customize for CES
- Replace CTA URLs in `app.py` to point to your category/product routes.
- Expand `compatibility_rules.json` with more series & internal SKU mapping.
- Optionally add a CSV/JSON of your catalog to power *in-stock* recommendations.
- When robots are allowed, wire the URL mode to your internal API or a controlled fetcher.

---

**Disclaimer**: This tool is an aid and not a substitute for manufacturer instructions or code compliance. Verify all selections with official documentation and local requirements.
