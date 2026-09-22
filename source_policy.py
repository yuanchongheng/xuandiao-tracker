"""Three-tier, exact-host source allowlist; domain is NOT proof of announcement content.

Government first; Jilin University second; reviewed official employment portals
of other universities only as discovery leads unless a human explicitly verifies
scope/attachments for publication. Never trust arbitrary *.edu.cn hosts.
"""
from urllib.parse import urlsplit

JLU_HOSTS = frozenset({'jdjywpt.jlu.edu.cn', 'jdjyw.jlu.edu.cn'})
OTHER_UNIVERSITY_HOSTS = frozenset({
    'jiuye.uestc.edu.cn',    # University of Electronic Science and Technology of China
    'www.job.ustc.edu.cn',  # University of Science and Technology of China
    'job.ustc.edu.cn',
    'job.hust.edu.cn',      # Huazhong University of Science and Technology
    'career.csu.edu.cn',   # Central South University
})


def source_tier(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.port not in (None, 443)):
            return None
        host = parsed.hostname.lower()
    except (ValueError, TypeError, AttributeError):
        return None
    if host == 'gov.cn' or host.endswith('.gov.cn'):
        return 'government'
    if host in JLU_HOSTS:
        return 'jlu_fallback'
    if host in OTHER_UNIVERSITY_HOSTS:
        return 'university_third'
    return None


def source_label(url):
    return {
        'government': '政府官网',
        'jlu_fallback': '吉林大学备用来源',
        'university_third': '其他高校官网·第三来源（待核验）',
    }.get(source_tier(url), '不符合来源政策')
