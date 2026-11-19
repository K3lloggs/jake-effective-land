"""Everything Jake might want changed lives here."""
ZIPS = ["19104", "19146", "19125"]
ZONING = ["RM1", "RM2"]                 # OPA writes RM-1 as RM1
LAND_CATEGORY_CODES = ["6", "12", "13"]  # vacant land, vacant land residential / non-residential
CARTO = "https://phl.carto.com/api/v2/sql"
ARCGIS = "https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest/services"
PAGE = 10000        # rows per Carto page
CHUNK = 250         # OPA numbers per IN (...) query
USER_AGENT = "jake-effective-land/0.1 (personal research tool)"
EXCLUDE_DESCRIPTIONS = ["CONDO PARKING SPACE"]   # coded as vacant land by OPA but not buildable lots
