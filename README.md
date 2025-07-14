# 3GPP Document Downloader

This is a Python tool for automatically downloading and extracting 3GPP (3rd Generation Partnership Project) specification documents.

## Features

- Automatically download specific 3GPP specs (TS/TR) and releases
- Automatic decoding of base-36 version codes
- Automatically select the latest version within a release
- Automatically extract DOC/DOCX/PDF files from ZIP archives
- **FastMCP server support** – Integrates with Claude Desktop
- Real-time download progress display
- Checks for existing files to avoid redundant downloads

## Installation

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. (Recommended) Use a virtual environment

```bash
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# macOS/Linux:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### 1. CLI Tool Usage

This is a standalone command-line tool.

```bash
python 3gpp_downloader.py "TS 38.331" "Rel-18"
```

#### Parameters

- `spec`: 3GPP spec number (e.g., "TS 24.301", "TS 38.101-1")
- `release`: Release number (e.g., "Rel-16", "Rel-17", "Rel-18")
- `--output`: Output folder (default: "./downloads")

#### Examples

```bash
# Download TS 38.331 Release 18
default
python 3gpp_downloader.py "TS 38.331" "Rel-18"

# Download TS 24.301 Release 16
python 3gpp_downloader.py "TS 24.301" "Rel-16"

# Download TS 38.101-1 Release 17
python 3gpp_downloader.py "TS 38.101-1" "Rel-17"

# Save to a different folder
python 3gpp_downloader.py "TS 23.501" "Rel-16" --output "./my_docs"
```

### 2. FastMCP Server Usage

Integrate with Claude Desktop to allow AI models to download 3GPP documents.

#### Start the MCP server

```bash
python mcp_server.py
```

#### MCP client configuration

Add the following to your Claude Desktop `mcp_config.json`:

```json
{
  "mcpServers": {
    "3gpp-document-downloader": {
      "command": "python",
      "args": ["mcp_server.py"],
      "env": {
        "PYTHONPATH": "."
      }
    }
  }
}
```

#### Available MCP Tools

1. **`check_3gpp_link`**: Check if a 3GPP spec and release combination exists and get the download link
   - Parameters:
     - `spec`: 3GPP spec number (e.g., "TS 38.331")
     - `release`: Release number (e.g., "Rel-18")
   - Returns: Download link info and Download ID

2. **`download_3gpp_document`**: Download a document using the Download ID
   - Parameters:
     - `download_id`: Download ID returned from `check_3gpp_link`
     - `output_dir`: Output directory (optional, default: "./downloads")
   - Returns: Download result and list of extracted files

3. **`list_available_specs`**: List available specs and releases
   - Parameters:
     - `spec`: Specific spec number (optional, e.g., "TS 38.331")
     - `release`: Specific release number (optional, e.g., "Rel-18")
   - Returns: Information about available docs

#### MCP Tool Usage Example

```
1. check_3gpp_link("TS 38.331", "Rel-18")
   → Returns Download ID

2. download_3gpp_document(download_id, "./downloads")
   → Download and extraction complete
```

## 3GPP Version Code System

3GPP ZIP filenames use a base-36 encoded version code:

- Filename format: `<TS number>-<version code>.zip`
- Example: `38331-i60.zip`
- Decoding the version code:
  - `i` = 18 (in base-36, i is 18)
  - `6` = 6
  - `0` = 0
  - So, version 18.6.0

### Release Mapping

- Rel-16 → g00, g10, g20, ...
- Rel-17 → h00, h10, h20, ...
- Rel-18 → i00, i10, i20, ...

## Project Structure

```
3gpp-document-downloader-mcp/
├── 3gpp_downloader.py     # CLI tool (standalone)
├── mcp_server.py          # FastMCP server (Claude Desktop integration)
├── mcp_config.json        # MCP configuration file
├── requirements.txt       # Python dependencies
├── README.md              # Project documentation
├── LICENSE                # MIT License
├── downloads/             # Downloaded document storage (default)
│   ├── 38331-i60.zip     # Downloaded ZIP file
│   ├── 38331-i60.docx    # Extracted DOCX file
│   └── ...
└── .venv/                 # Virtual environment (if created)
```

## Requirements

- Python 3.7+
- requests>=2.25.1
- beautifulsoup4>=4.9.3
- lxml>=4.6.3
- fastmcp>=2.10.0

## License

MIT License

