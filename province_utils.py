#!/usr/bin/env python3
"""Shared province and notice-title normalization helpers."""
from __future__ import annotations
import re

PROVINCES = ('北京', '天津', '河北', '山西', '内蒙古', '辽宁', '吉林', '黑龙江', '上海', '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南', '湖北', '湖南', '广东', '广西', '海南', '重庆', '四川', '贵州', '云南', '西藏', '陕西', '甘肃', '青海', '宁夏', '新疆')
ADMIN_FORMS = {
    '北京': ('北京市',), '天津': ('天津市',), '河北': ('河北省',), '山西': ('山西省',),
    '内蒙古': ('内蒙古自治区',), '辽宁': ('辽宁省',), '吉林': ('吉林省',), '黑龙江': ('黑龙江省',),
    '上海': ('上海市',), '江苏': ('江苏省',), '浙江': ('浙江省',), '安徽': ('安徽省',),
    '福建': ('福建省',), '江西': ('江西省',), '山东': ('山东省',), '河南': ('河南省',),
    '湖北': ('湖北省',), '湖南': ('湖南省',), '广东': ('广东省',), '广西': ('广西壮族自治区',),
    '海南': ('海南省',), '重庆': ('重庆市',), '四川': ('四川省',), '贵州': ('贵州省',),
    '云南': ('云南省',), '西藏': ('西藏自治区',), '陕西': ('陕西省',), '甘肃': ('甘肃省',),
    '青海': ('青海省',), '宁夏': ('宁夏回族自治区',), '新疆': ('新疆维吾尔自治区',),
}


def _clean(value: str) -> str:
    text = re.sub(r'[\u200b\ufeff]', '', str(value or '')).strip()
    text = re.sub(r'^[\s\[\]【】（）()「」『』《》〈〉·•—–_-]*', '', text)
    text = re.sub(r'^(?:置顶|招聘信息|通知公告)[：:\s-]*', '', text)
    return text.strip()


def province_from_title(value: str):
    """Infer the target jurisdiction without mistaking a university name for it.

    Strong signals only: title prefix, a province immediately following the year,
    or a full administrative name such as 重庆市/四川省. This intentionally avoids
    matching bare 吉林 inside 吉林大学 when the actual target is 重庆.
    """
    text = _clean(value)
    if not text:
        return None
    for province in sorted(PROVINCES, key=len, reverse=True):
        forms = ADMIN_FORMS.get(province, ())
        if text.startswith((province,) + forms):
            return province
    year_match = re.search(r'20\d{2}(?:年|届|年度)?[^省市区]{0,8}(' + '|'.join(map(re.escape, sorted(PROVINCES, key=len, reverse=True))) + r')', text)
    if year_match:
        return year_match.group(1)
    hits = []
    for province, forms in ADMIN_FORMS.items():
        for form in forms:
            pos = text.find(form)
            if pos >= 0:
                hits.append((pos, -len(form), province))
    if hits:
        hits.sort()
        return hits[0][2]
    return None


def normalized_notice_title(value: str) -> str:
    text = _clean(value)
    text = re.sub(r'[\s·•—–_()（）\[\]【】《》“”‘’：:，,。.!！?？/\\-]+', '', text)
    text = re.sub(r'(?:公告|简章|通知)$', '', text)
    return text
