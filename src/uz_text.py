"""O'zbekcha matnni ovozga tayyorlash (faqat ovozga ketadigan matn; subtitr asl matnda qoladi).

- apostroflar: ʻ ‘ ’ ` ʼ  ->  '   (oʻ, gʻ, ma'no ...)
- sonlar so'z bilan: 25 -> yigirma besh, 1937-yil -> bir ming to'qqiz yuz o'ttiz yettinchi yil,
  25% -> yigirma besh foiz, 2,5 -> ikki butun besh, 10:30 -> o'n o'ttiz
- ba'zi qisqartmalar: mln, mlrd, h.k.
"""
import re

APOS = str.maketrans({"ʻ": "'", "ʼ": "'", "‘": "'", "’": "'", "`": "'", "´": "'"})

ONES = ["nol", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz"]
TENS = ["", "o'n", "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson"]
SCALES = [(10 ** 12, "trillion"), (10 ** 9, "milliard"), (10 ** 6, "million"), (1000, "ming")]


def apostrophes(text: str) -> str:
    return text.translate(APOS)


def _under_1000(n: int) -> list[str]:
    out = []
    h, r = divmod(n, 100)
    if h:
        out += (["yuz"] if h == 1 else [ONES[h], "yuz"])
    t, o = divmod(r, 10)
    if t:
        out.append(TENS[t])
    if o:
        out.append(ONES[o])
    return out


def cardinal(n: int) -> str:
    if n == 0:
        return "nol"
    if n < 0:
        return "minus " + cardinal(-n)
    words = []
    for value, name in SCALES:
        q, n = divmod(n, value)
        if q:
            words += _under_1000(q) + [name]
    words += _under_1000(n)
    return " ".join(words)


def ordinal(n: int) -> str:
    words = cardinal(n).split()
    last = words[-1]
    if last == "ellik":
        last = "elligi"                      # ellik -> elliginchi
    elif last == "nol":
        last = "nol"
    words[-1] = last + ("nchi" if last[-1] in "aeiou" else "inchi")
    return " ".join(words)


def _int(s: str) -> int:
    return int(re.sub(r"[\s ,]", "", s))


GROUPED = r"\d{1,3}(?:[  ]\d{3})+"          # 1 000 000
NUM = rf"(?:{GROUPED}|\d+)"


def numbers(text: str) -> str:
    # 10:30 (vaqt)
    text = re.sub(r"\b(\d{1,2}):(\d{2})\b",
                  lambda m: f"{cardinal(int(m[1]))} {cardinal(int(m[2])) if int(m[2]) else 'nol nol'}", text)
    # 2,5 yoki 2.5 (o'nli kasr)
    text = re.sub(r"\b(\d+)[.,](\d+)\b(?![.,]\d)",
                  lambda m: f"{cardinal(int(m[1]))} butun {cardinal(int(m[2]))}", text)
    # 25% -> yigirma besh foiz
    text = re.sub(rf"({NUM})\s?%", lambda m: f"{cardinal(_int(m[1]))} foiz", text)
    # 1937-yil, 2-bob, 5-son -> tartib son
    text = re.sub(rf"\b({NUM})\s?[-–]\s?([^\W\d_])",
                  lambda m: f"{ordinal(_int(m[1]))} {m[2]}", text)
    # oddiy son
    text = re.sub(rf"\b{NUM}\b", lambda m: cardinal(_int(m[0])), text)
    return text


ABBR = [(r"\bmln\.?(?=\s|$)", "million"), (r"\bmlrd\.?(?=\s|$)", "milliard"),
        (r"\bh\.k\.", "hokazo"), (r"\bva b\.", "va boshqalar"), (r"№\s?", "raqam "),
        (r"\$", " dollar"), (r"€", " yevro")]


def abbreviations(text: str) -> str:
    for pat, rep in ABBR:
        text = re.sub(pat, rep, text)
    return re.sub(r"[ \t]{2,}", " ", text)


def for_speech(text: str, full: bool = True) -> str:
    """full=False — faqat apostroflar (uzunlik o'zgarmaydi). full=True — sonlar va qisqartmalar ham."""
    text = apostrophes(text)
    if full:
        text = numbers(abbreviations(text))
    return text.strip()
