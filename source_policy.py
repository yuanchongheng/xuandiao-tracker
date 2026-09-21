"""Source admission rules for published records and search candidates.

Government pages are first choice. The only permitted university fallback is
Jilin University's career portal. Domain eligibility does NOT verify content:
every new date/qualification still requires manual review.
"""
from urllib.parse import urlsplit

JLU_HOSTS = frozenset({'jdjywpt.jlu.edu.cn', 'jdjyw.jlu.edu.cn'})


def source_tier(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        return None
    host = parsed.hostname.lower()
    if host == 'gov.cn' or host.endswith('.gov.cn'):
        return 'government'
    if host in JLU_HOSTS:
        return 'jlu_fallback'
    return None


def source_label(url):
    return {'government': '政府官网', 'jlu_fallback': '吉林大学备用来源'}.get(source_tier(url), '不符合来源政策')
