
## SCRAPEAR X CANTIDAD DE PRODUCTOS (30 en el ejemplo)

./.venv/bin/python src/manage.py scrape_rg_products --limit 30 --delay 0.05 --top-categories 6

## IMPORTAR EN LA BBDD LOS PRODUCTOS SCRAPEADOS

./.venv/bin/python src/manage.py import_rg_products --input-file data/rg/rg_products_clean.json --report-file data/rg/rg_import_report.json