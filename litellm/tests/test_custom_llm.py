# What is this?
## Unit tests for the CustomLLM class


import asyncio
import os
import sys
import time
import traceback

import openai
import pytest

sys.path.insert(
    0, os.path.abspath("../..")
)  # Adds the parent directory to the system path
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncIterator, Iterator, Union
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from dotenv import load_dotenv

import litellm
from litellm import (
    ChatCompletionDeltaChunk,
    ChatCompletionUsageBlock,
    CustomLLM,
    GenericStreamingChunk,
    ModelResponse,
    acompletion,
    completion,
    get_llm_provider,
)
from litellm.utils import ModelResponseIterator


class CustomModelResponseIterator:
    def __init__(self, streaming_response: Union[Iterator, AsyncIterator]):
        self.streaming_response = streaming_response

    def chunk_parser(self, chunk: Any) -> GenericStreamingChunk:
        return GenericStreamingChunk(
            text="hello world",
            tool_use=None,
            is_finished=True,
            finish_reason="stop",
            usage=ChatCompletionUsageBlock(
                prompt_tokens=10, completion_tokens=20, total_tokens=30
            ),
            index=0,
        )

    # Sync iterator
    def __iter__(self):
        return self

    def __next__(self) -> GenericStreamingChunk:
        try:
            chunk: Any = self.streaming_response.__next__()  # type: ignore
        except StopIteration:
            raise StopIteration
        except ValueError as e:
            raise RuntimeError(f"Error receiving chunk from stream: {e}")

        try:
            return self.chunk_parser(chunk=chunk)
        except StopIteration:
            raise StopIteration
        except ValueError as e:
            raise RuntimeError(f"Error parsing chunk: {e},\nReceived chunk: {chunk}")

    # Async iterator
    def __aiter__(self):
        self.async_response_iterator = self.streaming_response.__aiter__()  # type: ignore
        return self

    async def __anext__(self) -> GenericStreamingChunk:
        try:
            chunk = await self.async_response_iterator.__anext__()
        except StopAsyncIteration:
            raise StopAsyncIteration
        except ValueError as e:
            raise RuntimeError(f"Error receiving chunk from stream: {e}")

        try:
            return self.chunk_parser(chunk=chunk)
        except StopIteration:
            raise StopIteration
        except ValueError as e:
            raise RuntimeError(f"Error parsing chunk: {e},\nReceived chunk: {chunk}")


class MyCustomLLM(CustomLLM):
    def completion(self, *args, **kwargs) -> litellm.ModelResponse:
        return litellm.completion(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello world"}],
            mock_response="Hi!",
        )  # type: ignore

    async def acompletion(self, *args, **kwargs) -> litellm.ModelResponse:
        return litellm.completion(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello world"}],
            mock_response="Hi!",
        )  # type: ignore

    def streaming(self, *args, **kwargs) -> Iterator[GenericStreamingChunk]:
        generic_streaming_chunk: GenericStreamingChunk = {
            "finish_reason": "stop",
            "index": 0,
            "is_finished": True,
            "text": "Hello world",
            "tool_use": None,
            "usage": {"completion_tokens": 10, "prompt_tokens": 20, "total_tokens": 30},
        }

        completion_stream = ModelResponseIterator(
            model_response=generic_streaming_chunk  # type: ignore
        )
        custom_iterator = CustomModelResponseIterator(
            streaming_response=completion_stream
        )
        return custom_iterator


def test_get_llm_provider():
    """"""
    from litellm.utils import custom_llm_setup

    my_custom_llm = MyCustomLLM()
    litellm.custom_provider_map = [
        {"provider": "custom_llm", "custom_handler": my_custom_llm}
    ]

    custom_llm_setup()

    model, provider, _, _ = get_llm_provider(model="custom_llm/my-fake-model")

    assert provider == "custom_llm"


def test_simple_completion():
    my_custom_llm = MyCustomLLM()
    litellm.custom_provider_map = [
        {"provider": "custom_llm", "custom_handler": my_custom_llm}
    ]
    resp = completion(
        model="custom_llm/my-fake-model",
        messages=[{"role": "user", "content": "Hello world!"}],
    )

    assert resp.choices[0].message.content == "Hi!"


@pytest.mark.asyncio
async def test_simple_acompletion():
    my_custom_llm = MyCustomLLM()
    litellm.custom_provider_map = [
        {"provider": "custom_llm", "custom_handler": my_custom_llm}
    ]
    resp = await acompletion(
        model="custom_llm/my-fake-model",
        messages=[{"role": "user", "content": "Hello world!"}],
    )

    assert resp.choices[0].message.content == "Hi!"


def test_simple_completion_streaming():
    my_custom_llm = MyCustomLLM()
    litellm.custom_provider_map = [
        {"provider": "custom_llm", "custom_handler": my_custom_llm}
    ]
    resp = completion(
        model="custom_llm/my-fake-model",
        messages=[{"role": "user", "content": "Hello world!"}],
        stream=True,
    )

    for chunk in resp:
        print(chunk)
        if chunk.choices[0].finish_reason is None:
            assert isinstance(chunk.choices[0].delta.content, str)
        else:
            assert chunk.choices[0].finish_reason == "stop"