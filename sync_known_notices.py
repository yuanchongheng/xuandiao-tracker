#!/usr/bin/env python3
"""Normalize province labels and keep a few same-day confirmed notices in sync.

Two jobs:
1) Province detection from a national JLU listing must prefer the administrative
   region at the beginning of the title, not a university name appearing later
   (e.g. "重庆市面向吉林大学..." must be 重庆, never 吉林).
2) Keep the newly published 2027 Chongqing notice and its monitor metadata fully
   structured even when GitHub Actions temporarily cannot fetch the JLU page.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))
OFFICIAL_CQ = "https://www.12371.gov.cn/web/article/1557705647757918208/web/content_1557705647757918208.html"
JLU_CQ = "https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=8cec6f02aeb2456686a4865bc6c691dd"
CQ_TITLE_KEY = "重庆市面向吉林大学定向选调"

ALIASES = [
    ("内蒙古", ("内蒙古自治区", "内蒙古")),
    ("黑龙江", ("黑龙江省", "黑龙江")),
    ("北京", ("北京市", "北京")), ("天津", ("天津市", "天津")),
    ("河北", ("河北省", "河北")), ("山西", ("山西省", "山西")),
    ("辽宁", ("辽宁省", "辽宁")), ("吉林", ("吉林省", "吉林")),
    ("上海", ("上海市", "上海")), ("江苏", ("江苏省", "江苏")),
    ("浙江", ("浙江省", "浙江")), ("安徽", ("安徽省", "安徽")),
    ("福建", ("福建省", "福建")), ("江西", ("江西省", "江西")),
    ("山东", ("山东省", "山东")), ("河南", ("河南省", "河南")),
    ("湖北", ("湖北省", "湖北")), ("湖南", ("湖南省", "湖南")),
    ("广东", ("广东省", "广东")), ("广西", ("广西壮族自治区", "广西")),
    ("海南", ("海南省", "海南")), ("重庆", ("重庆市", "重庆")),
    ("四川", ("四川省", "四川")), ("贵州", ("贵州省", "贵州")),
    ("云南", ("云南省", "云南")), ("西藏", ("西藏自治区", "西藏")),
    ("陕西", ("陕西省", "陕西")), ("甘肃", ("甘肃省", "甘肃")),
    ("青海", ("青海省", "青海")), ("宁夏", ("宁夏回族自治区", "宁夏")),
    ("新疆", ("新疆维吾尔自治区", "新疆")),
]


def load(name: str, default):
    p = ROOT / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(name: str, obj) -> None:
    (ROOT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def title_province(title: str) -> str | None:
    text = re.sub(r"^[\s\u200b\ufeff\[\]【】置顶]+", "", str(title or ""))
    for province, aliases in ALIASES:
        for alias in aliases:
            if text.startswith(alias):
                return province
    return None


def normalize_provinces(obj) -> int:
    changed = 0
    for item in obj:
        detected = title_province(item.get("title", ""))
        if detected and item.get("province") != detected:
            item["province"] = detected
            changed += 1
    return changed


def ensure_chongqing_record(data: dict) -> int:
    records = data.setdefault("records", [])
    record = next((r for r in records if CQ_TITLE_KEY in r.get("title", "") or r.get("source") == JLU_CQ), None)
    if record is None:
        record = {
            "province": "重庆",
            "title": "重庆市面向吉林大学定向选调2027届急需紧缺专业应届优秀大学毕业生公告",
            "type": "定向选调",
            "source": JLU_CQ,
            "sourceName": "吉林大学就业网（自动发布）",
            "sourceType": "吉林大学备用",
            "sourceTier": "jlu_fallback",
            "verified": "2026-10-08",
            "published": "2026-10-08",
            "autoPublished": True,
            "discoveredAt": "2026-10-08T15:47:58+08:00",
        }
        records.append(record)

    desired = {
        "province": "重庆",
        "type": "定向选调",
        "count": "610名（其中艰苦边远地区专项约60名）",
        "published": "2026-10-08",
        "start": "2026-10-19T10:00:00+08:00",
        "end": "2026-10-23T17:00:00+08:00",
        "exam": "2026-11-07T00:00:00+08:00",
        "examEnd": "",
        "examText": "11月7日；《行政职业能力测验》《申论》，具体时段以准考证及后续公告为准",
        "school": "吉林大学已发布面向本校的2027届定向选调通知；具体校内报考范围、推荐和盖章流程以吉林大学专属简章为准。",
        "eligibility": "面向有关高校硕士及以上应届优秀毕业生。急需紧缺专业中，经济金融、现代管理类明确包含理论经济学（0201）、应用经济学（0202）、金融、统计等；另须符合2026年10月前加入中国共产党（含预备党员）、优秀学生干部、校级及以上奖励、参军入伍经历之一等条件；硕士研究生一般不超过30周岁。公告规定的高层次荣誉等情形及艰苦边远地区专项可按规则不限专业。",
        "notes": "网上报名10月19日10:00—10月23日17:00；未通过初审且因信息错误需修改的，可在10月25日17:00前重新提交；缴费截至10月26日17:00；准考证11月3日10:00—11月7日9:30打印；笔试初定11月7日，面试初定12月5日。",
        "source": JLU_CQ,
        "sourceName": "吉林大学就业网（自动发布）",
        "sourceType": "吉林大学备用",
        "sourceTier": "jlu_fallback",
        "verified": "2026-10-08",
        "autoPublished": True,
    }
    changed = 0
    for k, v in desired.items():
        if record.get(k) != v:
            record[k] = v
            changed += 1
    record.pop("publishedEstimated", None)
    record.pop("startDateOnly", None)
    if changed:
        data["asOf"] = datetime.now(TZ).isoformat(timespec="seconds")
    return changed


def ensure_sources(sources: dict) -> int:
    changed = 0
    discovery = sources.setdefault("discovery", {})
    new_query = "{province} 2027 (定向选调 OR 选调生) (公告 OR 简章) (site:gov.cn OR site:jdjywpt.jlu.edu.cn OR site:jdjyw.jlu.edu.cn)"
    if discovery.get("query_template") != new_query:
        discovery["query_template"] = new_query
        changed += 1

    monitors = sources.setdefault("monitors", [])
    if not any(m.get("url") == OFFICIAL_CQ for m in monitors):
        monitors.append({
            "province": "重庆",
            "kind": "article",
            "name": "七一网：重庆市2027定向选调简章",
            "url": OFFICIAL_CQ,
        })
        changed += 1
    return changed


def main() -> None:
    data = load("data.json", {"records": []})
    queue = load("review_queue.json", {"candidates": []})
    sources = load("sources.json", {})

    n_data = normalize_provinces(data.get("records", []))
    n_queue = normalize_provinces(queue.get("candidates", []))
    n_cq = ensure_chongqing_record(data)
    n_sources = ensure_sources(sources)

    if n_queue:
        queue["updated"] = datetime.now(TZ).isoformat(timespec="seconds")
    save("data.json", data)
    save("review_queue.json", queue)
    save("sources.json", sources)
    print(f"known-notice sync: normalized_data={n_data}, normalized_queue={n_queue}, chongqing_fields={n_cq}, source_changes={n_sources}")


if __name__ == "__main__":
    main()
