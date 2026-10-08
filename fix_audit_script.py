#!/usr/bin/env python3
"""Repair quoting in the one-time audit migration before executing it."""
from pathlib import Path

path = Path(__file__).resolve().parent / "audit_migrate.py"
text = path.read_text(encoding="utf-8")
repls = {
    "        rss = '''<rss><channel><item><title>吉林大学就业信息更新</title><description>重庆2027定向选调公告</description><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>'''\n":
    "        rss = \"\"\"<rss><channel><item><title>吉林大学就业信息更新</title><description>重庆2027定向选调公告</description><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>\"\"\"\n",
    "        rss = '''<rss><channel><item><title>重庆2027定向选调公告</title><link>https://www.cq.gov.cn/a</link></item><item><title>重庆2027面向吉林大学定向选调公告</title><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>'''\n":
    "        rss = \"\"\"<rss><channel><item><title>重庆2027定向选调公告</title><link>https://www.cq.gov.cn/a</link></item><item><title>重庆2027面向吉林大学定向选调公告</title><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>\"\"\"\n",
}
changed = False
for old, new in repls.items():
    if old in text:
        text = text.replace(old, new)
        changed = True
path.write_text(text, encoding="utf-8")
print(f"audit migration quote repair: changed={changed}")
