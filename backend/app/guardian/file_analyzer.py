"""Guardian File Security Analyzer: Safe static inspection, signature verification, and hashing."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import math
import os
from pathlib import Path
import re
import struct
import tempfile
from typing import Any, BinaryIO, Iterator
import zipfile

from app.config import get_settings
from app.core.logging import get_logger
from app.schemas.guardian import GuardianFinding

logger = get_logger("guardian.file_analyzer")

# Magic bytes signature database
FILE_SIGNATURES: list[tuple[bytes, int, str, str]] = [
    # (magic_bytes, offset, format_name, mime_type)
    (b"%PDF-", 0, "PDF Document", "application/pdf"),
    (b"PK\x03\x04", 0, "ZIP Archive / Office Document", "application/zip"),
    (b"\x89PNG\r\n\x1a\n", 0, "PNG Image", "image/png"),
    (b"\xff\xd8\xff", 0, "JPEG Image", "image/jpeg"),
    (b"GIF87a", 0, "GIF Image", "image/gif"),
    (b"GIF89a", 0, "GIF Image", "image/gif"),
    (b"RIFF", 0, "RIFF Container (WebP/WAV/AVI)", "application/octet-stream"),
    (b"MZ", 0, "Windows PE Executable / DLL", "application/x-dosexec"),
    (b"\x7fELF", 0, "Linux ELF Executable", "application/x-executable"),
    (b"7z\xbc\xaf\x27\x1c", 0, "7-Zip Archive", "application/x-7z-compressed"),
    (b"Rar!\x1a\x07", 0, "RAR Archive", "application/vnd.rar"),
    (b"\x1f\x8b", 0, "Gzip Compressed File", "application/gzip"),
]

# File extension to expected format mapping
EXTENSION_EXPECTATIONS: dict[str, set[str]] = {
    ".pdf": {"PDF Document"},
    ".zip": {"ZIP Archive / Office Document"},
    ".docx": {"ZIP Archive / Office Document"},
    ".xlsx": {"ZIP Archive / Office Document"},
    ".pptx": {"ZIP Archive / Office Document"},
    ".png": {"PNG Image"},
    ".jpg": {"JPEG Image"},
    ".jpeg": {"JPEG Image"},
    ".gif": {"GIF Image"},
    ".exe": {"Windows PE Executable / DLL"},
    ".dll": {"Windows PE Executable / DLL"},
    ".sys": {"Windows PE Executable / DLL"},
    ".elf": {"Linux ELF Executable"},
    ".7z": {"7-Zip Archive"},
    ".rar": {"RAR Archive"},
    ".gz": {"Gzip Compressed File"},
}

DANGEROUS_EXTENSIONS = {
    ".exe", ".dll", ".scr", ".bat", ".cmd", ".vbs", ".ps1", ".jar",
    ".msi", ".pif", ".hta", ".cpl", ".iso", ".vhd", ".lnk"
}


def compute_shannon_entropy(data: bytes) -> float:
    """Calculate Shannon entropy of a byte sequence (0.0 to 8.0). High entropy indicates packing or encryption."""
    if not data:
        return 0.0
    byte_counts = [0] * 256
    for b in data:
        byte_counts[b] += 1
    entropy = 0.0
    total = len(data)
    for count in byte_counts:
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return round(entropy, 3)


def sanitize_filename(filename: str) -> str:
    """Strip path traversal, directory separators, and control characters from user filenames."""
    name = os.path.basename(filename.strip().replace("\\", "/"))
    # Remove null bytes and non-printable characters
    clean = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", name)
    return clean[:255] or "unnamed_file.bin"


class FileSecurityAnalyzer:
    """Performs defensive static analysis, cryptographic hashing, and signature validation."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @contextmanager
    def create_safe_temp_file(self, stream: BinaryIO, max_size: int | None = None) -> Iterator[tuple[Path, int]]:
        """Spool uploaded stream to a secure temporary file with 0o600 permissions and guaranteed cleanup."""
        limit = max_size or self.settings.guardian_max_file_size_bytes
        temp_dir = Path(tempfile.gettempdir()) / "lumo_guardian_spool"
        temp_dir.mkdir(parents=True, exist_ok=True)

        temp_file = tempfile.NamedTemporaryFile(
            dir=str(temp_dir),
            prefix="lumo_analysis_",
            suffix=".tmp",
            delete=False,
        )
        temp_path = Path(temp_file.name)
        # Enforce strict owner-only read/write permissions
        try:
            os.chmod(temp_path, 0o600)
        except Exception:
            pass

        total_bytes = 0
        try:
            chunk_size = 64 * 1024
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > limit:
                    raise ValueError(f"File exceeds maximum allowed upload size of {limit // (1024 * 1024)} MB.")
                temp_file.write(chunk)
            temp_file.flush()
            temp_file.close()

            yield temp_path, total_bytes
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception as exc:
                    logger.warning("Failed to remove temporary spool file %s: %s", temp_path, exc)

    def analyze_file_stream(
        self,
        stream: BinaryIO,
        original_filename: str,
    ) -> tuple[dict[str, str], str, str, list[GuardianFinding], dict[str, Any], int]:
        """Analyze a file stream, returning (hashes, signature_format, detected_mime, findings, static_features, size_bytes)."""
        safe_name = sanitize_filename(original_filename)

        with self.create_safe_temp_file(stream) as (temp_path, file_size):
            return self.analyze_file_path(temp_path, safe_name, file_size)

    def analyze_file_path(
        self,
        file_path: Path,
        filename: str,
        file_size: int,
    ) -> tuple[dict[str, str], str, str, list[GuardianFinding], dict[str, Any], int]:
        """Inspect on-disk file statically."""
        findings: list[GuardianFinding] = []
        static_features: dict[str, Any] = {}

        # 1. Cryptographic Hashing
        sha256_h = hashlib.sha256()
        sha1_h = hashlib.sha1()
        md5_h = hashlib.md5()

        header_bytes = b""
        with open(file_path, "rb") as f:
            header_bytes = f.read(4096)
            f.seek(0)
            while chunk := f.read(64 * 1024):
                sha256_h.update(chunk)
                sha1_h.update(chunk)
                md5_h.update(chunk)

        hashes = {
            "sha256": sha256_h.hexdigest(),
            "sha1": sha1_h.hexdigest(),
            "md5": md5_h.hexdigest(),
        }

        # Overall file entropy
        overall_entropy = compute_shannon_entropy(header_bytes)
        static_features["header_entropy"] = overall_entropy
        static_features["file_size_bytes"] = file_size

        # 2. File Signature Detection
        detected_format = "Unknown / Binary"
        detected_mime = "application/octet-stream"

        for magic, offset, fmt_name, mime in FILE_SIGNATURES:
            if len(header_bytes) >= offset + len(magic):
                if header_bytes[offset : offset + len(magic)] == magic:
                    # Specific RIFF WebP check
                    if magic == b"RIFF" and len(header_bytes) >= 12:
                        if header_bytes[8:12] == b"WEBP":
                            detected_format = "WebP Image"
                            detected_mime = "image/webp"
                            break
                    detected_format = fmt_name
                    detected_mime = mime
                    break

        # Check if text file (printable ASCII or UTF-8)
        if detected_format.startswith("Unknown"):
            try:
                header_bytes.decode("utf-8")
                detected_format = "Plain Text / Script"
                detected_mime = "text/plain"
            except UnicodeDecodeError:
                pass

        static_features["detected_format"] = detected_format
        static_features["detected_mime"] = detected_mime

        # 3. Extension vs Signature Mismatch Detection
        file_ext = Path(filename).suffix.lower()
        static_features["file_extension"] = file_ext

        if file_ext in EXTENSION_EXPECTATIONS:
            expected_formats = EXTENSION_EXPECTATIONS[file_ext]
            if detected_format not in expected_formats:
                findings.append(
                    GuardianFinding(
                        name="File Extension and Magic Signature Mismatch",
                        description=(
                            f"The file has extension '{file_ext}' but its initial magic bytes match '{detected_format}'. "
                            "This disguise is commonly used in deceptive malware payloads."
                        ),
                        severity="critical" if detected_format == "Windows PE Executable / DLL" else "high",
                        evidence=f"Extension '{file_ext}' vs Signature '{detected_format}'",
                        recommendation="Do not open this file. Renaming an executable to look like a document or image is an indicator of compromise.",
                    )
                )

        if file_ext in DANGEROUS_EXTENSIONS:
            findings.append(
                GuardianFinding(
                    name="Potentially Dangerous Executable File Extension",
                    description=f"The file extension '{file_ext}' indicates an executable, installer, or script capable of direct code execution.",
                    severity="high" if detected_format == "Windows PE Executable / DLL" else "medium",
                    evidence=f"File extension: {filename}",
                    recommendation="Ensure the file provenance is trusted. Never execute downloaded binaries from unverified sources.",
                )
            )

        # 4. Format-Specific Deep Static Inspection
        if detected_format == "PDF Document":
            pdf_findings = self._inspect_pdf(file_path, static_features)
            findings.extend(pdf_findings)
        elif detected_format == "ZIP Archive / Office Document":
            zip_findings = self._inspect_zip_archive(file_path, file_ext, static_features)
            findings.extend(zip_findings)
        elif detected_format == "Windows PE Executable / DLL":
            pe_findings = self._inspect_pe(file_path, static_features)
            findings.extend(pe_findings)
        elif detected_format == "Plain Text / Script":
            script_findings = self._inspect_script_text(file_path, static_features)
            findings.extend(script_findings)

        return hashes, detected_format, detected_mime, findings, static_features, file_size

    def _inspect_pdf(self, path: Path, static_features: dict[str, Any]) -> list[GuardianFinding]:
        """Inspect PDF structure for dangerous active content (JavaScript, Launch, EmbeddedFiles)."""
        findings: list[GuardianFinding] = []
        try:
            with open(path, "rb") as f:
                content = f.read(512 * 1024)  # Read up to 512KB for structure scan

            indicators = {
                b"/JavaScript": ("Embedded JavaScript in PDF", "medium"),
                b"/JS": ("Embedded JavaScript Action in PDF", "medium"),
                b"/Launch": ("Automatic Application Launch Action in PDF", "critical"),
                b"/EmbeddedFiles": ("Embedded File Attachment inside PDF", "medium"),
                b"/OpenAction": ("Automatic OpenAction Trigger on PDF Load", "low"),
                b"/AcroForm": ("Interactive Form (AcroForm) Present", "informational"),
            }

            detected_triggers = []
            for token, (name, severity) in indicators.items():
                if token in content:
                    detected_triggers.append(token.decode("ascii", errors="ignore"))
                    findings.append(
                        GuardianFinding(
                            name=name,
                            description=f"The PDF contains active element '{token.decode('ascii', errors='ignore')}' which can execute code or trigger external requests.",
                            severity=severity,
                            evidence=f"Found token {token.decode('ascii', errors='ignore')}",
                            recommendation="Disable PDF JavaScript and automatic execution in your PDF reader before opening.",
                        )
                    )
            static_features["pdf_triggers"] = detected_triggers
        except Exception as exc:
            logger.debug("PDF inspection error: %s", exc)
        return findings

    def _inspect_zip_archive(self, path: Path, file_ext: str, static_features: dict[str, Any]) -> list[GuardianFinding]:
        """Inspect ZIP / Office files for decompression bombs, path traversal, and macros."""
        findings: list[GuardianFinding] = []
        try:
            with zipfile.ZipFile(path, "r") as zf:
                infolist = zf.infolist()
                total_uncompressed = sum(info.file_size for info in infolist)
                total_compressed = sum(info.compress_size for info in infolist) or 1
                ratio = total_uncompressed / total_compressed

                static_features["zip_member_count"] = len(infolist)
                static_features["zip_total_uncompressed_bytes"] = total_uncompressed
                static_features["zip_compression_ratio"] = round(ratio, 2)

                # Decompression bomb detection
                if ratio > 100.0 and total_uncompressed > 50 * 1024 * 1024:
                    findings.append(
                        GuardianFinding(
                            name="Potential Decompression Bomb (Zip Bomb)",
                            description=f"Extreme compression ratio ({ratio:.1f}:1) detected. Extracting could exhaust memory or disk.",
                            severity="high",
                            evidence=f"Uncompressed: {total_uncompressed // (1024*1024)} MB, Compressed: {total_compressed // 1024} KB",
                            recommendation="Do not uncompress this archive automatically.",
                        )
                    )

                # Path traversal detection in member names
                traversal_members = []
                executable_members = []
                has_macros = False

                for info in infolist:
                    name = info.filename
                    if ".." in name or name.startswith("/") or name.startswith("\\"):
                        traversal_members.append(name)
                    ext = Path(name).suffix.lower()
                    if ext in DANGEROUS_EXTENSIONS:
                        executable_members.append(name)
                    if "vbaproject.bin" in name.lower() or "macros" in name.lower():
                        has_macros = True

                if traversal_members:
                    findings.append(
                        GuardianFinding(
                            name="Archive Path Traversal Attempt (Zip Slip)",
                            description="Archive contains files with relative or absolute directory traversal patterns.",
                            severity="critical",
                            evidence=f"Members: {traversal_members[:3]}",
                            recommendation="Do not extract this archive; it could overwrite critical system files.",
                        )
                    )

                if executable_members:
                    findings.append(
                        GuardianFinding(
                            name="Executable Binary Found Inside Archive",
                            description="Archive contains directly executable application files.",
                            severity="high",
                            evidence=f"Executable files: {executable_members[:3]}",
                            recommendation="Inspect all contained executables with caution before running.",
                        )
                    )

                if has_macros:
                    findings.append(
                        GuardianFinding(
                            name="Embedded VBA Macros in Office Document",
                            description="The archive contains a VBA project binary (vbaProject.bin) indicating embedded automated macros.",
                            severity="high",
                            evidence="VBA macros binary present in archive",
                            recommendation="Never enable macros when opening documents from untrusted or external sources.",
                        )
                    )
                static_features["has_vba_macros"] = has_macros

        except zipfile.BadZipFile:
            findings.append(
                GuardianFinding(
                    name="Corrupted or Malformed ZIP Archive",
                    description="The archive header is invalid or corrupted.",
                    severity="low",
                    evidence="BadZipFile exception",
                    recommendation="Confirm the integrity of the downloaded archive file.",
                )
            )
        except Exception as exc:
            logger.debug("Archive inspection error: %s", exc)
        return findings

    def _inspect_pe(self, path: Path, static_features: dict[str, Any]) -> list[GuardianFinding]:
        """Safely inspect Windows PE headers and section entropy without loading or executing."""
        findings: list[GuardianFinding] = []
        try:
            with open(path, "rb") as f:
                data = f.read(4096)

            if len(data) < 64:
                return findings

            # e_lfanew is at offset 0x3C
            e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
            if e_lfanew + 4 <= len(data) and data[e_lfanew : e_lfanew + 4] == b"PE\x00\x00":
                static_features["is_valid_pe"] = True
                machine = struct.unpack_from("<H", data, e_lfanew + 4)[0]
                num_sections = struct.unpack_from("<H", data, e_lfanew + 6)[0]
                timestamp = struct.unpack_from("<I", data, e_lfanew + 8)[0]

                static_features["pe_machine_code"] = hex(machine)
                static_features["pe_section_count"] = num_sections
                static_features["pe_compile_timestamp"] = timestamp

                # High header entropy check
                entropy = compute_shannon_entropy(data)
                static_features["pe_entropy"] = entropy
                if entropy > 7.1:
                    findings.append(
                        GuardianFinding(
                            name="High Binary Entropy (Likely Packed or Encrypted)",
                            description=f"Calculated binary entropy is {entropy:.2f}/8.0, indicating the executable is packed, compressed, or encrypted.",
                            severity="high",
                            evidence=f"Entropy score: {entropy:.2f}",
                            recommendation="Packed executables often obscure code logic. Perform in-depth sandbox analysis before execution.",
                        )
                    )
        except Exception as exc:
            logger.debug("PE inspection error: %s", exc)
        return findings

    def _inspect_script_text(self, path: Path, static_features: dict[str, Any]) -> list[GuardianFinding]:
        """Scan text/scripts for common high-risk invocation primitives."""
        findings: list[GuardianFinding] = []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read(128 * 1024)  # First 128KB

            suspicious_patterns = [
                (r"powershell(\.exe)?\s+(-e|-enc|-encodedcommand)", "Encoded PowerShell Execution", "critical"),
                (r"Invoke-Expression|IEX\b", "PowerShell Dynamic Code Execution (Invoke-Expression)", "high"),
                (r"wscript\.shell|cscript\.exe", "Windows Script Host Primitive Invocation", "medium"),
                (r"cmd\.exe\s+/c", "Command Shell Execution Invocation", "medium"),
                (r"certutil(\.exe)?\s+-urlcache", "Certutil Remote Download Primitive", "high"),
                (r"eval\s*\(base64_decode", "Obfuscated PHP / Script Eval Base64", "high"),
            ]

            detected_patterns = []
            for pattern, name, severity in suspicious_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    detected_patterns.append(name)
                    findings.append(
                        GuardianFinding(
                            name=name,
                            description="Script contains command patterns commonly observed in downloaders and droppers.",
                            severity=severity,
                            evidence=f"Pattern: {pattern}",
                            recommendation="Inspect script code thoroughly before running.",
                        )
                    )
            static_features["script_suspicious_patterns"] = detected_patterns
        except Exception as exc:
            logger.debug("Script inspection error: %s", exc)
        return findings
