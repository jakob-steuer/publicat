from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import re

from src.database import get_db
from src.models.item import Item

router = APIRouter()

class ExportRequest(BaseModel):
    item_ids: List[str]

def generate_bibtex(items: List[Item]) -> str:
    bibtex_entries = []
    for item in items:
        # Generate a citekey: First author's last name + Year + First word of title
        first_author = item.authors[0].split()[-1] if item.authors else "Unknown"
        year = item.published_at.year if item.published_at else "YYYY"
        first_title_word = re.sub(r'[^a-zA-Z0-9]', '', item.title.split()[0]) if item.title else "Title"
        citekey = f"{first_author}{year}{first_title_word}"
        
        authors_str = " and ".join(item.authors) if item.authors else "Unknown"
        
        entry = f"@article{{{citekey},\n"
        entry += f"    title = {{{item.title}}},\n"
        entry += f"    author = {{{authors_str}}},\n"
        entry += f"    year = {{{year}}},\n"
        entry += f"    journal = {{{item.venue or item.source}}},\n"
        if item.doi:
            entry += f"    doi = {{{item.doi}}},\n"
        if item.url:
            entry += f"    url = {{{item.url}}},\n"
        if item.abstract:
            # Escape braces in abstract
            safe_abstract = item.abstract.replace("{", "\\{").replace("}", "\\}")
            entry += f"    abstract = {{{safe_abstract}}}\n"
        entry += "}\n"
        bibtex_entries.append(entry)
        
    return "\n".join(bibtex_entries)

@router.post("/bibtex", response_class=PlainTextResponse)
def export_bibtex_selection(request: ExportRequest, db: Session = Depends(get_db)):
    items = db.query(Item).filter(Item.id.in_(request.item_ids)).all()
    bibtex_str = generate_bibtex(items)
    return Response(content=bibtex_str, media_type="application/x-bibtex", headers={
        "Content-Disposition": 'attachment; filename="publikater_export.bib"'
    })

@router.get("/bibtex/starred", response_class=PlainTextResponse)
def export_bibtex_starred(db: Session = Depends(get_db)):
    items = db.query(Item).filter(Item.is_starred).all()
    bibtex_str = generate_bibtex(items)
    return Response(content=bibtex_str, media_type="application/x-bibtex", headers={
        "Content-Disposition": 'attachment; filename="publikater_starred.bib"'
    })

@router.get("/zotero/rss", response_class=Response)
def zotero_rss_feed(topic_id: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Returns an RSS 2.0 XML feed of starred items, specifically formatted for Zotero subscription.
    """
    query = db.query(Item).filter(Item.is_starred)
    
    if topic_id:
        from src.models.item_score import ItemScore
        query = query.join(ItemScore, Item.id == ItemScore.item_id).filter(ItemScore.topic_id == topic_id)
        
    items = query.order_by(Item.published_at.desc()).limit(100).all()
    
    xml_items = []
    for item in items:
        # Zotero uses the link to fetch metadata, so the URL is crucial
        url = item.url or f"https://doi.org/{item.doi}" if item.doi else ""
        pub_date = item.published_at.strftime("%a, %d %b %Y %H:%M:%S +0000") if item.published_at else ""
        
        # Escape XML entities
        title = item.title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        abstract = (item.abstract or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        creators = "\n            ".join([f"<dc:creator>{a.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</dc:creator>" for a in (item.authors or [])])
        doi_elem = f"<prism:doi>{item.doi}</prism:doi>\n            <dc:identifier>doi:{item.doi}</dc:identifier>" if item.doi else ""
        journal_name = item.venue or item.source or ""
        journal_elem = f"<prism:publicationName>{journal_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</prism:publicationName>" if journal_name else ""
        
        xml_item = f"""
        <item>
            <title>{title}</title>
            <link>{url}</link>
            <description>{abstract}</description>
            {creators}
            {journal_elem}
            {doi_elem}
            <pubDate>{pub_date}</pubDate>
            <guid isPermaLink="false">{item.id}</guid>
        </item>
        """
        xml_items.append(xml_item)
        
    rss_feed = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:prism="http://prismstandard.org/namespaces/1.2/basic/">
<channel>
    <title>Publikater Starred Publications</title>
    <link>http://localhost:5173</link>
    <description>Automatically syncs papers you star in Publikater directly into Zotero.</description>
    {"".join(xml_items)}
</channel>
</rss>
    """
    return Response(content=rss_feed.strip(), media_type="application/rss+xml")
