# AGENTS.md: Invasion Toys Blog Scraper

This document outlines the process for scraping articles from the deprecated `blog.invasiontoys.com`, as archived on the Wayback Machine.

## Project Goal

The goal of this project is to scrape all articles from the blog. The scraped content, including text and images, should be organized into a specific directory structure.

## Directory Structure

The scraped content will be organized as follows:

```
/
├── scraped_content/
│   ├── articles/
│   │   ├── YYYY-MM-DD-article-title/
│   │   │   ├── article.md
│   │   │   ├── image1.jpg
│   │   │   └── image2.png
│   │   └── ...
│   ├── authors/
│   ├── categories.txt
│   ├── tags.txt
│   └── sitemap.md
```

- **`articles/`**: Contains a directory for each scraped article.
  - Each article directory is named using the format `YYYY-MM-DD-article-title`.
  - Inside each article directory:
    - `article.md`: The full text of the article in Markdown format.
    - `image1.jpg`, `image2.png`, etc.: All images from the article.
- **`authors/`**: This directory is created but may not be populated, as author information is now scraped from each article individually.
- **`categories.txt`**: A file containing a list of all unique categories found across all articles.
- **`tags.txt`**: A file containing a list of all unique tags found across all articles.
- **`sitemap.md`**: A Markdown file that provides a list of all scraped articles, with links to the local `article.md` files.

## Setup

This project requires Python 3. The necessary libraries can be installed using pip:

```bash
pip install requests beautifulsoup4
```

## Workflow

The scraping process is handled by the `scrape.py` script. To run it, simply execute the following command in your terminal:

```bash
python scrape.py
```

The script will:
1.  Create the necessary directories (`scraped_content/articles/`, `scraped_content/authors/`).
2.  Query the Wayback Machine's CDX API to get a list of all URLs captured for `blog.invasiontoys.com`.
3.  Filter this list to identify unique article URLs.
4.  For each article URL:
    - Scrape the title, date, author, content, images, categories, and tags.
    - Create a new directory for the article under `articles/`.
    - Save the article text to `article.md`.
    - Download and save all images to the article's directory.
5.  Compile and save all unique categories and tags into `categories.txt` and `tags.txt`.
6.  Generate a `sitemap.md` with links to all the scraped articles.

### Rate Limiting

To avoid being rate-limited or blocked by the Wayback Machine's servers, the script includes a `REQUEST_DELAY` constant (set to 1 second by default) that pauses the execution between requests. Please be patient, as scraping all the articles may take some time. If you encounter network errors, you can try increasing this delay in the `scrape.py` script.
