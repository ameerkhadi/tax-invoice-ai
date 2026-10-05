import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(ROOT, "output")

# Example VAT classes and rates (Swedish-style: 25 / 12 / 6 / exempt).
# Rates change over time (e.g. temporary food-VAT reductions), so they are configuration, not code,
# and must be verified against the tax authority before any real use.
VAT_RATES = {"standard": 0.25, "reduced_1": 0.12, "reduced_2": 0.06, "exempt": 0.0}

ROUNDING_TOLERANCE = 1.00   # SEK tolerated difference between expected and stated VAT
LARGE_INVOICE_Z = 4.0       # robust z-score threshold for unusually large invoices per supplier
