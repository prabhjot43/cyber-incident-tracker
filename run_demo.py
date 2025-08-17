
import os, sys
from incident_tracker import initialize_db, bulk_import_csv, generate_reports, get_incidents_df

DB = "incidents.db"
OUT = "reports"
CSV = "sample_data.csv"

# Clean prior run
def rm(path):
    if os.path.isdir(path):
        for r, d, files in os.walk(path, topdown=False):
            for name in files:
                os.remove(os.path.join(r, name))
            for name in d:
                os.rmdir(os.path.join(r, name))
        os.rmdir(path)
    elif os.path.isfile(path):
        os.remove(path)

rm(DB)
rm(OUT)

initialize_db(DB)
bulk_import_csv(DB, CSV)
paths = generate_reports(DB, OUT)

print("Generated outputs:")
for k, v in paths.items():
    print(f"{k}: {v}")

df = get_incidents_df(DB)
print("\\nPreview:")
print(df.head().to_string(index=False))
