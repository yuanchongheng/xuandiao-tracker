#!/usr/bin/env python3
"""One-time manual refresh for newly published 2027 selection notices on 2026-10-09."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))

ZHEJIANG = {
    "province": "浙江",
    "title": "2027年度浙江省党政机关选调应届优秀大学毕业生公告",
    "type": "常规选调 + 定向紧缺专业选调",
    "count": "850名（常规664名；定向紧缺专业186名）",
    "published": "2026-10-09",
    "start": "2026-10-10T09:00:00+08:00",
    "end": "2026-10-16T17:00:00+08:00",
    "exam": "2026-11-14T09:00:00+08:00",
    "examEnd": "2026-11-14T12:00:00+08:00",
    "examText": "11月14日 09:00—12:00；《综合能力测试》1科，180分钟，满分150分",
    "school": "常规选调面向59所院校；定向紧缺专业选调按39类紧缺专业及其对应院校、职位表执行。吉林大学是否适用于具体职位及专业，以2027年度附件1、附件6、附件7和学校推荐要求为准。",
    "eligibility": "面向2027年全日制应届毕业生；须符合公告规定的年龄、政治素质及党员/学生干部/校级综合荣誉或奖学金等资格条件之一（山区海岛县部分定向紧缺专业职位按公告规定执行），并满足职位专业等要求。具体以公告及附件为准。",
    "notes": "2026年10月10日9:00至10月16日17:00网上报名；10月11日9:00至10月17日12:00资格初审；11月3日9:00起打印准考证；11月14日9:00笔试。公告计划共850名，其中常规664名、定向紧缺专业186名。当前吉林大学就业网尚未同步2027浙江公告，本条依据山东大学就业中心官网当日发布线索并人工交叉核验公告正文；待吉大或浙江官方可稳定访问页面出现后优先替换来源。",
    "source": "https://www.job.sdu.edu.cn/xdgk.htm",
    "sourceName": "山东大学学生就业创业指导中心（人工核验补充）",
    "sourceType": "其他高校补充",
    "verified": "2026-10-09",
    "sourceTier": "university_third",
    "reviewedSource": True,
    "reviewedScope": True
}

SHANDONG = {
    "province": "山东",
    "title": "山东省2027年度选拔录用选调生公告",
    "type": "分两批选调（定向 + 常规）",
    "count": "1562名（两批合计）",
    "published": "2026-10-08",
    "start": "2026-10-09T09:00:00+08:00",
    "end": "2026-10-15T16:00:00+08:00",
    "exam": "2026-10-25T09:00:00+08:00",
    "examEnd": "2026-10-25T11:30:00+08:00",
    "examText": "第一批：10月25日 09:00—11:30；笔试内容包括公共基础知识、写作等",
    "school": "第一批仅面向公告列明的21所高校，吉林大学不在第一批名单；第二批面向部分高校及相关专业实施定向选调，并面向全国普通高校实施常规选调，具体院校、专业和职位以第二批附件及后续通知为准。",
    "eligibility": "面向2027年全日制大学本科及以上学历应届优秀毕业生；具体政治条件、年龄、学习成绩、学生干部/党员等要求及职位资格以公告和报考手册为准。",
    "notes": "本条报名及笔试时间对应第一批：10月9日9:00至10月15日16:00报名，10月25日9:00至11:30笔试。第二批职位计划和报名时间另行通知，不能把第一批时间直接套用于第二批。吉林大学不在第一批21校名单，后续重点关注第二批定向范围和常规选调职位。",
    "source": "https://www.dtdjzx.gov.cn/web/dtdjzx/dtrdtzgg/129481.html",
    "sourceName": "灯塔—党建在线 / 中共山东省委组织部官方公告",
    "sourceType": "官方",
    "verified": "2026-10-09",
    "sourceTier": "government"
}


def is_same_notice(record: dict, incoming: dict) -> bool:
    if record.get("province") != incoming["province"]:
        return False
    title = str(record.get("title", ""))
    if incoming["province"] == "浙江":
        return "2027" in title and "浙江" in title and "选调" in title
    if incoming["province"] == "山东":
        return "2027" in title and "山东" in title and "选调" in title
    return False


def main() -> None:
    path = ROOT / "data.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.setdefault("records", [])
    for incoming in (ZHEJIANG, SHANDONG):
        matches = [i for i, record in enumerate(records) if is_same_notice(record, incoming)]
        if matches:
            records[matches[0]] = incoming
            for index in reversed(matches[1:]):
                records.pop(index)
        else:
            records.append(incoming)
    data["asOf"] = datetime.now(TZ).isoformat(timespec="seconds")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("manual refresh: Zhejiang and Shandong 2027 notices upserted")


if __name__ == "__main__":
    main()
