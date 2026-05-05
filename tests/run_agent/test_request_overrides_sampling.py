from agent.transports.chat_completions import ChatCompletionsTransport


def test_request_overrides_merge_extra_body_sampler_fields():
    transport = ChatCompletionsTransport()
    kwargs = transport.build_kwargs(
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        request_overrides={
            "temperature": 0.2,
            "extra_body": {"top_k": 40, "min_p": 0.05},
        },
        is_openrouter=True,
        provider_preferences={"sort": "throughput"},
        supports_reasoning=True,
        reasoning_config={"effort": "medium"},
    )

    assert kwargs["temperature"] == 0.2
    assert kwargs["extra_body"]["provider"]["sort"] == "throughput"
    assert kwargs["extra_body"]["reasoning"]["effort"] == "medium"
    assert kwargs["extra_body"]["top_k"] == 40
    assert kwargs["extra_body"]["min_p"] == 0.05
