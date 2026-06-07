import json
from google import genai
from google.genai import types
from .base import LLMProvider

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.5-flash"
        
    async def summarize_brief(self, text: str, topic_desc: str) -> tuple[str, int]:
        prompt = f"""You are a scientific newsletter editor summarizing a paper for a researcher interested in: '{topic_desc}'.
Write a highly concise, dry, and factual 2-3 sentence overview of the publication.
Follow this exact structure: 'By doing X, this work shows Y, which is important because Z.'
CRITICAL RULES:
- DO NOT use ANY conversational filler (e.g., NEVER say "Here is a summary", "This groundbreaking paper...", or "Why you must read this").
- Start directly with the first factual sentence.
- Use a maximum of 3 sentences.
- STRICT MAXIMUM 250 CHARACTERS.
- Also provide a relevance score from 1 to 10 on how perfectly it matches the topic.

Abstract:
{text}

Respond ONLY with a valid JSON object matching this schema:
{{"summary": "...", "score": 8}}
"""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(response.text)
            return data.get("summary", ""), data.get("score", 5)
        except Exception as e:
            print(f"Gemini Error: {e}")
            return "", 0

    async def summarize_deep(self, text: str, topic_desc: str) -> tuple[str, list[str]]:
        prompt = f"""You are a scientific newsletter editor summarizing a publication.
Write a highly concise, dry, and factual 2-3 sentence overview of the publication.
CRITICAL RULES:
- DO NOT invent or hallucinate any information. Base your summary strictly on the provided abstract.
- If the abstract describes a specific experiment or study, try to use the structure: 'By doing X, this work shows Y, which is important because Z.'
- If the abstract is a review, editorial, or general discussion, DO NOT force the above structure. Simply summarize what is actually discussed.
- DO NOT use ANY conversational filler (e.g., NEVER say "Here is a summary", "This groundbreaking paper...", or "Why you must read this").
- Start directly with the first factual sentence.
- Use a maximum of 3 sentences.
- STRICT MAXIMUM 400 CHARACTERS.
- Analyze the abstract to determine if the paper introduces a NEW software tool, software package, open-source framework, database, or specific novel algorithm. If it does, extract its exact name. If the paper merely uses existing tools or discusses general concepts, return an empty list.

Abstract:
{text}

Respond ONLY with a valid JSON object matching this schema:
{{"summary": "...", "tools": ["Tool1", "Tool2"]}}
"""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(response.text)
            return data.get("summary", ""), data.get("tools", [])
        except Exception as e:
            print(f"Gemini Error: {e}")
            return "", []

    async def extract_keywords(self, text: str, topic_desc: str) -> list[str]:
        prompt = f"""You are a scientific data extractor analyzing a paper for a researcher interested in: '{topic_desc}'.
Analyze the abstract to determine if the paper introduces a NEW software tool, software package, open-source framework, database, or specific novel algorithm. If it does, extract its exact name. If the paper merely uses existing tools or discusses general concepts, return an empty list.

Abstract:
{text}

Respond ONLY with a valid JSON object matching this schema:
{{"tools": ["Keyword1", "Keyword2"]}}
"""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(response.text)
            return data.get("tools", [])
        except Exception as e:
            print(f"Gemini Error: {e}")
            return []

    async def generate(self, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            print(f"Gemini Error: {e}")
            return ""
