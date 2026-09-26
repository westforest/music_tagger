#!/usr/bin/env python3
import sys
import os
import re
import glob
import shutil
import argparse
import time
import warnings
from pathlib import Path

# Ensure UTF-8 console output on Windows terminals
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# On Windows or portable setups, detect fpcalc executable if placed in script folder
if not os.environ.get("FPCALC") and not shutil.which("fpcalc") and not shutil.which("fpcalc.exe"):
    script_dir = Path(__file__).resolve().parent
    for candidate in ("fpcalc.exe", "fpcalc"):
        local_fpcalc = script_dir / candidate
        if local_fpcalc.is_file():
            os.environ["FPCALC"] = str(local_fpcalc)
            break

# Suppress requests urllib3/chardet mismatch warning if present
warnings.filterwarnings("ignore", category=Warning, module="requests")

from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
import acoustid
import musicbrainzngs

SUPPORTED_EXTENSIONS = {".flac", ".mp3"}

# Public AcoustID application key for fingerprint lookups
ACOUSTID_API_KEY = "cSpUJKpD"

# Configure MusicBrainz identity
musicbrainzngs.set_useragent(
    app="HybridAudioTagger",
    version="1.0",
    contact="user@example.com"
)


def guess_track_info_from_filename(file_path: Path):
    """
    Strips leading track numbers and attempts to split 'Artist - Title'.
    Rejects generic names like 'Track 01', 'Audio_1', etc.
    """
    stem = file_path.stem
    cleaned = re.sub(r'^\d+[\s._-]+', '', stem).strip()

    # If the remaining string is a generic placeholder, treat as unusable text
    if re.match(r'^(track|audio|untitled|cdda|disc|file)[\s._-]*\d*$', cleaned, re.IGNORECASE):
        return None, None

    if " - " in cleaned:
        parts = cleaned.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    
    # Return cleaned string as title candidate if long enough
    if len(cleaned) > 2:
        return None, cleaned
    return None, None


def read_existing_metadata(file_path: Path):
    """Reads existing metadata (Vorbis comments or ID3) if present, falling back to filename parsing."""
    artist, title, album = None, None, None
    ext = file_path.suffix.lower()

    try:
        if ext == ".flac":
            audio = FLAC(file_path)
            artist = audio.get("artist", [None])[0]
            title = audio.get("title", [None])[0]
            album = audio.get("album", [None])[0]
        elif ext == ".mp3":
            audio = EasyID3(file_path)
            artist = audio.get("artist", [None])[0]
            title = audio.get("title", [None])[0]
            album = audio.get("album", [None])[0]
    except Exception:
        artist, title, album = None, None, None

    if not artist or not title:
        guessed_artist, guessed_title = guess_track_info_from_filename(file_path)
        artist = artist or guessed_artist
        title = title or guessed_title

    return {
        "artist": artist,
        "title": title,
        "album": album
    }


def query_by_text(title: str, artist: str = None, album: str = None):
    """Priority 1: Looks up track info via MusicBrainz text search."""
    if not title:
        return None

    query_params = {"recording": title}
    if artist:
        query_params["artist"] = artist
    if album:
        query_params["release"] = album

    try:
        time.sleep(1.0)  # Respect MusicBrainz rate limit (1 req/sec)
        result = musicbrainzngs.search_recordings(limit=1, **query_params)
        recording_list = result.get("recording-list", [])
        
        if not recording_list:
            return None

        rec = recording_list[0]
        album_title, date, track_num, total_tracks = "", "", "", ""

        if "release-list" in rec and len(rec["release-list"]) > 0:
            rel = rec["release-list"][0]
            album_title = rel.get("title", "")
            date = rel.get("date", "")
            medium_list = rel.get("medium-list", [])
            if medium_list:
                medium = medium_list[0]
                total_tracks = str(medium.get("track-count", ""))
                track_list = medium.get("track-list", [])
                if track_list:
                    track_num = str(track_list[0].get("number", ""))

        tags = {
            "TITLE": rec.get("title", title),
            "ARTIST": rec.get("artist-credit-phrase", artist or "Unknown Artist"),
            "ALBUM": album_title or (album if album else "Unknown Album"),
            "DATE": date,
            "TRACKNUMBER": track_num,
            "TRACKTOTAL": total_tracks,
            "MUSICBRAINZ_TRACKID": rec.get("id", "")
        }

        tag_list = rec.get("tag-list", [])
        if tag_list:
            tags["GENRE"] = tag_list[0].get("name", "").title()

        return tags

    except musicbrainzngs.WebServiceError as e:
        print(f"    [Text API Warning] {e}")
        return None


def query_by_acoustic_fingerprint(file_path: Path):
    """Priority 2: Decodes audio, fingerprints with Chromaprint, matches on AcoustID."""
    try:
        results = acoustid.match(ACOUSTID_API_KEY, str(file_path))
        
        for score, recording_id, title, artist in results:
            # Match confidence threshold (0.0 to 1.0)
            if score >= 0.75:
                time.sleep(1.0)
                rec_data = musicbrainzngs.get_recording_by_id(
                    recording_id, 
                    includes=["releases", "artists", "tags"]
                )
                rec = rec_data.get("recording", {})

                album_title, date, track_num, total_tracks = "", "", "", ""
                releases = rec.get("release-list", [])
                if releases:
                    rel = releases[0]
                    album_title = rel.get("title", "")
                    date = rel.get("date", "")
                    medium_list = rel.get("medium-list", [])
                    if medium_list:
                        total_tracks = str(medium_list[0].get("track-count", ""))
                        track_list = medium_list[0].get("track-list", [])
                        if track_list:
                            track_num = str(track_list[0].get("number", ""))

                tags = {
                    "TITLE": rec.get("title", title),
                    "ARTIST": rec.get("artist-credit-phrase", artist),
                    "ALBUM": album_title or "Unknown Album",
                    "DATE": date,
                    "TRACKNUMBER": track_num,
                    "TRACKTOTAL": total_tracks,
                    "MUSICBRAINZ_TRACKID": recording_id
                }

                tag_list = rec.get("tag-list", [])
                if tag_list:
                    tags["GENRE"] = tag_list[0].get("name", "").title()

                return tags
                
    except acoustid.NoBackendError:
        print("    [!] Chromaprint binary (fpcalc) not found. Acoustic fallback disabled.")
    except Exception as e:
        print(f"    [Acoustic API Warning] {e}")

    return None


def write_flac_tags(target_path: Path, metadata: dict):
    """Writes Vorbis comment blocks into the target FLAC file."""
    audio = FLAC(target_path)
    for key, value in metadata.items():
        if value:
            audio[key] = str(value)
    audio.save()


def write_mp3_tags(target_path: Path, metadata: dict):
    """Writes ID3 tags into the target MP3 file using EasyID3."""
    audio = MP3(target_path, ID3=EasyID3)
    if audio.tags is None:
        audio.add_tags(ID3=EasyID3)

    field_map = {
        "TITLE": "title",
        "ARTIST": "artist",
        "ALBUM": "album",
        "DATE": "date",
        "GENRE": "genre",
        "MUSICBRAINZ_TRACKID": "musicbrainz_trackid",
    }
    for meta_key, easy_key in field_map.items():
        val = metadata.get(meta_key)
        if val:
            audio[easy_key] = str(val)

    track_num = metadata.get("TRACKNUMBER")
    track_total = metadata.get("TRACKTOTAL")
    if track_num and track_total:
        audio["tracknumber"] = f"{track_num}/{track_total}"
    elif track_num:
        audio["tracknumber"] = str(track_num)

    audio.save()


def write_audio_tags(target_path: Path, metadata: dict):
    """Dispatches tag writing based on file format extension."""
    ext = target_path.suffix.lower()
    if ext == ".flac":
        write_flac_tags(target_path, metadata)
    elif ext == ".mp3":
        write_mp3_tags(target_path, metadata)
    else:
        raise ValueError(f"Unsupported audio format: {target_path.suffix}")


def _scan_directory(dir_path: Path, recursive: bool = True) -> list[Path]:
    """Scans a directory for supported audio files, optionally recurring into subdirectories."""
    files: list[Path] = []
    iterator = dir_path.rglob("*") if recursive else dir_path.iterdir()
    for child in sorted(iterator):
        # Ignore hidden files and directories (e.g. .git, .cache)
        try:
            rel_parts = child.relative_to(dir_path).parts
            if any(part.startswith(".") for part in rel_parts):
                continue
        except ValueError:
            pass

        if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(child)
    return files


def resolve_audio_files(sources, recursive: bool = True) -> list[Path]:
    """
    Resolves directories, file paths, or glob patterns into a sorted list of unique audio files.
    When directories or directory patterns are encountered, traverses them recursively if recursive is True.
    """
    if isinstance(sources, (str, Path)):
        sources = [sources]

    candidate_files: list[Path] = []

    for src in sources:
        src_str = str(src).strip()
        path_obj = Path(src_str).expanduser()

        if path_obj.exists():
            if path_obj.is_dir():
                candidate_files.extend(_scan_directory(path_obj, recursive=recursive))
            elif path_obj.is_file():
                if path_obj.suffix.lower() in SUPPORTED_EXTENSIONS:
                    candidate_files.append(path_obj)
                else:
                    print(f"  [!] Skipping unsupported file format: {path_obj}")
        else:
            expanded_pattern = os.path.expanduser(src_str)
            matches = sorted(glob.glob(expanded_pattern, recursive=True))
            if matches:
                for match in matches:
                    p = Path(match)
                    if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                        candidate_files.append(p)
                    elif p.is_dir():
                        candidate_files.extend(_scan_directory(p, recursive=recursive))
            else:
                print(f"  [!] No files or directories found matching: {src_str}")

    seen = set()
    unique_files: list[Path] = []
    for file_path in candidate_files:
        try:
            resolved = file_path.resolve()
        except Exception:
            resolved = file_path.absolute()
        # On Windows, path comparisons should be case-insensitive
        key = str(resolved).lower() if sys.platform == "win32" else str(resolved)
        if key not in seen:
            seen.add(key)
            unique_files.append(file_path)

    return unique_files


def process_files(sources, output_dir: Path = None, dry_run: bool = False, recursive: bool = True):
    audio_files = resolve_audio_files(sources, recursive=recursive)
    if not audio_files:
        ext_list = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        print(f"No supported audio files ({ext_list}) found.")
        return

    print(f"Found {len(audio_files)} audio file(s) to process.\n")

    for idx, src_file in enumerate(audio_files, start=1):
        print(f"[{idx}/{len(audio_files)}] {src_file.name}")
        metadata = None
        method_used = None

        # ------------------------------------------------------------------
        # Step 1: Text-Based Match (Priority 1)
        # ------------------------------------------------------------------
        seed = read_existing_metadata(src_file)
        if seed["title"]:
            print(f"  -> Attempting text match ('{seed['artist']}' - '{seed['title']}')...")
            metadata = query_by_text(seed["title"], seed["artist"], seed["album"])
            if metadata:
                method_used = "Text Search"

        # ------------------------------------------------------------------
        # Step 2: Acoustic Fingerprint Fallback (Priority 2)
        # ------------------------------------------------------------------
        if not metadata:
            print("  -> Text match failed or missing. Falling back to acoustic fingerprinting...")
            metadata = query_by_acoustic_fingerprint(src_file)
            if metadata:
                method_used = "Acoustic Fingerprint"

        # ------------------------------------------------------------------
        # Step 3: Handle Unmatched Tracks
        # ------------------------------------------------------------------
        if not metadata:
            print("  [!] Failed to match via text and audio. File untouched.\n")
            continue

        print(f"  Matched via [{method_used}]: {metadata.get('ARTIST')} - {metadata.get('TITLE')} [{metadata.get('ALBUM')}]")

        if dry_run:
            print("  [Dry-run] Skipping file writes.\n")
            continue

        # ------------------------------------------------------------------
        # Step 4: Write In-Place or Copy
        # ------------------------------------------------------------------
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            target = output_dir / src_file.name
            if target.resolve() != src_file.resolve():
                shutil.copy2(src_file, target)
                print(f"  Copied to: {target}")
            else:
                print(f"  Modifying in-place: {target}")
        else:
            target = src_file
            print(f"  Modifying in-place: {target}")

        write_audio_tags(target, metadata)
        print("  Tags updated.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Batch tag audio files (FLAC, MP3) using text lookup first, falling back to acoustic fingerprinting."
    )
    parser.add_argument(
        "source",
        nargs="+",
        help="Source directory, file, or pattern (e.g. /path/to/dir, '*.flac', song.mp3)"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Destination directory. If omitted, tags are updated in-place."
    )
    parser.add_argument(
        "-r", "--recursive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Search directories and dir patterns recursively for audio files (default: True)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate lookups without modifying or copying files."
    )

    args = parser.parse_args()

    process_files(args.source, args.output, dry_run=args.dry_run, recursive=args.recursive)


if __name__ == "__main__":
    main()
