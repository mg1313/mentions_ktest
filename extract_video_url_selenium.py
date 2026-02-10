import re

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from extract_video_url_api import extract_from_embed_url


def extract_okru_with_selenium(page_url):
    """
    Use Selenium for pages that load embeds via JavaScript
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1696")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)

    try:
        driver.set_page_load_timeout(20)
        driver.get(page_url)

        # Wait until DOM is available; some pages may not expose iframes immediately.
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            pass

        # Find all iframes
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        okru_urls = []

        for iframe in iframes:
            src = iframe.get_attribute("src")
            if src and "ok.ru" in src:
                video_url = extract_from_embed_url(src)
                if video_url:
                    okru_urls.append(video_url)

        # Also check page source for any OK.ru video/videoembed URLs
        page_source = driver.page_source
        matches = re.findall(r"https?://(?:www\.)?ok\.ru/video(?:embed)?/(\d+)", page_source)
        for video_id in matches:
            okru_urls.append(f"https://ok.ru/video/{video_id}")

        return list(set(okru_urls))

    except WebDriverException:
        # Fail open: let caller continue with other extractors.
        return []

    finally:
        driver.quit()
