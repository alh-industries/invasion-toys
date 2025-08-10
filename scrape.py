import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Constants ---
BASE_URL = "https://web.archive.org"
TARGET_DOMAIN = "blog.invasiontoys.com"
OUTPUT_DIR = "scraped_content"
ARTICLES_DIR = os.path.join(OUTPUT_DIR, "articles")
AUTHORS_DIR = os.path.join(OUTPUT_DIR, "authors")
REQUEST_DELAY = 1  # seconds
AUTHOR_ALIASES = {
    "brianbakerdigital": "99darwin"
}

# --- Helper Functions ---

def sanitize_filename(filename):
    """Sanitizes a string to be used as a valid filename."""
    filename = str(filename).lower()
    filename = filename.encode('ascii', 'ignore').decode('ascii')
    filename = re.sub(r'\s+', '-', filename)
    filename = re.sub(r'[^a-z0-9\.-]', '-', filename)
    filename = re.sub(r'-+', '-', filename)
    return filename.strip('.-')

def create_session_with_retries():
    """Creates a requests.Session with retry logic."""
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_article_urls(session):
    """Gets all article URLs from the Wayback Machine using the CDX API."""
    print(f"Fetching all URLs for {TARGET_DOMAIN} from CDX API...")
    cdx_url = (
        f"http://web.archive.org/cdx/search/cdx?url={TARGET_DOMAIN}/*&output=json"
        "&fl=timestamp,original&filter=mimetype:text/html&filter=statuscode:200&collapse=urlkey"
    )

    try:
        response = session.get(cdx_url, timeout=60)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching from CDX API: {e}")
        return []
    except ValueError:
        print("Error parsing JSON from CDX API response.")
        return []

    # Skip header row and process data
    article_snapshots = [tuple(row) for row in data[1:]]

    filtered_articles = []
    seen_urls = set()
    excluded_paths = ['/tag/', '/category/', '/author/', '/page/', '/wp-content/', '/wp-includes/', '/wp-login.php', '/authors/', '/submit/', '?rsd']

    # Iterate in reverse to get the latest snapshots first
    for timestamp, url_str in reversed(article_snapshots):
        # Normalize URL to remove query parameters for uniqueness
        normalized_url = urljoin(url_str, urlparse(url_str).path)

        if not normalized_url or not normalized_url.startswith('http'):
            continue

        if normalized_url in seen_urls:
            continue

        path = urlparse(normalized_url).path
        if any(ex_path in path for ex_path in excluded_paths):
            continue

        # Exclude URLs with file extensions (like .xml, .css)
        if os.path.splitext(path)[1]:
            continue

        # Exclude root path
        if path in ['/', '']:
            continue

        filtered_articles.append((timestamp, normalized_url))
        seen_urls.add(normalized_url)

    # The CDX API with collapse=urlkey should already return unique URLs, but this adds extra safety.
    print(f"Found {len(filtered_articles)} potential article URLs after filtering.")
    return filtered_articles


def scrape_article(timestamp, article_url, session):
    """Scrapes a single article page."""
    wayback_url = f"{BASE_URL}/web/{timestamp}/{article_url}"
    print(f"Scraping article: {wayback_url}")

    try:
        time.sleep(REQUEST_DELAY) # Keep a small polite delay
        response = session.get(wayback_url, timeout=30)


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

    # Normalize author name
    author_slug = sanitize_filename(author)
    if author_slug in AUTHOR_ALIASES:
        author = AUTHOR_ALIASES[author_slug]

    content_html = soup.select_one('div.single-body--content')
    if not content_html:
        print(f"No content found for article: {article_url}")
        return None

    # Remove any unwanted elements from content, like share buttons
    for unwanted_element in content_html.select('.sharedaddy, .jp-relatedposts'):
        unwanted_element.decompose()

    content_text = content_html.get_text('\n', strip=True)

    images = []
    for img_tag in content_html.select('img'):
        img_src = img_tag.get('src')
        if img_src:
            # Ensure the image URL is absolute
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

def save_article(article_data, session):
    """Saves the scraped article data to the specified directory structure."""
    if not article_data:
        return False

    folder_name = sanitize_filename(f"{article_data['date']}-{article_data['title']}")
    article_dir = os.path.join(ARTICLES_DIR, folder_name)

    if os.path.exists(article_dir):
        print(f"Article already exists, skipping: {folder_name}")
        return False

    os.makedirs(article_dir, exist_ok=True)

    # Save article markdown
    with open(os.path.join(article_dir, "article.md"), "w", encoding="utf-8") as f:
        f.write(f"# {article_data['title']}\n\n")
        f.write(f"**Author:** {article_data['author']}\n")
        f.write(f"**Date:** {article_data['date']}\n\n")
        f.write(article_data['content'])

    # Download and save images
    for img_url in article_data['images']:
        try:
            time.sleep(0.2) # Small delay to be polite
            img_response = session.get(img_url, timeout=20, stream=True)
            img_response.raise_for_status()

            # Sanitize image filename
            img_name = os.path.basename(urlparse(img_url).path)
            img_path = os.path.join(article_dir, sanitize_filename(img_name))

            with open(img_path, "wb") as f:
                for chunk in img_response.iter_content(chunk_size=8192):
                    f.write(chunk)
        except requests.exceptions.RequestException as e:
            print(f"Error downloading image {img_url}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred while saving image {img_url}: {e}")

    return True

def main():
    """Main function to orchestrate the scraping process."""
    print("Starting the scraping process...")
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    os.makedirs(AUTHORS_DIR, exist_ok=True)

    session = create_session_with_retries()
    all_article_urls = get_article_urls(session)

    if not all_article_urls:
        print("No articles found to scrape. Exiting.")
        return

    all_tags = set()
    all_categories = set()
    sitemap_entries = []

    print(f"\nScraping {len(all_article_urls)} articles...")
    for timestamp, url in all_article_urls:
        article_data = scrape_article(timestamp, url, session)
        if article_data:
            if save_article(article_data, session):
                all_tags.update(article_data['tags'])
                all_categories.update(article_data['categories'])
                folder_name = sanitize_filename(f"{article_data['date']}-{article_data['title']}")
                relative_path = os.path.join('articles', folder_name, 'article.md')
                sitemap_entries.append(f"- [{article_data['title']}]({relative_path})")

    # Save metadata
    with open(os.path.join(OUTPUT_DIR, "tags.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(list(all_tags))))

    with open(os.path.join(OUTPUT_DIR, "categories.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(list(all_categories))))

    with open(os.path.join(OUTPUT_DIR, "sitemap.md"), "w", encoding="utf-8") as f:
        f.write("# Sitemap\n\n")
        f.write("\n".join(sorted(sitemap_entries)))

    print("\nScraping complete!")
    print(f"Total articles scraped: {len(sitemap_entries)}")
    print(f"Total unique tags: {len(all_tags)}")
    print(f"Total unique categories: {len(all_categories)}")


if __name__ == "__main__":
    main()
