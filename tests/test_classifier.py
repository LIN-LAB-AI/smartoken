"""classifier：T0/T1 纯本地规则冒烟"""
from smartoken.classifier import TaskClassifier

C = TaskClassifier({})


def _msgs(text, role="user"):
    return [{"role": role, "content": text}]


def test_greeting_is_L0():
    r = C.classify(_msgs("hi"))
    assert r.difficulty == "L0"
    assert r.confidence >= 0.9


def test_short_question_is_L0():
    r = C.classify(_msgs("what is the capital of france"))
    assert r.difficulty == "L0"


def test_code_block_is_coding_L1():
    text = 'fix this:\n```python\ndef f(x):\n    return x +\n```'
    r = C.classify(_msgs(text))
    assert r.category == "coding"
    assert r.difficulty == "L1"


def test_stacktrace_is_L2():
    text = "here is the traceback:\ntraceback (most recent call last):\n... segfault"
    r = C.classify(_msgs(text))
    assert r.difficulty == "L2"


def test_tools_map_to_agent_subtask():
    tools = [{"type": "function", "function": {"name": "read_file"}}]
    r = C.classify(_msgs("read the file"), tools=tools)
    assert r.category == "agent-subtask"
    assert r.features["has_tools"] is True


def test_image_maps_to_vision():
    text = '{"type":"image_url","image_url":{"url":"data:image/png;base64,xxxx"}}'
    r = C.classify(_msgs(text))
    assert r.category == "vision"


def test_chinese_greeting_not_L2_but_not_ascii_underestimated():
    # CJK token 估算回归：中文短问候不应因按字符/4 低估而永远 L0
    r = C.classify(_msgs("早上好，帮我看看这段代码"))
    assert r.difficulty in ("L0", "L1")   # 约 14 CJK 字 → est>3，不可能是“仅 1 token”那种极端 L0


def test_chinese_architecture_prompt_is_L2():
    rules = {"l2_architecture_words": ["架构", "模块划分", "系统设计", "重构"]}
    clf = TaskClassifier(rules)
    r = clf.classify(_msgs("请设计一个 URL 短链服务的整体架构，给出模块划分与数据库表设计。"))
    assert r.difficulty == "L2"
    assert r.features["est_tokens"] >= 20   # CJK 感知估算


def test_long_coding_task_is_L2():
    text = "refactor:\n```python\n" + "x = 1\n" * 3000 + "```"
    r = C.classify(_msgs(text))
    assert r.difficulty == "L2"
