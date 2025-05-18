from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Advanced Email Template Verifier API")

class TemplateRequest(BaseModel):
    url: HttpUrl

# Some simple keywords to detect a test template
TEST_KEYWORDS = [
    "test", "dummy", "lorem ipsum", "sample template",
    "placeholder", "example", "this is a test"
]

# Regex to find company address pattern (a basic one for demo purposes)
ADDRESS_REGEX = re.compile(
    r'\d{1,5}\s+\w+(\s+\w+)*,\s*\w+(\s+\w+)*,\s*\w{2,}\s*\d{5,}', re.IGNORECASE)

@app.post("/verify-template")
def verify_template(data: TemplateRequest):
    try:
        resp = requests.get(data.url, timeout=10)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Unable to fetch URL, status code: {resp.status_code}")

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # 1. Check if it is a test template (search keywords in text)
        text_content = soup.get_text(separator=" ", strip=True).lower()
        is_test_template = any(keyword in text_content for keyword in TEST_KEYWORDS)

        # 2. Calculate image to text proportion (rough estimate by length)
        total_text_len = len(text_content)
        total_img_len = sum(len(str(img)) for img in soup.find_all("img"))

        # To avoid division by zero
        if total_text_len == 0:
            image_text_ratio = float('inf')  # All images, no text
        else:
            image_text_ratio = total_img_len / total_text_len

        # 3. Validate all clickable links
        links = soup.find_all("a", href=True)
        broken_links = []
        for link in links:
            href = link['href']
            # Only check absolute HTTP/HTTPS links
            if href.startswith("http://") or href.startswith("https://"):
                try:
                    r = requests.head(href, allow_redirects=True, timeout=5)
                    if r.status_code >= 400:
                        broken_links.append(href)
                except requests.RequestException:
                    broken_links.append(href)

        # 4. Footer checks
        footer = soup.find("footer")
        footer_link_valid = False
        footer_address_found = False

        if footer:
            # Check footer clickable links
            footer_links = footer.find_all("a", href=True)
            for f_link in footer_links:
                href = f_link['href']
                if href.startswith("http://") or href.startswith("https://"):
                    try:
                        r = requests.head(href, allow_redirects=True, timeout=5)
                        if r.status_code < 400:
                            footer_link_valid = True
                            break
                    except:
                        pass
            # Check footer text for company address (simple regex match)
            footer_text = footer.get_text(separator=" ", strip=True)
            if ADDRESS_REGEX.search(footer_text):
                footer_address_found = True

        else:
            footer_link_valid = False
            footer_address_found = False

        result = {
            "status": "success",
            "url": data.url,
            "checks": {
                "is_test_template": is_test_template,
                "image_text_ratio": image_text_ratio,
                "image_text_ratio_ok": 0.1 <= image_text_ratio <= 2.0,  # roughly balanced
                "broken_links": broken_links,
                "all_links_valid": len(broken_links) == 0,
                "footer_link_valid": footer_link_valid,
                "footer_address_found": footer_address_found,
            },
            "content_length": len(html),
            "preview_snippet": html[:300]
        }

        # Fail the verification if test template or footer checks fail
        if is_test_template:
            result["verification"] = "fail"
            result["message"] = "The template appears to be a test/dummy template."
        elif not result["checks"]["all_links_valid"]:
            result["verification"] = "fail"
            result["message"] = "One or more clickable links are broken."
        elif not footer_link_valid or not footer_address_found:
            result["verification"] = "fail"
            result["message"] = "Footer is missing a valid clickable website link or full company address."
        elif not result["checks"]["image_text_ratio_ok"]:
            result["verification"] = "warning"
            result["message"] = "Image to text ratio is not balanced."
        else:
            result["verification"] = "pass"
            result["message"] = "Template passed all basic standard checks."

        return result

    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {e}")
