"""

Observability Module for Deep Research Agent.



Provides logging utilities to capture agent inputs and outputs for debugging

and verification purposes. Creates structured logs for both the Conductor

(supervisor) agent and each sub-agent.

"""



import json

import os

from datetime import datetime

from pathlib import Path

from typing import Any, Optional



from deep_research.config import LOG_MODE, SAVE_SUBAGENT_REPORTS_TO_FILE, ENABLE_SOURCE_LOG



# Global variable to store the current run's log folder

_current_log_folder: Optional[Path] = None

_sub_agent_counter: int = 0

_source_counter: int = 0

_source_lock = None  # Will be initialized as threading.Lock() when needed





def _save_to_db(table_name: str, data: dict) -> None:

    """

    Placeholder for database insert logic.



    Implement your DB insert here when ready. Example:

        db.execute(f"INSERT INTO {table_name} ...", data)



    Args:

        table_name: Name of the table (e.g., "conductor_logs", "sub_agent_logs")

        data: Dictionary of data to insert

    """

    # TODO: Implement database insert logic

    # This is a placeholder - the data dict contains all fields ready for DB insert

    pass





def init_run_folder(output_dir: Path, timestamp: str) -> Path:

    """

    Initialize the logging folder for a research run.



    Args:

        output_dir: Base output directory (e.g., "outputs")

        timestamp: Timestamp string for the run (e.g., "2026-01-15_16-45-00")



    Returns:

        Path to the created log folder

    """

    global _current_log_folder, _sub_agent_counter, _source_counter, _source_lock

    import threading



    # Create the run folder

    run_folder = output_dir / f"research_{timestamp}"

    run_folder.mkdir(parents=True, exist_ok=True)



    # Create sub_agents folder

    (run_folder / "sub_agents").mkdir(exist_ok=True)



    _current_log_folder = run_folder

    _sub_agent_counter = 0

    _source_counter = 0

    _source_lock = threading.Lock()



    return run_folder





def get_log_folder() -> Optional[Path]:

    """Get the current run's log folder."""

    return _current_log_folder





def log_conductor_turn(

    system_prompt: str,

    messages: list,

    response: Any,

    elapsed_minutes: float,

    iteration: int

) -> None:

    """

    Log a single turn of the Conductor agent.



    Args:

        system_prompt: The full system prompt sent to the agent (includes timing)

        messages: The conversation messages

        response: The LLM response object

        elapsed_minutes: How many minutes have elapsed since research started

        iteration: Which research iteration this is

    """

    if _current_log_folder is None:

        return



    log_file = _current_log_folder / "conductor_log.json"



    # Load existing log or create new

    if log_file.exists():

        with open(log_file, "r", encoding="utf-8") as f:

            log_data = json.load(f)

    else:

        log_data = {"agent_type": "conductor", "turns": []}



    # Extract response content

    response_content = ""

    tool_calls = []

    if hasattr(response, "content"):

        response_content = str(response.content)

    if hasattr(response, "tool_calls"):

        tool_calls = [

            {"name": tc.get("name", ""), "args": tc.get("args", {})}

            for tc in response.tool_calls

        ]



    # Add this turn

    turn_data = {

        "iteration": iteration,

        "timestamp": datetime.now().isoformat(),

        "elapsed_minutes": round(elapsed_minutes, 2),

        "system_prompt": system_prompt,

        "messages_count": len(messages),

        "response": response_content[:2000] + ("..." if len(response_content) > 2000 else ""),

        "tool_calls": tool_calls

    }



    log_data["turns"].append(turn_data)



    # Write to file if enabled

    if LOG_MODE in ("file", "both"):

        with open(log_file, "w", encoding="utf-8") as f:

            json.dump(log_data, f, indent=2, ensure_ascii=False)



    # Save to database if enabled

    if LOG_MODE in ("db", "both"):

        _save_to_db("conductor_logs", turn_data)





def log_sub_agent(

    research_topic: str,

    system_prompt: str,

    compressed_research: str,

    agent_type: str = "research_agent",

    search_queries: list = None

) -> None:

    """

    Log a sub-agent's full lifecycle.



    Args:

        research_topic: The topic the sub-agent was asked to research

        system_prompt: The system prompt sent to the sub-agent

        compressed_research: The final compressed research output

        agent_type: Type of agent ("research_agent" or "discovery_agent")

        search_queries: List of search queries made by this agent

    """

    global _sub_agent_counter



    if _current_log_folder is None:

        return



    _sub_agent_counter += 1

    log_file = _current_log_folder / "sub_agents" / f"sub_agent_{_sub_agent_counter:03d}.json"



    log_data = {

        "agent_type": agent_type,

        "agent_number": _sub_agent_counter,

        "timestamp": datetime.now().isoformat(),

        "research_topic": research_topic,

        "search_queries": search_queries or [],

        "system_prompt": system_prompt,

        "compressed_research": compressed_research[:5000] + ("..." if len(compressed_research) > 5000 else "")

    }



    # Write to file if enabled

    if LOG_MODE in ("file", "both"):

        with open(log_file, "w", encoding="utf-8") as f:

            json.dump(log_data, f, indent=2, ensure_ascii=False)

        # Full-length .md copy of the deliverable for review (JSON above stays
        # truncated to 5000 chars to keep the pipeline's copy bounded).
        if SAVE_SUBAGENT_REPORTS_TO_FILE:

            md_file = _current_log_folder / "sub_agents" / f"sub_agent_{_sub_agent_counter:03d}.md"

            md_content = (
                f"# {agent_type} — sub-agent {_sub_agent_counter:03d}\n\n"
                f"**Topic:** {research_topic}\n\n"
                f"**Queries:** {', '.join(search_queries or [])}\n\n"
                "---\n\n"
                f"{compressed_research}"
            )

            with open(md_file, "w", encoding="utf-8") as f:

                f.write(md_content)



    # Save to database if enabled

    if LOG_MODE in ("db", "both"):

        _save_to_db("sub_agent_logs", log_data)





def log_source(

    tool_name: str,

    link: str,

    content: str

) -> int:

    """

    Log a source (URL + content) discovered during research.



    This function is thread-safe and can be called from parallel tool executions.

    Sources are written immediately to a JSONL file for crash safety.



    Args:

        tool_name: Name of the tool that found this source (e.g., "tavily", "reddit_post", "reddit_subreddit")

        link: The URL of the source

        content: The content (AI summary for Tavily, full text for Reddit)



    Returns:

        The assigned source ID

    """

    global _source_counter, _source_lock

    if not ENABLE_SOURCE_LOG:
        return -1

    if _current_log_folder is None:

        return -1



    # Thread-safe counter increment

    if _source_lock is None:

        import threading

        _source_lock = threading.Lock()



    with _source_lock:

        _source_counter += 1

        source_id = _source_counter



    # Build the source entry

    entry = {

        "id": source_id,

        "tool": tool_name,

        "link": link,

        "content": content,

        "timestamp": datetime.now().isoformat()

    }



    # Append to JSONL file (one JSON object per line)

    sources_file = _current_log_folder / "sources.jsonl"



    if LOG_MODE in ("file", "both"):

        with open(sources_file, "a", encoding="utf-8") as f:

            f.write(json.dumps(entry, ensure_ascii=False) + "\n")



    if LOG_MODE in ("db", "both"):

        _save_to_db("sources", entry)



    return source_id





def aggregate_sources() -> dict:

    """

    Aggregate all sources from the current run into a dictionary.



    Call this at the end of a research run to get the complete source map.



    Returns:

        Dictionary with source IDs as keys: {1: {"link": "...", "content": "..."}, 2: ...}

    """

    if _current_log_folder is None:

        return {}



    sources_file = _current_log_folder / "sources.jsonl"



    if not sources_file.exists():

        return {}



    sources = {}

    with open(sources_file, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if line:

                entry = json.loads(line)

                sources[entry["id"]] = {

                    "tool": entry["tool"],

                    "link": entry["link"],

                    "content": entry["content"]

                }



    return sources





# ===== RESEARCH TRACE LOGGING =====

# Captures supervisor-subagent interaction loops for process traceability



_research_trace: list = []





def clear_research_trace() -> None:

    """Clear the research trace for a new run.



    Call this at the start of each research run to reset the trace.

    """

    global _research_trace

    _research_trace = []





def log_trace_delegation(research_topic: str) -> int:

    """Log when the supervisor delegates a research task to a subagent.



    Args:

        research_topic: The research topic/prompt given to the subagent



    Returns:

        The loop index for this delegation (use to update with findings later)

    """

    global _research_trace

    loop_entry = {

        "loop_number": len(_research_trace) + 1,

        "timestamp": datetime.now().isoformat(),

        "research_topic": research_topic,

        "findings": None,

        "supervisor_reaction": None

    }

    _research_trace.append(loop_entry)

    return len(_research_trace) - 1





def log_trace_findings(loop_index: int, findings: str) -> None:

    """Log the findings returned by a subagent.



    Args:

        loop_index: The index returned by log_trace_delegation

        findings: The compressed research findings from the subagent

    """

    global _research_trace

    if 0 <= loop_index < len(_research_trace):

        _research_trace[loop_index]["findings"] = findings





def log_trace_supervisor_reaction(reaction: str) -> None:

    """Log the supervisor's reaction (think_tool) after receiving findings.



    This attaches the reaction to the most recent loop that doesn't have one yet.



    Args:

        reaction: The think_tool reflection content

    """

    global _research_trace

    # Find the most recent loop without a reaction

    for loop in reversed(_research_trace):

        if loop.get("findings") is not None and loop.get("supervisor_reaction") is None:

            loop["supervisor_reaction"] = reaction

            break





def get_research_trace() -> list:

    """Get the accumulated research trace for the current run.



    Returns:

        List of loop dictionaries, each containing:

        - loop_number: Sequential loop number

        - timestamp: When the delegation occurred

        - research_topic: What the supervisor asked the subagent to research

        - findings: What the subagent returned

        - supervisor_reaction: The supervisor's think_tool reflection (if any)

    """

    return _research_trace.copy()

