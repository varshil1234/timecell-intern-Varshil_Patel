import os
import json
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

# Importing our deterministic math engine from Task 1
from task_1 import compute_risk_metrics 

# =========================================================
# 1. STRUCTURED OUTPUT SCHEMA (PYDANTIC)
# =========================================================
class PortfolioAnalysis(BaseModel):
    summary: str = Field(description="A 3-4 sentence plain English summary of the risk level. Must explicitly mention the runway_months.")
    doing_well: str = Field(description="One specific thing the investor is doing right.")
    needs_change: str = Field(description="One specific thing to change and the reason why.")
    verdict: str = Field(description="Must be exactly one of: 'Aggressive', 'Balanced', or 'Conservative'")


class PortfolioExplainer:
    def __init__(self):
        load_dotenv()
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("API Key missing. Please set the GEMINI_API_KEY in your .env file.")
        
        # Explicitly pass the key to avoid system environment variable conflicts
        self.client = genai.Client(api_key=api_key)

    # =========================================================
    # 2. OUTPUT PARSER (SEPARATED LOGIC)
    # =========================================================
    @staticmethod
    def parse_llm_response(raw_text: str) -> dict:
        """
        Safely parses and validates the LLM JSON output. 
        Instead of a blind json.loads(), this forces the string through 
        Pydantic's strict type-checking to guarantee structural integrity.
        """
        try:
            # model_validate_json ensures the LLM didn't hallucinate keys or types
            parsed_model = PortfolioAnalysis.model_validate_json(raw_text)
            
            # Convert the validated Pydantic object back into a standard Python dictionary
            return parsed_model.model_dump()
            
        except ValidationError as e:
            print(f"\n[!] Pydantic Parsing Error: The LLM broke the schema constraints:\n{e}")
            raise
        except json.JSONDecodeError as e:
            print(f"\n[!] JSON Parsing Error: The LLM returned malformed JSON:\n{e}")
            raise

    # =========================================================
    # 3. MAIN EXPLAINER AGENT (NEURO-SYMBOLIC)
    # =========================================================
    def generate_explanation(self, portfolio: dict, risk_metrics: dict, tone: str = "beginner") -> tuple[str, dict]:
        
        # --- PHASE 1: PROMPT LOGIC ---
        system_instruction = f"""
        You are a financial advisor at a family office called Timecell. 
        Your job is to explain a portfolio's risk profile to the client. I will give you their raw portfolio and the stress-test metrics my backend calculated.
        
        Tone constraint: The client's financial literacy is '{tone}'.
        - If 'beginner': Keep it simple, use basic analogies, and explain what their runway actually means and dont keep the explanation quant heavy just use comparative terms.
        - If 'experienced': Use standard terms like drawdown, volatility, and allocation.
        - If 'expert': Be direct, highly quantitative, and focus on recovery percentages.
        
        Rules you must follow:
        1. Only use the numbers I provide in the metrics. Do not invent or recalculate anything.
        2. You must explicitly mention their 'runway_months' from the metrics in your summary.
        3. Be honest but professional.
        """

        prompt = f"""
        Original Portfolio:
        {json.dumps(portfolio, indent=2)}
        
        Calculated Risk Metrics (Severe Crash):
        {json.dumps(risk_metrics, indent=2)}
        """

        print(f"[*] Generating '{tone}' AI explanation...")
        
        # --- PHASE 2: API CALL (WITH EXPONENTIAL BACKOFF) ---
        max_retries = 3
        response = None
        
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=PortfolioAnalysis,
                        temperature=0.3 
                    ),
                )
                break  # If successful, exit the retry loop immediately
                
            except Exception as e:
                error_msg = str(e)
                if "503" in error_msg or "429" in error_msg:
                    wait_time = 5 * (attempt + 1)
                    print(f"   [!] API overloaded during generation (Attempt {attempt+1}/{max_retries}). Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        raise RuntimeError("Failed to generate explanation: API remains unavailable.")
                else:
                    raise e
        
        # --- PHASE 3: OUTPUT PARSING ---
        # Delegating the raw text to our dedicated parsing method
        structured_data = self.parse_llm_response(response.text)
        
        return response.text, structured_data

    # =========================================================
    # 4. CIO CRITIQUE AGENT (WITH EXPONENTIAL BACKOFF)
    # =========================================================
    def critique_analysis(self, portfolio: dict, risk_metrics: dict, generated_analysis: dict) -> str:
        
        system_instruction = """
        You are the Chief Investment Officer (CIO) at Timecell. 
        Review the junior advisor's explanation below. 
        Did they interpret the math correctly? Did they miss any glaring risks? 
        Keep your review to 2-3 sentences and give a final Pass/Fail grade.
        """

        prompt = f"""
        Original Portfolio:
        {json.dumps(portfolio, indent=2)}
        
        Backend Risk Metrics:
        {json.dumps(risk_metrics, indent=2)}
        
        Junior Advisor's Output to review:
        {json.dumps(generated_analysis, indent=2)}
        """

        print("[*] CIO Agent is reviewing the analysis for accuracy...")
        
        # Robust Retry Logic to handle Google API 503 (Overloaded) errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.1
                    ),
                )
                return response.text
                
            except Exception as e:
                error_msg = str(e)
                if "503" in error_msg or "429" in error_msg:
                    wait_time = 5 * (attempt + 1)
                    print(f"   [!] API overloaded during critique (Attempt {attempt+1}/{max_retries}). Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise e
                    
        return "CIO Review Failed: API remains unavailable after multiple retries."


# =========================================================
# EXECUTION BLOCK
# =========================================================
if __name__ == "__main__":
    
    sample_portfolio = {
        "total_value_inr": 10_000_000,
        "monthly_expenses_inr": 150_000, 
        "assets": [
            {"name": "NIFTY50", "allocation_pct": 20, "expected_crash_pct": -40},
            {"name": "BTC", "allocation_pct": 80, "expected_crash_pct": -80} 
        ]
    }

    try:
        # Step 1: Run Math Engine
        print("[*] Running quantitative stress test (Task 1)...")
        calculated_metrics = compute_risk_metrics(sample_portfolio, scenario="severe")
        
        # Step 2: Run AI Explainer
        explainer = PortfolioExplainer()
        raw_resp, structured_resp = explainer.generate_explanation(
            portfolio=sample_portfolio, 
            risk_metrics=calculated_metrics, 
            tone="beginner" 
        )

        print("\n--- EXTRACTED AI ANALYSIS ---")
        print(f"Verdict:      {structured_resp['verdict']}")
        print(f"Summary:      {structured_resp['summary']}")
        print(f"Doing Well:   {structured_resp['doing_well']}")
        print(f"Needs Change: {structured_resp['needs_change']}")

        print("\n[*] Cooldown initiated (5 seconds) to respect rate limits...")
        time.sleep(5)

        # Step 3: Run Critique Agent
        critique = explainer.critique_analysis(sample_portfolio, calculated_metrics, structured_resp)
        
        print("\n--- CIO CRITIQUE (LLM evaluating LLM) ---")
        print(critique)
        print("\n")

    except Exception as e:
        print(f"Fatal Error: {e}")