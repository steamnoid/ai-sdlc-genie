from unittest.mock import AsyncMock, Mock, patch

import pytest

from aisdlc.llm.factory import get_llm


@pytest.mark.asyncio
async def test_llm_connectivity():
    """
    Verify that a model produced by the factory satisfies the asynchronous
    LangChain invocation contract without leaking an event-loop-bound client.
    """
    # Arrange
    prompt = "Hello, are you working?"
    model = Mock(ainvoke=AsyncMock(return_value=Mock(content="Yes.")))

    # Act
    with patch("aisdlc.llm.factory.LLMFactory.create_model", return_value=model):
        llm = get_llm()
        response = await llm.ainvoke([{"role": "user", "content": prompt}])

    assert response.content == "Yes."
    model.ainvoke.assert_awaited_once_with([{"role": "user", "content": prompt}])