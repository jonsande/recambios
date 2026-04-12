"""
ERA TecDoc data scraper.
Extracts vehicle compatibility and product data from ERA electronic catalog.
"""
import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://ecom.eraspares.es/ec"
OUTPUT_DIR = Path(__file__).parent.parent.parent.parent.parent.parent.parent.parent / "era_data"
CACHE_DIR = OUTPUT_DIR / "cache"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
})


@dataclass
class VehicleType:
    """Represents a vehicle type (TecDoc Type)."""
    type_id: int
    brand_name: str
    model_name: str
    type_name: str
    engine_code: str
    power_kw: int
    power_hp: int
    year_from: str
    year_to: str
    displacement: int
    fuel_type: str


@dataclass
class ProductApplication:
    """Vehicle application for a product."""
    brand: str
    models: list[str]


@dataclass
class Product:
    """ERA product with OE numbers and applications."""
    reference: str
    brand: str
    description: str
    category_path: list[str]
    category_ids: list[int]
    oe_numbers: list[str]
    comparison_numbers: list[str]
    applications: list[dict]
    attributes: dict
    image_url: Optional[str]


def fetch_page(url: str, params: dict = None) -> Optional[BeautifulSoup]:
    """Fetch a page and return BeautifulSoup object."""
    try:
        response = SESSION.get(url, params=params, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def extract_categories(soup: BeautifulSoup) -> list[dict]:
    """Extract category tree from area page."""
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
            
            if area_id > 0 and name and name != "-":
                categories.append({
                    "area_id": area_id,
                    "name": name,
                    "product_count": count,
                    "url": f"{BASE_URL}/TabelloneArea.asp?IdArea={area_id}",
                })
    
    return categories


def extract_products_from_page(soup: BeautifulSoup) -> list[dict]:
    """Extract products from a product listing page."""
    products = []
    
    tables = soup.find_all("table", class_="TabRubrica")
    
    for table in tables:
        reference_cell = table.find("a", href=re.compile(r"print\.asp\?referenza="))
        if not reference_cell:
            continue
        
        href = reference_cell.get("href", "")
        match = re.search(r"referenza=([A-Z0-9]+)", href)
        if not match:
            continue
        
        reference = match.group(1)
        
        desc_elem = table.find("td", class_="TabRubricaDesc")
        description = desc_elem.get_text(strip=True) if desc_elem else ""
        
        brand = "ERA"
        
        category_path = []
        category_ids = []
        for crumb in soup.find_all("a", href=re.compile(r"TabelloneArea\.asp\?IdArea=")):
            crumb_href = crumb.get("href", "")
            crumb_match = re.search(r"IdArea=(\d+)", crumb_href)
            if crumb_match:
                category_ids.append(int(crumb_match.group(1)))
            crumb_text = crumb.get_text(strip=True)
            if crumb_text and crumb_text != "HOJEAR CATÁLOGO":
                category_path.append(crumb_text)
        
        oe_numbers = []
        comparison_numbers = []
        applications = []
        attributes = {}
        
        products.append({
            "reference": reference,
            "brand": brand,
            "description": description,
            "category_path": category_path,
            "category_ids": category_ids,
            "oe_numbers": oe_numbers,
            "comparison_numbers": comparison_numbers,
            "applications": applications,
            "attributes": attributes,
        })
    
    return products


def extract_vehicle_types(soup: BeautifulSoup) -> list[VehicleType]:
    """Extract vehicle types from search results."""
    vehicles = []
    
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) >= 8:
            try:
                type_link = cells[0].find("a")
                if type_link:
                    href = type_link.get("href", "")
                    match = re.search(r"IdTipoVehiculo=(\d+)", href)
                    type_id = int(match.group(1)) if match else 0
                    
                    vehicles.append(VehicleType(
                        type_id=type_id,
                        brand_name=cells[1].get_text(strip=True),
                        model_name=cells[2].get_text(strip=True),
                        type_name=cells[3].get_text(strip=True),
                        engine_code=cells[4].get_text(strip=True),
                        power_kw=int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else 0,
                        power_hp=int(cells[6].get_text(strip=True)) if cells[6].get_text(strip=True).isdigit() else 0,
                        year_from=cells[7].get_text(strip=True),
                        year_to=cells[8].get_text(strip=True) if len(cells) > 8 else "",
                        displacement=int(cells[9].get_text(strip=True).replace(".", "")) if len(cells) > 9 and cells[9].get_text(strip=True).replace(".", "").isdigit() else 0,
                        fuel_type=cells[10].get_text(strip=True) if len(cells) > 10 else "",
                    ))
            except (ValueError, IndexError):
                continue
    
    return vehicles


def scrape_categories(start_area_id: int = 0) -> dict:
    """Scrape the category tree."""
    cache_file = CACHE_DIR / "categories.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    
    categories = {}
    
    def process_area(area_id: int, path: list[str]):
        if area_id in categories:
            return
        
        url = f"{BASE_URL}/TabelloneArea.asp?IdArea={area_id}"
        soup = fetch_page(url)
        if not soup:
            return
        
        sub_categories = extract_categories(soup)
        
        categories[area_id] = {
            "id": area_id,
            "path": path,
            "sub_categories": [c["area_id"] for c in sub_categories],
            "products": [],
        }
        
        time.sleep(0.5)
        
        for sub_cat in sub_categories:
            process_area(sub_cat["area_id"], path + [sub_cat["name"]])
    
    process_area(start_area_id, [])
    
    with open(cache_file, "w") as f:
        json.dump(categories, f, indent=2)
    
    return categories


def scrape_products_for_category(area_id: int, max_pages: int = 10) -> list[dict]:
    """Scrape products from a category."""
    products = []
    
    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/TabelloneArea.asp"
        params = {"IdArea": area_id, "Pagina": page}
        
        soup = fetch_page(url, params)
        if not soup:
            break
        
        page_products = extract_products_from_page(soup)
        if not page_products:
            break
        
        products.extend(page_products)
        
        if "Página 1 de" in soup.get_text():
            page_info_match = re.search(r"Página \d+ de (\d+)", soup.get_text())
            if page_info_match:
                total_pages = int(page_info_match.group(1))
                if page >= total_pages:
                    break
        
        time.sleep(0.3)
    
    return products


def scrape_vehicle_types_for_product(reference: str) -> list[dict]:
    """Get vehicle compatibility for a product."""
    url = f"{BASE_URL}/print.asp"
    params = {"referenza": reference}
    
    soup = fetch_page(url, params)
    if not soup:
        return []
    
    vehicles = []
    
    tables = soup.find_all("table", class_="TabRubrica")
    for table in tables:
        brand_cells = table.find_all("td", class_="TabRubricaInt")
        for brand_cell in brand_cells:
            brand_name = brand_cell.get_text(strip=True)
            models_td = brand_cell.find_next_sibling("td")
            if models_td:
                models_text = models_td.get_text(strip=True)
                models = [m.strip() for m in models_text.split(",")]
                vehicles.append({
                    "brand": brand_name,
                    "models": models,
                })
    
    return vehicles


def scrape_brand_models(brand_id: str) -> dict:
    """Scrape vehicle models for a brand."""
    url = f"{BASE_URL}/Tabellone.asp"
    params = {
        "Marca": brand_id,
        "Action": "CercaModelli",
    }
    
    soup = fetch_page(url, params)
    if not soup:
        return {}
    
    models = {}
    for option in soup.find_all("option"):
        value = option.get("value")
        if value and value != "":
            models[value] = option.get_text(strip=True)
    
    return models


def export_to_json(data: dict, filename: str):
    """Export data to JSON file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / filename
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Exported to {output_file}")


def main():
    """Main scraping function."""
    print("ERA TecDoc Scraper")
    print("=" * 50)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("\n1. Scraping category tree...")
    categories = scrape_categories(0)
    export_to_json(categories, "categories.json")
    
    print(f"   Found {len(categories)} categories")
    
    print("\n2. Scraping products by category...")
    all_products = []
    processed_areas = set()
    
    leaf_areas = [
        aid for aid, cat in categories.items() 
        if not cat.get("sub_categories") and aid > 0
    ]
    
    for i, area_id in enumerate(leaf_areas[:50]):
        if area_id in processed_areas:
            continue
        
        print(f"   [{i+1}/{len(leaf_areas[:50])}] Area {area_id}: ", end="")
        products = scrape_products_for_category(area_id)
        print(f"{len(products)} products")
        
        for p in products:
            p["area_id"] = area_id
            p["category_path"] = categories.get(area_id, {}).get("path", [])
        
        all_products.extend(products)
        processed_areas.add(area_id)
        
        if len(all_products) >= 1000:
            break
    
    export_to_json(all_products, "products_sample.json")
    print(f"\n   Total products scraped: {len(all_products)}")
    
    print("\n3. Sample vehicle types extraction...")
    export_to_json([], "vehicle_types.json")
    
    print("\nScraping complete!")
    print(f"Data saved to: {OUTPUT_DIR}")
    print("\nNext steps:")
    print("  1. Review the JSON files")
    print("  2. Run full scrape with increased limits")
    print("  3. Create Django management command to import data")


if __name__ == "__main__":
    main()
