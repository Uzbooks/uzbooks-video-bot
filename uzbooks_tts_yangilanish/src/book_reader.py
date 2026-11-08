"""Kitob faylidan toza matn chiqarish (PDF, EPUB, TXT, DOCX, FB2)."""
import re
from pathlib import Path


def read_book(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        import fitz  # pymupdf
        with fitz.open(path) as doc:
            text = "\n".join(page.get_text() for page in doc)
    elif ext == ".epub":
        from ebooklib import epub, ITEM_DOCUMENT
        from bs4 import BeautifulSoup
        book = epub.read_epub(str(path))
        parts = [BeautifulSoup(it.get_content(), "html.parser").get_text("\n")
                 for it in book.get_items_of_type(ITEM_DOCUMENT)]
        text = "\n".join(parts)
    elif ext == ".docx":
        import docx
        text = "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    elif ext == ".fb2":
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(path.read_bytes(), "html.parser")
        text = "\n".join(p.get_text() for p in soup.find_all("p"))
    else:
        raw = path.read_bytes()
        for enc in ("utf-8", "cp1251", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if len(text) < 2000:
        raise ValueError("Kitobdan matn deyarli chiqmadi. Ehtimol bu skanerlangan "
                         "(rasm ko'rinishidagi) PDF. Matnli versiyasini yuboring.")
    return text


def chunks(text: str, size: int = 350_000) -> list[str]:
    """Uzun kitobni bo'laklarga ajratadi (paragraf chegarasida)."""
    out, cur = [], []
    n = 0
    for para in text.split("\n\n"):
        if n + len(para) > size and cur:
            out.append("\n\n".join(cur))
            cur, n = [], 0
        cur.append(para)
        n += len(para) + 2
    if cur:
        out.append("\n\n".join(cur))
    return out
