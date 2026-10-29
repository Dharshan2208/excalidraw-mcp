"""Font discovery, selection, and fallback rendering engine.

Discovers system TrueType/OpenType fonts across Linux, macOS, and Windows,
categorizes them into semantic families (sans-serif, monospace, serif, handwriting),
and provides cached font instantiation with robust fallback handling.
"""

import glob
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import ImageFont


# Standard font search paths by platform
def _get_font_directories() -> list[str]:
    dirs = []
    # Environment variable override/addition
    env_dir = os.environ.get("EXCALIDRAW_FONT_DIR")
    if env_dir and os.path.isdir(env_dir):
        dirs.append(env_dir)

    if sys.platform.startswith("linux"):
        dirs.extend(
            [
                "/usr/share/fonts",
                "/usr/local/share/fonts",
                os.path.expanduser("~/.local/share/fonts"),
                os.path.expanduser("~/.fonts"),
            ]
        )
    elif sys.platform == "darwin":
        dirs.extend(
            [
                "/System/Library/Fonts",
                "/Library/Fonts",
                os.path.expanduser("~/Library/Fonts"),
            ]
        )
    elif sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", "C:\\Windows")
        dirs.append(os.path.join(windir, "Fonts"))

    return [d for d in dirs if os.path.isdir(d)]


def _classify_category(name: str) -> str:
    """Classify a font family name into a standard semantic category."""
    lower = name.lower()
    if any(k in lower for k in ("mono", "code", "console", "typewriter", "courier", "fixed", "terminal")):
        return "monospace"
    if any(k in lower for k in ("serif", "times", "roman", "georgia", "garamond", "charter", "cambria", "c059")):
        return "serif"
    if any(k in lower for k in ("hand", "script", "virgil", "comic", "casual", "chalk", "caveat", "comfortaa", "excalifont")):
        return "handwriting"
    return "sans-serif"


PREFERRED_FAMILIES = {
    "sans-serif": (
        "liberation sans",
        "dejavu sans",
        "open sans",
        "noto sans",
        "roboto",
        "cantarell",
        "adwaita sans",
        "arial",
        "helvetica",
        "freesans",
        "ubuntu",
        "inter",
    ),
    "monospace": (
        "liberation mono",
        "dejavu sans mono",
        "jetbrains mono",
        "noto sans mono",
        "cascadia",
        "courier new",
        "consolas",
        "fira code",
        "freemono",
    ),
    "handwriting": (
        "excalifont",
        "virgil",
        "comic shanns",
        "caveat",
        "comfortaa",
    ),
    "serif": (
        "liberation serif",
        "dejavu serif",
        "noto serif",
        "times new roman",
        "georgia",
        "garamond",
        "freeserif",
    ),
}

NON_LATIN_SCRIPTS = (
    "ethiopic",
    "khmer",
    "arabic",
    "hebrew",
    "thai",
    "devanagari",
    "bengali",
    "tamil",
    "telugu",
    "kannada",
    "malayalam",
    "sinhala",
    "tibetan",
    "cherokee",
    "syriac",
    "thaana",
    "georgian",
    "armenian",
    "myanmar",
    "lao",
)


def _sort_category_records(records: list[dict[str, str]], category: str) -> list[dict[str, str]]:
    preferred = PREFERRED_FAMILIES.get(category, ())

    def sort_key(r: dict[str, str]):
        fam = r["family"].lower()
        is_non_latin = any(s in fam for s in NON_LATIN_SCRIPTS)
        pref_rank = 999
        for idx, pref in enumerate(preferred):
            if fam == pref:
                pref_rank = idx
                break
            elif pref in fam and not is_non_latin:
                pref_rank = 50 + idx
                break
        return (1 if is_non_latin else 0, pref_rank, fam)

    return sorted(records, key=sort_key)


def _font_renders_latin(font: ImageFont.ImageFont | ImageFont.FreeTypeFont) -> bool:
    """Check if the font contains valid glyphs for standard Latin text instead of .notdef fallback."""
    try:
        mask_a = font.getmask("A")
        mask_q = font.getmask("?")
        mask_b = font.getmask("B")
        if list(mask_a) == list(mask_q) and list(mask_b) == list(mask_q):
            return False
        return True
    except Exception:
        return True


class FontRegistry:
    """Discovers and caches available system and bundled fonts."""

    def __init__(self):
        self._fonts: list[dict[str, str]] = []
        self._by_family: dict[str, list[dict[str, str]]] = {}
        self._by_category: dict[str, list[dict[str, str]]] = {
            "sans-serif": [],
            "monospace": [],
            "serif": [],
            "handwriting": [],
        }
        self._discovered = False

    def discover(self, force: bool = False):
        if self._discovered and not force:
            return

        if force:
            self.load_font.cache_clear()

        self._fonts.clear()
        self._by_family.clear()
        for cat in self._by_category:
            self._by_category[cat].clear()

        # 1. Bundled assets directory (always prioritized)
        bundled_dir = Path(__file__).resolve().parent / "assets" / "fonts"
        if bundled_dir.is_dir():
            self._scan_directory(bundled_dir)

        # 2. Environment variable directory
        env_dir = os.environ.get("EXCALIDRAW_FONT_DIR")
        if env_dir and os.path.isdir(env_dir):
            self._scan_directory(env_dir)

        # 3. Try fc-list on Linux/macOS
        found_via_fclist = False
        if shutil.which("fc-list"):
            try:
                result = subprocess.run(
                    ["fc-list", ":", "file", "family", "style"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        parts = line.split(":")
                        if len(parts) >= 2:
                            path = parts[0].strip()
                            if not (path.endswith(".ttf") or path.endswith(".otf") or path.endswith(".ttc")):
                                continue
                            family = parts[1].strip().split(",")[0].strip()
                            style = "Regular"
                            if len(parts) > 2 and "style=" in parts[2]:
                                style = parts[2].split("style=")[1].split(",")[0].strip()
                            category = _classify_category(family)
                            record = {
                                "family": family,
                                "style": style,
                                "path": path,
                                "category": category,
                            }
                            self._add_record(record)
                    found_via_fclist = len(self._fonts) > 0
            except Exception:
                found_via_fclist = False

        # 4. Filesystem scan fallback or supplement
        if not found_via_fclist:
            for font_dir in _get_font_directories():
                self._scan_directory(font_dir)

        for cat in self._by_category:
            self._by_category[cat] = _sort_category_records(self._by_category[cat], cat)

        self._discovered = True

    def _scan_directory(self, font_dir: str | Path):
        for ext in ("**/*.ttf", "**/*.otf", "**/*.ttc"):
            for file_path in glob.glob(os.path.join(str(font_dir), ext), recursive=True):
                try:
                    test_font = ImageFont.truetype(file_path, 12)
                    names = test_font.getname()
                    family = (names[0] or Path(file_path).stem) if names else Path(file_path).stem
                    style = (names[1] or "Regular") if len(names) > 1 else "Regular"
                    category = _classify_category(family)
                    record = {
                        "family": family,
                        "style": style,
                        "path": file_path,
                        "category": category,
                    }
                    self._add_record(record)
                except Exception:
                    continue

    def _add_record(self, record: dict[str, str]):
        # Prevent duplicate paths
        if any(r["path"] == record["path"] for r in self._fonts):
            return
        self._fonts.append(record)
        fam_key = record["family"].lower()
        if fam_key not in self._by_family:
            self._by_family[fam_key] = []
        self._by_family[fam_key].append(record)
        self._by_category[record["category"]].append(record)

    def list_fonts(self, category: str | None = None) -> list[dict[str, str]]:
        self.discover()
        if category:
            cat = category.strip().lower()
            return list(self._by_category.get(cat, []))
        return list(self._fonts)

    @lru_cache(maxsize=128)
    def load_font(
        self,
        family: str | int | None = None,
        size: int = 14,
        bold: bool = False,
        italic: bool = False,
    ) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
        self.discover()
        size = max(6, min(200, int(size)))

        # 1. Map Excalidraw integer or string family names
        if isinstance(family, int):
            int_map = {
                1: "excalifont",  # Excalifont (Virgil)
                2: "sans-serif",  # Helvetica
                3: "monospace",  # Cascadia / code
                4: "handwriting",  # Comic Shanns
            }
            family = int_map.get(family, "sans-serif")
        elif isinstance(family, str):
            f_norm = family.strip().lower()
            if f_norm in ("1", "excalifont", "virgil"):
                family = "excalifont"
            elif f_norm in ("2", "sans-serif", "sans", "helvetica"):
                family = "sans-serif"
            elif f_norm in ("3", "monospace", "mono", "code", "cascadia"):
                family = "monospace"
            elif f_norm in ("4", "comic-shanns", "comic", "comic shanns"):
                family = "handwriting"

        # 2. Check environment overrides
        if not family:
            family = os.environ.get("EXCALIDRAW_DEFAULT_FONT") or "sans-serif"
        elif str(family).lower() in ("mono", "monospace", "code"):
            family = os.environ.get("EXCALIDRAW_MONO_FONT") or "monospace"

        fam_str = str(family).strip().lower()

        # Match preference: exact family -> partial family -> category -> system font
        matched_records = []
        if fam_str in self._by_family:
            matched_records = self._by_family[fam_str]
        elif fam_str in self._by_category:
            matched_records = self._by_category[fam_str]
        else:
            # Partial substring match
            for k, records in self._by_family.items():
                if fam_str in k:
                    matched_records = records
                    break

        # Filter by style if requested, prioritizing matching styles and valid Latin glyphs
        if matched_records:
            candidates = list(matched_records)
            if bold and italic:
                candidates.sort(key=lambda r: 0 if ("bold" in r["style"].lower() and "italic" in r["style"].lower()) else 1)
            elif bold:
                candidates.sort(key=lambda r: 0 if "bold" in r["style"].lower() else 1)
            elif italic:
                candidates.sort(key=lambda r: 0 if "italic" in r["style"].lower() else 1)
            else:
                candidates.sort(key=lambda r: 0 if "regular" in r["style"].lower() else 1)

            for target_record in candidates:
                try:
                    cand_font = ImageFont.truetype(target_record["path"], size)
                    if _font_renders_latin(cand_font):
                        return cand_font
                except Exception:
                    continue

        # 3. Fallback category search
        cat = _classify_category(fam_str)
        cat_records = self._by_category.get(cat, [])
        for r in cat_records:
            try:
                cand_font = ImageFont.truetype(r["path"], size)
                if _font_renders_latin(cand_font):
                    return cand_font
            except Exception:
                continue

        # 4. Fallback to any discovered font
        for r in self._fonts:
            try:
                cand_font = ImageFont.truetype(r["path"], size)
                if _font_renders_latin(cand_font):
                    return cand_font
            except Exception:
                continue

        # 5. Ultimate fallback: Pillow scalable default
        try:
            return ImageFont.load_default(size=size)
        except Exception:
            return ImageFont.load_default()

    def get_char_dimensions(
        self, font: ImageFont.ImageFont | ImageFont.FreeTypeFont
    ) -> tuple[float, float]:
        """Estimate standard character width and line height for layout calculations."""
        try:
            bbox = font.getbbox("M")
            char_w = max(7.0, float(bbox[2] - bbox[0]))
            char_h = max(12.0, float(bbox[3] - bbox[1]) * 1.3)
            return char_w, char_h
        except Exception:
            return 8.5, 18.0


# Global singleton registry
registry = FontRegistry()


def get_font(
    family: str | int | None = None,
    size: int = 14,
    bold: bool = False,
    italic: bool = False,
) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Convenience getter for cached font instances with fallback."""
    return registry.load_font(family=family, size=size, bold=bold, italic=italic)


def list_fonts(category: str | None = None) -> list[dict[str, str]]:
    """List all fonts discovered in the environment."""
    return registry.list_fonts(category=category)


def measure_text_dimensions(
    text_content: str,
    font_family: str | int | None = None,
    font_size: int = 20,
    line_height_mul: float = 1.25,
) -> tuple[float, float, list[float]]:
    """Accurately measure multiline text dimensions using actual font metrics.

    Returns:
        (max_line_width, total_height, line_widths)
    """
    if not text_content:
        return 0.0, float(font_size) * line_height_mul, [0.0]
    font = get_font(font_family, font_size)
    lines = text_content.splitlines() or [""]
    line_widths = []
    for line in lines:
        if not line:
            line_widths.append(0.0)
            continue
        try:
            bbox = font.getbbox(line)
            w = float(bbox[2] - bbox[0])
        except Exception:
            w = float(len(line)) * float(font_size) * 0.6
        line_widths.append(w)
    max_w = max(line_widths) if line_widths else 0.0
    line_h = float(font_size) * line_height_mul
    total_h = max(line_h, len(lines) * line_h)
    return max_w, total_h, line_widths
