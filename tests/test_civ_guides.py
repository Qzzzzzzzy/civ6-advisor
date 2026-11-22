"""文明攻略 md：每个文件结构完整，资料库能加载，局势上下文里带上本文明攻略。"""

from civ6_advisor.civs import CIVS
from civ6_advisor.kb import KnowledgeBase, load_civ_markdown

REQUIRED = ("速览", "特色怎么用", "局势 → 建议")


def test_every_civ_has_markdown():
    md = load_civ_markdown()
    missing = sorted(set(CIVS) - set(md))
    assert not missing, f"缺攻略：{missing}"


def test_markdown_structure():
    for t, doc in load_civ_markdown().items():
        assert t in doc.title, t
        for s in REQUIRED:
            assert doc.section(s), f"{t} 缺「{s}」"
        assert doc.aliases and doc.aliases[0]


def test_kb_uses_markdown_and_excerpt_budget():
    kb = KnowledgeBase()
    e = kb.get("GUIDE_CIVILIZATION_ETHIOPIA")
    assert e and "关键时机" in e.desc
    assert "简要档案" in kb.render(e)
    ex = kb.civ_excerpt("CIVILIZATION_ETHIOPIA", "前期", budget=1200)
    assert ex.startswith("【文明攻略】") and len(ex) <= 1300
    assert "### 速览" in ex


def test_search_by_leader_name():
    kb = KnowledgeBase()
    assert kb.search("哈拉尔")[0].type == "GUIDE_CIVILIZATION_NORWAY"
    assert kb.search("狄多")[0].type == "GUIDE_CIVILIZATION_PHOENICIA"


def test_context_includes_civ_guide():
    from civ6_advisor.mock import mock_situation

    sit = mock_situation()
    ctx = KnowledgeBase().context_for(sit)
    assert "【文明攻略】" in ctx and "CIVILIZATION_CHINA" in ctx
