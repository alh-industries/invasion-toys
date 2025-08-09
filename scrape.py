import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# --- Constants ---
BASE_URL = "https://web.archive.org"
TARGET_DOMAIN = "blog.invasiontoys.com"
OUTPUT_DIR = "scraped_content"
ARTICLES_DIR = os.path.join(OUTPUT_DIR, "articles")
AUTHORS_DIR = os.path.join(OUTPUT_DIR, "authors")
REQUEST_DELAY = 1  # seconds

# --- Helper Functions ---

def sanitize_filename(filename):
    """Sanitizes a string to be used as a valid filename."""
    filename = str(filename).lower()
    filename = filename.encode('ascii', 'ignore').decode('ascii')
    filename = re.sub(r'\s+', '-', filename)
    filename = re.sub(r'[^a-z0-9\.-]', '-', filename)
    filename = re.sub(r'-+', '-', filename)
    return filename.strip('.-')

def get_article_urls_from_cdx():
    """Gets all article URLs from the Wayback Machine's CDX API."""
    print(f"Fetching all URLs for {TARGET_DOMAIN} from CDX API...")
    cdx_url = (
        f"http://web.archive.org/cdx/search/cdx?url={TARGET_DOMAIN}/*&output=json"
        "&fl=original&filter=mimetype:text/html&filter=statuscode:200&collapse=urlkey"
    )

    try:
        response = requests.get(cdx_url, timeout=60)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching from CDX API: {e}")
        return []
    except ValueError:
        print("Error parsing JSON from CDX API response.")
        return []

    urls = [row[0] for row in data[1:]]

    article_urls = []
    excluded_paths = ['/tag/', '/category/', '/author/', '/page/', '/wp-content/', '/wp-includes/', '/wp-login.php', '/authors/', '/submit/', '?rsd']

    for url_str in urls:
        # Strip query parameters
        url_str = urljoin(url_str, urlparse(url_str).path)

        if not url_str or not url_str.startswith('http'):
            continue

        if any(ex_path in url_str for ex_path in excluded_paths):
            continue

        if os.path.splitext(urlparse(url_str).path)[1]:
            continue

        if urlparse(url_str).path in ['/', '']:
            continue

        article_urls.append(url_str)

    article_urls = sorted(list(set(article_urls)))
    print(f"Found {len(article_urls)} potential article URLs after filtering.")
    return article_urls


def scrape_article(article_url):
    """Scrapes a single article page."""
    wayback_url = f"{BASE_URL}/web/*/{article_url}"
    print(f"Scraping article: {wayback_url}")

    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(wayback_url, timeout=30)
        if response.status_code == 404:
            print(f"Article not found (404): {wayback_url}")
            return None
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching article {wayback_url}: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    title_tag = soup.select_one('h1.post__title, h1.entry-title')
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"

    date_tag = soup.select_one('time.published, span.entry-date')
    date = date_tag.get('datetime') if date_tag and date_tag.has_attr('datetime') else (date_tag.get_text(strip=True) if date_tag else "Unknown-Date")

    author_tag = soup.select_one('a.entry-author__name')
    author = author_tag.get_text(strip=True) if author_tag else "Unknown-Author"

    content_html = soup.select_one('div.entry-content')
    if not content_html:
        print(f"No content found for article: {article_url}")
        return None

    content_text = content_html.get_text('\n', strip=True)

    images = []
    for img_tag in content_html.select('img'):
        img_src = img_tag.get('src')
        if img_src:
            full_img_url = urljoin(response.url, img_src)
            images.append(full_img_url)

    categories = {a.get_text(strip=True) for a in soup.select('a[rel="category"]')}
    tags = {a.get_text(strip=True) for a in soup.select('a[rel="tag"]')}

    return {
        "url": article_url,
        "title": title,
        "date": date.split('T')[0],
        "author": author,
        "content": content_text,
        "images": images,
        "categories": list(categories),
        "tags": list(tags)
    }

def save_article(article_data):
    """Saves the scraped article data to the specified directory structure."""
    if not article_data:
        return False

    folder_name = sanitize_filename(f"{article_data['date']}-{article_data['title']}")
    article_dir = os.path.join(ARTICLES_DIR, folder_name)

    if os.path.exists(article_dir):
        print(f"Article already exists, skipping: {folder_name}")
        return False

    os.makedirs(article_dir, exist_ok=True)

    with open(os.path.join(article_dir, "article.md"), "w", encoding="utf-8") as f:
        f.write(f"# {article_data['title']}\n\n")
        f.write(f"**Author:** {article_data['author']}\n")
        f.write(f"**Date:** {article_data['date']}\n\n")
        f.write(article_data['content'])

    for i, img_url in enumerate(article_data['images']):
        try:
            time.sleep(0.2)
            img_response = requests.get(img_url, timeout=15)
            if img_response.status_code == 200:
                img_name = os.path.basename(urlparse(img_url).path)
                img_path = os.path.join(article_dir, sanitize_filename(img_name))
                with open(img_path, "wb") as f:
                    f.write(img_response.content)
            else:
                print(f"Skipping image {img_url}: Status code {img_response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Error downloading image {img_url}: {e}")

    return True

def main():
    """Main function to orchestrate the scraping process."""
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    os.makedirs(AUTHORS_DIR, exist_ok=True)

    all_article_urls = get_article_urls_from_cdx()

    all_tags = set()
    all_categories = set()
    sitemap_entries = []

    if not all_article_urls:
        print("No articles found to scrape. Exiting.")
        return

    for url in all_article_urls:
        article_data = scrape_article(url)
        if article_data:
            if save_article(article_data):
                all_tags.update(article_data['tags'])
                all_categories.update(article_data['categories'])
                folder_name = sanitize_filename(f"{article_data['date']}-{article_data['title']}")
                sitemap_entries.append(f"- [{article_data['title']}]({os.path.join(ARTICLES_DIR, folder_name, 'article.md')})")

    with open(os.path.join(OUTPUT_DIR, "tags.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(list(all_tags))))

    with open(os.path.join(OUTPUT_DIR, "categories.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(list(all_categories))))

    with open(os.path.join(OUTPUT_DIR, "sitemap.md"), "w", encoding="utf-8") as f:
        f.write("# Sitemap\n\n")
        f.write("\n".join(sorted(sitemap_entries)))

    print("\nScraping complete!")


if __name__ == "__main__":
    main()
