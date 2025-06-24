import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup as bs
import json
from urllib.parse import urlparse
import logging
import time
import random
from fake_useragent import UserAgent
import certifi
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================
# CONFIG & LOGGING
# ==========================
logging.basicConfig(
    filename='comment_poster.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

ua = UserAgent()
with open("config.json") as f:
    config = json.load(f)

RETRY_COUNT = config.get("retry_count", 3)
DELAY_MIN = config.get("delay_min", 0.5)
DELAY_MAX = config.get("delay_max", 1)
SSL_VERIFY = config.get("ssl_verify", True)
FORM_FIELD_MAPPINGS = config.get("form_field_mappings", {
    "comment": ["comment", "message", "text", "content", "body"],
    "author": ["author", "name", "username"],
    "email": ["email", "mail"],
    "url": ["url", "website", "site"]
})
SUCCESS_FILE = config.get("success_file", "success.txt")
MAX_WORKERS = config.get("max_workers", 1) #good

# ==========================
# LOAD POST DATA & LINKS
# ==========================
with open("postData.json") as f:
    default_data = json.load(f)

with open("links.txt") as f:
    links = [line.strip() for line in f if line.strip()]

# ==========================
# UTILITY FUNCTIONS
# ==========================
def contains_captcha(soup):
    """Check for common CAPTCHA patterns."""
    captcha_patterns = ["g-recaptcha", "hcaptcha", "captcha", "recaptcha"]
    html = str(soup).lower()
    return any(pattern in html for pattern in captcha_patterns)

def find_comment_form(soup):
    """Find the first form with a <textarea>."""
    for form in soup.find_all("form"):
        if form.find("textarea"):
            return form
    return None

def map_form_fields(form, default_data):
    """Map available inputs to the fields in postData.json."""
    inputs = form.find_all(["input", "textarea"])
    form_data = {}
    for inp in inputs:
        name = inp.get("name")
        if not name:
            continue
        matched = False
        for key, aliases in FORM_FIELD_MAPPINGS.items():
            if any(alias in name.lower() for alias in aliases) and key in default_data:
                form_data[name] = default_data.get(key, "")
                matched = True
                break
        if not matched and inp.get("value"):
            form_data[name] = inp.get("value")
    return form_data

def is_submission_successful(response):
    """Check if the comment submission was successful."""
    text = response.text.lower()
    success_indicators = ["comment", "success", "thank you", "submitted", "posted"]
    return any(indicator in text for indicator in success_indicators) or response.status_code == 302

def setup_session():
    """Setup a requests session with retries."""
    session = requests.Session()
    retries = Retry(total=RETRY_COUNT, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

# ==========================
# MAIN WORKER FUNCTION
# ==========================
def process_link(link):
    """Process a single link for comment posting."""
    session = setup_session()
    headers = {"user-agent": ua.random}
    try:
        r = session.get(link, headers=headers, timeout=10,
                        verify=SSL_VERIFY,
                        cert=certifi.where() if SSL_VERIFY else None)
        if r.status_code != 200:
            logging.warning(f"Skipped link due to status {r.status_code}: {link}")
            return None
    except requests.RequestException as e:
        logging.error(f"Request error for {link}: {e}")
        return None

    soup = bs(r.text, "lxml")

    # 🛡️ CAPTCHA detection
    if contains_captcha(soup):
        logging.warning(f"CAPTCHA detected, skipping link: {link}")
        return None

    form = find_comment_form(soup)
    if not form:
        logging.warning(f"No comment form found: {link}")
        return None

    form_data = map_form_fields(form, default_data)

    link_parse = urlparse(link)
    form_action = form.get("action") or f"{link_parse.scheme}://{link_parse.netloc}/"

    if not form_action.startswith(("http://", "https://")):
        form_action = f"{link_parse.scheme}://{link_parse.netloc}/{form_action.lstrip('/')}"

    method = form.get("method", "post").lower()
    request_func = session.post if method == "post" else session.get

    try:
        resp = request_func(
            form_action,
            data=form_data if method == "post" else None,
            params=form_data if method == "get" else None,
            headers=headers,
            timeout=10,
            verify=SSL_VERIFY,
            cert=certifi.where() if SSL_VERIFY else None
        )
        if is_submission_successful(resp):
            logging.info(f"Comment submitted successfully: {link}")
            with open(SUCCESS_FILE, "a") as f:
                f.write(f"{link}\n")
            print(f"[+] Comment submitted successfully: {link}")

        else:
            logging.warning(f"Comment submission may have failed for {link}")

    except requests.RequestException as e:
        logging.error(f"Submission error for {link}: {e}")

    # Random delay
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


# ==========================
# MAIN LOOP
# ==========================
if __name__ == '__main__':
    logging.info(f"Starting comment poster for {len(links)} links...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_link, link) for link in links]

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Error in thread: {e}")

    logging.info("Script completed.")
    print("[+] All links processed.")
