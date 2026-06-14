WEEK2_Research_agent

I built a Perplexity-style research agent that runs entirely in the terminal using a Textual TUI. The user types a research question, and the agent autonomously searches the web, reads pages, and finds academic papers before synthesising a cited answer.
1. The user's message plus the full conversation history is sent to the model along with four tool schemas.
2. The model responds with a final answer.
3. If tools are requested, the dispatcher routes each tool call to the correct Python function, which actually runs the search or fetch.
4. The results are appended to the message list.
5. The model now sees the tool results and decides what to do next — call more tools, or synthesise a final answer.
6. The loop is capped at 10 iterations to prevent runaway loops.


The most important design decision I made was limiting each web_fetch call to 4,000 characters (roughly 3,000 tokens).
  By truncating to 4,000 characters per fetch, I can safely fetch 3–4 pages per query while keeping the total usage under 20K tokens. I chose to truncate at the start of the content rather than summarising it, because trafilatura already strips nav/ads/footers, so the first 4,000 characters of the extracted text are usually the most relevant part of an article.
