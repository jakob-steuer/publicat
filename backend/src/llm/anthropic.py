import json
from anthropic import AsyncAnthropic
from .base import LLMProvider

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = "claude-3-5-haiku-latest"
        
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
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            data = json.loads(response.content[0].text)
            return data.get("summary", ""), data.get("score", 5)
        except Exception as e:
            print(f"Anthropic Error: {e}")
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
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Anthropic doesn't have a strict JSON mode parameter natively exposed like Gemini, but it follows instructions well.
            content = response.content[0].text
            # Simple parse to grab JSON block if it included markdown
            if "{" in content and "}" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                content = content[start:end]
            
            data = json.loads(content)
            return data.get("summary", ""), data.get("tools", [])
        except Exception as e:
            print(f"Anthropic Error: {e}")
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
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=200,
                system="You are a data extraction API that responds only in JSON.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            content = response.content[0].text
            
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            elif not content.strip().startswith("{"):
                start = content.find("{")
                end = content.rfind("}") + 1
                content = content[start:end]
            
            data = json.loads(content)
            return data.get("tools", [])
        except Exception as e:
            print(f"Anthropic Error: {e}")
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
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.content[0].text
            if "{" in content and "}" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                content = content[start:end]
            
            data = json.loads(content)
            return data.get("score", 0), data.get("reason", "No reason provided.")
        except Exception as e:
            print(f"Anthropic Evaluate Error: {e}")
            return 0, "Error evaluating relevance."

    async def generate(self, prompt: str) -> str:
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            print(f"Anthropic generate error: {e}")
            return ""
