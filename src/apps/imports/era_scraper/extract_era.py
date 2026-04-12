"""
ERA TecDoc data scraper - extracts product data with OE numbers and vehicle applications.
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
OUTPUT_DIR = Path("era_data")
OUTPUT_FILE = OUTPUT_DIR / "era_products.json"


@dataclass
class Product:
    reference: str
    brand: str
    description: str
    category_names: list[str]
    oe_numbers: list[dict]
    applications: list[dict]
    attributes: dict


def fetch_page(url: str, params: dict = None) -> Optional[BeautifulSoup]:
    """Fetch a page and return BeautifulSoup object."""
    try:
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
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def parse_oe_numbers(text: str) -> list[dict]:
    """Parse OE numbers from text like 'FIAT4067872,4108672,LADA2101-3808'."""
    oes = []
    
    known_brands = [
        'GENERAL MOTORS', 'ALFA ROMEO', 'AUSTIN', 'BEDFORD', 'BMW', 'CITROEN',
        'DAEWOO', 'DAIHATSU', 'FIAT', 'FORD', 'HONDA', 'HYUNDAI', 'ISUZU',
        'IVECO', 'KIA', 'LANCIA', 'LAND ROVER', 'MAZDA', 'MERCEDES', 'MITSUBISHI',
        'NISSAN', 'OPEL', 'PEUGEOT', 'PORSCHE', 'RENAULT', 'ROVER', 'SAAB',
        'SEAT', 'SKODA', 'SUZUKI', 'TOYOTA', 'VAUXHALL', 'VOLVO', 'VW', 'AUDI',
        'LADA', 'CHRYSLER', 'DODGE', 'JEEP', 'SUBARU', 'MASERATI', 'ZAZ',
    ]
    known_brands.sort(key=len, reverse=True)
    
    upper_text = text.upper()
    
    positions = []
    for brand in known_brands:
        pos = upper_text.find(brand)
        if pos >= 0:
            positions.append((pos, brand))
    
    positions.sort(key=lambda x: x[0])
    
    for i, (pos, brand) in enumerate(positions):
        if i + 1 < len(positions):
            end = positions[i + 1][0]
        else:
            end = len(text)
        
        segment = text[pos:end]
        segment = segment[len(brand):]
        
        numbers = re.findall(r'(\d{4,})', segment)
        if numbers:
            oes.append({'brand': brand.title(), 'numbers': numbers[:15]})
    
    return oes


def parse_applications(text: str) -> list[dict]:
    """Parse vehicle applications from text like 'ALFA ROMEO156FIAT124,124 Familiare,126'."""
    apps = []
    
    known_brands = [
        'GENERAL MOTORS', 'ALFA ROMEO', 'AUSTIN', 'BEDFORD', 'BMW', 'CITROEN',
        'DAEWOO', 'DAIHATSU', 'FIAT', 'FORD', 'HONDA', 'HYUNDAI', 'ISUZU',
        'IVECO', 'KIA', 'LANCIA', 'LAND ROVER', 'MAZDA', 'MERCEDES', 'MITSUBISHI',
        'NISSAN', 'OPEL', 'PEUGEOT', 'PORSCHE', 'RENAULT', 'ROVER', 'SAAB',
        'SEAT', 'SKODA', 'SUZUKI', 'TOYOTA', 'VAUXHALL', 'VOLVO', 'VW', 'AUDI',
        'CHRYSLER', 'DODGE', 'JEEP', 'SUBARU', 'MASERATI', 'LADA', 'ZAZ',
    ]
    known_brands.sort(key=len, reverse=True)
    
    upper_text = text.upper()
    
    # Find all brand positions
    positions = []
    for brand in known_brands:
        pos = upper_text.find(brand)
        if pos >= 0:
            positions.append((pos, brand))
    
    positions.sort(key=lambda x: x[0])
    
    for i, (pos, brand) in enumerate(positions):
        if i + 1 < len(positions):
            end = positions[i + 1][0]
        else:
            end = len(text)
        
        segment = text[pos:end]
        segment = segment[len(brand):]
        
        # Split by comma for model lists
        models = []
        for part in segment.split(','):
            part = part.strip()
            if not part:
                continue
            
            # Extract model codes - alphanumeric, underscore, hyphen
            codes = re.findall(r'([A-Z0-9][A-Z0-9\-]{1,30})', part)
            models.extend([c for c in codes if c.upper() not in [b.upper() for b in known_brands]])
        
        if models:
            apps.append({'brand': brand.title(), 'models': list(dict.fromkeys(models))[:50]})
    
    return apps


def extract_products_from_soup(soup: BeautifulSoup, category_name: str) -> list[Product]:
    """Extract all products from a page."""
    products = []
    seen_refs = set()
    
    tables = soup.find_all("table")
    
    for table in tables:
        rows = table.find_all("tr")
        
        for row in rows:
            cells = row.find_all("td")
            
            # Need at least 7 cells
            if len(cells) < 7:
                continue
            
            ref_text = cells[0].get_text(strip=True)
            
            # Reference should be 6 digits
            if not re.match(r'^\d{6}$', ref_text):
                continue
            
            # Skip duplicates
            if ref_text in seen_refs:
                continue
            seen_refs.add(ref_text)
            
            reference = ref_text
            brand = cells[1].get_text(strip=True) or "ERA"
            
            # OE numbers from cell[2]
            oe_text = cells[2].get_text(strip=True)
            oe_numbers = parse_oe_numbers(oe_text)
            
            # Vehicle applications from cell[6]
            app_text = cells[6].get_text(strip=True)
            applications = parse_applications(app_text)
            
            # Try to get description from category paths in collapsible div
            description = ""
            div_id = f"AlberoReferenza{reference}"
            prod_div = soup.find("div", {"id": div_id})
            if prod_div:
                # Look for sensor type in category paths
                paths = prod_div.get_text(separator=" | ", strip=True)
                if "TEMPERATURA" in paths:
                    description = "Coolant Temperature Sensor"
                elif "RPM" in paths or "CIGUEÑAL" in paths:
                    description = "RPM Sensor"
                elif "PRESIÓN" in paths or "PRESION" in paths:
                    description = "Pressure Sensor"
                elif "NIVEL" in paths:
                    description = "Level Sensor"
                elif "VELOCIDAD" in paths or "VELOCIT" in paths:
                    description = "Speed Sensor"
                elif "POSICIÓN" in paths or "POSICION" in paths:
                    description = "Position Sensor"
                elif "SENSOR" in paths:
                    description = "Sensor"
                
                # Add category path as sub-description
                if description:
                    cats = [p.strip() for p in paths.split("|") if p.strip()]
                    if cats:
                        description = f"{description} ({cats[-1]})"
            
            products.append(Product(
                reference=reference,
                brand=brand,
                description=description or f"ERA Sensor {reference}",
                category_names=[category_name],
                oe_numbers=oe_numbers,
                applications=applications,
                attributes={},
            ))
    
    return products


def get_all_areas() -> list[dict]:
    """Get all product areas from the catalog."""
    soup = fetch_page(f"{BASE_URL}/TabelloneArea.asp", {"IdArea": 0})
    if not soup:
        return []
    
    areas = []
    links = soup.find_all("a", href=re.compile(r'IdArea=\d+'))
    
    for link in links:
        href = link.get("href", "")
        match = re.search(r'IdArea=(\d+)', href)
        if match:
            area_id = int(match.group(1))
            name = link.get_text(strip=True)
            if name and area_id > 0:
                areas.append({"area_id": area_id, "name": name})
    
    return areas


def main():
    """Main extraction function."""
    print("ERA TecDoc Data Extraction")
    print("=" * 60)
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    all_data = {
        "source": "ERA TecDoc Electronic Catalog",
        "url": BASE_URL,
        "extraction_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "products": [],
        "areas_scraped": [],
    }
    
    # Key product areas with products
    areas = [
        {"area_id": 1960, "name": "Sensores"},
        {"area_id": 2068, "name": "Dinamo/Alternador/Piezas"},
        {"area_id": 1338, "name": "Sistema de arranque"},
        {"area_id": 1265, "name": "Relé"},
        {"area_id": 1293, "name": "Instrumentos"},
        {"area_id": 2051, "name": "Alternador/Arrancador"},
        {"area_id": 2287, "name": "Unidades de control"},
        {"area_id": 1696, "name": "Sistema eléctrico del motor"},
        {"area_id": 1169, "name": "Interruptor/Sensor"},
        {"area_id": 3513, "name": "Sensores/Conmutadores"},
        {"area_id": 2058, "name": "Interruptores/Relés"},
        {"area_id": 2349, "name": "Relé/Intermitentes"},
        {"area_id": 2035, "name": "Iluminación/Señales"},
        {"area_id": 2381, "name": "Faros principales"},
    ]
    
    total_products = 0
    
    for area in areas:
        print(f"\n[{area['name']}] (Area {area['area_id']})")
        
        soup = fetch_page(
            f"{BASE_URL}/TabelloneArea.asp",
            {"IdArea": area["area_id"]}
        )
        
        if not soup:
            print("   Failed to fetch")
            continue
        
        products = extract_products_from_soup(soup, area["name"])
        print(f"   Found {len(products)} products")
        
        if products:
            # Show sample
            p = products[0]
            print(f"   Sample: {p.reference} - {p.description[:40]}")
            print(f"     OEs: {[oe['brand'] for oe in p.oe_numbers]}")
            print(f"     Apps: {[app['brand'] for app in p.applications]}")
        
        all_data["products"].extend([asdict(p) for p in products])
        all_data["areas_scraped"].append(area["name"])
        total_products += len(products)
        
        time.sleep(0.3)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'=' * 60}")
    print(f"Data saved to: {OUTPUT_FILE}")
    print(f"Total products: {len(all_data['products'])}")
    print(f"Areas scraped: {all_data['areas_scraped']}")


if __name__ == "__main__":
    main()
