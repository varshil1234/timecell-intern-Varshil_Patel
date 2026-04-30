

## Overview
This is my submission for TimeCell Assignment.

---

## Task 1: Risk Engine (Deterministic Math)

**Objective:** Build a stress-test calculator for multi-asset portfolios.

### How I Built It
- **Correctness & Edge Cases:** The math holds up even when things get weird. It handles `0%` allocations without complaining, it won't throw a `ZeroDivisionError` if the portfolio is 100% cash, and it processes negative expected returns cleanly.
- **Code Clarity:** Kept it functional and strictly typed. No spaghetti, just clean inputs and outputs. 

### 💡 Where I had to get creative: The "Infinite" Runway
I ran into an interesting problem: what happens if the portfolio's passive yield is higher than the monthly burn rate? Or if the portfolio is entirely cash with no expected crash? The math tries to calculate a runway, but technically, the runway is infinite. 

Instead of letting the code throw an error or return a massive garbage number, I explicitly return `float('inf')`. This is way cleaner for downstream systems (like the AI in Task 3) to parse and explain to a user.

### AI Usage Note
I used Gemini for this project. I mostly used it to quickly scaffold out the boilerplate stuff (like setting up the initial dictionaries and doing the standard Python type-hinting). This saved me a lot of typing and let me spend my actual brainpower on getting the core risk math right.

---

## Task 2: Live Data Pipeline (Asynchronous Concurrency)

**Objective:** Fetch live market data concurrently without blocking the terminal.

### How I Built It
- **Working Fetch:** I used `yfinance` to grab the data, but I pushed the blocking network calls into background worker threads using `asyncio.to_thread`. This means whether you are fetching 5 assets or 500, it all happens at the same time (O(1) time complexity relative to the asset count).
- **Error Handling:** I designed this so it literally can't crash the main loop. If an asset is delisted or the API 404s, that specific thread swallows the exception, returns a clean error dict, and the UI prints `FETCH FAILED` for that row while keeping the rest of the table intact.

### ⚠️ The Headache: Global Thread Contention
I ran into a massive wall here. `yfinance` is super chatty and prints a bunch of warning messages directly to the terminal, which was ruining my clean UI table. 

At first, I tried to mute it using `contextlib.redirect_stdout` inside the worker threads. **This immediately caused a catastrophic crash (`ValueError: I/O operation on closed file`).**

**The Fix:** I realized `sys.stdout` is a global resource in Python. Multiple threads trying to redirect the global terminal output to a black hole at the exact same time was creating a massive race condition. I fixed it by ripping out the context managers and simply disabling the `yfinance` logger globally *before* any threads even booted up. 

## Task 3: AI-Powered Portfolio Explainer

**Objective:** Generate a plain-English risk explanation using an LLM.

### How I Built It
- **Prompt Quality:** I set up a strict Persona, injected a dynamic `tone` variable, and gave it hard rules (like "Do not invent math").
- **Code Structure:** Separated into three clean phases: Prompt building, API network call, and a dedicated `@staticmethod` for parsing the output. 

### 💡 Where I had to get creative: Neuro-Symbolic AI
The biggest mistake you can make with LLMs is asking them to do math—they hallucinate. 

To fix this, I imported the `compute_risk_metrics` function from Task 1 directly into Task 3. My Python backend calculates the exact runway and post-crash values, and then I inject those hard, deterministic facts into the LLM prompt. The AI acts purely as a translator, not a calculator.

I also used **Pydantic Structured Outputs** (`response_schema`). I didn't trust the LLM to just return a raw JSON string. Pydantic acts as a strict bouncer, forcing the Gemini model to return the exact schema I defined. If it messes up, my `parse_llm_response` method catches the `ValidationError`.

### The Bonus Features
1. **Configurable Tone:** You can pass `beginner`, `experienced`, or `expert` into the engine, and it completely shifts the vocabulary of the prompt.
2. **LLM-on-LLM Critique:** I built a second `CIO Critique Agent`. After the first agent writes the draft, the CIO agent reads it, compares it against the raw math, and grades it.
3. **Exponential Backoff (Rate Limiting):** Because free-tier APIs throw 503 (Server Overloaded) and 429 (Rate Limit) errors constantly, I built a retry loop with exponential backoff. If the API drops, the code waits a few seconds and tries again rather than crashing the application.

---

## Task 4:Triangular Arbitrage Engine

**Objective:** Build something interesting that demonstrates initiative and how I think about the wealth management problem space.

### What I Built
I built a real-time **Triangular Arbitrage Engine** using graph theory (specifically a modified Bellman-Ford algorithm) to hunt for multi-hop, risk-free yield loops across financial assets.

### Why I Built It & How I Approached It

1.When tasked with building a financial tool, the obvious route is a simple price tracker or a 2-exchange comparison script (e.g., checking BTC on Coinbase vs. Binance). I wanted to build something that required actual computer science fundamentals. 
I treated the market as a **Directed Graph**. By taking the negative natural logarithm (`-log(price)`) of exchange rates, I transformed a multiplicative financial problem into an additive shortest-path problem. The engine doesn't just look at two assets; it scans the entire interconnected market matrix for Negative Weight Cycles—which represent literal mathematical profit loops.


2.Traditional wealth management (like Task 1 and 3) is largely defensive—tracking burn rates and stress-testing crashes. But family offices and quant funds are also obsessed with active, risk-free yield (Alpha). While High-Frequency Trading (HFT) bots usually close real-world arbitrage gaps in milliseconds, building the *architecture* for this proves I understand the mathematical plumbing required for high-performance quantitative trading pipelines.


3.The script doesn't just do theory. It uses `asyncio` to fetch live data from `yfinance` in parallel. 
However, because real markets are brutally efficient, it's rare to catch a live 5% arbitrage gap while just running a CLI script. To prove the algorithm's execution actually works, I engineered an `ENABLE_SYNTHETIC_INEFFICIENCY` toggle. When set to `True`, the script injects a fake pricing error into the live data stream. You can watch the Bellman-Ford algorithm successfully detect the anomaly, backtrack through the predecessor array to isolate the exact trade route, filter out duplicate loops, and print a ranked profitability leaderboard. 

---

### Final Thoughts
This assessment was a lot of fun.
