import hashlib
import re

MIN_CHUNK = 100
MAX_CHUNK = 1500


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def hash_chunk(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def split_md(text: str) -> list[str]:
    parts = re.split(r"(?m)^(#{2,3} .+)", text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        if re.match(r"#{2,3} ", part):
            if buf.strip():
                chunks.append(buf.strip())
            buf = part
        else:
            buf += "\n" + part
    if buf.strip():
        chunks.append(buf.strip())

    # 짧은 섹션 병합
    merged: list[str] = []
    for c in chunks:
        if merged and len(merged[-1]) < MIN_CHUNK:
            merged[-1] += "\n\n" + c
        else:
            merged.append(c)

    # 너무 긴 섹션 분할
    result: list[str] = []
    for c in merged:
        if len(c) <= MAX_CHUNK:
            result.append(c)
        else:
            lines = c.splitlines()
            buf = ""
            for line in lines:
                if len(buf) + len(line) > MAX_CHUNK and buf:
                    result.append(buf.strip())
                    buf = line
                else:
                    buf += "\n" + line
            if buf.strip():
                result.append(buf.strip())

    return [c for c in result if c.strip()]


def split_log(text: str) -> list[str]:
    paragraphs = re.split(r"\n{2,}", text.strip())
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) > MAX_CHUNK and buf:
            chunks.append(buf.strip())
            buf = para
        else:
            buf = (buf + "\n\n" + para).strip()
    if buf:
        chunks.append(buf.strip())

    # 너무 짧은 조각 병합
    merged: list[str] = []
    for c in chunks:
        if merged and len(c) < MIN_CHUNK:
            merged[-1] += "\n\n" + c
        else:
            merged.append(c)

    return [c for c in merged if len(c) >= 20]


if __name__ == "__main__":
    sample_md = """# Title
## Section A
Content A line 1
Content A line 2

## Section B
Content B

### Sub-section B1
Sub content here with more text to make it longer than minimum chunk size threshold
"""
    chunks = split_md(sample_md)
    print(f"md chunks: {len(chunks)}")
    for i, c in enumerate(chunks):
        print(f"  [{i}] {len(c)}자: {c[:60]!r}")

    sample_log = """query result 1
row1 col1 col2

query result 2
row2 col1 col2

short
"""
    log_chunks = split_log(sample_log)
    print(f"log chunks: {len(log_chunks)}")
    for i, c in enumerate(log_chunks):
        print(f"  [{i}] {len(c)}자: {c[:60]!r}")
