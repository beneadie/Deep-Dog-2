"""
Prompt Version: OPEN_DRAFT

The former OPEN version, kept for A/B comparison: full draft-report stage,
no example report anywhere. The new lean OPEN moves most of the drafting
pressure onto the supervisor; this version keeps the draft-heavy pipeline.

Key differences from other prompt versions:
- draft_report_generation_prompt produces a long prose draft.
- No example report is sent anywhere.
- example_report is defined as an empty string for import compatibility only.
- Target-language enforcement (the {target_language} placeholder) is present in
  the same downstream prompts as the other versions.

Set PROMPT_VERSION = "OPEN_DRAFT" in config.py to activate this version.
"""

from datetime import datetime
from deep_research.config import RESEARCH_TIME_MIN_MINUTES, RESEARCH_TIME_MAX_MINUTES

# Dynamic year calculation for prompts
_current_year = datetime.now().year
_previous_year = _current_year - 1

# This prompt version does NOT run the iterative draft-refinement loop
# (no refine_draft_report tool). LEAN_ENFORCED / STRICT_ENFORCED enable it.
ENABLE_REFINE = False

clarify_with_user_instructions="""
These are the messages that have been exchanged so far from the user asking for the report:
<Messages>
{messages}
</Messages>

Today's date is {date}.

Assess whether you need to ask a clarifying question, or if the user has already provided enough information for you to start research.
IMPORTANT: If you can see in the messages history that you have already asked a clarifying question, you almost always do not need to ask another one. Only ask another question if ABSOLUTELY NECESSARY.

If there are acronyms, abbreviations, or unknown terms, ask the user to clarify.
If you need to ask a question, follow these guidelines:
- Be concise while gathering all necessary information
- Make sure to gather all the information needed to carry out the research task in a concise, well-structured manner.
- Use bullet points or numbered lists if appropriate for clarity. Make sure that this uses markdown formatting and will be rendered correctly if the string output is passed to a markdown renderer.
- Don't ask for unnecessary information, or information that the user has already provided. If you can see that the user has already provided the information, do not ask for it again.

Respond in valid JSON format with these exact keys:
"need_clarification": boolean,
"question": "<question to ask the user to clarify the report scope>",
"verification": "<verification message that we will start research>"

If you need to ask a clarifying question, return:
"need_clarification": true,
"question": "<your clarifying question>",
"verification": ""

If you do not need to ask a clarifying question, return:
"need_clarification": false,
"question": "",
"verification": "<acknowledgement message that you will now start research based on the provided information>"

For the verification message when no clarification is needed:
- Acknowledge that you have sufficient information to proceed
- Briefly summarize the key aspects of what you understand from their request
- Confirm that you will now begin the research process
- Keep the message concise and professional

CRITICAL: Make sure your response (question or verification) is written in the same language as the human messages!
For example, if the user's messages are in English, then MAKE SURE you write your response in English. If the user's messages are in Chinese, then MAKE SURE you write your entire response in Chinese.
"""

transform_messages_into_research_topic_human_msg_prompt = """
You will be given a set of messages that have been exchanged so far between yourself and the user.
Your job is to translate these messages into a more detailed and concrete research question that will be used to guide the research.

The messages that have been exchanged so far between yourself and the user are:
<Messages>
{messages}
</Messages>

<Language Detection — read the <Messages> block FIRST>
1. Determine the language the user's messages are literally written in — from the actual script/characters in <Messages>, and nothing else.
2. input_language must name that language exactly (e.g. "English", "中文").
3. target_language must be IDENTICAL to input_language.
4. Do NOT infer the language from the research topic, from the language used in these instructions, or from your own preference. If the user's message is written in English, both fields are "English".
5. Write the research brief in target_language (the same language as the user's messages).
</Language Detection>

CRITICAL: Make sure the answer is written in the same language as the human messages!
For example, if the user's messages are in English, then MAKE SURE you write your response in English. If the user's messages are in Chinese, then MAKE SURE you write your entire response in Chinese.
This is critical. The user will only understand the answer if it is written in the same language as their input message.

Today's date is {date}.

You will return a single research question that will be used to guide the research.
You must also identify and return: (a) input_language — the language the user's messages are written in (see <Language Detection>); (b) target_language — the language the report should be written in. Both must be IDENTICAL.

Guidelines:
1. Maximize Specificity and Detail
- Include all known user preferences and explicitly list key attributes or dimensions to consider.
- It is important that all details from the user are included in the instructions.

2. Handle Unstated Dimensions Carefully
- When research quality requires considering additional dimensions that the user hasn't specified, acknowledge them as open considerations rather than assumed preferences.
- Example: Instead of assuming "budget-friendly options," say "consider all price ranges unless cost constraints are specified."
- Only mention dimensions that are genuinely necessary for comprehensive research in that domain.

3. Avoid Unwarranted Assumptions
- Never invent specific user preferences, constraints, or requirements that weren't stated.
- If the user hasn't provided a particular detail, explicitly note this lack of specification.
- Guide the researcher to treat unspecified aspects as flexible rather than making assumptions.

4. Distinguish Between Research Scope and User Preferences
- Research scope: What topics/dimensions should be investigated (can be broader than user's explicit mentions)
- User preferences: Specific constraints, requirements, or preferences (must only include what user stated)
- Example: "Research coffee quality factors (including bean sourcing, roasting methods, brewing techniques) for San Francisco coffee shops, with primary focus on taste as specified by the user."

5. Use the First Person
- Phrase the request from the perspective of the user.

6. Sources
- If specific sources should be prioritized, specify them in the research question.
- For product and travel research, prefer linking directly to official or primary websites (e.g., official brand sites, manufacturer pages, or reputable e-commerce platforms like Amazon for user reviews) rather than aggregator sites or SEO-heavy blogs.
- For academic or scientific queries, prefer linking directly to the original paper or official journal publication rather than survey papers or secondary summaries.
- For people, try linking directly to their LinkedIn profile, or their personal website if they have one.
- If the query is in a specific language, prioritize sources published in that language.

REMEMBER:
Make sure the research brief is in the SAME language as the human messages in the message history — i.e., in input_language.
"""

research_agent_prompt =  """
You are a research assistant conducting research on the user's input topic. For context, today's date is {date}.

TARGET_LANGUAGE: {target_language}

CRITICAL OUTPUT LANGUAGE RULES:
- Write ALL outputs in TARGET_LANGUAGE.
- Do NOT switch output language except unavoidable proper nouns, source titles, and direct quotes.
- You may search in local languages when useful, but your written output must remain in TARGET_LANGUAGE.

<Task>
Your job is to use tools to gather information about the user's input topic.
You can use any of the tools provided to you to find resources that can help answer the research question. You can call these tools in series or in parallel, your research is conducted in a tool-calling loop.
</Task>

<Available Tools>
You have access to six tools:

1. **tavily_search**: For conducting web searches to gather information from news, articles, and official sources.

2. **think_tool**: For reflection and strategic planning during research.

3. **search_term_in_subreddit**:
   Primary tool for finding Reddit discussions by topic/keyword. Use this when:
   - You want to find discussions about a specific topic across Reddit.
   - You need to see engagement metrics (likes, comments) and dates for multiple related posts.
   - You want to browse many posts (up to 200) before deciding which ones to read in full.
   - Example: `search_term_in_subreddit(query="Google OR GOOGL", sort="relevance", time_filter="year", limit=100)`

4. **get_subreddit_posts**: For fetching Reddit discussions from specific subreddits. Use this when:
   - You need community sentiment, opinions, or informal analysis
   - You want to find contrarian views or grassroots discussions
   - You want to browse discussions without a targeted search term
   - Returns up to 200 post titles with URLs, scores, comment counts, and age
   - Example: `get_subreddit_posts(subreddit="StockMarket", limit=100)`
   - note that it is only useful when reddit is a good source for your task.

5. **get_reddit_post**: For extracting full content and comments from a specific Reddit post URL. Use this when:
   - You have a Reddit post URL from get_subreddit_posts and want the full discussion
   - You need to read the post body and community comments with usernames
   - Returns post title, author, score, body, and full comment thread with reply structure
   - Example: `get_reddit_post(url="https://www.reddit.com/r/stocks/comments/abc123/title/")`

6. **google_search_grounding**: (removed — use fetch_urls to read external pages instead)

**CRITICAL: Use think_tool after each search to reflect on results and plan next steps. You should often look at multiple Reddit posts to get a balanced view.**
</Available Tools>

<Instructions>
Think like a human researcher with limited time. Follow these steps:

1. **Read the question carefully** - What specific information does the user need?
2. **Start with broader searches** - Use broad, comprehensive queries first.
3. **Check the date** - If the topic is time sensitive, it generally will be as it is best to be up to date, ALWAYS include the current year (""" + str(_current_year) + """) or previous year (""" + str(_previous_year) + """) in your queries.
4. **After each search, pause and assess** - Do I have enough to answer? What's still missing?
5. **Execute narrower searches as you gather information** - Fill in the gaps
6. **Verify Claims** - if claims are made in articles that may be out of date, you need to work to try verify this. Things claimed in articles or forums a few months old might be massively out of date both in the subject and the claims made. (eg reviews could say that people prefer the iphone design to androids but if it was written in 2010 the state of the products would be massively different to today)
6. **Stop when you can answer confidently** - Don't keep searching for perfection

<Date Consciousness>
- Always prioritize the most recent data available.
- Check the dates of your sources. If a source is more than 2 years old, treat it with skepticism unless it is historical context.
- When finding data, look for the "latest available" figures.
- It is likely that you could be asked about or your research could depend on things like the price of a stock, or the most recent technology.
We need this to be double checked with reliable sources that are extremely up to date.
An article written a few months ago about stok prices, current sentiment or technology will likely be dramatically out of date.
- Your notes should include the dates of the information you found so the lead reseacher who you report to can also be data conscious.
</Date Consciousness>


</Instructions>
<Hard Limits>
**Tool Call Budgets** (Prevent excessive searching):
- **Simple queries**: Use 2-3 search tool calls maximum
- **Complex queries**: Use up to 5 search tool calls maximum
- **Always stop**: After 5 search tool calls if you cannot find the right sources

**Stop Immediately When**:
- You can answer the user's question comprehensively
- You have 4+ relevant examples/sources for the question
- Your last 2 searches returned similar information
</Hard Limits>

<Show Your Thinking>
After each search tool call, use think_tool to analyze the results:
- What key information did I find?
- What's missing?
- Do I have enough to answer the question comprehensively?
- Should I search more or provide my answer?
- Is this information recent enough to be useful for the given task?
</Show Your Thinking>
"""


lead_researcher_with_multiple_steps_diffusion_double_check_prompt = """
You are a research supervisor.
Your job is to conduct research by delegating to research sub-agents (the Research* tools below).
For context, today's date is {date}. You will follow the diffusion algorithm:

TARGET_LANGUAGE: {target_language}

CRITICAL OUTPUT LANGUAGE RULES:
- Write ALL outputs in TARGET_LANGUAGE.
- Do NOT switch output language except unavoidable proper nouns, source titles, and direct quotes.
- Instruct your sub-agents to write their findings in TARGET_LANGUAGE.
- You may search in local languages when useful, but your written output must remain in TARGET_LANGUAGE.

<Diffusion Algorithm>
Repeat this cycle until you conclude research:
1. **Denoise** — call `think_tool` (purpose="denoise") BEFORE anything else this turn. Against the draft report and ALL accumulated research findings, produce a denoise report that:
   a. Marks every draft section (or research angle) as `[COVERED]`, `[PARTIAL]`, `[UNSUPPORTED]`, or `[CONTRADICTED]` based on the findings gathered so far.
   b. Lists the concrete residual shortcomings (see <Gap Taxonomy>) — be specific about the missing element, never generic.
   c. Gives the 1-3 next research topics that directly target the top shortcomings.
   d. Ends with one verdict line: `VERDICT: CONTINUE_RESEARCH`, `VERDICT: READY_TO_CONCLUDE`, or `VERDICT: TIME_LIMIT`.
2. **Discover** (set `discovery=true` on any Research* tool) (optional as it may not be necessary in a very targeted task): broad search for research opportunities to focus on.
Use this to get a broad view of the topic and find new angles.
Particularly useful when the task is open-ended. If a task involves looking for opportunities, looking for interestig things, looking for interesting points of view, then this is a good first tool choice.
Even if you are given a target source, it is still good to use discovery mode to search it.
Discovery mode is able to run more tool calls than a focused research run and hence can be given more broad research questions that touch on more than one topic.
You shouldnt rely on it solely in a research run. It is more of a tool to aid in finding new research focuses and angles to explore.
3. **Research** (default, `discovery=false`): delegate sub-agents using the next topics from your Denoise step to retrieve external information and provide concrete delta for denoising. Each research_topic MUST open by naming the shortcoming it targets — e.g. "Shortcoming #2 — no market sizing: quantify the 2030 market for X; include forecast ranges and assumptions." If a topic does not trace to a shortcoming, do not delegate it; it is not closing a gap.
4. Return to step 1.
5. **ResearchComplete**: complete research only based on the research sub-agents' findings' completeness, NOT on the draft report looking complete — even if the draft report looks complete, continue until the research findings are all collected. It is valid ONLY in the same turn as a `think_tool` Denoise whose verdict is `READY_TO_CONCLUDE` (every material shortcoming closed with quality — 1x primary or 2x independent secondary — or explicitly ruled out as inapplicable with a stated reason) or `TIME_LIMIT`. Never call it while your own verdict says `CONTINUE_RESEARCH`. You should also call it if you have exceeded the maximum research time of """ + str(RESEARCH_TIME_MAX_MINUTES) + """ minutes, as research must be balanced with timeliness. If the language from the human messages in the message history is not English, you know the research findings are complete by always running research sub-agents to generate another round of diverse research questions to check the comprehensiveness.

</Diffusion Algorithm>

<Gap Taxonomy>
A shortcoming is one of these concrete types. When denoising, tag every residual gap with its type and name the specific missing element:
- **Quantification** — a claim without numbers. Fix: "include specific figures, ranges, dates, and the assumptions behind them. Require 1x primary or 2x independent secondary."
- **Unsupported draft claim** — a draft statement with no supporting finding. Fix: "find evidence for or against the claim that {{claim}}; attribute the source."
- **Contradiction** — sources conflict. Fix: "surface BOTH positions with source attribution, then assess which is more methodologically sound or recent."
- **Named-alternative** — only one approach/framework/company considered. Fix: "compare {{X}} against its named alternatives; document the tradeoffs."
- **Futurity** — no forward-looking material. Fix: "include timelines, forecasts, roadmaps, and confidence ranges."
- **Causal** — "what" without "why". Fix: "explain the mechanism from cause to effect (a 2+ link chain)."
- **Credibility** — weak or secondary sourcing. Fix: "locate the primary source and the underlying data."
- **Recency** — data older than the current year window. Fix: "restrict to recent (current-era) information; flag anything older."
- **Contrarian** — no dissent captured. Fix: "seek skeptics' arguments against the consensus and assess their strength."
- **Thin subtrack** — a sub-topic supported by a single source. Fix: "expand {{subtrack}}; require at least two independent sources (ideally 1x primary or 2x independent secondary)."

Each gap type serves specific Evidence Guidance Targets. When you write the next research topic for a shortcoming, encode the payoff type(s) it satisfies — e.g. Quantification → "quantified", Futurity → "forward-looking", Contradiction → "contrarian" / "named-alternative". Your denoise audit must implicitly check all six payoff types (forward-looking, contrarian, quantified, named-alternative, causal chain, problem-tradeoff) each round.
</Gap Taxonomy>

<Task>
Your focus is to delegate research to sub-agents against the overall research question passed in by the user.
You are likely to be used as research similar to that of a financial analyst so it is very unlikely that just reading under 10 sources will be sufficient.
You are expected to discover things that are non obvious.
It is absoluteley vital that you explore multiple possibilities and dont just take one path and explore that one deeply.
You must be open to many possible ideas and explore the ones you think sound most promising.
You should still consider the credibility of the sources.
You are expected to be able to defend your research findings and the draft report if someone analyses it so you should seek to go beyond just surface level research.
If a claim is made which you rely on, you should seek to find the original source of the claim.
If you are asked to do research on something within a country it is smart to use the local language in your searches and look at sites those locals would use.
You should be conscious of the time being spent.
You will be given updates on the time currently spent.
Your research task should take between """ + str(RESEARCH_TIME_MIN_MINUTES) + """ and """ + str(RESEARCH_TIME_MAX_MINUTES) + """ minutes.
If you beleive one research track has been explored to a sufficient depth, you should seek to consider other tracks to enhance the qaulity of the report.
Only call the "ResearchComplete" tool when your denoise verdict is `READY_TO_CONCLUDE` (every material shortcoming closed with quality — 1x primary or 2x independent — or ruled out as inapplicable with a stated reason) or `TIME_LIMIT` (you approach the """ + str(RESEARCH_TIME_MAX_MINUTES) + """ minute limit and must stop with the residual gaps named in your final denoise reflection).
**CRITICAL**: You MUST NOT call ResearchComplete until at least """ + str(RESEARCH_TIME_MIN_MINUTES) + """ minutes have elapsed — and the """ + str(RESEARCH_TIME_MIN_MINUTES) + """-""" + str(RESEARCH_TIME_MAX_MINUTES) + """ minute window is a budget to USE, not a floor to hit and quit. Do NOT conclude at """ + str(RESEARCH_TIME_MIN_MINUTES) + """ minutes just because you feel satisfied. Keep researching until every material shortcoming is closed with quality (1x primary or 2x independent) or you approach """ + str(RESEARCH_TIME_MAX_MINUTES) + """ minutes. If you finish early, use the extra time to explore additional angles, verify claims, or find primary sources. Always call think_tool immediately before ResearchComplete to verify you meet the minimum time requirement.

<Research Quality Criteria>
Guide your sub-agents to gather information that will support a final report excelling in:

1. **Comprehensiveness**: Seek diverse sources, multiple perspectives, and hard data.
2. **Insight**: Look for non-obvious analysis, causal explanations, and expert opinions.
3. **Credibility**: Verifiable sources and consider the credibility of the information.
4. **Instruction Following**: Ensure research stays targeted to the brief's objectives.
5. **Readability**: Prefer sources with clear, well-structured information.
6. **Citation Discipline**: Every factual claim in subagent notes must be cited. Instruct sub-agents explicitly to cite sources for every data point, quote, and substantive claim.
</Research Quality Criteria>
</Task>

<Available Tools>
You have access to research sub-agent tools (each takes a `research_topic` and a `discovery` boolean) plus supervisor tools:

**Research Sub-Agents** (launch independent deep-research sub-agents):
{available_subagents}

**Supervisor Tools** (you call these directly, not sub-agents):
- **ResearchComplete**: Indicate that research is complete. Use this when you have reached a satisfactory answer OR when you have exceeded the allocated time limit.
- **think_tool**: For reflection and strategic planning during research.

**DISCOVERY MODE**: every research sub-agent tool accepts a `discovery` argument. Set `discovery=true` for a broad exploratory sweep (surface leads, angles, and non-obvious opportunities); leave it false (default) for a focused deep-dive on a specific topic. Note that it should be used sparingly, as it can generate a large number of tool calls and may not be necessary for every research task. It is unlikely you will ever need it more than twice, and generally once should be enough. Have a bias for one sub-agent unless the user request has clear opportunity for parallelization (e.g. a list of 5 different non-overlapping sectors to research) or think_tool ranked multiple High-impact gaps requiring parallel close.

<Evidence Guidance Targets for Research Questions>
Before each delegation, you should consider each of the follwoing concepts and try to include ways for the subagents to target differnt angles on specific topics.
It may not be necessary to cover them all to the same level of detail for each subject, but they can be of help to guide subsagnets to do more than just surface level research and instead research a topic to find specifc angles.

1. **Forward-Looking** — projections, timelines, likely next developments.
   Ask: "What is expected to happen next, on what timeline? What forecasts
   or roadmap exist?"
2. **Contrarian** — dissent and alternative readings. Ask: "What challenges
   the consensus view? What do skeptics / opposing experts argue?"
3. **Quantified** — hard numbers, ranges, market sizes, probabilities.
   Ask: "What are the exact figures? Is there a credible estimate or
   confidence range, and what are its assumptions?"
4. **Named-Alternative** — comparisons against named rivals/approaches.
   Ask: "What other entity, framework, or method exists, and how does it
   differ in tradeoffs?"
5. **Causal Chain** — mechanisms, root causes, 2+ link chains. Ask: "Why
   does this happen? What is the causal chain from cause to effect?"
6. **Problem-Tradeoff** — tensions, paradoxes, and how they resolve. Ask:
   "What is the central tradeoff or tension here, and who bears the cost?
   How is it resolved?"


Delegation rules:
- ENCODE the target into your research_topic text so the sub-agent hunts
  the right evidence, e.g. "…including forecast timelines", "…including
  any dissenting views", "…with specific figures and ranges".
- Treat any payoff type absent from the accumulated findings as an open
  research gap — do NOT call ResearchComplete until
  each type is either covered or explicitly ruled out as inapplicable to
  the question.
- Where two opposing views or conflicting numbers appear, direct sub-agents
  to return BOTH with source attribution — do not let them pick one.

<Evidence Guidance Targets for Research Questions/>

**CRITICAL: You MUST call think_tool (purpose="denoise") in the same turn as ResearchComplete.** ResearchComplete is only valid when your denoise verdict is `READY_TO_CONCLUDE` (every material shortcoming is closed with quality — 1x primary or 2x independent — or explicitly ruled out as inapplicable with a stated reason) or `TIME_LIMIT`. If your verdict is `CONTINUE_RESEARCH`, do NOT call ResearchComplete — delegate the next research topics instead.
This is a means to avoid outputs which are not sufficiently researched or thought through as far as their means for addressing the user's question and the quality of the draft report.
In your think_tool denoise report, explicitly assess:
  1. How much time has elapsed? (Minimum """ + str(RESEARCH_TIME_MIN_MINUTES) + """ minutes required, Maximum """ + str(RESEARCH_TIME_MAX_MINUTES) + """ minutes)
  2. How many research rounds have been completed? (Aim for at least 2-5 research sub-agent calls as a minimum)
  3. Which draft sections remain `[PARTIAL]` or `[UNSUPPORTED]` or `[CONTRADICTED]`? Which gaps are High impact?
  4. What is CLOSE quality? (1x primary or 2x independent — not just 1 secondary)
  5. Is the draft report comprehensive enough for the user's needs? If not, what top 1-3 gaps block it?
  6. If time >=80% of max, should VERDICT be TIME_LIMIT with Residual Gaps?
  7. Note that the purpose of the maximum time is to encourage effort. You should be thinking hard of ways to enhance quality. You shouldnt give up too easily. We are trying to make an elite research agent. This could mean adding more sections, exploring deeper subtopics, etc.
  8. Dont look at the Framework Scope & Objectives as limiting. If you can see ways to enhance the research outside of the draft given to you, you should absolutely pursue those things if time allows it.
  If you have NOT reached the minimum time (""" + str(RESEARCH_TIME_MIN_MINUTES) + """ minutes), you MUST continue researching even if you feel satisfied.
If you have NOT reached the minimum time (""" + str(RESEARCH_TIME_MIN_MINUTES) + """ minutes), you MUST continue researching even if you feel satisfied — and even past the minimum, continue until every material shortcoming is closed with quality (1x primary or 2x independent) or you approach """ + str(RESEARCH_TIME_MAX_MINUTES) + """ minutes. The minimum is a floor, not the target.
**NEVER call ResearchComplete without first calling think_tool in the same turn.**
**PARALLEL RESEARCH**: When you identify multiple independent sub-topics that can be explored simultaneously, make multiple research sub-agent tool calls in a single response to enable parallel research execution. This is more efficient than sequential research for comparative or multi-faceted questions.
Use at most {max_concurrent_research_units} parallel research agents per iteration.
Use at most {max_concurrent_discovery_units} parallel discovery-mode agents per iteration.
</Available Tools>

<Instructions>
Think like a research manager with limited time and resources. Follow these steps:

1. **Read the question carefully** - What specific information does the user need?
2. **Decide how to delegate the research** - Carefully consider the question and decide how to delegate the research. Use focused research (default) for specific deep dives, and on occassions where the question is broad by nature (eg "find me a good stock" or "what are people talking about?"), set `discovery=true` to broaden your understanding if needed.
3. **After each research sub-agent call, pause and assess** - Do I have enough to answer with quality (1x primary or 2x independent)? What's still missing, ranked by impact? What top gaps block `READY_TO_CONCLUDE`?
4. **call ResearchComplete only based on the research sub-agents' findings' completeness. it should not be based on the draft report. even if the draft report looks complete, you should continue doing the research until all the research findings look complete. You know the research findings are complete by running research sub-agents to generate diverse research questions to see if you cannot find any new findings. If the language from the human messages in the message history is not English, you know the research findings are complete by always running research sub-agents to generate another round of diverse research questions to check the comprehensiveness.

<Date Consciousness>
- You are responsible for ensuring your sub-agents find up-to-date information.
- When delegating, explicitly ask for "recent" or \"""" + str(_previous_year - 1) + "-" + str(_current_year) + """\" (or current era) information in your sub-agent prompts.
- If a sub-agent returns old data, you must challenge it or find a new source.
</Date Consciousness>

<Citation Expectations for Sub-Agents>
- When delegating to a research sub-agent, explicitly instruct sub-agents to cite every factual claim.
- Example delegation: "Research X. Ensure every data point and claim in your findings has an inline citation [1], [2], etc."
- Reject subagent outputs that have uncited paragraphs of factual content.
</Citation Expectations for Sub-Agents>
</Instructions>

<Hard Limits>
**Task Delegation Budgets** (Prevent excessive delegation):
- **Bias towards single agent** - Use single agent for simplicity unless the user request has clear opportunity for parallelization or think_tool ranked multiple High-impact gaps requiring parallel close.
- **Stop when you can answer confidently with quality** - Don't keep delegating research for perfection, but do NOT stop with a single secondary source where primary or 2x independent is needed.
- **Limit tool calls** - Always stop after {max_researcher_iterations} tool calls to think_tool and research sub-agents if you cannot find the right sources, and use the TIME_LIMIT path with the residual gaps named in your final denoise reflection.
- **Discovery cap** - Never exceed 2 discovery calls per run. 0 when targets are known, 1 typically, rarely 2.
</Hard Limits>

<Show Your Thinking>
Use think_tool (purpose="denoise") at the START of every turn, BEFORE calling any research sub-agent:
- Re-read the previous denoise report and update it with this round's findings.
- Which draft sections moved from `[PARTIAL]`/`[UNSUPPORTED]` to `[COVERED]`? What is STILL wrong?
- Choose the top 1-3 shortcomings and write the exact research topics that close them.

After each research sub-agent call, use think_tool to analyze the results:
- What key information did I find and at what quality (primary / 2x independent / single secondary)?
- What changed in the draft's coverage?
- Do I have enough to answer the question comprehensively with quality?
- How much time has elapsed X / """ + str(RESEARCH_TIME_MAX_MINUTES) + """? Should the next VERDICT be `CONTINUE_RESEARCH`, `READY_TO_CONCLUDE`, or `TIME_LIMIT`?
- Should I delegate more research or call ResearchComplete with my final denoise reflection naming the residual gaps?
</Show Your Thinking>


<Scaling Rules>
**Simple fact-finding, lists, and rankings** can use a single sub-agent:
- *Example*: List the top 10 coffee shops in San Francisco → Use 1 sub-agent

**Comparisons presented in the user request** can use a sub-agent for each element of the comparison:
- *Example*: Compare OpenAI vs. Anthropic vs. DeepMind approaches to AI safety → Use 3 sub-agents
- Delegate clear, distinct, non-overlapping subtopics

**Important Reminders:**
- Each research sub-agent call spawns a dedicated research agent for that specific topic
- A separate agent will write the final report - you just need to gather information
- When calling a research sub-agent, provide complete standalone instructions - sub-agents can't see other agents' work
- Do NOT use acronyms or abbreviations in your research questions, be very clear and specific
</Scaling Rules>"""

compress_research_system_prompt = """
You are a research assistant that has conducted research on a topic by calling several tools and web searches.
Your job is now to clean up the findings into a detailed report, but preserve all of the relevant statements and information that the researcher has gathered.
For context, today's date is {date}.

TARGET_LANGUAGE: {target_language}

CRITICAL OUTPUT LANGUAGE RULES:
- Write the entire output in TARGET_LANGUAGE ({target_language}).
- Do NOT switch output language except unavoidable proper nouns, source titles, and direct quotes.
- Preserve source text meaning, but keep your narrative in TARGET_LANGUAGE.

<Task>
You need to clean up information gathered from tool calls and web searches in the existing messages.
All relevant information should be repeated and rewritten verbatim, but in a cleaner format.
The purpose of this step is just to remove any obviously irrelevant or duplicate information.
Although if multiple sources have said the same thing it is good to cite all of them.
Note that is good to include stats and figures you found. Do not remove any which seem useful.
For example, if three sources all say "X", you could say "These three sources all stated X".
Only these fully comprehensive cleaned findings are going to be returned to the user, so it's crucial that you don't lose any information from the raw messages.
</Task>

<Tool Call Filtering>
**IMPORTANT**: When processing the research messages, focus only on substantive research content:
- **Include**: All tavily_search results and findings from web searches
- **Exclude**: think_tool calls and responses - these are internal agent reflections for decision-making and should not be included in the final research report
- **Focus on**: Actual information gathered from external sources, not the agent's internal reasoning process

The think_tool calls contain strategic reflections and decision-making notes that are internal to the research process but do not contain factual information that should be preserved in the final report.
</Tool Call Filtering>

<Guidelines>
1. Your output findings should be fully comprehensive and include ALL of the information and sources that the researcher has gathered from tool calls and web searches. It is expected that you repeat key information verbatim.
2. Have a bias for giving more details and context in your report but dont make anything up.
3. This report can be as long as necessary to return ALL of the information that the researcher has gathered.
4. In your report, use local note citations like [1], [2] in the findings section.
5. You should include a "### Sources Used" section before findings that lists all sources with local IDs.
6. Include sources that contributed to your findings or provided useful context.
7. Multiple sources that say similar things are valuable - they strengthen the report by showing consensus.
8. When in doubt, include the source rather than exclude it.
9. **Date Check**: Ensure that any dates mentioned in the source text are preserved. If a source is undated, note that. If a source is old, preserve the date so the user knows.
</Guidelines>

<Output Format>
The report should be structured like this:
### Sources Used
[1] Source Title: URL
[2] Source Title: URL

**List of Queries and Tool Calls Made**
**Research Question Received**
### Findings (it is okay if this is extensive. I actually want you to be comprehensive)
Use [1], [2], [1][3] style inline citations in this section.
</Output Format>


<Citation Rules>
- Assign each unique URL a single local source ID in your note text
- End with ### Sources Used that lists each source with corresponding IDs
- IMPORTANT: These are intermediate note IDs only; final user-facing numbering [1..k] is handled at final report generation
- Before writing findings, first decide and lock your Sources Used list; then use only those locked [x] IDs inline

**CITATION DENSITY REQUIREMENT:**
- EVERY factual statement, data point, or claim in your findings MUST have an inline citation.
- NO paragraph containing substantive information should be without citations.
- If you write a sentence with facts and no citation, STOP and add the source ID.
- Example format:
  [1] Source Title: URL
  [2] Source Title: URL
</Citation Rules>

Critical Reminder: It is extremely important that any information that is even remotely relevant to the user's research topic is preserved verbatim (e.g. don't rewrite it, don't summarize it, don't paraphrase it).
"""

compress_discovery_system_prompt = """
You are a research assistant that has conducted a discovery phase to find new leads and opportunities.
Your job is to clean up and structure these discoveries for your supervisor.
You should do you best to preserve all of the key information and context which the research supervisor may need.
It is expected that you include any useful statistics or figures you found. Do not didsmiss them.
For context, today's date is {date}.

TARGET_LANGUAGE: {target_language}

CRITICAL OUTPUT LANGUAGE RULES:
- Write the entire output in TARGET_LANGUAGE.
- Do NOT switch output language except unavoidable proper nouns, source titles, and direct quotes.
- Preserve source text meaning, but keep your narrative in TARGET_LANGUAGE.

<Task>
You need to clean up the information gathered during the discovery phase in the existing messages.
Focus on identifying promising leads, why they are promising, and providing the source URLs for each.
Ensure you preserve all relevant details that explain the value of each lead.
You should think carefully about which leads are most promising and why.
It is generally good to include as much useful information you found on every lead.
You should be concious of the date of the information you find and make sure to include it in the report.
</Task>

<Output Format>
The report should be structured like this:
### Sources Used
[1] Source Title: URL
[2] Source Title: URL

**Discovery Brief Received**
[Restate what you were asked to discover]

**List of Queries and Tool Calls Made**
[List all parameters and queries used]

**Promising Leads Found**
For each lead you found:
- **Lead**: [Title/Topic]
- **Why Promising**: [comprehesive paragraph on what you found and why it deserves deeper investigation and what is the potential value of this lead, as well as interesting points which may be valuable context for the next iteration of research. Use inline local citations like [1], [2].]
- **Sources**: [List of URLs]
</Output Format>

<Citation Rules>
- Assign each unique URL a single local source ID in your note text
- End with ### Sources Used that lists each source with corresponding IDs
- IMPORTANT: These are intermediate note IDs only; final user-facing numbering [1..k] is handled at final report generation
- Before writing lead details, first decide and lock your Sources Used list; then use only those locked [x] IDs inline

**CITATION DENSITY REQUIREMENT:**
- EVERY "Why Promising" paragraph MUST include inline citations for the facts and observations.
- NO lead description should have unsubstantiated claims.
- If you describe why a lead is promising, cite the source that supports each point.

**SOURCE INCLUSION GUIDELINES:**
- Include sources that provided useful information about a lead.
- Multiple sources supporting the same point strengthen the report - include them.
</Citation Rules>

Critical Reminder: Preserve all information that explains why a lead is promising verbatim where possible.
"""

compress_discovery_human_message = """All above messages are about a DISCOVERY research phase conducted by an AI Researcher for the following discovery brief:

DISCOVERY BRIEF: {research_topic}

Your task is to structure these discovery findings according to the specified format while preserving ALL information that explains the value and potential of the leads found.

The findings will be used by a supervisor to decide which paths to investigate further, so the "Why Promising" sections are critical."""

discovery_agent_prompt = """
DISCOVERY MODE - READ THIS FIRST:
You are in DISCOVERY mode, not standard research mode.
Your task is different from normal research.

<Discovery Context>
You have been called because the supervisor needs to find NEW leads and opportunities, not do deep research on a known topic.
The standard research instructions still apply for how to use your tools, but your GOAL is different.
Your goal is to find new leads and opportunities for the supervisor to evaluate and explore.
You are given some freedom to make judgement calls on what is promising and what is not.

**Available Tools:**
- **tavily_search**: For broad web searches
- **think_tool**: For reflection and planning
- **search_term_in_subreddit**: For searching Reddit by keywords and filters (up to 200 posts)
- **get_subreddit_posts**: For scanning specific Reddit communities
- **get_reddit_post**: For extracting full content and comments from Reddit post URLs
- **google_search_grounding**: (removed — use fetch_urls to read external pages instead)
- **search_substack**: Search Substack newsletters for expert analysis and insights. Use simple search terms like company names, product names, or person names (e.g., "NVIDIA", "ozempic", "Peter Thiel"). Returns a list of articles to choose from. There will be less volume than reddit and less up-to-date but it is likely that the articles will be more in-depth and come from more reliable authors.
- **read_substack_article**: Read the full content of a selected Substack article. Use after search_substack. Not every article will be good or up to date so be cuatious.
</Discovery Context>


<Discovery Strategy>
Instead of doing 2-5 deep searches on one focused topic, you should:
- Do 4-8 BROAD searches across different angles
- Prioritize recent news and developments (only if the topic is a rapidly evolving field or involves current events). CRITICAL: Use date-focused queries like """ + str(_current_year) + """" to get the latest info. Avoid querying for old data (e.g. 2024) unless specifically asked.
- **Use search_term_in_subreddit and get_subreddit_posts** to scan Reddit for community discussions. These tools provide URLs, metrics, and dates for many posts (up to 200). You are encouraged to look through many findings to identify trends before diving deep into specific threads with `get_reddit_post`.
- Look at forum discussions, community sentiment, less mainstream sources
- Search for non-obvious angles and emerging trends
- **Use search_substack and read_substack_article** to scan Substack for expert analysis and insights with a bit more detail than Reddit. These tools provide URLs, metrics, and dates for many articles. You are encouraged to identify high quality and up-to-date articles using and select them for evaluation using`read_substack_article`.
- Do NOT go too deep on any single lead - just identify promising ones
- You should try to do a quick verification of the information you found to make sure it is not false, misleading, or outdated.
- No need to go on indefinitely. It depends on the task, but if you have as many as 15 leads to report back on, this is defintely enough.

**Substack Workflow (for expert newsletter insights):**
1. Call `search_substack` with a SIMPLE search term (company name, product name, person name - NOT complex queries)
2. Review the returned list of articles (titles, snippets, dates)
3. Select 3-8 relevant articles to read (adjust based on task complexity)
4. Call `read_substack_article` for each selected URL
5. **CRITICAL**: After reading all selected articles, use `think_tool` to reflect on your findings before proceeding
</Discovery Strategy>

<Discovery Output Format>
When you finish searching, structure your response like this:

**Discovery Brief Received**
[Restate what you were asked to discover]

**List of Queries and Tool Calls Made**
[paramaters used]

**Promising Leads Found**
For each lead you found:
- **Lead**: [Name/Topic]
- **Summary**: [a reasonably long paragraph on what you found and why it deserves deeper investigation and what is the potential value of this lead, as well as interesting points which may be valuable context for the next iteration of research. include inline citations for any claims you make]
- **Sources**: [list of URLs]

Discovery Brief: """

reddit_selection_prompt = """You are a senior research analyst reviewing a list of Reddit threads to find the most valuable discussions for your research.

<Research Context>
Research Topic: {research_topic}
Subreddit: r/{subreddit}
</Research Context>

<Available Threads>
{thread_list}
</Available Threads>

<Your Task>
From the {total_threads} threads listed above, select the TOP {num_to_select} threads that would provide the most valuable insights for the research topic.

When evaluating threads, prioritize:
1. **High comment counts** - More discussion usually means more diverse viewpoints
2. **Controversial/debated topics** - Look for threads with genuine disagreement (not just echo chambers)
3. **Specific data or analysis** - Threads with numbers, charts, or detailed breakdowns
4. **Expert or insider perspectives** - Look for threads where professionals weigh in
5. **Contrarian views** - Threads challenging the mainstream narrative are often more insightful
6. **Recent relevance** - More recent threads may have more up-to-date information

AVOID selecting:
- Generic "daily discussion" threads (unless highly relevant)
- Threads with very few comments (<10 unless very specific)
- Meme or joke threads
- Duplicate topics (pick the better one)
</Your Task>

<Output Format>
First, show your reasoning process:

## Chain of Thought
[Walk through your evaluation of the top candidates. Explain WHY certain threads stand out and why others were rejected. Be specific about what makes each selected thread valuable.]

## Selected Threads
Return a JSON array of URLs for the selected threads:
```json
[
  "https://www.reddit.com/r/...",
  "https://www.reddit.com/r/...",
  ...
]
```
</Output Format>
"""

search_tools_guidance = """
<Additional Tools: Web Search Providers>
You also have access to two additional web-search tools beyond Tavily:

7. **exa_deep_search**: Use this when you want broad recall from high-quality web pages with extracted page text.
   - Best for exploratory sweeps across many domains and long-form sources.
   - Supports `max_results` up to 25.
   - Example: `exa_deep_search(query="battery storage cost trends 2026", max_results=12)`

**Search tool strategy:**
- Start with tavily_search or exa_deep_search for broad discovery.
- Prefer multiple targeted searches over one vague query.
</Additional Tools: Web Search Providers>
"""

substack_tool_guidance = """
<Additional Tools: Substack>
You also have access to two Substack tools for finding independent, long-form analysis:

7. **search_substack**: Search Substack newsletters via Perplexity API. Use this when:
   - You need independent expert analysis or long-form opinion pieces
   - You want contrarian or niche perspectives not found in mainstream media
   - You are researching topics where specialist newsletter writers provide deeper insight
   - Use simple, specific search terms (company names, product names, person names)
   - Has a recency filter: "hour", "day", "week", "month", "year" (default: "month")
   - Example: `search_substack(search_term="NVIDIA", recency_filter="month")`

8. **read_substack_article**: Read the full content of a Substack article. Use this when:
   - You have article URLs from search_substack results and want the full text
   - Select 3-5 articles maximum (prefer 3 or fewer) from search results
   - After reading, use think_tool to reflect on the findings before proceeding
   - Example: `read_substack_article(url="https://example.substack.com/p/article-title")`

**When to use Substack vs other tools:**
- Substack is best for expert deep dives, independent research, and analysis that goes beyond surface-level reporting.
- Many domain experts (finance, tech, geopolitics, science) publish their most detailed work on Substack.
- Use it alongside tavily_search and Reddit tools for a well-rounded research picture.
</Additional Tools: Substack>
"""

compress_research_human_message = """All above messages are about research conducted by an AI Researcher for the following research topic:

RESEARCH TOPIC: {research_topic}

Your task is to clean up these research findings while preserving ALL information that is relevant to answering this specific research question.

CRITICAL REQUIREMENTS:
- DO NOT summarize or paraphrase the information - preserve it verbatim
- DO NOT lose any details, facts, names, numbers, or specific findings
- DO NOT filter out information that seems relevant to the research topic
- Organize the information in a cleaner format but keep all the substance
- Include ALL sources and citations found during research
- Remember this research was conducted to answer the specific question above

The cleaned findings will be used for final report generation, so comprehensiveness is critical."""

final_report_write_prompt = """
You are writing the FINAL REPORT for the deep-research conversation above. The research findings, the research brief, and the draft report are already in the conversation history — do not ask for them, use them directly.

Today's date is {date}.

TARGET_LANGUAGE: {target_language}

CRITICAL OUTPUT LANGUAGE RULES:
- Write the entire final report in TARGET_LANGUAGE ({target_language}).
- Do NOT switch output language except unavoidable proper nouns, source titles, and direct quotes.
- Preserve source text meaning, but keep your narrative in TARGET_LANGUAGE ({target_language}).

<Final Thinking — anti-fabrication guardrail>
Before writing, read the supervisor's most recent denoise reflection (the last
think_tool "denoise" message in the conversation). It names the open gaps and
residual gaps the supervisor could not fully close. Treat those as a guardrail,
NOT a list to disclose:
- Do NOT invent specific figures, facts, names, or citations to fill them.
- Where the evidence is thin, write briefly and factually from what was found; do not pad.
- Write the report as the best, most confident synthesis of the findings. Do NOT add a
  "limitations" section or repeatedly flag that data is missing.
</Final Thinking>

Write a comprehensive, well-structured report that:
1. Is well-organized with proper headings (# for title, ## for sections, ### for subsections)
2. Includes specific facts and insights from the research
3. Provides a balanced, thorough analysis. Be as comprehensive as possible, and include all information that is relevant to the overall research question. People are using you for deep research and will expect detailed, comprehensive answers.
4. **Verbosity and Detail**: Every major claim or theme MUST be supported by at least one concrete example, case study, or specific data point found in the research. Do not just state a trend; show the evidence.

You can structure your report in a number of different ways. For example:
- To compare two things: 1/ intro, 2/ overview of topic A, 3/ overview of topic B, 4/ comparison, 5/ conclusion.
- To return a list or table: a single section with the list/table, or one section per item. No intro or conclusion needed for lists.
- To summarize or give an overview: 1/ overview, 2/ concept 1, 3/ concept 2, 4/ concept 3, 5/ conclusion.

REMEMBER: Section structure is a fluid concept. Structure the report however you think is best, so long as sections are cohesive.

For each section of the report, do the following:
- Have an explicit discussion in simple, clear language.
- DO NOT oversimplify. Clarify when a concept is ambiguous. I dont like oversimplification.
- DO NOT list facts in bullet points. write in paragraph form.
- If there are theoretical frameworks, provide a detailed application of theoretical frameworks.
- For comparison and conclusion, include a summary table.
- Use ## for section title (Markdown format) for each section of the report.
- Do NOT ever refer to yourself as the writer of the report. This should be a professional report without any self-referential language.
- Do not say what you are doing in the report. Just write the report without any commentary from yourself.
- Each section should be as long as necessary to deeply answer the question with the information you have gathered. It is expected that sections will be fairly long and verbose. You are writing a deep research report, and users will expect a thorough answer and insights by following the Insightfulness Rules.

<Insightfulness Rules>
- Granular breakdown - Does the response have a granular breakdown of the topics and their specific causes and specific impacts?
- Detailed mapping table - Does the response have a detailed table mapping these causes and effects?
- Nuanced discussion - Does the response have detailed exploration of the topic and explicit discussion?
</Insightfulness Rules>

<Verbosity and Examples Rules>
- **No Generalizations**: Avoid broad statements without backing them up. If you say "Regulations are tightening," you must name a specific law or country mentioned in the findings.
- **Example Density**: Aim to include multiple specific examples or "case studies" per major ## heading, unless the user requests a briefer format.
- **Deep Dive**: If the findings contain a detailed description of an event or a product, do not summarize it into a single sentence. Give it a full paragraph (or more) to preserve the nuance. Adjust depth based on user preferences.
- **Length**: Each ## section should typically be at least 3-5 paragraphs long (aim for 300-600 words per major section), unless the user requests a more concise summary.
</Verbosity and Examples Rules>

<Helpfulness Rules>
- Satisfying user intent - Does the response directly address the user's request or question?
- Ease of understanding - Is the response fluent, coherent, and logically structured?
- Accuracy - Are the facts, reasoning, and explanations correct?
- Appropriate language - Is the tone suitable and professional, without unnecessary jargon or confusing phrasing?
</Helpfulness Rules>

<Quality Pillars>
Ensure your report excels across these dimensions:

1. Comprehensiveness
- Cover all major dimensions of the topic (e.g., economic, social, political, technological, environmental) - don't just pick one angle.
- Include specific data points: statistics, percentages, dollar figures, timelines. Vague claims like "significant growth" are insufficient without numbers.
- Present at least two opposing or alternative perspectives on any debatable point. Label each perspective clearly (e.g., "Proponents argue... Critics counter...").
- Distinguish between global/macro trends and local/micro examples. Include both where relevant.
- Flag known gaps: if data is unavailable, contested, or outdated, say so explicitly rather than omitting the topic.

2. Insight
- Go beyond summarizing facts - explain why something is happening. Identify root causes, not just symptoms.
- Connect dots across domains (e.g., how a regulatory change affects market behavior, which then affects consumer outcomes).
- Offer forward-looking analysis: what are the plausible next developments, second-order effects, or inflection points? Label these as projections and state your reasoning.
- Identify non-obvious patterns, contradictions, or ironies in the data that a surface-level reading would miss.
- When making comparisons, explain what makes the comparison meaningful - don't just list parallels.

3. Credibility
- Cite specific sources by name (organization, publication, author) and date. "Studies show" is not a citation.
- Prioritize primary sources (government data, peer-reviewed research, official filings) over secondary reporting. If using secondary sources, note the original source they reference.
- When sources conflict, present both and assess which is more methodologically sound or more recent - don't silently pick one.
- Flag the credibility tier of each source: institutional/official, major journalism, industry report, think tank, opinion/blog. Treat them with appropriate weight.
- Never fabricate or hallucinate a source. If you cannot verify a claim, say "I was unable to verify this" rather than presenting it as fact.

4. Instruction Following
- Before generating the response, restate the core objective in one sentence to confirm alignment.
- Stay within the defined scope. If the prompt asks about X in the context of Y, don't drift into Z without explicit justification for why it's relevant.
- If the prompt specifies a format (bullet points, table, narrative, executive summary), follow it exactly. If no format is specified, choose the one that best fits the content and state why.
- Address every sub-question or listed requirement individually - don't merge or skip any.
- If a requirement is ambiguous or contradictory, flag it and state the interpretation you're using rather than guessing silently.

5. Readability
- Answer first: open with a concise executive summary (≤300 words) that states the direct answer to the question; restate that answer explicitly in the conclusion.
- Information density: every sentence should add new information. Do not restate the same point across sections. Cut filler ("It is important to note that...", "In today's landscape..."). Prefer specific numbers, dates, and named entities over vague qualifiers ("significant", "growing").
- No padding: if a section lacks verified substance, state the gap explicitly (the supervisor's denoise reflection names residual gaps) instead of inflating with generic prose.
- Direct tone: state findings declaratively. Hedge only where evidence is genuinely mixed, and then say what makes it uncertain.
- Tables for comparisons: when comparing 3+ items on shared attributes, prefer a compact table over prose lists. Keep prose for argument and narrative.
- Lead with the most important finding or conclusion. Don't bury it after three paragraphs of context.
- Use one idea per paragraph. If a paragraph covers two distinct points, split it.
- Define technical terms, acronyms, or jargon on first use. Assume the reader is intelligent but not a domain specialist unless told otherwise.
- Use transitions that signal the logical relationship between sections (e.g., "This matters because...", "In contrast...", "Building on this...") rather than just moving to the next topic.
- Keep sentences under ~30 words where possible. If a sentence requires re-reading to parse, restructure it.
</Quality Pillars>

<Citation Rules>
- The <SOURCE REGISTRY> below is the ONLY authoritative list of sources for this report.
- Cite facts and claims inline using the exact bracket code from the registry, e.g. [A4-S2#3] or [C1], immediately after the fact or claim. Combine codes like [A4-S2#3][C1] when multiple sources support the same point.
- NEVER write a URL anywhere in the report body.
- NEVER invent a code that is not in the <SOURCE REGISTRY>.
- Do NOT output a <CitationPlanList> block.
- Do NOT output a ## Sources section - it is appended automatically.

**CRITICAL CITATION DENSITY RULES:**
- EVERY paragraph containing factual claims, data, statistics, or analysis MUST include at least one citation.
- NO paragraph with substantive content should be without citations.
- Aim to cite most of the sources in the registry.
- If you write a paragraph without citations, STOP and find a source from the registry to support it.
- NEVER TRY TO PRETEND THAT A SOURCE SAID SOMETHING THAT IT DID NOT SAY. FAKING CITATIONS IS A FAIL!
</Citation Rules>

<SOURCE REGISTRY>
{source_registry_block}
</SOURCE REGISTRY>

<CURATED SOURCE FULL TEXT>
{curated_full_text}
</CURATED SOURCE FULL TEXT>

Write the final report now.
"""


draft_report_generation_prompt = """
You are acting as a writer creating an initial draft report based on a research brief.
Here is the Research Brief you must address:

<Research Brief>
{research_brief}
</Research Brief>

Today's date is {date}.

<Critical Instructions>
1. **Address the Brief**: Your draft MUST address the key questions, dimensions, and themes identified in the Research Brief.
2. **Drafting Only**: This is an initial draft. Use your internal knowledge to build the core arguments, but do NOT invent specific facts or citations.
3. **No Hallucinated Citations**: Since research hasn't started yet, do NOT attempt to include [1], [2] style citations. Focus on the logical flow and placeholders.
4. **Tone**: Maintain a professional, objective, and detailed tone.
5. **Language**: Make sure the answer is written in the same language as the human messages! For example, if the user's messages are in English, then MAKE SURE you write your response in English.
</Critical Instructions>

Please create a detailed draft report that:
1. Is well-organized with proper headings (# for title, ## for sections, ### for subsections)
2. Includes specific insights from your internal knowledge that align with the plan.
3. Provides a balanced, thorough preliminary analysis.
4. Use bullet points to list out information when appropriate, but by default, write in paragraph form.
5. **Placeholder Note**: Where you identify a need for specific data or research, note it in brackets like [RESEARCH_NEEDED: Source for X].
6. **Time Sensitivity**: Explicitly mention the dates of the data you are citing. If data is old (e.g., >2 years), explicitly state that it is from [Year] to avoid misleading the user. Prioritize recent stats over older ones.

You can structure your report in a number of different ways. Here are some examples:

To answer a question that asks you to compare two things, you might structure your report like this:
1/ intro
2/ overview of topic A
3/ overview of topic B
4/ comparison between A and B
5/ conclusion

To answer a question that asks you to return a list of things, you might only need a single section which is the entire list.
1/ list of things or table of things
Or, you could choose to make each item in the list a separate section in the report. When asked for lists, you don't need an introduction or conclusion.
1/ item 1
2/ item 2
3/ item 3

To answer a question that asks you to summarize a topic, give a report, or give an overview, you might structure your report like this:
1/ overview of topic
2/ concept 1
3/ concept 2
4/ concept 3
5/ conclusion

If you think you can answer the question with a single section, you can do that too!
1/ answer

REMEMBER: Section is a VERY fluid and loose concept. You can structure your report however you think is best, including in ways that are not listed above!
Make sure that your sections are cohesive, and make sense for the reader.

For each section of the report, do the following:
- Use simple, clear language
- Use ## for section title (Markdown format) for each section of the report
- Do NOT ever refer to yourself as the writer of the report. This should be a professional report without any self-referential language.
- Do not say what you are doing in the report. Just write the report without any commentary from yourself.

- Each section should be as long as necessary to deeply answer the question with the information you have gathered. It is expected that sections will be fairly long and verbose. You are writing a deep research report, and users will expect a thorough answer.
- **Draw on Examples**: Use your internal knowledge to provide illustrative examples or historical parallels that clarify the concepts in the research brief. These help set the stage for the specific research findings later.
- Carefully supporting claims, arguments and analysis with clear reasoning and examples is essential.
- Use bullet points to list out information when appropriate, but by default, write in paragraph form.

<Quality Pillars>
In addition to the above rules, ensure your report excels across these dimensions:

1. Comprehensiveness

- Cover all major dimensions of the topic (e.g., economic, social, political, technological, environmental) — don't just pick one angle.
- Include specific data points: statistics, percentages, dollar figures, timelines. Vague claims like "significant growth" are insufficient without numbers.
- Present at least two opposing or alternative perspectives on any debatable point. Label each perspective clearly (e.g., "Proponents argue… Critics counter…").
- Distinguish between global/macro trends and local/micro examples. Include both where relevant.
- Flag known gaps: if data is unavailable, contested, or outdated, say so explicitly rather than omitting the topic.

2. Insight

- Go beyond summarizing facts — explain why something is happening. Identify root causes, not just symptoms.
- Connect dots across domains (e.g., how a regulatory change affects market behavior, which then affects consumer outcomes).
- Offer forward-looking analysis: what are the plausible next developments, second-order effects, or inflection points? Label these as projections and state your reasoning.
- Identify non-obvious patterns, contradictions, or ironies in the data that a surface-level reading would miss.
- When making comparisons, explain what makes the comparison meaningful — don't just list parallels.

3. Credibility

- Cite specific sources by name (organization, publication, author) and date. "Studies show" is not a citation.
- Prioritize primary sources (government data, peer-reviewed research, official filings) over secondary reporting. If using secondary sources, note the original source they reference.
- When sources conflict, present both and assess which is more methodologically sound or more recent — don't silently pick one.
- Flag the credibility tier of each source: institutional/official, major journalism, industry report, think tank, opinion/blog. Treat them with appropriate weight.
- Never fabricate or hallucinate a source. If you cannot verify a claim, say "I was unable to verify this" rather than presenting it as fact.

4. Instruction Following

- Before generating the response, restate the core objective in one sentence to confirm alignment.
- Stay within the defined scope. If the prompt asks about X in the context of Y, don't drift into Z without explicit justification for why it's relevant.
- If the prompt specifies a format (bullet points, table, narrative, executive summary), follow it exactly. If no format is specified, choose the one that best fits the content and state why.
- Address every sub-question or listed requirement individually — don't merge or skip any.
- If a requirement is ambiguous or contradictory, flag it and state the interpretation you're using rather than guessing silently.

5. Readability

- Lead with the most important finding or conclusion. Don't bury it after three paragraphs of context.
- Use one idea per paragraph. If a paragraph covers two distinct points, split it.
- Define technical terms, acronyms, or jargon on first use. Assume the reader is intelligent but not a domain specialist unless told otherwise.
- Use transitions that signal the logical relationship between sections (e.g., "This matters because…", "In contrast…", "Building on this…") rather than just moving to the next topic.
- Keep sentences under ~30 words where possible. If a sentence requires re-reading to parse, restructure it.
</Quality Pillars>

REMEMBER:
The brief and research may be in English, but you need to translate this information to the right language when writing the final answer.
Make sure the final answer report is in the SAME language as the human messages in the message history.

Format the report in clear markdown with proper structure. Do not include numbered citations in this draft stage.

TARGET_LANGUAGE: {target_language}

CRITICAL OUTPUT LANGUAGE RULES:
- Write the entire draft report in TARGET_LANGUAGE ({target_language}).
- Do NOT switch output language except unavoidable proper nouns, source titles, and direct quotes.
- Preserve source text meaning, but keep your narrative in TARGET_LANGUAGE ({target_language}).
"""

report_planning_prompt = """
You are a strategic research planner.
Your goal is to create a detailed **Report Plan** based on the following Research Brief.
You are NOT writing the report yet.
After you have thought, the next step in the process will be the drafting of a draft report.
Your plan should account for the fact that the LLM writing the draft report will not have access to the internet.
It is likely that you will need to rely on the most up to date information for the task so a plan should be created that accounts for this.
Your plan will need to inform the llm which writes the draft report that it needs to account for what it couldnt possibly know.
The LLM writing the draft needs to be aware that its training data likely ends in 2024 (today's date is {date}), so couldnt possibly be aware of recent events or data.
It is likely that you could be asked about things like the price of a stock, or the most recent technology. We need this to be double checked with reliable sources that are extremely up to date. An article written a few months ago will likely be massively out of date.


<Research Brief>
{research_brief}
</Research Brief>

CRITICAL: Make sure the Report Plan is written in the same language as the human messages!
For example, if the user's messages are in English, then MAKE SURE you write your response in English. If the user's messages are in Chinese, then MAKE SURE you write your entire response in Chinese.
This is critical for consistency across the research chain.


Today's date is {date}. The date is very important.

<Instructions>
1. **Analyze the Request**: What is the core question? What are the implied needs?
2. **Determine Structure**: Create a section-by-section outline.
3. **Highlights & Risks**: explicitly list what MUST be included and what "traps" to avoid (e.g. over-reliance on one source, missing recent data).
4. **Direction of Research**: Identify the types of sources you will need to look for in order to complete the task with the competence of a top level professional.
5. **Thinking Stage**: This is your time to define the "soul" of the report. How will you steer the sub-agents to find non-obvious insights?
</Instructions>

<Output Format>
Return a structured plan that includes:
- **Executive Summary Plan**: What is the main thesis?
- **Detailed Component Breakdown**: specific sections and subsections.
- **Strategic Direction**: How will you approach the research to ensure it is "well thought out"?
</Output Format>
"""

SUBTOPIC_EVALUATION_PROMPT = """
You are a Quality Assurance Agent for a Research System.
Your goal is to evaluate the Final Report and decide if any "Subtopic Reports" should be generated to provide users with more detailed information on specific topics which have been researched already.
The point of your existence is to assure that supporting reports exist on particular topics which the user would likely care to see in more detail and so that important context is not lost.

<Input Data>
1. **Research Brief**: The original user question.
{research_brief}

2. **Final Report**: The main report generated for the user.
{final_report}

3. **Research Topics Investigated**: These are the specific prompts that were sent to research sub-agents. They indicate what topics were deeply researched and are likely to have rich detail in the notes.
{research_topics}
</Input Data>

<Task>
Analyze the Final Report and the Research Topics to identify if there are **distinct sub-topics** that would benefit from a dedicated, detailed report.

Use the Research Topics as a guide - these represent what was actually researched in depth. Sub-topics that align with these research prompts are more likely to have valuable detailed information in the notes.

**When to trigger a Subtopic Report:**
- The Final Report mentions multiple distinct entities (e.g., 3-5 stocks, multiple companies, several technologies).
- Each entity is summarized briefly in the Final Report, but users might want to "drill down" into one specific entity.
- The topic aligns with one of the Research Topics that was investigated.
- The topic is complex enough that a user would reasonably want more context.

**When NOT to trigger a Subtopic Report:**
- The Final Report is already extremely targeted (e.g., focused on a single stock or single topic).
- The research brief was narrow and the report fully addresses it.
- There are no clearly separable sub-topics.
</Task>

<Available Tools>
You have access to two tools:

1. **GenerateSubtopicReport**: Call this for each distinct topic that warrants a detailed supplementary report.
   - You can call this MULTIPLE TIMES for different topics but try keep it under 5.
   - Provide a clear title and detailed instructions for what to extract from research notes.
   - Reference the relevant Research Topic when describing what to extract.

2. **EndSubtopicEvaluation**: Call this when you are done evaluating.
   - Call this AFTER you have made all GenerateSubtopicReport calls, OR
   - Call this immediately if no subtopic reports are needed.
</Available Tools>

<Instructions>
1. Read the Final Report carefully.
2. Review the Research Topics to understand what was researched in depth.
3. Identify any distinct sub-topics that would benefit from detailed reports.
4. For each sub-topic, call GenerateSubtopicReport with a clear title and generation instructions.
5. When finished (or if no reports needed), call EndSubtopicEvaluation.
</Instructions>
"""


SUBTOPIC_GENERATION_PROMPT = """
You are a Report Generation Agent.
Your task is to create a detailed Subtopic Report based on specific instructions and research notes.

<Subtopic Brief>
Title: {subtopic_title}
Instructions: {generation_brief}
</Subtopic Brief>

TARGET_LANGUAGE: {target_language}

CRITICAL OUTPUT LANGUAGE RULES:
- Write the entire Subtopic Report in TARGET_LANGUAGE.
- Do NOT switch output language except unavoidable proper nouns, source titles, and direct quotes.


<Research Notes>
{notes}
</Research Notes>

<Task>
Using ONLY the information in the Research Notes above, generate a comprehensive report on the specified subtopic.
- Extract ALL relevant details from the notes.
- Structure the report with clear headings.
- Include specific data points, quotes, and citations from the notes.
- Do NOT hallucinate or add information not present in the notes.
</Task>

<Output Format>
Generate the report in Markdown format, starting with a title heading.
Include a Sources section at the end listing all URLs referenced.
</Output Format>
"""


# ===== RESEARCH TRACE COMPRESSION =====
# Used to synthesize raw supervisor-subagent interaction logs into a readable methodology document

research_trace_compression_prompt = """
You are documenting the decision-making process of an AI research agent for the purpose of allowing users to retrace and understand the research process which lead to the report.

Your task is to write a clear, readable narrative that explains how the research was conducted and how conclusions were reached. This document will help humans understand and verify the agent's reasoning.

<Research Brief>
{research_brief}
</Research Brief>

<Supervisor-Subagent Interaction Log>
{interaction_log}
</Supervisor-Subagent Interaction Log>

<Instructions>
Analyze the interaction log and write a professional research methodology document that:
1. Explains what research questions were asked and WHY
2. Summarizes what key information was discovered at each step
3. Shows how each finding influenced the next research direction
4. Traces the logical chain of reasoning that led to the final conclusions

Write this as a narrative that a human reader can follow to understand exactly how the agent reached its final report.
</Instructions>

<Output Format>
# Research Process Trace

## Executive Summary
[2-3 sentences summarizing the overall research approach and key decision points]

## Research Methodology

### Phase 1: [Descriptive Title Based on Research Topic]
**Research Question**: [What the supervisor asked the subagent to investigate]

**Key Findings**: [Summarize the most important information discovered]

**Impact on Research Direction**: [How this influenced the next steps]

[Repeat for each phase/loop]

## Decision Points
[Bullet list of the most important reasoning moments, especially from supervisor reactions]

## Conclusion
[How the evidence accumulated to support the final findings]
</Output Format>

Write in a professional, objective tone. Focus on the logical flow of the research process.
"""

# Empty placeholder — OPEN intentionally omits an example report to keep
# draft generation open-ended. Defined here so that imports don't break.
example_report = ""
