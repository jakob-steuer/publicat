import datetime
import uuid
from sqlalchemy import Column, String, DateTime, Integer, JSON, Boolean
from .base import Base

class Item(Base):
    __tablename__ = "items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String, nullable=False, index=True)
    source_native_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    authors = Column(JSON, nullable=False)
    author_details = Column(JSON, nullable=True) # Array of objects: [{"name": "...", "authorId": "...", "orcid": "..."}]
    abstract = Column(String, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=False, index=True)
    url = Column(String, nullable=False)
    doi = Column(String, nullable=True, index=True)
    venue = Column(String, nullable=True)
    citation_count = Column(Integer, nullable=True)
    raw_metadata_json = Column(JSON, nullable=False)
    
    # S2 Specific Identifiers
    corpus_id = Column(String, unique=True, index=True, nullable=True)
    pmid = Column(String, nullable=True)
    orcid_list = Column(JSON, nullable=True)
    
    # S2 Enrichment Data
    is_open_access = Column(Boolean, nullable=False, default=False)
    open_access_pdf_url = Column(String, nullable=True)
    reference_count = Column(Integer, nullable=True)
    influential_citation_count = Column(Integer, nullable=True)
    citation_styles = Column(JSON, nullable=True)
    embedding = Column(JSON, nullable=True) # Specter v2 embedding from S2
    
    # Summaries
    t1_tldr = Column(String, nullable=True)
    t2_summary = Column(String, nullable=True)
    t3_summary = Column(String, nullable=True)
    tools = Column(JSON, nullable=True)
    
    is_acknowledged = Column(Boolean, nullable=False, default=False, index=True)
    is_starred = Column(Boolean, nullable=False, default=False, index=True)
    is_hidden = Column(Boolean, nullable=False, default=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))
