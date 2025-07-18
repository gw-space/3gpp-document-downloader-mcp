#!/usr/bin/env python3
"""
3GPP Document Downloader FastMCP Server
Simple MCP server using the working code from main.py
"""

import os
import re
import time
import requests
import threading
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

    # Search URL and release suffix info

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

    if not candidates:
        # No ZIP file found starting with release
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
    return urljoin(doc_url, latest)


def download_and_extract(zip_url, output_dir, task_id):
    """Background download and extract function"""
    try:
        background_tasks[task_id] = {
            "status": "running",
            "progress": "Starting download...",
        }

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        local_zip = os.path.join(output_dir, os.path.basename(urlparse(zip_url).path))

        # Download ZIP file
        background_tasks[task_id]["progress"] = f"Downloading ZIP file: {zip_url}"
        with requests.get(zip_url, stream=True, timeout=600) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))
            downloaded_size = 0

            with open(local_zip, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        # Update progress every 10%
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            if int(progress) % 10 == 0:
                                background_tasks[task_id][
                                    "progress"
                                ] = f"Download progress: {progress:.1f}% ({downloaded_size / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB)"

        # Extract files
        background_tasks[task_id]["progress"] = "Extracting PDF/DOC/DOCX files..."
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

        # Mark as completed
        background_tasks[task_id] = {
            "status": "completed",
            "progress": "Download and extraction completed successfully",
            "files": extracted_files,
            "output_dir": output_dir,
            "zip_file": local_zip,
        }

    except Exception as e:
        background_tasks[task_id] = {
            "status": "error",
            "progress": f"Error: {str(e)}",
        }


# Global download state
download_state = {}
background_tasks = {}


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
            f"Link found for {spec} {release}!\n\n"
            f"Spec: {spec}\n"
            f"Release: {release}\n"
            f"ZIP Link: {zip_link}\n"
            f"Download ID: {download_id}\n\n"
            f"Use download_3gpp_document with this download ID to begin downloading."
        )
    except Exception as e:
        return f"❌ Error occurred: {str(e)}"


@mcp.tool()
def download_3gpp_document(download_id: str, output_dir: str = "./downloads") -> str:
    """
    Download and extract a 3GPP specification document using a download ID from check_3gpp_link.
    This will start the download in the background and return immediately.

    Args:
        download_id (str): Download ID from check_3gpp_link.
        output_dir (str, optional): Directory to save the extracted files. Defaults to "./downloads".

    Returns:
        str: Task ID for checking download status.
    """
    try:
        if download_id not in download_state:
            return f"❌ Invalid download ID: {download_id}. Please run check_3gpp_link first."

        info = download_state[download_id]
        zip_link = info["zip_link"]

        # Generate task ID
        task_id = f"task_{download_id}_{int(time.time())}"

        # Start background download
        thread = threading.Thread(
            target=download_and_extract, args=(zip_link, output_dir, task_id)
        )
        thread.daemon = True
        thread.start()

        # Clean up download state
        del download_state[download_id]

        return (
            f"Download request completed. It will take several minutes to complete.\n\n"
            f"Spec: {info['spec']}\n"
            f"Release: {info['release']}\n"
            f"Output directory: {os.path.abspath(output_dir)}\n"
            f"Task ID: {task_id}\n\n"
            f"Use check_download_status with this Task ID to monitor progress."
        )

    except Exception as e:
        return f"❌ Failed to start download: {str(e)}"
    finally:
        # Clean up download state even if there was an error
        if download_id in download_state:
            del download_state[download_id]


@mcp.tool()
def check_download_status(task_id: str) -> str:
    """
    Check the status of a background download task.

    Args:
        task_id (str): Task ID from download_3gpp_document.

    Returns:
        str: Current status and progress of the download task.
    """
    if task_id not in background_tasks:
        return f"❌ Task ID not found: {task_id}"

    task = background_tasks[task_id]
    status = task["status"]
    progress = task["progress"]

    if status == "running":
        return f"Download in progress...\n\nStatus: {progress}"
    elif status == "completed":
        files = task.get("files", [])
        files_info = "\n".join([f"  - {f}" for f in files])
        return (
            f"Download completed!\n\n"
            f"Output directory: {task['output_dir']}\n"
            f"Extracted files ({len(files)}):\n{files_info}"
        )
    elif status == "error":
        return f"Download failed: {progress}"
    else:
        return f"Unknown status: {status}"


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

            # Checking spec at URL

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
