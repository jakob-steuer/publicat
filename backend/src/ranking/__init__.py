"""Relevance ranking for Publicat.

`scoring` is the single source of truth for how a paper is scored against a
topic. Ingestion, bulk rescoring and topic create/edit all call into it so the
three code paths cannot drift apart.
"""
