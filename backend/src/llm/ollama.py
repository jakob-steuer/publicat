import json
import httpx
from .base import LLMProvider

class OllamaProvider(LLMProvider):
    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host
        self.model = "llama3" # Assuming llama3 is pulled locally
        
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

Respond ONLY with a valid JSON object matching this schema, nothing else:
{{"summary": "...", "score": 8}}
"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json"
                    },
                    timeout=60.0
                )
                response.raise_for_status()
                data = json.loads(response.json()["response"])
                return data.get("summary", ""), data.get("score", 5)
        except httpx.HTTPStatusError as e:
            print(f"Ollama Error: {e} - {e.response.text}")
            return "", 0
        except Exception as e:
            print(f"Ollama Error: {e}")
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
- Analyze the abstract to determine if the paper introduces a NEW software tool, software package, open-source framework, database, specific novel algorithm, or a new AI model (e.g., PLMs, LLMs). If it does, extract its exact name. If the paper merely uses existing tools or discusses general concepts, return an empty list.

Abstract:
{text}

Respond ONLY with a valid JSON object matching this schema:
{{"summary": "...", "tools": ["Tool1", "Tool2"]}}
"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json"
                    },
                    timeout=60.0
                )
                response.raise_for_status()
                data = json.loads(response.json()["response"])
                return data.get("summary", ""), data.get("tools", [])
        except httpx.HTTPStatusError as e:
            print(f"Ollama Error: {e} - {e.response.text}")
            return "", []
        except Exception as e:
            print(f"Ollama Error: {e}")
            return "", []

    async def extract_keywords(self, text: str, topic_desc: str) -> list[str]:
        prompt = f"""You are a scientific data extractor analyzing a paper for a researcher interested in: '{topic_desc}'.
Analyze the abstract to determine if the paper introduces a NEW software tool, software package, open-source framework, database, specific novel algorithm, or a new AI model (e.g., PLMs, LLMs). If it does, extract its exact name. If the paper merely uses existing tools or discusses general concepts, return an empty list.

Abstract:
{text}

Respond ONLY with a valid JSON object matching this schema:
{{"tools": ["Keyword1", "Keyword2"]}}
"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json"
                    },
                    timeout=60.0
                )
                response.raise_for_status()
                data = json.loads(response.json()["response"])
                return data.get("tools", [])
        except httpx.HTTPStatusError as e:
            print(f"Ollama Error: {e} - {e.response.text}")
            return []
        except Exception as e:
            print(f"Ollama Error: {e}")
            return []

    async def evaluate_relevance(self, text: str, topic_desc: str) -> tuple[int, str]:
        prompt = f"""You are a scientific peer-reviewer evaluating if a publication matches a specific research topic.
Topic Description: '{topic_desc}'

Publication Abstract:
{text}

Evaluate how relevant this publication is to the topic on a scale of 0 to 100.
Also provide a 1-sentence justification for your score.

Respond ONLY with a valid JSON object matching this schema:
{{"score": 85, "reason": "The paper directly addresses the topic by investigating..."}}
"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json"
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                data = json.loads(response.json()["response"])
                return data.get("score", 0), data.get("reason", "No reason provided.")
        except Exception as e:
            print(f"Ollama Evaluate Error: {e}")
            return 0, "Error evaluating relevance."

    async def generate(self, prompt: str) -> str:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=60.0
                )
                response.raise_for_status()
                return response.json()["response"]
        except Exception as e:
            print(f"Ollama Error: {e}")
            return ""
