# Music Tagger

A CLI tool for batch tagging audio files (**FLAC** and **MP3**) using a hybrid lookup approach:
1. **Text Search**: Attempts metadata search on MusicBrainz using existing Vorbis/ID3 tags or filename heuristics (`Artist - Title`).
2. **Acoustic Fingerprinting**: Falls back to audio fingerprinting via Chromaprint (`fpcalc`) and AcoustID to identify tracks even when metadata and filenames are generic (e.g., `Track 01.flac`).

---

## Features

- **Multi-Format Support**: Reads and writes tags for both **FLAC** (Vorbis comments) and **MP3** (ID3v2 tags via EasyID3).
- **Flexible Source Inputs**: Accepts directories, single files, multiple files, and glob patterns (including recursive `**/*`).
- **Safe Operations**:
  - **In-place updates** (default) or **copy-to-destination** via `-o / --output`.
  - **Dry-run mode** (`--dry-run`) to preview matches without writing to files.
- **Rich Metadata Enrichment**: Automatically retrieves and populates Title, Artist, Album, Date/Year, Track Number, Total Tracks, Genre, and MusicBrainz Recording ID.

---

## Prerequisites

### 1. Python 3.8+
Make sure Python 3 and `pip` are installed on your system:
- **Windows**: Download from [python.org](https://www.python.org/downloads/) (check **"Add python.exe to PATH"** during setup) or install via `winget install Python.Python.3.11`.
- **Linux / macOS**: Preinstalled or available via your distribution's package manager.

### 2. Chromaprint (`fpcalc`)
The acoustic fingerprinting fallback requires the `fpcalc` CLI binary from Chromaprint:

- **Windows**:
  - **Option A (Package Managers)**:
    ```powershell
    # Via Winget
    winget install AcoustID.Chromaprint

    # Or via Chocolatey
    choco install chromaprint

    # Or via Scoop
    scoop install fpcalc
    ```
  - **Option B (Direct Download — No Admin Required)**:
    1. Download the Windows release archive (`chromaprint-fpcalc-*.zip`) from the [Chromaprint Releases](https://github.com/acoustid/chromaprint/releases) or [AcoustID.org](https://acoustid.org/chromaprint).
    2. Extract `fpcalc.exe` and place it directly inside the `music_tagger` repository folder (the script automatically checks for `fpcalc.exe` in the script directory), or place it in any directory in your system `PATH`.
- **Debian / Ubuntu / Raspberry Pi OS**:
  ```bash
  sudo apt update
  sudo apt install libchromaprint-tools
  ```
- **Fedora / RHEL**:
  ```bash
  sudo dnf install chromaprint-tools
  ```
- **Arch Linux**:
  ```bash
  sudo pacman -S chromaprint
  ```
- **macOS** (Homebrew):
  ```bash
  brew install chromaprint
  ```

---

## Installation

### Linux & macOS
1. **Clone the repository**:
   ```bash
   git clone https://github.com/westforest/music_tagger.git
   cd music_tagger
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

### Windows (PowerShell or Command Prompt)
1. **Clone the repository** (or download and extract the ZIP):
   ```powershell
   git clone https://github.com/westforest/music_tagger.git
   cd music_tagger
   ```

2. **Create a virtual environment**:
   ```powershell
   python -m venv venv
   ```

3. **Activate the virtual environment**:
   - **PowerShell**:
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
     *(If PowerShell blocks script execution, run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`)*
   - **Command Prompt (`cmd.exe`)**:
     ```cmd
     .\venv\Scripts\activate.bat
     ```

4. **Install dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

---

## Usage

```text
usage: tagger.py [-h] [-o OUTPUT] [-r | --recursive | --no-recursive]
                 [--remove-comments] [-v] [--dry-run]
                 source [source ...]

Batch tag audio files (FLAC, MP3) using text lookup first, falling back to
acoustic fingerprinting.

positional arguments:
  source                Source directory, file, or pattern (e.g. /path/to/dir, '*.flac', song.mp3)

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Destination directory. If omitted, tags are updated in-place.
  -r, --recursive, --no-recursive
                        Search directories and dir patterns recursively for audio files (default: True).
  --remove-comments     Remove all comment metadata fields (Vorbis COMMENT/DESCRIPTION, ID3 COMM frames).
  -v, --verbose         Print details on what tags and values get updated.
  --dry-run             Simulate lookups without modifying or copying files.
```

### Examples

#### 1. Tag an Entire Album or Library Directory (Recursive by Default)
Traverses the specified directory and all nested subdirectories:
```bash
./tagger.py /path/to/music_collection
```

#### 2. Using Directory Patterns (Recursive Expansion)
Tag all audio files under every matched artist or album folder:
```bash
./tagger.py "music/Artist*"
./tagger.py "albums/*"
```

#### 3. Stripping Comment Metadata
Removes all Vorbis `COMMENT`/`DESCRIPTION` tags from FLAC files and `COMM` frames from MP3 files:
```bash
./tagger.py --remove-comments /path/to/album
```

#### 4. Dry-Run Simulation (No Files Modified)
Preview metadata matches and status statistics before committing changes:
```bash
./tagger.py --dry-run /path/to/album
```

#### 5. Copy Tagged Files to an Output Directory
Leave originals untouched and write tagged copies to a new folder:
```bash
./tagger.py -o /path/to/sorted_music /path/to/album
```

#### 6. Using File Patterns (Globbing)
Process all MP3 files in the current folder:
```bash
./tagger.py "*.mp3"
```

Process all FLAC files recursively across nested directories:
```bash
./tagger.py "**/*.flac"
```

#### 7. Disabling Recursive Traversal (Top-Level Only)
Scan only the top-level directory without descending into subfolders:
```bash
./tagger.py --no-recursive /path/to/music_collection
```

#### 8. Specifying Individual Files or Mixed Sources
```bash
./tagger.py song1.flac "album2/*.mp3" /path/to/album3
```

### Windows Command Examples (PowerShell & CMD)

On Windows, invoke the script using `python tagger.py` (or `py tagger.py`):

```powershell
# Tag an entire music folder recursively in-place
python tagger.py "C:\Users\YourName\Music\AlbumName"

# Tag and strip comments
python tagger.py --remove-comments "C:\Users\YourName\Music\AlbumName"

# Dry-run preview on a folder without modifying files
python tagger.py --dry-run "D:\Music\Downloads"

# Tag all MP3 files matching a pattern and copy them to a destination directory
python tagger.py -o "D:\Music\Tagged" "D:\Music\Incoming\*.mp3"

# Tag multiple folders using wildcards
python tagger.py "D:\Music\Albums\*"
```

---

## Update Statistics & Progress Tracking

During execution, `tagger.py` prints running statistics after each file is processed, followed by a final summary report across 4 non-exclusive categories:

1. **All metadata fields updated**: Every incoming non-empty metadata field differs from existing values (including empty $\to$ populated updates).
2. **Partially updated**: Some incoming fields differ while other existing fields already match the update values.
3. **No changes**: All incoming update values are identical to existing fields.
4. **Some fields removed**: Comment metadata was removed (via `--remove-comments`).

#### Output Example (with `-v / --verbose`):
```text
[1/2] 01 - Queen - Bohemian Rhapsody.flac
  Matched via [Text Search]: Queen - Bohemian Rhapsody [A Night at the Opera]
  Tags updated.
  Status: [All metadata fields updated, Some fields removed]
  Updated tags:
    - TITLE: <empty> -> 'Bohemian Rhapsody'
    - ARTIST: <empty> -> 'Queen'
    - ALBUM: <empty> -> 'A Night at the Opera'
    - DATE: <empty> -> '1975'
    - TRACKNUMBER: <empty> -> '11'
    - TRACKTOTAL: <empty> -> '12'
    - MUSICBRAINZ_TRACKID: <empty> -> 'b0a70f5e-149b-4bf1-893d-4c3e8006e897'
    - COMMENT: <present> -> <removed>
[Running Stats] All updated: 1 | Partially updated: 0 | No changes: 0 | Fields removed: 1 (1/2)

[2/2] 02 - Queen - Another One Bites the Dust.mp3
  Matched via [Text Search]: Queen - Another One Bites the Dust [The Game]
  Tags updated.
  Status: [Partially updated]
  Updated tags:
    - ALBUM: 'Greatest Hits' -> 'The Game'
    - DATE: '1981' -> '1980'
    - TRACKNUMBER: '3' -> '3/10'
[Running Stats] All updated: 1 | Partially updated: 1 | No changes: 0 | Fields removed: 1 (2/2)

============================================================
Update Statistics Summary (2 files processed)
------------------------------------------------------------
  1) All metadata fields updated: 1
  2) Partially updated:           1
  3) No changes:                  0
  4) Some fields removed:         1
============================================================
```

---

## Metadata Mapping

The script maps the discovered metadata to format-native tag structures:

| Metadata Field | FLAC (Vorbis Comment) | MP3 (ID3v2 Frame) |
|---|---|---|
| **Title** | `TITLE` | `TIT2` (`title`) |
| **Artist** | `ARTIST` | `TPE1` (`artist`) |
| **Album** | `ALBUM` | `TALB` (`album`) |
| **Date / Year** | `DATE` | `TDRC` (`date`) |
| **Track / Total** | `TRACKNUMBER`, `TRACKTOTAL` | `TRCK` (`tracknumber`, formatted as `X/Y`) |
| **Genre** | `GENRE` | `TCON` (`genre`) |
| **MusicBrainz ID** | `MUSICBRAINZ_TRACKID` | `UFID:http://musicbrainz.org` (`musicbrainz_trackid`) |

---

## How Matching Works

```
           +--------------------------+
           |       Audio File         |
           +--------------------------+
                        |
                        v
        +-------------------------------+
        |  Read Existing Tags / Name   |
        +-------------------------------+
                        |
            Found Artist & Title?
           /                     \
        (Yes)                    (No)
         /                         \
        v                           v
+------------------+     +------------------------+
| MusicBrainz Text |     | AcoustID Fingerprint   |
| API Search       |     | (fpcalc audio decode)  |
+------------------+     +------------------------+
        |                           |
     Matched?                    Matched?
     /      \                    /      \
  (Yes)     (No) ------------> (Yes)    (No)
   /                             /        \
  v                             v          v
+----------------------------------+     +-------------------+
|      Write Enriched Tags         |     | File Left Untouched|
+----------------------------------+     +-------------------+
```

1. **Text Search**: First inspects the file for existing tags (`title`, `artist`, `album`). If absent, it attempts to parse filenames matching `[TrackNumber] - [Artist] - [Title]`. Queries MusicBrainz recording search using a 1 req/sec rate limit.
2. **Acoustic Fingerprint**: If text matching fails or is ambiguous, it decodes the raw audio stream with `fpcalc` and queries the AcoustID database for a fingerprint match with confidence score $\ge 0.75$.
3. **Write**: Updates tags in-place or copies the file to the target output directory. Unmatched tracks remain completely untouched.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
