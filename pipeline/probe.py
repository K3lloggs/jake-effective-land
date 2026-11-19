"""Hit every source once and print its columns. Run this first: python -m pipeline.probe"""
from pipeline import fetch
from pipeline.sources import CARTO_SOURCES, ARCGIS_SOURCES

def main():
    for name, table, col, _, _ in [("opa", "opa_properties_public", "parcel_number", None, None)] + CARTO_SOURCES:
        try:
            row = fetch.carto(f"SELECT * FROM {table} LIMIT 1")[0]
            ok = "OK " if col in row else "JOIN COLUMN MISSING "
            print(f"{ok}{name:11} {table}: join={col}\n    {', '.join(sorted(row))}\n")
        except Exception as e:
            print(f"FAIL {name:11} {table}: {str(e)[:200]}\n")
    for name, layer, col, _ in ARCGIS_SOURCES:
        try:
            row = fetch.arcgis(layer, "1=1", limit=1)[0]
            ok = "OK " if col.lower() in row else "JOIN COLUMN MISSING "
            print(f"{ok}{name:11} {layer}: join={col}\n    {', '.join(sorted(row))}\n")
        except Exception as e:
            print(f"FAIL {name:11} {layer}: {str(e)[:200]}")
            try: print("    Services with a similar name:", fetch.arcgis_services([name, layer.split("_")[0].lower()]), "\n")
            except Exception as e2: print("    Could not list services:", str(e2)[:120], "\n")

if __name__ == "__main__":
    main()
