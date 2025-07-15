#!/usr/bin/env python3
"""
3GPP Document Downloader CLI
Automatically downloads and extracts specific 3GPP spec documents (e.g., TS 24.301, TS 38.101-1).
"""

import os
import re
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag
import zipfile
import argparse


def parse_spec_number(spec: str):
    m = re.match(r"(TS|TR|GS|GR)\s*(\d{2})\.(\d{3})(?:-(\d+))?", spec.upper())
    if not m:
        raise ValueError("Invalid spec format. Example: TS 24.301, TR 38.101-1")
    spec_type, series, number, sub = m.groups()
    return series, number, sub or "1"


def rel_to_zip_suffix(rel: str):
    # Convert release number to base-36 (e.g., Rel-18 → i)
    m = re.match(r"Rel-(\d+)", rel, re.I)
    if not m:
        raise ValueError("Invalid release format. Example: Rel-18")

    rel_num = int(m.group(1))
    # Base-36: 0-9 as is, 10-35 as a-z
    if rel_num < 10:
        return f"{rel_num}00"  # Example: Rel-8 → 800
    elif rel_num < 36:
        return f"{chr(ord('a') + rel_num - 10)}00"  # Example: Rel-18 → i00
    else:
        raise ValueError(f"Unsupported release number: {rel_num}")


def find_spec_zip_link(series, number, rel_suffix):
    base_url = f"https://www.3gpp.org/ftp/Specs/archive/{series}_series/"
    doc_dir = f"{series}.{number}"
    doc_url = urljoin(base_url, doc_dir + "/")

    print(f"Search URL: {doc_url}")
    print(f"Looking for release suffix: {rel_suffix}")

    r = requests.get(doc_url)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")

    # Find ZIP files starting with the release suffix
    candidates = []
    for a in soup.find_all("a", href=True):
        if isinstance(a, Tag):
            href = a.get("href")
            if isinstance(href, str) and href.endswith(".zip"):
                # Extract version code from filename (e.g., 38331-i60.zip → i60)
                filename = os.path.basename(href)
                if filename.startswith(f"{series}{number}-") and filename.endswith(
                    ".zip"
                ):
                    version_code = filename[
                        len(f"{series}{number}-") : -4
                    ]  # remove .zip
                    if version_code.startswith(
                        rel_suffix[:1]
                    ):  # first char matches release
                        candidates.append(href)
                        print(
                            f"Release candidate ZIP: {href} (version code: {version_code})"
                        )

    if not candidates:
        print(f"No ZIP file found starting with release {rel_suffix[:1]}")
        all_zips = [
            a.get("href")
            for a in soup.find_all("a", href=True)
            if isinstance(a, Tag)
            and isinstance(a.get("href"), str)
            and a.get("href") is not None
            and a.get("href").endswith(".zip")
        ]
        print(f"Available ZIP files: {all_zips[:10]}...")  # Show first 10 only
        return None

    # Select the latest version (largest base-36 value)
    def extract_version(href):
        filename = os.path.basename(href)
        version_code = filename[len(f"{series}{number}-") : -4]
        try:
            return int(version_code, 36)
        except ValueError:
            return 0

    latest = max(candidates, key=extract_version)
    print(f"Latest ZIP: {latest}")
    return urljoin(doc_url, latest)


def download_and_extract(zip_url, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    local_zip = os.path.join(output_dir, os.path.basename(urlparse(zip_url).path))
    with requests.get(zip_url, stream=True, timeout=600) as r:  # 10분 timeout
        r.raise_for_status()
        with open(local_zip, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    # Extract doc/pdf/docx from ZIP
    with zipfile.ZipFile(local_zip, "r") as z:
        for name in z.namelist():
            if name.lower().endswith((".pdf", ".doc", ".docx")):
                z.extract(name, output_dir)
                print(f"Extracted: {name}")
    print(f"Download and extraction complete: {local_zip}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", help="e.g., TS 24.301")
    parser.add_argument("release", help="e.g., Rel-16")
    parser.add_argument("--output", default="./downloads", help="Output folder")
    args = parser.parse_args()

    series, number, _ = parse_spec_number(args.spec)
    rel_suffix = rel_to_zip_suffix(args.release)
    zip_link = find_spec_zip_link(series, number, rel_suffix)
    if not zip_link:
        print("Could not find ZIP file for the specified release.")
    else:
        print(f"ZIP file: {zip_link}")
        download_and_extract(zip_link, args.output)
