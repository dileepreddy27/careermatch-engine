import hashlib
import re

from .models import Chunk


def chunk_document(text: str, max_chars: int = 700, overlap: int = 100) -> list[Chunk]:
    """Keep section/paragraph boundaries and exact offsets; window only oversized paragraphs."""
    if not 0 <= overlap < max_chars:
        raise ValueError("overlap must be nonnegative and less than max_chars")
    chunks = []
    section = "Experience"
    for match in re.finditer(r"[^\r\n]+", text):
        raw = match.group()
        if raw.lstrip().startswith("#"):
            section = raw.strip().lstrip("# ")
            continue
        left = match.start() + len(raw) - len(raw.lstrip())
        end = match.end() - len(raw) + len(raw.rstrip())
        while left < end:
            right = min(left + max_chars, end)
            if right < end:
                boundary = text.rfind(" ", left + max_chars // 2, right)
                if boundary > left:
                    right = boundary
            value = text[left:right]
            digest = hashlib.sha256(f"{left}:{right}:{value}".encode()).hexdigest()[:16]
            chunks.append(Chunk(id=digest, section=section, text=value, start=left, end=right))
            if right == end:
                break
            left = max(left + 1, right - overlap)
    return chunks
