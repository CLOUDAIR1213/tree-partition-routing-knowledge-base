from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    AnswerSource,
    DecisionSource,
    Partition,
    RouteKind,
    RouteName,
    SafetyAction,
)
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    LLMRoutePlan,
    RetrievalGroup,
    RetrievalHit,
    RoutedSubquery,
    WebCitation,
)
from app.services.answering import LLMAnswerer, LLMWebAnswerer
from app.services.input_safety import InputSafetyGuard
from app.services.llm import LLMOutputError, LLMProviderError
from app.services.retriever import Retriever
from app.services.routing import LLMRouter
from app.services.web_search import (
    WebSearchProvider,
    WebSearchProviderError,
    is_web_fallback_eligible,
)


class ChatService:
    def __init__(
        self,
        index_registry,
        retrieval_top_k: int,
        retrieval_min_score: float,
        composite_top_k: int,
        router: LLMRouter | None = None,
        answerer: LLMAnswerer | None = None,
        web_search_provider: WebSearchProvider | None = None,
        web_answerer: LLMWebAnswerer | None = None,
        web_search_max_results: int = 5,
        answer_mode: str = "llm",
    ) -> None:
        self.safety = InputSafetyGuard()
        self.retriever = Retriever(index_registry, retrieval_min_score)
        self.retrieval_top_k = retrieval_top_k
        self.composite_top_k = composite_top_k
        self.router = router
        self.answerer = answerer
        self.web_search_provider = web_search_provider
        self.web_answerer = web_answerer
        self.web_search_max_results = web_search_max_results
        self.answer_mode = answer_mode

    async def answer(
        self,
        session: AsyncSession,
        payload: ChatRequest,
        request_id: str,
    ) -> ChatResponse:
        safety = self.safety.inspect(payload.question)
        if safety.action == SafetyAction.BLOCKED:
            return ChatResponse(
                code="SENSITIVE_INPUT_BLOCKED",
                answer="问题包含密钥、密码或其他秘密值，请删除后重新提交。",
                route=RouteName.CLARIFY,
                decision_source=DecisionSource.SAFETY_FALLBACK,
                answerable=False,
                answer_source=AnswerSource.NONE,
                searched_partitions=[],
                citations=[],
                web_citations=[],
                suggested_partitions=[],
                request_id=request_id,
                warning="敏感输入未发送给索引或外部模型。",
            )

        question = safety.safe_question or payload.question
        if payload.partition_hint is not None:
            plan = LLMRoutePlan(
                route_kind=RouteKind.SINGLE,
                subqueries=[
                    RoutedSubquery(partition=payload.partition_hint, query=question)
                ],
                needs_clarification=False,
                reason_code=self._reason_for_partition(payload.partition_hint),
            )
            decision_source = DecisionSource.USER_HINT
        else:
            routed = await self._route(question, request_id, safety.action)
            if isinstance(routed, ChatResponse):
                return routed
            plan = routed
            decision_source = DecisionSource.LLM

        limit = (
            self.composite_top_k
            if plan.route_kind == RouteKind.COMPOSITE
            else self.retrieval_top_k
        )
        groups = await self.retriever.search_groups(session, plan.subqueries, limit)
        route = (
            RouteName.COMPOSITE
            if plan.route_kind == RouteKind.COMPOSITE
            else RouteName(groups[0].partition.value)
        )
        searched_partitions = [group.partition for group in groups]
        if not any(group.hits for group in groups):
            return await self._answer_without_internal_evidence(
                question=question,
                allow_web_fallback=payload.allow_web_fallback,
                groups=groups,
                route=route,
                decision_source=decision_source,
                request_id=request_id,
                safety_action=safety.action,
            )

        if self.answerer is not None:
            try:
                draft = await self.answerer.answer(question, groups)
            except LLMProviderError:
                return self._build_extractive_answer(
                    groups,
                    route,
                    decision_source,
                    request_id,
                    safety.action,
                    "回答模型暂不可用，已回退为抽取式回答。",
                )
            except LLMOutputError:
                return ChatResponse(
                    code="NO_INTERNAL_EVIDENCE",
                    answer="回答模型返回的引用未通过校验，暂时无法提供有依据的回答。",
                    route=route,
                    decision_source=decision_source,
                    answerable=False,
                    answer_source=AnswerSource.NONE,
                    searched_partitions=searched_partitions,
                    citations=[],
                    web_citations=[],
                    suggested_partitions=[],
                    request_id=request_id,
                    warning=self._warning(
                        safety.action,
                        "模型输出未通过本地证据白名单校验。",
                    ),
                )
            return self._build_llm_answer(
                draft.answer,
                draft.citation_chunk_ids,
                groups,
                route,
                decision_source,
                request_id,
                safety.action,
            )

        fallback_warning = (
            "回答模型未配置，已使用抽取式回答。"
            if self.answer_mode == "llm"
            else None
        )
        return self._build_extractive_answer(
            groups,
            route,
            decision_source,
            request_id,
            safety.action,
            fallback_warning,
        )

    async def _route(
        self,
        question: str,
        request_id: str,
        safety_action: SafetyAction,
    ) -> LLMRoutePlan | ChatResponse:
        if self.router is None:
            return self._clarification(
                request_id,
                DecisionSource.SAFETY_FALLBACK,
                self._warning(
                    safety_action,
                    "Router LLM 未配置，当前请求未访问任何知识索引。",
                ),
            )
        try:
            plan = await self.router.route(question)
        except (LLMProviderError, LLMOutputError):
            return self._clarification(
                request_id,
                DecisionSource.SAFETY_FALLBACK,
                self._warning(
                    safety_action,
                    "自动路由暂不可用，当前请求未访问任何知识索引。",
                ),
            )
        if plan.route_kind == RouteKind.CLARIFY:
            return self._clarification(
                request_id,
                DecisionSource.LLM,
                self._warning(safety_action),
            )
        return plan

    @staticmethod
    def _clarification(
        request_id: str,
        decision_source: DecisionSource,
        warning: str | None,
    ) -> ChatResponse:
        return ChatResponse(
            code="ROUTE_CLARIFICATION_REQUIRED",
            answer="问题涉及范围不明确或超过两个分区，请选择财务、人事或技术分区后继续。",
            route=RouteName.CLARIFY,
            decision_source=decision_source,
            answerable=False,
            answer_source=AnswerSource.NONE,
            searched_partitions=[],
            citations=[],
            web_citations=[],
            suggested_partitions=list(Partition),
            request_id=request_id,
            warning=warning,
        )

    @classmethod
    def _build_llm_answer(
        cls,
        answer: str,
        citation_ids: list[str],
        groups: list[RetrievalGroup],
        route: RouteName,
        decision_source: DecisionSource,
        request_id: str,
        safety_action: SafetyAction,
    ) -> ChatResponse:
        by_id = {hit.chunk_id: hit for group in groups for hit in group.hits}
        return ChatResponse(
            code="OK",
            answer=answer,
            route=route,
            decision_source=decision_source,
            answerable=True,
            answer_source=AnswerSource.INTERNAL,
            searched_partitions=[group.partition for group in groups],
            citations=[cls._citation(by_id[chunk_id]) for chunk_id in citation_ids],
            web_citations=[],
            suggested_partitions=[],
            request_id=request_id,
            warning=cls._warning(safety_action),
        )

    @classmethod
    def _build_extractive_answer(
        cls,
        groups: list[RetrievalGroup],
        route: RouteName,
        decision_source: DecisionSource,
        request_id: str,
        safety_action: SafetyAction,
        fallback_warning: str | None,
    ) -> ChatResponse:
        sections: list[str] = []
        citations: list[Citation] = []
        for group in groups:
            if not group.hits:
                sections.append(
                    f"【{cls._partition_label(group.partition)}】当前内部知识库暂无可用依据。"
                )
                continue
            primary = group.hits[0]
            location = f"（{primary.section}）" if primary.section else ""
            prefix = (
                f"【{cls._partition_label(group.partition)}】"
                if len(groups) > 1
                else ""
            )
            sections.append(
                f"{prefix}根据《{primary.title}》{location}：{primary.text}"
            )
            citations.append(cls._citation(primary))
        return ChatResponse(
            code="OK",
            answer="\n\n".join(sections),
            route=route,
            decision_source=decision_source,
            answerable=True,
            answer_source=AnswerSource.INTERNAL,
            searched_partitions=[group.partition for group in groups],
            citations=citations,
            web_citations=[],
            suggested_partitions=[],
            request_id=request_id,
            warning=cls._warning(safety_action, fallback_warning),
        )

    async def _answer_without_internal_evidence(
        self,
        *,
        question: str,
        allow_web_fallback: bool,
        groups: list[RetrievalGroup],
        route: RouteName,
        decision_source: DecisionSource,
        request_id: str,
        safety_action: SafetyAction,
    ) -> ChatResponse:
        searched_partitions = [group.partition for group in groups]

        def unavailable(extra_warning: str | None = None) -> ChatResponse:
            return ChatResponse(
                code="NO_INTERNAL_EVIDENCE",
                answer="已检索的内部知识分区中暂无可用依据。",
                route=route,
                decision_source=decision_source,
                answerable=False,
                answer_source=AnswerSource.NONE,
                searched_partitions=searched_partitions,
                citations=[],
                web_citations=[],
                suggested_partitions=[],
                request_id=request_id,
                warning=self._warning(safety_action, extra_warning),
            )

        if not allow_web_fallback:
            return unavailable()
        if safety_action != SafetyAction.SAFE:
            return unavailable("问题经过脱敏处理，本次未发送到联网搜索。")
        if not is_web_fallback_eligible(question):
            return unavailable("该问题不符合公开、低风险的联网回答范围。")
        if self.web_search_provider is None:
            return unavailable("联网搜索未配置，本次仅完成内部知识检索。")
        if self.web_answerer is None:
            return unavailable("联网回答模型未配置，本次未生成网络答案。")

        try:
            results = await self.web_search_provider.search(
                question,
                self.web_search_max_results,
            )
        except WebSearchProviderError as exc:
            return unavailable(exc.safe_message)
        if not results:
            return unavailable("联网搜索没有返回可验证的公开来源。")

        try:
            draft = await self.web_answerer.answer(question, results)
        except (LLMProviderError, LLMOutputError):
            return unavailable("联网结果不足以形成带来源的可靠回答。")

        by_url = {result.url: result for result in results}
        web_citations = [
            WebCitation(
                title=by_url[url].title,
                url=url,
                domain=by_url[url].domain,
            )
            for url in draft.citation_urls
        ]
        return ChatResponse(
            code="OK",
            answer=draft.answer,
            route=route,
            decision_source=decision_source,
            answerable=True,
            answer_source=AnswerSource.WEB,
            searched_partitions=searched_partitions,
            citations=[],
            web_citations=web_citations,
            suggested_partitions=[],
            request_id=request_id,
            warning="内部知识库无可用依据，以下内容来自公开网络信息。",
        )

    @staticmethod
    def _citation(hit: RetrievalHit) -> Citation:
        return Citation(
            partition=hit.partition,
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            title=hit.title,
            section=hit.section,
            page_start=hit.page_start,
            page_end=hit.page_end,
        )

    @staticmethod
    def _warning(
        safety_action: SafetyAction,
        extra: str | None = None,
    ) -> str | None:
        warnings: list[str] = []
        if safety_action == SafetyAction.REDACTED:
            warnings.append("问题中的个人信息或内网地址已在检索前脱敏。")
        if extra:
            warnings.append(extra)
        return " ".join(warnings) or None

    @staticmethod
    def _partition_label(partition: Partition) -> str:
        return {
            Partition.FINANCE: "财务",
            Partition.HR: "人事",
            Partition.TECH: "技术",
        }[partition]

    @staticmethod
    def _reason_for_partition(partition: Partition) -> str:
        return {
            Partition.FINANCE: "finance_policy",
            Partition.HR: "hr_policy",
            Partition.TECH: "technical_operation",
        }[partition]
