#!/usr/bin/env python3

"""

Deep Research Agent - Server Runner



A standalone script for running the Deep Research agent on a server.

Loads environment variables, runs research, and saves outputs with citations.



Usage (with uv):

    uv run python run_research.py --prompt "Your research question here"

    uv run python run_research.py --prompt-file input.txt

    uv run python run_research.py --prompt-file input.txt --output-dir my_outputs



Usage (without uv, if dependencies are installed):

    python run_research.py --prompt "Your research question here"

"""



import asyncio

import argparse

import logging

import os

import sys

import random

import string

from datetime import datetime

from pathlib import Path

from typing import Dict, Any



# Add 'src' to python path so we can import deep_research

# Get the absolute path to the script's directory, then add 'src'

script_dir = Path(__file__).resolve().parent

src_dir = script_dir / 'src'

sys.path.insert(0, str(src_dir))



# Load environment variables before importing anything else

from dotenv import load_dotenv



# Find and load .env file from project root

env_path = Path(__file__).resolve().parent / '.env'

load_dotenv(dotenv_path=env_path)



from langchain_core.messages import HumanMessage

from langgraph.checkpoint.memory import InMemorySaver



from deep_research.research_agent_full import deep_researcher_builder



from deep_research.config import SUBAGENT_MODEL_FALLBACK_CHAIN, OUTPUT_MODE, ENABLE_RESEARCH_TRACE, RESEARCH_TIME_MIN_MINUTES, RESEARCH_TIME_MAX_MINUTES, get_supervisor_model

from deep_research.observability import init_run_folder, aggregate_sources, get_research_trace, clear_research_trace

from deep_research.utils import extract_text_from_response

from deep_research.prompts import research_trace_compression_prompt





def _save_output_to_db(output_data: dict) -> None:

    """

    Placeholder for database insert logic for research outputs.



    Implement your DB insert here when ready. The output_data dict contains:

        - thread_id: Unique identifier for this research session

        - timestamp: When the research was run

        - prompt: Original user query

        - research_brief: The generated research plan

        - final_report: The main report content

        - notes: List of raw research notes



    Args:

        output_data: Dictionary containing all research output fields

    """

    # TODO: Implement database insert logic

    # Example: db.execute("INSERT INTO research_outputs ...", output_data)

    pass



# Configure logging

logging.basicConfig(

    level=logging.INFO,

    format='%(asctime)s - %(levelname)s - %(message)s',

    handlers=[

        logging.StreamHandler(sys.stdout)

    ]

)

logger = logging.getLogger(__name__)



logger.info(f"Initialized with sub-agent model: {SUBAGENT_MODEL_FALLBACK_CHAIN[0]}")





async def run_research(prompt: str, output_dir: Path, thread_id: str = None, clean_output: bool = False) -> Dict[str, Any]:

    """

    Run the Deep Research agent and save the output to a file.



    Args:

        prompt: The research prompt/question

        output_dir: Directory to save the output file

        thread_id: Optional thread ID for the research session



    Returns:

        Dictionary with:

            - output_file: Path to the saved output file

            - final_report: The raw final report content

            - sources: List of source dictionaries

    """

    # Create output directory if it doesn't exist

    output_dir.mkdir(parents=True, exist_ok=True)



    # Generate timestamp for filename and thread

    # Added 3 random letters to avoid collisions when multiple agents start at the same second

    random_suffix = ''.join(random.choices(string.ascii_lowercase, k=3))

    timestamp = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{random_suffix}"



    if thread_id is None:

        thread_id = timestamp



    output_file = output_dir / f"research_{timestamp}.md"



    # Initialize observability logging folder

    log_folder = init_run_folder(output_dir, timestamp)



    logger.info(f"Starting research with thread ID: {thread_id}")

    logger.info(f"Output will be saved to: {output_file}")



    # Clear research trace from any previous run

    clear_research_trace()



    try:

        # Compile the agent with an in-memory checkpointer

        checkpointer = InMemorySaver()

        agent = deep_researcher_builder.compile(checkpointer=checkpointer)



        # Configure the run

        config = {

            "configurable": {

                "thread_id": thread_id,

                "recursion_limit": 50

            }

        }



        logger.info(f"Running research agent... (this may take {RESEARCH_TIME_MIN_MINUTES}-{RESEARCH_TIME_MAX_MINUTES} minutes)")



        import time

        start_time = time.time()



        # Run the agent

        result = await agent.ainvoke(

            {

                "messages": [HumanMessage(content=prompt)],

                "start_time": start_time

            },

            config=config

        )



        # Extract the final report

        final_report = result.get("final_report", "")

        research_brief = result.get("research_brief", "")

        notes = result.get("notes", [])



        if not final_report:

            logger.warning("No final report generated, checking for draft report...")

            final_report = result.get("draft_report", "No report generated")



        # Prepare structured output data (for both file and DB)

        output_data = {

            "thread_id": thread_id,

            "timestamp": datetime.now().isoformat(),

            "prompt": prompt,

            "research_brief": research_brief,

            "final_report": final_report

        }



        # Write to file if enabled

        if OUTPUT_MODE in ("file", "both"):

            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:

                if not clean_output:

                    f.write("# Deep Research Report\n\n")

                    f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                    f.write("---\n\n")



                    # Include the original prompt

                    f.write("## Research Prompt\n\n")

                    f.write(f"{prompt}\n\n")

                    f.write("---\n\n")



                    # Include the research brief if available

                    if research_brief:

                        f.write("## Research Brief\n\n")

                        f.write(f"{research_brief}\n\n")

                        f.write("---\n\n")



                # The main report (includes citations)

                f.write("## Final Report\n\n")

                f.write(f"{final_report}\n\n")







            logger.info(f"Report saved to file: {output_file}")



        # Aggregate all sources (always, for programmatic access)

        sources = aggregate_sources()



        # Save sources to JSON if file output is enabled

        if OUTPUT_MODE in ("file", "both") and sources:

            import json

            sources_json_file = output_dir / f"research_data_{timestamp}.json"

            research_data = {

                "thread_id": thread_id,

                "timestamp": datetime.now().isoformat(),

                "prompt": prompt,

                "sources": sources,

                "final_report": final_report

            }

            sources_json_file.parent.mkdir(parents=True, exist_ok=True)

            with open(sources_json_file, "w", encoding="utf-8") as f:

                json.dump(research_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Sources saved to: {sources_json_file} ({len(sources)} sources)")



        # Save to database if enabled

        if OUTPUT_MODE in ("db", "both"):

            _save_output_to_db(output_data)

            logger.info("Report saved to database")



        logger.info("Research complete!")



        # Generate research trace content (only if enabled)

        trace_content = None

        trace_file = None

        trace_data = get_research_trace() if ENABLE_RESEARCH_TRACE else []



        if trace_data:

            # Format raw interaction log for the prompt

            interaction_log = ""

            for loop in trace_data:

                interaction_log += f"""

--- Loop {loop['loop_number']} (at {loop['timestamp']}) ---



SUPERVISOR DELEGATED RESEARCH TOPIC:

{loop['research_topic']}



SUBAGENT RETURNED FINDINGS:

{loop['findings'][:] if loop.get('findings') else 'No findings returned'}{'' if loop.get('findings') and len(loop['findings']) > 3000 else ''}



SUPERVISOR REACTION:

{loop.get('supervisor_reaction', 'No explicit reaction captured')}



"""



            # Compress trace into readable document using LLM

            try:

                logger.info("Generating research trace document...")

                trace_prompt = research_trace_compression_prompt.format(

                    research_brief=research_brief,

                    interaction_log=interaction_log

                )



                # Use resilient model for trace compression

                trace_model = get_supervisor_model(max_tokens=16000)

                trace_response = await trace_model.ainvoke([HumanMessage(content=trace_prompt)])

                trace_content = extract_text_from_response(trace_response.content)



            except Exception as e:

                logger.warning(f"Failed to generate research trace: {e}")

                # Fall back to raw trace output

                trace_content = "# Research Process Trace (Raw)\n\n"

                trace_content += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

                trace_content += f"**Research Brief:** {research_brief}\n\n"

                trace_content += "---\n\n"

                trace_content += interaction_log



            # Write trace file ONLY if file output is enabled

            if OUTPUT_MODE in ("file", "both") and trace_content:

                trace_file = output_dir / f"trace_{timestamp}.md"

                trace_file.parent.mkdir(parents=True, exist_ok=True)

                with open(trace_file, "w", encoding="utf-8") as f:

                    f.write(trace_content)

                logger.info(f"Research trace saved to: {trace_file}")



        # Add trace content to output_data for DB/API usage

        output_data["trace_content"] = trace_content



        # Save to database if enabled

        if OUTPUT_MODE in ("db", "both"):

            _save_output_to_db(output_data)

            logger.info("Report saved to database")



        # Return structured data for programmatic access

        return {

            "output_file": output_file,

            "final_report": final_report,

            "sources": sources if sources else [],

            "trace_content": trace_content

        }



    except Exception as e:

        import traceback

        tb_str = traceback.format_exc()

        logger.error(f"Error during research: {e}")

        logger.error(f"Full traceback:\n{tb_str}")



        # Save error to file for debugging

        error_file = output_dir / f"error_{timestamp}.txt"

        error_file.parent.mkdir(parents=True, exist_ok=True)

        with open(error_file, "w", encoding="utf-8") as f:

            f.write(f"Error occurred at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write(f"Prompt:\n{prompt}\n\n")

            f.write(f"Error:\n{str(e)}\n\n")

            f.write(f"Full Traceback:\n{tb_str}\n")



        logger.error(f"Error details saved to: {error_file}")

        raise





def main():

    """Main entry point for the script."""

    parser = argparse.ArgumentParser(

        description="Run the Deep Research Agent",

        formatter_class=argparse.RawDescriptionHelpFormatter,

        epilog="""

Examples:

    python run_research.py --prompt "What are the latest developments in AI safety?"

    python run_research.py --prompt-file research_question.txt

    python run_research.py --prompt-file input.txt --output-dir results

        """

    )



    # Input options (mutually exclusive)

    input_group = parser.add_mutually_exclusive_group(required=True)

    input_group.add_argument(

        "--prompt", "-p",

        type=str,

        help="Research prompt/question to investigate"

    )

    input_group.add_argument(

        "--prompt-file", "-f",

        type=str,

        help="Path to a file containing the research prompt"

    )



    # Output options

    parser.add_argument(

        "--output-dir", "-o",

        type=str,

        default="outputs",

        help="Directory to save output files (default: outputs)"

    )



    # Optional thread ID

    parser.add_argument(

        "--thread-id", "-t",

        type=str,

        default=None,

        help="Thread ID for the research session (default: auto-generated timestamp)"

    )



    args = parser.parse_args()



    # Get the prompt

    if args.prompt:

        prompt = args.prompt

    else:

        prompt_path = Path(args.prompt_file)

        if not prompt_path.exists():

            logger.error(f"Prompt file not found: {prompt_path}")

            sys.exit(1)



        with open(prompt_path, "r", encoding="utf-8") as f:

            prompt = f.read().strip()



    if not prompt:

        logger.error("Empty prompt provided")

        sys.exit(1)



    logger.info(f"Prompt length: {len(prompt)} characters")



    # Run the research

    output_dir = Path(args.output_dir)



    try:

        result = asyncio.run(run_research(prompt, output_dir, args.thread_id))

        print(f"\n✅ Research complete! Output saved to: {result['output_file']}")

    except KeyboardInterrupt:

        logger.info("Research interrupted by user")

        sys.exit(1)

    except Exception as e:

        logger.error(f"Research failed: {e}")

        sys.exit(1)





if __name__ == "__main__":

    main()

