from run_agent import AIAgent


def _make_agent():
    agent = object.__new__(AIAgent)
    agent._strip_think_blocks = AIAgent._strip_think_blocks.__get__(agent, AIAgent)
    return agent


def test_terminal_post_tool_fallback_accepts_finished_answer():
    agent = _make_agent()
    assert agent._is_terminal_post_tool_fallback(
        "Installed the requested packages successfully."
    )


def test_terminal_post_tool_fallback_rejects_planning_narration():
    agent = _make_agent()
    assert not agent._is_terminal_post_tool_fallback(
        "I'll create a comprehensive todo list and install everything from the 8 categories."
    )


def test_terminal_post_tool_fallback_rejects_follow_up_question():
    agent = _make_agent()
    assert not agent._is_terminal_post_tool_fallback(
        "Would you like me to demonstrate any specific tool, or shall we start working on a multi-agent project using these capabilities?"
    )
