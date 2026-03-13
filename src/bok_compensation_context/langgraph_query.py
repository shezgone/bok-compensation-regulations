"""Minimal LangGraph wrapper around the markdown-context reasoning path."""

from __future__ import annotations

import sys
from typing import Annotated, List, TypedDict
import operator

from langgraph.graph import END, START, StateGraph

from .context_query import answer_with_context


class AgentState(TypedDict):
    query: str
    semantic_queries: List[str]
    data_queries: List[str]
    semantic_results: Annotated[List[str], operator.add]
    data_results: Annotated[List[str], operator.add]
    final_answer: str


def reasoner_node(state: AgentState):
    answer, sections = answer_with_context(state["query"])
    titles = ", ".join(section["title"] for section in sections)
    return {
        "semantic_results": [f"선택된 전처리 문맥 섹션: {titles}"],
        "data_results": [],
        "final_answer": answer,
    }


def create_langgraph():
    workflow = StateGraph(AgentState)
    workflow.add_node("context_reasoner", reasoner_node)
    workflow.add_edge(START, "context_reasoner")
    workflow.add_edge("context_reasoner", END)
    return workflow.compile()


def run_langgraph(query: str) -> str:
    app = create_langgraph()
    final_state = app.invoke(
        {
            "query": query,
            "semantic_queries": [],
            "data_queries": [],
            "semantic_results": [],
            "data_results": [],
        }
    )
    return str(final_state.get("final_answer", ""))


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or "기한부 고용계약자가 상여금을 받을 수 있는지와 G5 직원의 초봉을 함께 알려줘."
    print(run_langgraph(query))
