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
Make sure Python 3 and `pip` are installed on your system.

### 2. Chromaprint (`fpcalc`)
The acoustic fingerprinting fallback requires the `fpcalc` CLI binary from Chromaprint:

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

1. **Clone the repository**:
   ```bash
   git clone https://github.com/westforest/music_tagger.git
   cd music_tagger
   ```

2. **Create and activate a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## Usage

```text
usage: tagger.py [-h] [-o OUTPUT] [--dry-run] source [source ...]

Batch tag audio files (FLAC, MP3) using text lookup first, falling back to
acoustic fingerprinting.

positional arguments:
  source                Source directory, file, or pattern (e.g. /path/to/dir, '*.flac', song.mp3)

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Destination directory. If omitted, tags are updated in-place.
  --dry-run             Simulate lookups without modifying or copying files.
```

### Examples

#### 1. Tag an Entire Album Directory (In-Place)
```bash
./tagger.py /path/to/album
```

#### 2. Dry-Run Simulation (No Files Modified)
Preview metadata matches before committing changes:
```bash
./tagger.py --dry-run /path/to/album
```

#### 3. Copy Tagged Files to an Output Directory
Leave originals untouched and write tagged copies to a new folder:
```bash
./tagger.py -o /path/to/sorted_music /path/to/album
```

#### 4. Using File Patterns (Globbing)
Process all MP3 files in the current folder:
```bash
./tagger.py "*.mp3"
```

Process all FLAC files recursively across nested directories:
```bash
./tagger.py "**/*.flac"
```

#### 5. Specifying Individual Files or Mixed Sources
```bash
./tagger.py song1.flac "album2/*.mp3" /path/to/album3
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
