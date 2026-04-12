"""
ERA TecDoc data scraper - Quick extraction test.
Extracts a small sample of data to demonstrate structure.
"""
import json
import re
import time

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://ecom.eraspares.es/ec"
OUTPUT_FILE = "era_sample_data.json"


def fetch_page(url: str, params: dict = None) -> BeautifulSoup:
    """Fetch a page and return BeautifulSoup object."""
    response = requests.get(
        url, 
        params=params, 
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "es-ES,es;q=0.9",
        }
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def extract_categories(soup: BeautifulSoup) -> list[dict]:
    """Extract categories from area page."""
    categories = []
    for link in soup.find_all("a", href=re.compile(r"TabelloneArea\.asp\?IdArea=\d+")):
        href = link.get("href", "")
        match = re.search(r"IdArea=(\d+)", href)
        if match:
            area_id = int(match.group(1))
            name = link.get_text(strip=True)
            
            parent_td = link.find_parent("td")
            count_text = ""
            if parent_td:
                next_td = parent_td.find_next_sibling("td")
                if next_td:
                    count_text = next_td.get_text(strip=True)
            
            try:
                count = int(count_text) if count_text.isdigit() else 0
            except ValueError:
                count = 0
            
            if area_id > 0 and name and name not in ["-", "HOJEAR CATÁLOGO"]:
                categories.append({
                    "area_id": area_id,
                    "name": name,
                    "product_count": count,
                })
    
    return categories


def extract_products(soup: BeautifulSoup, area_id: int, category_path: list[str]) -> list[dict]:
    """Extract products from a listing page."""
    products = []
    
    for table in soup.find_all("table", class_="TabRubrica"):
        reference_link = table.find("a", href=re.compile(r"print\.asp\?referenza="))
        if not reference_link:
            continue
        
        href = reference_link.get("href", "")
        match = re.search(r"referenza=([A-Z0-9]+)", href)
        if not match:
            continue
        
        reference = match.group(1)
        
        desc_elem = table.find("td", class_="TabRubricaDesc")
        description = desc_elem.get_text(strip=True) if desc_elem else ""
        
        attributes = {}
        for label in table.find_all("td", class_="TabRubricaInt"):
            label_text = label.get_text(strip=True)
            if "  " in label_text:
                parts = label_text.split("  ")
                if len(parts) == 2:
                    attr_name = parts[0].strip().rstrip(" ")
                    attr_value = parts[1].strip()
                    if attr_name and attr_value:
                        attributes[attr_name] = attr_value
        
        products.append({
            "reference": reference,
            "brand": "ERA",
            "description": description,
            "area_id": area_id,
            "category_path": category_path,
            "attributes": attributes,
            "oe_numbers": [],
            "applications": [],
        })
    
    return products


def main():
    """Main extraction function."""
    print("ERA TecDoc Data Extraction")
    print("=" * 50)
    
    all_data = {
        "source": "ERA TecDoc Electronic Catalog",
        "url": BASE_URL,
        "extraction_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "categories": [],
        "products": [],
    }
    
    print("\n1. Extracting main categories...")
    soup = fetch_page(f"{BASE_URL}/TabelloneArea.asp", {"IdArea": 0})
    
    categories = extract_categories(soup)
    print(f"   Found {len(categories)} main categories")
    
    all_data["categories"] = categories
    
    main_cats_to_scrape = [
        cat for cat in categories 
        if cat["product_count"] > 0 and cat["product_count"] < 500
    ][:10]
    
    print(f"\n2. Extracting products from {len(main_cats_to_scrape)} categories...")
    
    for i, cat in enumerate(main_cats_to_scrape):
        print(f"   [{i+1}/{len(main_cats_to_scrape)}] {cat['name']}...", end=" ", flush=True)
        
        try:
            soup = fetch_page(
                f"{BASE_URL}/TabelloneArea.asp",
                {"IdArea": cat["area_id"]}
            )
            
            sub_categories = extract_categories(soup)
            category_path = [cat["name"]]
            
            if sub_categories:
                first_sub = sub_categories[0]
                soup = fetch_page(
                    f"{BASE_URL}/TabelloneArea.asp",
                    {"IdArea": first_sub["area_id"]}
                )
                category_path.append(first_sub["name"])
            
            products = extract_products(soup, cat["area_id"], category_path)
            print(f"{len(products)} products")
            
            all_data["products"].extend(products)
            
            if len(all_data["products"]) >= 100:
                break
                
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error: {e}")
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n3. Data saved to {OUTPUT_FILE}")
    print(f"   Categories: {len(all_data['categories'])}")
    print(f"   Products: {len(all_data['products'])}")
    
    if all_data["products"]:
        print("\nSample product:")
        sample = all_data["products"][0]
        print(f"   Reference: {sample['reference']}")
        print(f"   Description: {sample['description']}")
        print(f"   Category: {' > '.join(sample['category_path'])}")
        if sample['attributes']:
            print(f"   Attributes: {sample['attributes']}")


if __name__ == "__main__":
    main()
