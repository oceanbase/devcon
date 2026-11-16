"""GLM 标准 API 配置；由用户显式选择型号，不自动切换。"""

import asyncio
from contextlib import contextmanager
import os
from pathlib import Path
import time

from dotenv import load_dotenv
import httpx2
import openai
from langchain_openai import ChatOpenAI


ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "glm-5.3-flash"
MODEL_CHOICES = ("glm-4.7-flash", "glm-4.7-flashx", "glm-5.3-flash")
BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"


class ChatGLM(ChatOpenAI):
    """保留智谱工具调用下一轮所需的 reasoning_content 扩展字段。"""

    def _create_chat_result(self, response, generation_info=None):
        result = super()._create_chat_result(response, generation_info)
        payload = response if isinstance(response, dict) else response.model_dump()
        for generation, choice in zip(result.generations, payload.get("choices", [])):
            reasoning = choice.get("message", {}).get("reasoning_content")
            if reasoning is not None:
                generation.message.additional_kwargs["reasoning_content"] = reasoning
        return result

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(messages, stop=stop, **kwargs)
        for message, encoded in zip(messages, payload["messages"]):
            reasoning = message.additional_kwargs.get("reasoning_content")
            if reasoning is not None:
                encoded["reasoning_content"] = reasoning
        return payload


def load_api_key():
    load_dotenv(ROOT / ".env", override=False)
    key = os.environ.get("ZHIPU_API_KEY", "").strip()
    if not key:
        raise ValueError("请将智谱标准 API Key 配置为 ZHIPU_API_KEY 环境变量，或写入项目 .env 文件。")
    return key


def close_async_client(client):
    """兼容脚本和已有事件循环的 Notebook；同步调用不嵌套 asyncio.run。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(client.aclose())
    else:
        loop.create_task(client.aclose())


@contextmanager
def open_glm_model(model_name=MODEL_NAME):
    if model_name not in MODEL_CHOICES:
        raise ValueError("当前试用脚本只支持明确列出的 GLM Flash 型号。")
    key = load_api_key()
    use_proxy = os.environ.get("ZHIPU_USE_PROXY", "0") == "1"
    # 锁定的 OpenAI 3.x SDK 使用 httpx2；为同步和异步客户端显式设置网络配置。
    async_http = httpx2.AsyncClient(trust_env=use_proxy, timeout=40.0)
    try:
        with httpx2.Client(trust_env=use_proxy, timeout=40.0) as sync_http:
            paid_flash = model_name == "glm-5.3-flash"
            model = ChatGLM(
                model=model_name,
                api_key=key,
                base_url=BASE_URL,
                use_responses_api=False,
                temperature=1.0 if paid_flash else 0.2,
                max_retries=0,
                timeout=40.0,
                http_client=sync_http,
                http_async_client=async_http,
                http_socket_options=(),
                stream_usage=False,
                # GLM 使用 max_tokens；放入 extra_body 避免转换成 OpenAI 专属参数名。
                extra_body={"thinking": {"type": "enabled" if paid_flash else "disabled"}, "max_tokens": 1024},
                **({"reasoning_effort": "low"} if paid_flash else {}),
            )
            yield model
    finally:
        close_async_client(async_http)


def describe_api_error(error):
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        info = body.get("error", body)
    else:
        info = {"message": str(body or type(error).__name__)}
    message = str(info.get("message", "请求未成功"))
    key = os.environ.get("ZHIPU_API_KEY", "")
    if key:
        message = message.replace(key, "[REDACTED]")
    return {
        "http_status": getattr(error, "status_code", None),
        "code": str(info.get("code", "")),
        "message": message[:500],
    }


def invoke_stage(runnable, messages, trace, label, attempts=1):
    """记录每次实际模型请求的耗时与 Token，不保存推理原文或凭证。"""
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            result = runnable.invoke(messages)
            raw = result.get("raw") if isinstance(result, dict) else result
            trace.append({
                "stage": label, "attempt": attempt, "status": "success",
                "seconds": round(time.perf_counter() - started, 3),
                "usage": getattr(raw, "usage_metadata", None),
            })
            return result
        except (openai.APIStatusError, openai.APIConnectionError) as error:
            info = describe_api_error(error)
            trace.append({"stage": label, "attempt": attempt, "status": "api_error",
                          "seconds": round(time.perf_counter() - started, 3), **info})
            retryable = info["http_status"] == 429 or (info["http_status"] or 0) >= 500 or isinstance(error, openai.APIConnectionError)
            if not retryable or attempt == attempts:
                raise
            time.sleep(5)
        except RuntimeError as error:
            trace.append({"stage": label, "attempt": attempt, "status": "model_error",
                          "seconds": round(time.perf_counter() - started, 3), "message": str(error)[:500]})
            raise
