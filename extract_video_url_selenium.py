from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re

from extract_video_url_api import extract_from_embed_url


def extract_okru_with_selenium(page_url):
    """
    Use Selenium for pages that load embeds via JavaScript
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get(page_url)
        
        # Wait for iframes to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "iframe"))
        )
        
        # Find all iframes
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        okru_urls = []
        
        for iframe in iframes:
            src = iframe.get_attribute('src')
            if src and 'ok.ru' in src:
                video_url = extract_from_embed_url(src)
                if video_url:
                    okru_urls.append(video_url)
        
        # Also check page source for any OK.ru URLs
        page_source = driver.page_source
        matches = re.findall(r'https?://(?:www\.)?ok\.ru/video(?:embed)?/(\d+)', page_source)
        for video_id in matches:
            okru_urls.append(f'https://ok.ru/video/{video_id}')
        
        return list(set(okru_urls))
    
    finally:
        driver.quit()
