"""Agent 协同轨迹 service：批量落库 / 按 session 查询。仿 knowledge_gap_service。"""
from typing import Any, Dict, List

from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.models.chat_history import AgentTrace


class AgentTraceService:

    async def save_traces(self, session_id: str, trace: List[Dict[str, Any]]) -> None:
        """把一次图执行的 trace 批量落库；失败只记日志，不影响主流程。"""
        if not session_id or not trace:
            return
        try:
            async with AsyncSessionLocal() as db:
                for i, item in enumerate(trace):
                    db.add(AgentTrace(
                        session_id=session_id,
                        agent_name=str(item.get("agent", "unknown")),
                        output=str(item.get("output", ""))[:4000],
                        status=str(item.get("status", "done")),
                        seq=i,
                    ))
                await db.commit()
        except Exception as e:
            logger.error(f"[AgentTrace] 落库失败 session={session_id}: {e}", exc_info=True)

    async def list_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            rows = await db.run_sync(
                lambda s: s.query(AgentTrace)
                .filter(AgentTrace.session_id == session_id)
                .order_by(AgentTrace.seq.asc())
                .all()
            )
            return [{
                "agent_name": r.agent_name,
                "status": r.status,
                "output": r.output,
                "seq": r.seq,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            } for r in rows]


agent_trace_service = AgentTraceService()
