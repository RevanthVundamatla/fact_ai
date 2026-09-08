"""Optional Gemini adapter. The core app works without it; set GEMINI_API_KEY to enable semantic extraction/review."""
import os, json

def configured(): return bool(os.getenv('GEMINI_API_KEY'))

def extract_facts_with_gemini(text: str):
    if not configured(): return []
    try:
        from google import genai
        client=genai.Client(api_key=os.environ['GEMINI_API_KEY'])
        prompt=('Extract only factual claims from this PDF text. Return JSON array with fields '
                'claim, value, unit, subject, predicate, time_scope. Do not invent facts.\n\n'+text[:30000])
        r=client.models.generate_content(model=os.getenv('GEMINI_MODEL','gemini-2.5-flash'),contents=prompt)
        raw=r.text.strip().removeprefix('```json').removesuffix('```').strip()
        return json.loads(raw) if raw else []
    except Exception:
        return []
