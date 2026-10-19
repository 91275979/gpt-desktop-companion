"""准备好的 Responses API 接入点；不由 UI 定时器调用。"""

import asyncio
import os
from decimal import Decimal


class TrackedResponsesClient:
    def __init__(self, tracker, client=None):
        self.tracker = tracker
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError("请先在环境变量中配置 OPENAI_API_KEY")
            from openai import AsyncOpenAI
            client = AsyncOpenAI()  # SDK 从环境变量读取密钥，不输出密钥。
        self.client = client

    async def create(self, *, model, input, cost_estimator=None, **kwargs):
        if kwargs.get("stream") or kwargs.get("background"):
            raise ValueError("当前接入点仅支持非流式、非后台请求；流式请在最终 response 到达后记录 usage")
        response = await self.client.responses.create(model=model, input=input, **kwargs)
        # 定价由调用方明确提供；未知费用保持 None。估价失败不能丢失真实 usage。
        cost = None
        if cost_estimator is not None:
            try:
                estimate = cost_estimator(response)
                cost = Decimal(str(estimate)) if estimate is not None else None
                if cost is not None and (not cost.is_finite() or cost < 0):
                    cost = None
            except Exception:
                cost = None
        await asyncio.to_thread(self.tracker.record_response, response, cost)
        return response

    async def close(self):
        await self.client.close()
