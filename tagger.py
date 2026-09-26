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


def has_comment_metadata(file_path: Path) -> bool:
    """Checks if an audio file contains any comment metadata fields."""
    ext = file_path.suffix.lower()
    try:
        if ext == ".flac":
            audio = FLAC(file_path)
            return any(k.upper() in {"COMMENT", "DESCRIPTION", "COMMENTS"} for k in audio.keys())
        elif ext == ".mp3":
            audio = MP3(file_path)
            if audio.tags:
                return any(k.startswith("COMM") for k in audio.tags.keys())
    except Exception:
        pass
    return False


def remove_comment_metadata(target_path: Path) -> bool:
    """
    Removes comment metadata from FLAC (COMMENT/DESCRIPTION) or MP3 (COMM frames).
    Returns True if any comments were found and deleted.
    """
    ext = target_path.suffix.lower()
    removed = False
    try:
        if ext == ".flac":
            audio = FLAC(target_path)
            comment_keys = [k for k in audio.keys() if k.upper() in {"COMMENT", "DESCRIPTION", "COMMENTS"}]
            for k in comment_keys:
                del audio[k]
                removed = True
            if removed:
                audio.save()
        elif ext == ".mp3":
            audio = MP3(target_path)
            if audio.tags:
                comm_keys = [k for k in audio.tags.keys() if k.startswith("COMM")]
                for k in comm_keys:
                    del audio.tags[k]
                    removed = True
                if removed:
                    audio.save()
    except Exception as e:
        print(f"    [Warning] Failed to remove comments from {target_path.name}: {e}")
    return removed


def inspect_existing_tags(file_path: Path) -> dict[str, str]:
    """Reads current tag values for comparison with incoming updates."""
    ext = file_path.suffix.lower()
    tags: dict[str, str] = {}
    try:
        if ext == ".flac":
            audio = FLAC(file_path)
            tags["TITLE"] = audio.get("title", [""])[0] or ""
            tags["ARTIST"] = audio.get("artist", [""])[0] or ""
            tags["ALBUM"] = audio.get("album", [""])[0] or ""
            tags["DATE"] = audio.get("date", [""])[0] or ""
            tags["TRACKNUMBER"] = audio.get("tracknumber", [""])[0] or ""
            tags["TRACKTOTAL"] = audio.get("tracktotal", [""])[0] or ""
            tags["GENRE"] = audio.get("genre", [""])[0] or ""
            tags["MUSICBRAINZ_TRACKID"] = audio.get("musicbrainz_trackid", [""])[0] or ""
        elif ext == ".mp3":
            audio = EasyID3(file_path)
            tags["TITLE"] = audio.get("title", [""])[0] or ""
            tags["ARTIST"] = audio.get("artist", [""])[0] or ""
            tags["ALBUM"] = audio.get("album", [""])[0] or ""
            tags["DATE"] = audio.get("date", [""])[0] or ""
            tags["TRACKNUMBER"] = audio.get("tracknumber", [""])[0] or ""
            tags["GENRE"] = audio.get("genre", [""])[0] or ""
            tags["MUSICBRAINZ_TRACKID"] = audio.get("musicbrainz_trackid", [""])[0] or ""
    except Exception:
        pass
    return tags


def evaluate_tag_update_status(
    file_path: Path,
    new_metadata: dict | None,
    remove_comments: bool,
    has_comments: bool,
) -> tuple[bool, bool, bool, bool, list[str]]:
    """
    Compares existing tags with proposed updates to classify update status:
      1) all_updated: all incoming non-empty metadata fields differ from existing.
      2) partially_updated: some incoming fields differ and some already match existing values.
      3) no_changes: all incoming fields match existing values.
      4) fields_removed: comment metadata was removed.
    Returns: (is_all_updated, is_partially_updated, is_no_changes, is_fields_removed, status_descriptions)
    """
    is_fields_removed = remove_comments and has_comments

    if not new_metadata:
        status_descs = []
        if is_fields_removed:
            status_descs.append("Some fields removed")
        else:
            status_descs.append("Unmatched / Untouched")
        return False, False, False, is_fields_removed, status_descs

    existing = inspect_existing_tags(file_path)
    ext = file_path.suffix.lower()

    fields_to_check: dict[str, str] = {}
    if ext == ".flac":
        for k, v in new_metadata.items():
            if v:
                fields_to_check[k] = str(v).strip()
    elif ext == ".mp3":
        for k in ("TITLE", "ARTIST", "ALBUM", "DATE", "GENRE", "MUSICBRAINZ_TRACKID"):
            v = new_metadata.get(k)
            if v:
                fields_to_check[k] = str(v).strip()
        t_num = new_metadata.get("TRACKNUMBER")
        t_tot = new_metadata.get("TRACKTOTAL")
        if t_num and t_tot:
            fields_to_check["TRACKNUMBER"] = f"{t_num}/{t_tot}"
        elif t_num:
            fields_to_check["TRACKNUMBER"] = str(t_num)

    updated_count = 0
    same_count = 0

    for field, new_val in fields_to_check.items():
        old_val = existing.get(field, "").strip()
        if old_val == new_val:
            same_count += 1
        else:
            updated_count += 1

    is_all_updated = (updated_count > 0 and same_count == 0)
    is_partially_updated = (updated_count > 0 and same_count > 0)
    is_no_changes = (updated_count == 0 and same_count > 0)

    status_descs = []
    if is_all_updated:
        status_descs.append("All metadata fields updated")
    elif is_partially_updated:
        status_descs.append("Partially updated")
    elif is_no_changes:
        status_descs.append("No changes")

    if is_fields_removed:
        status_descs.append("Some fields removed")

    return is_all_updated, is_partially_updated, is_no_changes, is_fields_removed, status_descs


def write_flac_tags(target_path: Path, metadata: dict, remove_comments: bool = False):
    """Writes Vorbis comment blocks into the target FLAC file."""
    if remove_comments:
        remove_comment_metadata(target_path)
    audio = FLAC(target_path)
    for key, value in metadata.items():
        if value:
            audio[key] = str(value)
    audio.save()


def write_mp3_tags(target_path: Path, metadata: dict, remove_comments: bool = False):
    """Writes ID3 tags into the target MP3 file using EasyID3."""
    if remove_comments:
        remove_comment_metadata(target_path)

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


def write_audio_tags(target_path: Path, metadata: dict, remove_comments: bool = False):
    """Dispatches tag writing based on file format extension."""
    ext = target_path.suffix.lower()
    if ext == ".flac":
        write_flac_tags(target_path, metadata, remove_comments=remove_comments)
    elif ext == ".mp3":
        write_mp3_tags(target_path, metadata, remove_comments=remove_comments)
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


def process_files(
    sources,
    output_dir: Path = None,
    dry_run: bool = False,
    recursive: bool = True,
    remove_comments: bool = False,
):
    audio_files = resolve_audio_files(sources, recursive=recursive)
    if not audio_files:
        ext_list = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        print(f"No supported audio files ({ext_list}) found.")
        return

    print(f"Found {len(audio_files)} audio file(s) to process.\n")

    stats = {
        "all_updated": 0,
        "partially_updated": 0,
        "no_changes": 0,
        "fields_removed": 0,
    }

    for idx, src_file in enumerate(audio_files, start=1):
        print(f"[{idx}/{len(audio_files)}] {src_file.name}")
        metadata = None
        method_used = None

        # Check existing comment status before any modification
        file_has_comments = has_comment_metadata(src_file)

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
        # Evaluate Update Status for Statistics
        # ------------------------------------------------------------------
        all_up, part_up, no_chg, rem_fld, status_descs = evaluate_tag_update_status(
            src_file, metadata, remove_comments, file_has_comments
        )
        if all_up:
            stats["all_updated"] += 1
        if part_up:
            stats["partially_updated"] += 1
        if no_chg:
            stats["no_changes"] += 1
        if rem_fld:
            stats["fields_removed"] += 1

        # ------------------------------------------------------------------
        # Step 3: Handle Tag Writing or Comment Stripping
        # ------------------------------------------------------------------
        if not metadata:
            if remove_comments and file_has_comments and not dry_run:
                if output_dir:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    target = output_dir / src_file.name
                    if target.resolve() != src_file.resolve():
                        shutil.copy2(src_file, target)
                else:
                    target = src_file
                remove_comment_metadata(target)
                print("  [!] Unmatched metadata. Comment metadata removed.")
            else:
                print("  [!] Failed to match via text and audio. File untouched.")
        else:
            print(f"  Matched via [{method_used}]: {metadata.get('ARTIST')} - {metadata.get('TITLE')} [{metadata.get('ALBUM')}]")

            if dry_run:
                print("  [Dry-run] Skipping file writes.")
            else:
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

                write_audio_tags(target, metadata, remove_comments=remove_comments)
                print("  Tags updated.")

        # Display update status and running stats after each file
        status_line = ", ".join(status_descs) if status_descs else "No update"
        print(f"  Status: [{status_line}]")
        print(
            f"  [Running Stats] All updated: {stats['all_updated']} | "
            f"Partially updated: {stats['partially_updated']} | "
            f"No changes: {stats['no_changes']} | "
            f"Fields removed: {stats['fields_removed']} ({idx}/{len(audio_files)})\n"
        )

    # Summary report
    print("=" * 60)
    print(f"Update Statistics Summary ({len(audio_files)} files processed)")
    print("-" * 60)
    print(f"  1) All metadata fields updated: {stats['all_updated']}")
    print(f"  2) Partially updated:           {stats['partially_updated']}")
    print(f"  3) No changes:                  {stats['no_changes']}")
    print(f"  4) Some fields removed:         {stats['fields_removed']}")
    print("=" * 60 + "\n")


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
        "--remove-comments",
        action="store_true",
        help="Remove all comment metadata fields (Vorbis COMMENT/DESCRIPTION, ID3 COMM frames)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate lookups without modifying or copying files."
    )

    args = parser.parse_args()

    process_files(
        args.source,
        args.output,
        dry_run=args.dry_run,
        recursive=args.recursive,
        remove_comments=args.remove_comments,
    )


if __name__ == "__main__":
    main()
