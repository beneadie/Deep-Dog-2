
"""User Clarification and Research Brief Generation.

This module implements the scoping phase of the research workflow, where we:
1. Assess if the user's request needs clarification
2. Generate a detailed research brief from the conversation

The workflow uses structured output to make deterministic decisions about
whether sufficient context exists to proceed with research.
"""

import asyncio
from typing_extensions import Literal

from langchain_core.messages import HumanMessage, get_buffer_string
from langchain_core.output_parsers import PydanticOutputParser
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from deep_research.prompts import transform_messages_into_research_topic_human_msg_prompt, draft_report_generation_prompt, clarify_with_user_instructions, example_report
from deep_research.state_scope import AgentState, ResearchQuestion, AgentInputState
from deep_research.config import get_draft_report_model, get_subagent_model, TARGET_LANGUAGE_FALLBACK
from deep_research.utils import extract_text_from_response, get_today_str

# ===== CONFIGURATION =====

# Research brief: written on the sub-agent chain (lighter model) since it only
# extracts a topic + language from the conversation.
model = get_subagent_model(max_tokens=32000)
# Draft report: long-form synthesis on the configurable draft model (defaults
# to the supervisor chain; set DRAFT_REPORT_MODEL for a cheaper writer). This
# pass is cold/non-cacheable and only needs to be LONG, not perfect.
creative_model = get_draft_report_model(max_tokens=32000)

# ===== WORKFLOW NODES =====

def clarify_with_user(state: AgentState) -> Command[Literal["write_research_brief"]]:
    #uncomment if you want to enable this module
    """
    Determine if the user's request contains sufficient information to proceed with research.

    Uses structured output to make deterministic decisions and avoid hallucination.
    Routes to either research brief generation or ends with a clarification question.
    """

    """
    # Set up structured output model
    structured_output_model = model.with_structured_output(ClarifyWithUser, method="function_calling")

    # Invoke the model with clarification instructions
    response = structured_output_model.invoke([
        HumanMessage(content=clarify_with_user_instructions.format(
            messages=get_buffer_string(messages=state["messages"]),
            date=get_today_str()
        ))
    ])

    # Route based on clarification need
    if response.need_clarification:
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=response.question)]}
        )
    else:
    """
    return Command(
        goto="write_research_brief"
    )

def write_research_brief(state: AgentState) -> Command[Literal["write_draft_report"]]:
    """
    Transform the conversation history into a comprehensive research brief.

    Uses structured output to ensure the brief follows the required format
    and contains all necessary details for effective research.
    """
    # json_mode (response_format=json_object), NOT function_calling:
    # reasoning-mode providers (DeepSeek thinking mode is on by default) reject
    # forced tool_choice with a 400; json_object is the cross-provider path
    # (DeepSeek JSON Output guide, MiMo/OpenRouter OpenAI-compatible APIs).
    parser = PydanticOutputParser(pydantic_object=ResearchQuestion)
    structured_output_model = model.with_structured_output(ResearchQuestion, method="json_mode")

    # Generate research brief from conversation history. get_format_instructions()
    # supplies the JSON schema + the word "json" (required by DeepSeek json_object).
    response = structured_output_model.invoke([
        HumanMessage(content=transform_messages_into_research_topic_human_msg_prompt.format(
            messages=get_buffer_string(state.get("messages", [])),
            date=get_today_str()
        ) + "\n\n" + parser.get_format_instructions())
    ])
    # Update state with generated research brief and pass it to the draft writer.
    # Hard language rule: the model detects `input_language` from the user's
    # message; `target_language` is DERIVED from it so a mismatch is impossible
    # (a single mis-detection can still occur, but the two can never diverge).
    input_language = response.input_language or response.target_language or TARGET_LANGUAGE_FALLBACK
    return Command(
            goto="write_draft_report",
            update={
                "research_brief": response.research_brief,
                "input_language": input_language,
                "target_language": input_language,
            }
        )

async def write_draft_report(state: AgentState) -> Command[Literal["__end__"]]:
    """
    Final report generation node.

    Synthesizes all research findings into a comprehensive final report
    """
    research_brief = state.get("research_brief", "")
    target_language = state.get("target_language") or TARGET_LANGUAGE_FALLBACK

    draft_report_prompt = draft_report_generation_prompt.format(
        research_brief=research_brief,
        date=get_today_str(),
        example_report=example_report,
        target_language=target_language
    )

    # Generate long-form text directly (avoid structured JSON wrapping for large payloads)
    response = await asyncio.wait_for(
        creative_model.ainvoke([HumanMessage(content=draft_report_prompt)]),
        timeout=420,  # 7 minutes — allows headroom when running concurrent tasks
    )
    draft_report = extract_text_from_response(response.content)

    original_question = get_buffer_string(state.get("messages", []))
    return {
        "research_brief": research_brief,
        "draft_report": draft_report,
        "target_language": target_language,
        "supervisor_messages": [
            "Here is the draft report: " + draft_report,
            research_brief,
            "ORIGINAL USER QUESTION (verbatim — the report MUST answer this):\n" + original_question,
        ]
    }

# ===== GRAPH CONSTRUCTION =====

# Build the scoping workflow
deep_researcher_builder = StateGraph(AgentState, input_schema=AgentInputState)

# Add workflow nodes
deep_researcher_builder.add_node("clarify_with_user", clarify_with_user)
deep_researcher_builder.add_node("write_research_brief", write_research_brief)
deep_researcher_builder.add_node("write_draft_report", write_draft_report)

# Add workflow edges
deep_researcher_builder.add_edge(START, "clarify_with_user")
deep_researcher_builder.add_edge("write_research_brief", "write_draft_report")
deep_researcher_builder.add_edge("write_draft_report", END)

# Compile the workflow
scope_research = deep_researcher_builder.compile()
