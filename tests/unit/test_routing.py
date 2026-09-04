import json

from app.models.enums import Partition, RouteKind
from app.services.routing import LLMRouter


class RecordingLLMProvider:
    def __init__(self) -> None:
        self.system_prompts: list[str] = []
        self.user_prompts: list[str] = []

    async def complete(self, *, model, system_prompt, user_prompt) -> str:
        self.system_prompts.append(system_prompt)
        self.user_prompts.append(user_prompt)
        return json.dumps(
            {
                "route_kind": "single",
                "subqueries": [
                    {"partition": "hr", "query": "公司基本信息和组织概况"}
                ],
                "needs_clarification": False,
                "reason_code": "hr_policy",
            },
            ensure_ascii=False,
        )


async def test_router_prompt_assigns_company_basics_to_hr():
    provider = RecordingLLMProvider()
    router = LLMRouter(
        provider=provider,
        model="router-test",
        retry_count=0,
        max_question_length=2000,
        max_partitions=2,
    )

    plan = await router.route("请介绍公司的基本信息和组织概况")

    assert plan.route_kind == RouteKind.SINGLE
    assert plan.subqueries[0].partition == Partition.HR
    assert json.loads(provider.user_prompts[0]) == {
        "question": "请介绍公司的基本信息和组织概况"
    }
    assert "公司基础信息一律输出 single，并路由到 hr" in provider.system_prompts[0]
    assert "公司基础信息输出模板" in provider.system_prompts[0]
