#!/usr/bin/env python3
"""
3GPP Document Downloader FastMCP Server
Simple MCP server using the working code from main.py
"""

import os
import re
import time
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag
import zipfile
from fastmcp import FastMCP

# Create FastMCP server instance
mcp = FastMCP("3gpp-document-downloader")


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
        all_zips = []
        for a in soup.find_all("a", href=True):
            if isinstance(a, Tag):
                href = a.get("href")
                if isinstance(href, str) and href.endswith(".zip"):
                    all_zips.append(href)
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


def download_and_extract(zip_url, output_dir, log=None):
    if log is None:
        log = []

    log.append(f"📥 Downloading ZIP file: {zip_url}")
    os.makedirs(output_dir, exist_ok=True)
    local_zip = os.path.join(output_dir, os.path.basename(urlparse(zip_url).path))
    log.append(f"📁 Saving to: {local_zip}")

    with requests.get(zip_url, stream=True, timeout=600) as r:  # 10분 timeout
        r.raise_for_status()
        total_size = int(r.headers.get("content-length", 0))
        downloaded_size = 0

        log.append(f"📊 Total file size: {total_size / (1024*1024):.1f} MB")

        with open(local_zip, "wb") as f:
            last_progress = -1
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)

                    if total_size > 0:
                        progress = (downloaded_size / total_size) * 100
                        # Print every 10% (0%, 10%, 20%, ..., 100%)
                        if int(progress) // 10 > last_progress // 10:
                            log.append(
                                f"📈 Download progress: {progress:.1f}% ({downloaded_size / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB)"
                            )
                            last_progress = int(progress)
                    else:
                        # If file size is unknown, print every 1MB
                        if downloaded_size // (1024 * 1024) > last_progress // (
                            1024 * 1024
                        ):
                            log.append(
                                f"📈 Downloaded: {downloaded_size / (1024*1024):.1f} MB"
                            )
                            last_progress = downloaded_size

    log.append(f"✅ ZIP download completed: {local_zip}")
    log.append("📂 Extracting PDF/DOC/DOCX files...")

    # Extract doc/pdf/docx from ZIP
    extracted_files = []
    with zipfile.ZipFile(local_zip, "r") as z:
        file_list = [
            name
            for name in z.namelist()
            if name.lower().endswith((".pdf", ".doc", ".docx"))
        ]
        total_files = len(file_list)

        for i, name in enumerate(file_list, 1):
            z.extract(name, output_dir)
            extracted_files.append(name)
            progress = (i / total_files) * 100
            log.append(f"📄 Extracting: {progress:.0f}% - {name}")

    log.append(f"✅ Download and extraction completed: {local_zip}")
    log.append(f"📊 Total extracted files: {len(extracted_files)}")
    return extracted_files


# Global download state
download_state = {}


@mcp.tool()
def check_3gpp_link(spec: str, release: str) -> str:
    """
    Check if a 3GPP specification and release combination exists and get the download link.

    Args:
        spec (str): 3GPP specification number (e.g., "TS 38.331", "TS 24.301").
        release (str): Release number (e.g., "Rel-16", "Rel-17", "Rel-18").

    Returns:
        str: Information about the spec-release combination and download link if available.
    """
    try:
        # Parse spec number
        series, number, _ = parse_spec_number(spec)
        rel_suffix = rel_to_zip_suffix(release)

        # Find ZIP link
        zip_link = find_spec_zip_link(series, number, rel_suffix)

        if not zip_link:
            return f"❌ Could not find ZIP file for {spec} release {release}. This spec-release combination may not exist in the 3GPP archive."

        # Store download info for next steps
        download_id = f"{spec}_{release}_{int(time.time())}"
        download_state[download_id] = {
            "spec": spec,
            "release": release,
            "zip_link": zip_link,
            "series": series,
            "number": number,
            "status": "link_found",
            "start_time": time.time(),
        }

        return (
            f"✅ Link found for {spec} {release}!\n\n"
            f"📄 Spec: {spec}\n"
            f"🔄 Release: {release}\n"
            f"🔗 ZIP Link: {zip_link}\n"
            f"🆔 Download ID: {download_id}\n\n"
            f"💡 Use start_3gpp_download with this download ID to begin downloading."
        )
    except Exception as e:
        return f"❌ Error occurred: {str(e)}"


@mcp.tool()
def download_3gpp_document(download_id: str, output_dir: str = "./downloads") -> str:
    """
    Download and extract a 3GPP specification document using a download ID from check_3gpp_link.

    Args:
        download_id (str): Download ID from check_3gpp_link.
        output_dir (str, optional): Directory to save the extracted files. Defaults to "./downloads".

    Returns:
        str: Download result with progress information and extracted files.
    """
    try:
        if download_id not in download_state:
            return f"❌ Invalid download ID: {download_id}. Please run check_3gpp_link first."

        info = download_state[download_id]
        zip_link = info["zip_link"]

        # Get file size first
        with requests.get(zip_link, stream=True, timeout=600) as r:  # 10분 timeout
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))

        # Start download
        os.makedirs(output_dir, exist_ok=True)
        local_zip = os.path.join(output_dir, os.path.basename(urlparse(zip_link).path))

        downloaded_size = 0
        with requests.get(zip_link, stream=True, timeout=600) as r:  # 10분 timeout
            r.raise_for_status()
            with open(local_zip, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

        # Extract files
        extracted_files = []
        with zipfile.ZipFile(local_zip, "r") as z:
            file_list = [
                name
                for name in z.namelist()
                if name.lower().endswith((".pdf", ".doc", ".docx"))
            ]
            for name in file_list:
                z.extract(name, output_dir)
                extracted_files.append(name)

        # Clean up download state
        del download_state[download_id]

        # Return result
        files_info = "\n".join([f"  - {f}" for f in extracted_files])
        return (
            f"✅ Download completed successfully!\n\n"
            f"📄 Spec: {info['spec']}\n"
            f"🔄 Release: {info['release']}\n"
            f"📁 Output directory: {output_dir}\n"
            f"📦 ZIP file: {os.path.basename(local_zip)}\n"
            f"📊 File size: {total_size / (1024*1024):.1f} MB\n"
            f"📄 Extracted files ({len(extracted_files)} files):\n{files_info}"
        )

    except Exception as e:
        return f"❌ Error occurred: {str(e)}"


@mcp.tool()
def list_available_specs(spec: str = "", release: str = "") -> str:
    """
    List available 3GPP specifications and their releases.

    Args:
        spec (str, optional): Full specification number (e.g., "TS 38.331", "TS 23.501").
                             If empty, lists all specs in all series.
        release (str, optional): Release number (e.g., "Rel-16", "Rel-18").
                                If provided with spec, checks if that combination exists.

    Returns:
        str: Information about available specifications and releases.
    """
    try:
        if spec:
            series, number, _ = parse_spec_number(spec)
            base_url = f"https://www.3gpp.org/ftp/Specs/archive/{series}_series/"
            doc_dir = f"{series}.{number}"
            doc_url = urljoin(base_url, doc_dir + "/")

            print(f"Checking spec: {spec} at URL: {doc_url}")

            r = requests.get(doc_url)
            r.raise_for_status()
            soup = BeautifulSoup(r.content, "html.parser")

            # Get all ZIP files
            zip_files = []
            for a in soup.find_all("a", href=True):
                if isinstance(a, Tag):
                    href = a.get("href")
                    if isinstance(href, str) and href.endswith(".zip"):
                        zip_files.append(href)

            if not zip_files:
                return f"❌ Spec {spec} does not exist in the 3GPP archive."

            # Extract release information from ZIP files
            releases = {}
            for zip_file in zip_files:
                filename = os.path.basename(zip_file)
                if filename.startswith(f"{series}{number}-") and filename.endswith(
                    ".zip"
                ):
                    version_code = filename[len(f"{series}{number}-") : -4]
                    # Convert version code to release number
                    try:
                        version_num = int(version_code, 36)
                        if version_num < 10:
                            release_num = version_num
                        else:
                            release_num = 10 + (version_num // 100) - 1
                        release_name = f"Rel-{release_num}"
                        if release_name not in releases:
                            releases[release_name] = []
                        releases[release_name].append(version_code)
                    except ValueError:
                        continue

            if release:
                # Check specific release
                if release in releases:
                    versions = releases[release]
                    versions.sort(key=lambda x: int(x, 36))
                    latest_version = versions[-1]
                    return (
                        f"✅ Spec {spec} with {release} is available!\n\n"
                        f"📄 Spec: {spec}\n"
                        f"🔄 Release: {release}\n"
                        f"📦 Available versions: {', '.join(versions)}\n"
                        f"🎯 Latest version: {latest_version}\n"
                        f"🔗 URL: {doc_url}"
                    )
                else:
                    available_releases = ", ".join(sorted(releases.keys()))
                    return (
                        f"❌ Spec {spec} with {release} does not exist.\n\n"
                        f"📋 Available releases for {spec}:\n"
                        f"{available_releases}\n\n"
                        f"💡 Try one of the available releases above."
                    )
            else:
                # List all releases for the spec
                if releases:
                    releases_info = []
                    for rel, versions in sorted(releases.items()):
                        versions.sort(key=lambda x: int(x, 36))
                        latest = versions[-1]
                        releases_info.append(
                            f"- {rel}: {len(versions)} versions (latest: {latest})"
                        )

                    releases_list = "\n".join(releases_info)
                    return (
                        f"📋 Available releases for {spec}:\n\n"
                        f"{releases_list}\n\n"
                        f"🔗 URL: {doc_url}"
                    )
                else:
                    return f"❌ No valid releases found for {spec}."

        else:
            # List all series and specs
            all_series = []
            for series_num in range(20, 40):  # Common 3GPP series
                series = str(series_num)
                base_url = f"https://www.3gpp.org/ftp/Specs/archive/{series}_series/"

                try:
                    r = requests.get(base_url)
                    r.raise_for_status()
                    soup = BeautifulSoup(r.content, "html.parser")

                    specs = []
                    for a in soup.find_all("a", href=True):
                        if isinstance(a, Tag):
                            href = a.get("href")
                            if (
                                isinstance(href, str)
                                and href.endswith("/")
                                and href != "../"
                            ):
                                spec_name = href.rstrip("/")
                                if re.match(r"\d+\.\d+", spec_name):
                                    specs.append(spec_name)

                    if specs:
                        all_series.append(f"Series {series}: {len(specs)} specs")

                except requests.exceptions.HTTPError:
                    continue
                except Exception:
                    continue

            if all_series:
                series_list = "\n".join(all_series)
                return (
                    f"📋 Available 3GPP series:\n\n"
                    f"{series_list}\n\n"
                    f"💡 Use 'list_available_specs' with a specific spec (e.g., 'TS 38.331') "
                    f"to see available releases for that spec."
                )
            else:
                return "❌ Could not retrieve series information."

    except Exception as e:
        return f"❌ Error occurred: {str(e)}"


if __name__ == "__main__":
    mcp.run()
