import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "microfoodlab.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")

# ------------------------------------------------------------------
# Seed data for the Standard Comparison Module.
# (food_category, parameter, satisfactory_limit "m", unsatisfactory_limit "M", unit, source)
#
# parameter must be one of: SPC, Coliform, Yeast_Mold
# Interpretation (ICMSF 3-class sampling plan, used by FSSAI & Codex):
#   value <= m            -> Satisfactory
#   m  <  value <= M       -> Marginal / Borderline
#   value  >  M            -> Unsatisfactory (Not Safe)
# ------------------------------------------------------------------
SEED_STANDARDS = [
    ("Street Food / Fast Food", "SPC", 1000, 100000, "CFU/g",
     "Centre for Food Safety (HK), Microbiological Guidelines for Food 2014, Table 1.2 - Category 2 (foods cooked immediately prior to sale)"),
    ("Street Food / Fast Food", "Coliform", 100, 10000, "CFU/g",
     "Centre for Food Safety (HK), Microbiological Guidelines for Food 2014, Table 1.3 - Enterobacteriaceae (general RTE hygiene indicator)"),

    ("Processed / Ready-to-Eat Food", "SPC", 1000, 100000, "CFU/g",
     "Centre for Food Safety (HK), Microbiological Guidelines for Food 2014, Table 1.2 - Category 2/3 (RTE food)"),
    ("Processed / Ready-to-Eat Food", "Coliform", 100, 10000, "CFU/g",
     "Centre for Food Safety (HK), Microbiological Guidelines for Food 2014, Table 1.3 - Enterobacteriaceae"),

    ("Bakery Products", "SPC", 10000, 1000000, "CFU/g",
     "Centre for Food Safety (HK), Microbiological Guidelines for Food 2014, Table 1.2 - Category 4 (bakery & confectionery)"),
    ("Bakery Products", "Coliform", 10, 100, "CFU/g",
     "FSSAI Appendix B (2023), Table 9A - Enterobacteriaceae, fermented grain / bakery products"),

    ("Dairy Products", "SPC", 30000, 50000, "CFU/ml",
     "FSSAI Appendix B (2023), Table 2A - Pasteurized / Boiled Milk"),
    ("Dairy Products", "Coliform", 10, 10, "CFU/ml",
     "FSSAI Appendix B (2023), Table 2A - Pasteurized / Boiled Milk"),

    ("Meat & Poultry", "SPC", 1000000, 5000000, "CFU/g",
     "FSSAI Appendix B (2023), Table 5A - Fresh / Chilled Meat"),
    ("Meat & Poultry", "Coliform", 100, 1000, "CFU/g",
     "FSSAI Appendix B (2023), Table 5A - Fresh / Chilled Meat (E. coli used as hygiene indicator)"),
    ("Meat & Poultry", "Yeast_Mold", 10000, 50000, "CFU/g",
     "FSSAI Appendix B (2023), Table 5A - Fresh / Chilled Meat"),

    ("Seafood", "SPC", 500000, 10000000, "CFU/g",
     "FSSAI Appendix B (2023), Table 1A - Chilled / Frozen Finfish"),

    ("Fruits & Vegetables", "SPC", 1000000, 10000000, "CFU/g",
     "FSSAI Appendix B (2023), Table 4A - Cut / minimally processed fruits & vegetables"),
    ("Fruits & Vegetables", "Yeast_Mold", 100, 10000, "CFU/g",
     "FSSAI Appendix B (2023), Table 4A - Cut / minimally processed fruits & vegetables"),

    ("Beverages", "SPC", 50, 50, "CFU/ml",
     "FSSAI Appendix B (2023), Table 7 - Non-Carbonated Water Based Beverages"),
    ("Beverages", "Yeast_Mold", 2, 2, "CFU/ml",
     "FSSAI Appendix B (2023), Table 7 - Non-Carbonated Water Based Beverages"),
    ("Beverages", "Coliform", 0, 0, "CFU/100ml",
     "FSSAI Appendix B (2023), Table 7 - Non-Carbonated Water Based Beverages (Absent in 100ml)"),

    ("Cereals & Spices", "SPC", 1000000, 10000000, "CFU/g",
     "FSSAI Appendix B (2023), Table 3A - Ground / Powdered Spices"),
    ("Cereals & Spices", "Yeast_Mold", 10000, 100000, "CFU/g",
     "FSSAI Appendix B (2023), Table 3A - Ground / Powdered Spices"),
    ("Cereals & Spices", "Coliform", 100, 1000, "CFU/g",
     "FSSAI Appendix B (2023), Table 3A - Enterobacteriaceae, Ground / Powdered Spices"),

    ("Water Sample", "Coliform", 0, 0, "CFU/100ml",
     "Centre for Food Safety (HK), Microbiological Guidelines for Food 2014, Table 3.2 - Bottled/Packaged Drinking Water"),
]


def get_db():
    """Return a new SQLite connection with rows accessible by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def seed_standards(conn):
    """Populate the standards table with reference limits the first time only."""
    count = conn.execute("SELECT COUNT(*) AS c FROM standards").fetchone()["c"]
    if count == 0:
        conn.executemany(
            """INSERT INTO standards
               (food_category, parameter, satisfactory_limit, unsatisfactory_limit, unit, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            SEED_STANDARDS,
        )
        conn.commit()


def init_db():
    """Create the database file (if missing), all tables, and seed reference standards."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    seed_standards(conn)
    conn.close()
