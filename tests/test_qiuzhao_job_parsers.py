import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QIUZHAO = ROOT / "qiuzhao"
sys.path.insert(0, str(QIUZHAO))

from job_parsers import parse_source, score_candidate


def test_zhiye_extracts_job_codes():
    source = {"id": "itg", "name": "厦门国贸校园招聘", "parser": "zhiye"}
    html = '''
    <html><body>
      <a href="/job/13647">贸易运营岗（J13647）</a>
      <a href="/job/13649">行业研究岗（J13649）</a>
    </body></html>
    '''
    rows = parse_source(source, html, "https://itgholding.zhiye.com/gmkgxzlb")
    assert {r["jobCode"] for r in rows} == {"J13647", "J13649"}
    assert all(r["url"].startswith("https://itgholding.zhiye.com/") for r in rows)


def test_51job_category_parser_keeps_relevant_categories_only():
    source = {"id": "cofco", "name": "中粮集团校园招聘", "parser": "51job_categories"}
    html = '''<html><body>
      <div>投资研究类</div><div>大宗贸易类</div><div>战略规划类</div>
      <div>运营管理类</div><div>技术研发类</div><div>校园招聘</div>
    </body></html>'''
    rows = parse_source(source, html, "https://campus.51job.com/cofco")
    titles = {r["title"] for r in rows}
    assert {"投资研究类", "大宗贸易类", "战略规划类", "运营管理类"}.issubset(titles)
    assert "技术研发类" not in titles


def test_hard_school_requirement_is_blocked():
    scored = score_candidate("总部产业研究岗，本科毕业院校须为985/211/双一流，硕士学历")
    assert scored["eligibility"] == "blocked"
    assert scored["score"] == 0


def test_vague_preference_is_not_blocked():
    scored = score_candidate("行业研究岗，经济学相关专业，重点高校优先，硕士学历")
    assert scored["eligibility"] != "blocked"
    assert scored["score"] >= 72


def test_trade_operations_scores_high_for_profile():
    scored = score_candidate("贸易运营岗，负责国际贸易、供应链经营分析，硕士，2027届")
    assert scored["eligibility"] == "likely"
    assert scored["score"] >= 80
