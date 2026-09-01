from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DecisionSource, Partition, RouteName, SafetyAction
from app.models.schemas import ChatRequest, ChatResponse, Citation, RetrievalHit
from app.services.input_safety import InputSafetyGuard
from app.services.retriever import Retriever


class ChatService:
    def __init__(self, index_registry, retrieval_top_k: int) -> None:
        self.safety = InputSafetyGuard()
        self.retriever = Retriever(index_registry)
        self.retrieval_top_k = retrieval_top_k

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
                citations=[],
                suggested_partitions=[],
                request_id=request_id,
                warning="敏感输入未发送给索引或外部模型。",
            )

        if payload.partition_hint is None:
            return ChatResponse(
                code="ROUTE_CLARIFICATION_REQUIRED",
                answer="自动路由尚未配置，请选择财务、人事或技术分区后继续。",
                route=RouteName.CLARIFY,
                decision_source=DecisionSource.SAFETY_FALLBACK,
                answerable=False,
                citations=[],
                suggested_partitions=list(Partition),
                request_id=request_id,
                warning="当前请求未访问任何知识索引。",
            )

        partition = payload.partition_hint
        hits = await self.retriever.search(
            session,
            partition,
            safety.safe_question or payload.question,
            self.retrieval_top_k,
        )
        if not hits:
            return ChatResponse(
                code="NO_INTERNAL_EVIDENCE",
                answer="当前选定分区的内部知识库中暂无可用依据。",
                route=RouteName(partition.value),
                decision_source=DecisionSource.USER_HINT,
                answerable=False,
                citations=[],
                suggested_partitions=[],
                request_id=request_id,
                warning=(
                    "问题中的个人信息或内网地址已在检索前脱敏。"
                    if safety.action == SafetyAction.REDACTED
                    else None
                ),
            )

        return self._build_answer(hits, partition, request_id, safety.action)

    @staticmethod
    def _build_answer(
        hits: list[RetrievalHit],
        partition: Partition,
        request_id: str,
        safety_action: SafetyAction,
    ) -> ChatResponse:
        primary = hits[0]
        location = f"（{primary.section}）" if primary.section else ""
        answer = f"根据《{primary.title}》{location}：{primary.text}"
        return ChatResponse(
            code="OK",
            answer=answer,
            route=RouteName(partition.value),
            decision_source=DecisionSource.USER_HINT,
            answerable=True,
            citations=[
                Citation(
                    chunk_id=primary.chunk_id,
                    document_id=primary.document_id,
                    title=primary.title,
                    section=primary.section,
                    page_start=primary.page_start,
                    page_end=primary.page_end,
                )
            ],
            suggested_partitions=[],
            request_id=request_id,
            warning=(
                "问题中的个人信息或内网地址已在检索前脱敏。"
                if safety_action == SafetyAction.REDACTED
                else None
            ),
        )
