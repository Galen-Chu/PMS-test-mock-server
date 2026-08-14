# extract_sa.py — 把 SA docx 萃取成保留表格結構的純文字(供比對 SA 規格用)
import sys
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def para_text(p):
    return "".join(t.text or "" for t in p.iter(f"{W}t"))


def walk(body, out):
    for child in body:
        if child.tag == f"{W}p":
            txt = para_text(child).strip()
            if txt:
                out.append(txt)
        elif child.tag == f"{W}tbl":
            out.append("┌─TABLE─┐")
            for tr in child.findall(f"{W}tr"):
                cells = []
                for tc in tr.findall(f"{W}tc"):
                    cells.append(" ".join(
                        para_text(p).strip() for p in tc.iter(f"{W}p") if para_text(p).strip()))
                out.append(" │ " + " │ ".join(cells))
            out.append("└───────┘")


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    with zipfile.ZipFile(src) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    out = []
    walk(root.find(f"{W}body"), out)
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"{dst}: {len(out)} lines")
