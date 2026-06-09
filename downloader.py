import os
import re
import sys
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET

# Configuration
SITEMAP_URL = "https://flagdownload.com/post-sitemap.xml"
OUTPUT_DIR = "downloads"
MAX_WORKERS = 10  # Number of concurrent page parsers/downloads

# Define styles and their corresponding resolution preference
# We will look for 1024px or fall back to whatever is available
STYLES = {
    "normal": {
        "pattern": re.compile(r"https://flagdownload\.com/wp-content/uploads/Flag_of_[A-Za-z0-9_%-]+-1024x\d+\.png"),
        "fallback": re.compile(r"https://flagdownload\.com/wp-content/uploads/Flag_of_[A-Za-z0-9_%-]+\.png")
    },
    "round": {
        "pattern": re.compile(r"https://flagdownload\.com/wp-content/uploads/Flag_of_[A-Za-z0-9_%-]+_Flat_Round-1024x1024\.png"),
        "fallback": re.compile(r"https://flagdownload\.com/wp-content/uploads/Flag_of_[A-Za-z0-9_%-]+_Flat_Round\.png")
    },
    "round_corner": {
        "pattern": re.compile(r"https://flagdownload\.com/wp-content/uploads/Flag_of_[A-Za-z0-9_%-]+_Flat_Round_Corner-1024x1024\.png"),
        "fallback": re.compile(r"https://flagdownload\.com/wp-content/uploads/Flag_of_[A-Za-z0-9_%-]+_Flat_Round_Corner\.png")
    },
    "square": {
        "pattern": re.compile(r"https://flagdownload\.com/wp-content/uploads/Flag_of_[A-Za-z0-9_%-]+_Flat_Square-1024x1024\.png"),
        "fallback": re.compile(r"https://flagdownload\.com/wp-content/uploads/Flag_of_[A-Za-z0-9_%-]+_Flat_Square\.png")
    },
    "wavy": {
        "pattern": re.compile(r"https://flagdownload\.com/wp-content/uploads/Flag_of_[A-Za-z0-9_%-]+_Flat_Wavy-1024x\d+\.png"),
        "fallback": re.compile(r"https://flagdownload\.com/wp-content/uploads/Flag_of_[A-Za-z0-9_%-]+_Flat_Wavy\.png")
    }
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def fetch_url(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read()
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def get_flag_pages():
    print(f"Fetching sitemap: {SITEMAP_URL}...")
    sitemap_data = fetch_url(SITEMAP_URL)
    if not sitemap_data:
        print("Failed to download sitemap.")
        return []
    
    try:
        # Parse sitemap XML
        root = ET.fromstring(sitemap_data)
        # XML namespaces
        ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = []
        for url_node in root.findall("ns:url", ns):
            loc = url_node.find("ns:loc", ns)
            if loc is not None and loc.text:
                url = loc.text.strip()
                # Filter to only keep flag pages, e.g., flag-of-...
                if "flag-of-" in url:
                    urls.append(url)
        return urls
    except Exception as e:
        print(f"Error parsing sitemap XML: {e}")
        # Fallback regex if XML parsing fails
        urls = re.findall(r"<loc>(https://flagdownload\.com/flag-of-[^<]+)</loc>", sitemap_data.decode('utf-8', errors='ignore'))
        return urls

def download_image(img_url, filepath):
    if os.path.exists(filepath):
        # Skip if already exists
        return True
    
    img_data = fetch_url(img_url)
    if img_data:
        try:
            with open(filepath, "wb") as f:
                f.write(img_data)
            return True
        except Exception as e:
            print(f"Error saving {filepath}: {e}")
    return False

def process_flag_page(page_url, selected_styles):
    html_bytes = fetch_url(page_url)
    if not html_bytes:
        return
    
    html = html_bytes.decode('utf-8', errors='ignore')
    
    # Extract slug/name from page URL (e.g. flag-of-belarus)
    slug = page_url.strip("/").split("/")[-1]
    
    # Find all anchor hrefs and image sources
    urls_in_page = re.findall(r'href=["\'](https?://[^"\']+)["\']', html)
    urls_in_page += re.findall(r'src=["\'](https?://[^"\']+)["\']', html)
    urls_in_page = list(set(urls_in_page))
    
    for style_name in selected_styles:
        style_cfg = STYLES[style_name]
        
        # Try primary pattern first (usually -1024x...)
        matching_urls = [u for u in urls_in_page if style_cfg["pattern"].match(u)]
        
        # If not found, try fallback pattern
        if not matching_urls:
            matching_urls = [u for u in urls_in_page if style_cfg["fallback"].match(u)]
            
        if matching_urls:
            # Pick the first match
            img_url = matching_urls[0]
            
            # Determine extension
            ext = ".png"
            if img_url.lower().endswith(".jpg"):
                ext = ".jpg"
            elif img_url.lower().endswith(".svg"):
                ext = ".svg"
                
            filename = f"{slug}{ext}"
            filepath = os.path.join(OUTPUT_DIR, style_name, filename)
            
            success = download_image(img_url, filepath)
            if success:
                print(f"Downloaded [{style_name}]: {filename}")
            else:
                print(f"Failed to download {img_url}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="World Flags Downloader")
    parser.add_argument(
        "--styles", 
        type=str, 
        help="Comma-separated list of styles to download (e.g. normal,round,square,wavy,round_corner) or 'all'."
    )
    parser.add_argument(
        "--workers", 
        type=int, 
        default=MAX_WORKERS, 
        help=f"Number of concurrent workers (default: {MAX_WORKERS})"
    )
    args = parser.parse_args()

    style_list = list(STYLES.keys())
    
    if args.styles:
        user_choice = args.styles.strip().lower()
    else:
        print("=== World Flags Downloader ===")
        print("Available styles:")
        for idx, style in enumerate(style_list, 1):
            print(f" {idx}. {style}")
        
        print("\nSelect styles to download (comma separated, e.g. 1,2 or type 'all'):")
        user_choice = input("> ").strip().lower()
    
    selected_styles = []
    if user_choice == "all" or not user_choice:
        selected_styles = style_list
    else:
        parts = [p.strip() for p in user_choice.split(",")]
        for part in parts:
            try:
                idx = int(part) - 1
                if 0 <= idx < len(style_list):
                    selected_styles.append(style_list[idx])
            except ValueError:
                if part in style_list:
                    selected_styles.append(part)
                    
    if not selected_styles:
        print("No valid styles selected. Exiting.")
        return
        
    print(f"Selected styles: {', '.join(selected_styles)}")
    
    # Create folders
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for style in selected_styles:
        os.makedirs(os.path.join(OUTPUT_DIR, style), exist_ok=True)
        
    pages = get_flag_pages()
    if not pages:
        print("No flag pages found.")
        return
        
    print(f"Found {len(pages)} flag pages. Starting download using {args.workers} threads...")
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_flag_page, page, selected_styles): page for page in pages}
        
        try:
            for future in as_completed(futures):
                page = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"Error processing page {page}: {e}")
        except KeyboardInterrupt:
            print("\nDownload cancelled by user. Exiting...")
            executor.shutdown(wait=False)
            sys.exit(1)
            
    print("\nDone! All selected flags have been processed and downloaded.")

if __name__ == "__main__":
    main()
