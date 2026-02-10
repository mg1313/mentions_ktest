import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote

def extract_okru_url_from_page(page_url):
    """
    Extract OK.ru video URL from a page containing embedded video
    """
    response = requests.get(page_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    okru_urls = []
    
    # Method 1: Find iframe embeds
    iframes = soup.find_all('iframe')
    for iframe in iframes:
        src = iframe.get('src', '')
        if 'ok.ru' in src:
            # Extract the actual video URL from embed URL
            video_url = extract_from_embed_url(src)
            if video_url:
                okru_urls.append(video_url)
    
    # Method 2: Find direct links in the page
    links = soup.find_all('a', href=re.compile(r'ok\.ru'))
    for link in links:
        href = link.get('href', '')
        if '/video/' in href:
            okru_urls.append(href)
    
    # Method 3: Search in script tags for embedded players
    scripts = soup.find_all('script')
    for script in scripts:
        if script.string:
            # Look for OK.ru URLs in JavaScript
            matches = re.findall(r'https?://(?:www\.)?ok\.ru/[^\s"\'>]+', script.string)
            okru_urls.extend(matches)
    
    return list(set(okru_urls))  # Remove duplicates

def extract_from_embed_url(embed_url):
    """
    Convert OK.ru embed URL to actual video URL
    
    Embed URLs typically look like:
    https://ok.ru/videoembed/1234567890
    or
    https://ok.ru/videoembed/1234567890?autoplay=1
    
    Actual video URLs look like:
    https://ok.ru/video/1234567890
    """
    
    # Clean up the URL
    embed_url = unquote(embed_url)
    
    # Pattern 1: Direct embed URL
    match = re.search(r'ok\.ru/videoembed/(\d+)', embed_url)
    if match:
        video_id = match.group(1)
        return f'https://ok.ru/video/{video_id}'
    
    # Pattern 2: Already a video URL
    match = re.search(r'ok\.ru/video/(\d+)', embed_url)
    if match:
        return embed_url.split('?')[0]  # Remove query params
    
    # Pattern 3: Extract from player URL
    match = re.search(r'st\.vkuservideo=([^&]+)', embed_url)
    if match:
        video_path = unquote(match.group(1))
        video_id = re.search(r'(\d+)', video_path)
        if video_id:
            return f'https://ok.ru/video/{video_id.group(1)}'
    
    return None

def get_okru_metadata_from_embed(embed_url):
    """
    Fetch the embed page to extract video ID and metadata
    """
    response = requests.get(embed_url)
    
    # OK.ru embeds often have metadata in the page
    video_id_match = re.search(r'"videoId":"(\d+)"', response.text)
    if video_id_match:
        video_id = video_id_match.group(1)
        return {
            'video_id': video_id,
            'url': f'https://ok.ru/video/{video_id}'
        }
    
    # Alternative: look in meta tags
    soup = BeautifulSoup(response.text, 'html.parser')
    og_url = soup.find('meta', property='og:url')
    if og_url and og_url.get('content'):
        return {'url': og_url['content']}
    
    return None

# Usage Examples
def main():
    # Example 1: Extract from a page with embedded video
    page_url = 'https://example.com/page-with-embedded-video'
    okru_urls = extract_okru_url_from_page(page_url)
    print("Found OK.ru URLs:", okru_urls)
    
    # Example 2: Convert embed URL to video URL
    embed_url = 'https://ok.ru/videoembed/1234567890'
    video_url = extract_from_embed_url(embed_url)
    print("Video URL:", video_url)
    
    # Example 3: Get metadata from embed
    metadata = get_okru_metadata_from_embed(embed_url)
    print("Metadata:", metadata)

if __name__ == '__main__':
    main()