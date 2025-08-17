
import sqlite3
from pathlib import Path
from datetime import datetime
import argparse
import pandas as pd
import matplotlib.pyplot as plt
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors

ISO_FMT = "%Y-%m-%d %H:%M:%S"

def _connect(db_path: str):
    return sqlite3.connect(db_path)

def initialize_db(db_path: str):
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            closed_at TEXT,
            severity TEXT NOT NULL,
            category TEXT NOT NULL,
            system TEXT NOT NULL,
            description TEXT NOT NULL,
            reporter TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Open', 'In Progress', 'Closed'))
        )
    """)
    conn.commit()
    conn.close()

def add_incident(db_path: str, created_at: str, severity: str, category: str, system: str,
                 description: str, reporter: str, status: str = "Open", closed_at: str = None):
    try:
        datetime.strptime(created_at, ISO_FMT)
    except ValueError:
        raise ValueError(f"created_at must be in ISO format {ISO_FMT}")
    if closed_at:
        try:
            datetime.strptime(closed_at, ISO_FMT)
        except ValueError:
            raise ValueError(f"closed_at must be in ISO format {ISO_FMT}")

    if severity not in ("Low", "Medium", "High", "Critical"):
        raise ValueError("severity must be one of Low, Medium, High, Critical")
    if status not in ("Open", "In Progress", "Closed"):
        raise ValueError("status must be one of Open, In Progress, Closed")

    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO incidents (created_at, closed_at, severity, category, system, description, reporter, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (created_at, closed_at, severity, category, system, description, reporter, status))
    conn.commit()
    conn.close()

def update_status(db_path: str, incident_id: int, status: str, closed_at: str = None):
    if status not in ("Open", "In Progress", "Closed"):
        raise ValueError("status must be one of Open, In Progress, Closed")
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE incidents SET status=?, closed_at=? WHERE id=?", (status, closed_at, incident_id))
    conn.commit()
    conn.close()

def get_incidents_df(db_path: str):
    import pandas as pd
    conn = _connect(db_path)
    df = pd.read_sql_query("SELECT * FROM incidents", conn, parse_dates=["created_at", "closed_at"])
    conn.close()
    return df

def export_csv(df, out_path: str):
    df.to_csv(out_path, index=False)

def _ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def generate_charts(df, out_dir: Path):
    _ensure_dir(out_dir)

    if not df.empty:
        monthly = df.copy()
        monthly["month"] = monthly["created_at"].dt.to_period("M").dt.to_timestamp()
        monthly_counts = monthly.groupby("month").size()
        plt.figure()
        monthly_counts.plot(kind="bar")
        plt.title("Incidents by Month")
        plt.xlabel("Month")
        plt.ylabel("Count")
        plt.tight_layout()
        monthly_chart = out_dir / "incidents_by_month.png"
        plt.savefig(monthly_chart)
        plt.close()
    else:
        monthly_chart = None

    if not df.empty:
        cat_counts = df["category"].value_counts()
        plt.figure()
        cat_counts.plot(kind="bar")
        plt.title("Incidents by Category")
        plt.xlabel("Category")
        plt.ylabel("Count")
        plt.tight_layout()
        category_chart = out_dir / "incidents_by_category.png"
        plt.savefig(category_chart)
        plt.close()
    else:
        category_chart = None

    if not df.empty:
        severity_order = ["Low", "Medium", "High", "Critical"]
        sev_counts = df["severity"].value_counts().reindex(severity_order).fillna(0)
        plt.figure()
        sev_counts.plot(kind="bar")
        plt.title("Incidents by Severity")
        plt.xlabel("Severity")
        plt.ylabel("Count")
        plt.tight_layout()
        severity_chart = out_dir / "incidents_by_severity.png"
        plt.savefig(severity_chart)
        plt.close()
    else:
        severity_chart = None

    if not df.empty:
        closed = df[df["closed_at"].notna()].copy()
        if not closed.empty:
            closed["resolution_hours"] = (closed["closed_at"] - closed["created_at"]).dt.total_seconds() / 3600.0
            mean_res = closed.groupby("category")["resolution_hours"].mean().sort_values(ascending=False)
            plt.figure()
            mean_res.plot(kind="bar")
            plt.title("Mean Resolution Time (Hours) by Category")
            plt.xlabel("Category")
            plt.ylabel("Hours")
            plt.tight_layout()
            resolution_chart = out_dir / "mean_resolution_time_by_category.png"
            plt.savefig(resolution_chart)
            plt.close()
        else:
            resolution_chart = None
    else:
        resolution_chart = None

    return {
        "monthly": monthly_chart,
        "category": category_chart,
        "severity": severity_chart,
        "resolution": resolution_chart
    }

def generate_pdf_report(df, charts: dict, out_path: Path):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(out_path), pagesize=LETTER)
    elems = []

    title = Paragraph("<b>Cybersecurity Incident Tracker - Summary Report</b>", styles["Title"])
    elems.append(title)
    elems.append(Spacer(1, 12))

    total_incidents = len(df)
    last_30 = 0
    if not df.empty:
        import pandas as pd
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=30)
        last_30 = (df["created_at"] >= cutoff).sum()

    closed_df = df[df["closed_at"].notna()]
    if not closed_df.empty:
        hrs = (closed_df["closed_at"] - closed_df["created_at"]).dt.total_seconds() / 3600.0
        avg_resolution = f"{hrs.mean():.2f} hrs"
    else:
        avg_resolution = "-"

    summary_data = [
        ["Total Incidents", str(total_incidents)],
        ["Incidents (Last 30 Days)", str(last_30)],
        ["Avg. Resolution Time (Closed)", avg_resolution],
    ]
    table = Table(summary_data, hAlign='LEFT')
    table.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 1, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    elems.append(table)
    elems.append(Spacer(1, 16))

    # Charts
    for label in ["monthly", "category", "severity", "resolution"]:
        img_path = charts.get(label)
        if img_path and Path(img_path).exists():
            pretty = label.replace("_", " ").title()
            elems.append(Paragraph(f"<b>{pretty}</b>", styles["Heading2"]))
            elems.append(Spacer(1, 6))
            elems.append(RLImage(str(img_path), width=500, height=300))
            elems.append(Spacer(1, 12))

    doc.build(elems)

def generate_reports(db_path: str, out_dir: str):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = get_incidents_df(db_path)
    export_csv(df, str(out_dir / "incidents_export.csv"))

    import csv, json
    metrics = {"total_incidents": len(df)}
    if not df.empty:
        metrics["by_category"] = df["category"].value_counts().to_dict()
        metrics["by_severity"] = df["severity"].value_counts().to_dict()
        closed = df[df["closed_at"].notna()].copy()
        if not closed.empty:
            closed["resolution_hours"] = (closed["closed_at"] - closed["created_at"]).dt.total_seconds() / 3600.0
            metrics["avg_resolution_hours"] = float(closed["resolution_hours"].mean())
        else:
            metrics["avg_resolution_hours"] = None
    else:
        metrics["by_category"] = {}
        metrics["by_severity"] = {}
        metrics["avg_resolution_hours"] = None

    with open(out_dir / "metrics_summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["total_incidents", metrics["total_incidents"]])
        w.writerow(["avg_resolution_hours", metrics["avg_resolution_hours"]])
        import json
        w.writerow(["by_category_json", json.dumps(metrics["by_category"])])
        w.writerow(["by_severity_json", json.dumps(metrics["by_severity"])])

    charts = generate_charts(df, out_dir)
    generate_pdf_report(df, charts, out_dir / "incident_report.pdf")

    return {
        "export_csv": str(out_dir / "incidents_export.csv"),
        "metrics_csv": str(out_dir / "metrics_summary.csv"),
        "pdf_report": str(out_dir / "incident_report.pdf"),
        "charts": {k: str(v) if v else None for k, v in charts.items()}
    }

def bulk_import_csv(db_path: str, csv_path: str):
    import pandas as pd
    df = pd.read_csv(csv_path)
    expected = {"created_at", "closed_at", "severity", "category", "system", "description", "reporter", "status"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in CSV: {missing}")

    def norm(ts):
        if pd.isna(ts) or str(ts).strip() == "":
            return None
        dt = pd.to_datetime(ts)
        return dt.strftime(ISO_FMT)

    df["created_at"] = df["created_at"].apply(norm)
    df["closed_at"] = df["closed_at"].apply(norm)

    conn = _connect(db_path)
    cur = conn.cursor()
    for _, row in df.iterrows():
        cur.execute("""
            INSERT INTO incidents (created_at, closed_at, severity, category, system, description, reporter, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["created_at"], row["closed_at"], row["severity"], row["category"], row["system"],
            row["description"], row["reporter"], row["status"]
        ))
    conn.commit()
    conn.close()

def main():
    parser = argparse.ArgumentParser(description="Cybersecurity Incident Tracker")
    parser.add_argument("--db", default="incidents.db", help="Path to SQLite database file")

    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Initialize the database")

    add_p = sub.add_parser("add", help="Add an incident")
    add_p.add_argument("--created_at", required=True, help="YYYY-MM-DD HH:MM:SS")
    add_p.add_argument("--severity", required=True, choices=["Low", "Medium", "High", "Critical"])
    add_p.add_argument("--category", required=True)
    add_p.add_argument("--system", required=True)
    add_p.add_argument("--description", required=True)
    add_p.add_argument("--reporter", required=True)
    add_p.add_argument("--status", default="Open", choices=["Open", "In Progress", "Closed"])
    add_p.add_argument("--closed_at", default=None)

    upd_p = sub.add_parser("update", help="Update incident status")
    upd_p.add_argument("--id", type=int, required=True)
    upd_p.add_argument("--status", required=True, choices=["Open", "In Progress", "Closed"])
    upd_p.add_argument("--closed_at", default=None)

    imp_p = sub.add_parser("import", help="Bulk import from CSV")
    imp_p.add_argument("--csv", required=True)

    rep_p = sub.add_parser("report", help="Generate CSV exports and PDF report")
    rep_p.add_argument("--out_dir", default="reports")

    list_p = sub.add_parser("list", help="List incidents")

    args = parser.parse_args()

    if args.cmd == "init":
        initialize_db(args.db)
        print(f"Database initialized at {args.db}")
    elif args.cmd == "add":
        add_incident(args.db, args.created_at, args.severity, args.category, args.system,
                     args.description, args.reporter, args.status, args.closed_at)
        print("Incident added.")
    elif args.cmd == "update":
        update_status(args.db, args.id, args.status, args.closed_at)
        print("Incident updated.")
    elif args.cmd == "import":
        bulk_import_csv(args.db, args.csv)
        print("Import complete.")
    elif args.cmd == "report":
        paths = generate_reports(args.db, args.out_dir)
        for k, v in paths.items():
            print(k, "->", v)
    elif args.cmd == "list":
        df = get_incidents_df(args.db)
        if df.empty:
            print("No incidents found.")
        else:
            print(df.to_string(index=False))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
