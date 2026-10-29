"""Download the public inputs and cut them down to a manageable size.

Medicaid State Drug Utilization Data (SDUD) is about 5.3 million rows a year. This script streams
each year's file and keeps:

- every product under the main labeler code of the four companies that make branded GLP-1 drugs,
  so the pipeline still has to pick the GLP-1 drugs out from their insulins and everything else,
  and
- the GLP-1 products of generic makers and repackagers, whose 5-digit labeler codes bring in the
  NDC formats that are easy to get wrong.

It also cuts the FDA NDC directory down to the same labeler codes.

The files in data/raw/ are the ones the published answer key was built from. The FDA directory
changes every day, so by default this script writes to data/fresh/ and leaves data/raw/ alone.

Usage: python data/prepare.py [output_dir]
"""

import csv
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

OUT = Path(__file__).parent / "fresh"

SDUD_URLS = {
    2024: "https://download.medicaid.gov/data/sdud2024_updatedJuly2026.csv",
    2025: "https://download.medicaid.gov/data/sdud2025_updatedjuly2026.csv",
}
FDA_NDC_ZIP = "https://www.accessdata.fda.gov/cder/ndctext.zip"
GLP1_CLASS = "GLP-1 Receptor Agonist [EPC]"

# Every product is kept for these main labeler codes (5-digit form). The companies' other codes,
# such as Sanofi's 00088 (Lantus), have no GLP-1 products.
BRAND_LABELERS = {"00002", "00024", "00169", "00310"}  # Lilly, Sanofi, Novo Nordisk, AstraZeneca

# Only GLP-1 products are kept for these generic makers and repackagers
OTHER_LABELERS = {
    "00143", "00480", "14403", "50090", "69097", "70121",
    "70377", "70748", "71288", "72603", "81607",
}


def labeler5(ndc: str) -> str:
    """'0169-4060-13' -> '00169': FDA writes the labeler with 4 or 5 digits."""
    return ndc.split("-")[0].zfill(5)


def ndc11(package_code: str) -> str:
    """FDA package codes come as 4-4-2, 5-3-2 or 5-4-1; SDUD uses 11 digits (5-4-2)."""
    labeler, product, package = package_code.split("-")
    return labeler.zfill(5) + product.zfill(4) + package.zfill(2)


def read_fda(archive: zipfile.ZipFile, name: str) -> tuple[list[str], list[list[str]]]:
    # The FDA files are tab-separated and not always valid UTF-8
    reader = csv.reader(io.StringIO(archive.read(name).decode("latin-1")), delimiter="\t")
    header = next(reader)
    return header, list(reader)


def write_fda(name: str, header: list[str], rows: list[list[str]]) -> None:
    out = OUT / f"fda_{name}"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    print(f"wrote {out} ({len(rows):,} rows)")


def prepare_fda() -> set[str]:
    """Write the cut-down FDA files and return the 11-digit NDCs of every GLP-1 package."""
    with urllib.request.urlopen(FDA_NDC_ZIP, timeout=600) as resp:
        archive = zipfile.ZipFile(io.BytesIO(resp.read()))
    labelers = BRAND_LABELERS | OTHER_LABELERS

    product_header, products = read_fda(archive, "product.txt")
    ndc_col = product_header.index("PRODUCTNDC")
    products = [p for p in products if labeler5(p[ndc_col]) in labelers]
    write_fda("product.txt", product_header, products)

    id_col = product_header.index("PRODUCTID")
    class_col = product_header.index("PHARM_CLASSES")
    glp1_products = {p[id_col] for p in products if GLP1_CLASS in p[class_col]}

    package_header, packages = read_fda(archive, "package.txt")
    pkg_ndc_col = package_header.index("PRODUCTNDC")
    packages = [p for p in packages if labeler5(p[pkg_ndc_col]) in labelers]
    write_fda("package.txt", package_header, packages)

    pkg_id_col = package_header.index("PRODUCTID")
    code_col = package_header.index("NDCPACKAGECODE")
    return {ndc11(p[code_col]) for p in packages if p[pkg_id_col] in glp1_products}


def keep(row: list[str], labeler_col: int, ndc_col: int, glp1_ndcs: set[str]) -> bool:
    if row[labeler_col] in BRAND_LABELERS:
        return True
    return row[labeler_col] in OTHER_LABELERS and row[ndc_col] in glp1_ndcs


def prepare_sdud(glp1_ndcs: set[str]) -> None:
    out = OUT / "sdud_2024_2025.csv"
    kept = 0
    with out.open("w", newline="") as f:
        writer = None
        for year, url in SDUD_URLS.items():
            with urllib.request.urlopen(url, timeout=600) as resp:
                reader = csv.reader(io.TextIOWrapper(resp, encoding="utf-8", newline=""))
                header = next(reader)
                if writer is None:
                    writer = csv.writer(f)
                    writer.writerow(header)
                labeler_col, ndc_col = header.index("Labeler Code"), header.index("NDC")
                for row in reader:
                    if keep(row, labeler_col, ndc_col, glp1_ndcs):
                        writer.writerow(row)
                        kept += 1
            print(f"SDUD {year}: done ({kept:,} rows kept so far)")
    print(f"wrote {out} ({kept:,} rows)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        OUT = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    prepare_sdud(prepare_fda())
