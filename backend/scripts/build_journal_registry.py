import sys
import os
import json
import urllib.request
from typing import List, Dict
import numpy as np

# Add backend to path so we can import embeddings
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.embeddings import get_embedding, compute_cosine_similarity

CATEGORIES = [
    "Multidisciplinary Sciences",
    "Oncology and Cancer Research",
    "Neuroscience and Neurology",
    "Cardiovascular Medicine",
    "Immunology and Infectious Diseases",
    "Genetics and Genomics",
    "Biochemistry and Molecular Biology",
    "Cell Biology",
    "Structural Biology",
    "Bioinformatics and Computational Biology",
    "Microbiology and Virology",
    "Endocrinology and Metabolism",
    "Pharmacology and Toxicology",
    "Public Health and Epidemiology",
    "Clinical Medicine and Surgery",
    "Psychiatry and Psychology",
    "Artificial Intelligence and Machine Learning",
    "Computer Science and Software Engineering",
    "Robotics and Control Systems",
    "Materials Science and Nanotechnology",
    "Chemistry and Chemical Engineering",
    "Physics and Astronomy",
    "Mathematics and Statistics",
    "Earth Sciences and Geology",
    "Environmental Science and Ecology",
    "Plant Sciences and Botany",
    "Zoology and Animal Sciences",
    "Agricultural Sciences",
    "Engineering and Technology",
    "Economics and Social Sciences"
]

def main():
    url = "https://raw.githubusercontent.com/sg-s/science-journal-feeds/master/all-feeds.txt"
    print(f"Downloading {url}...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        text = response.read().decode('utf-8')
    
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    print("Embedding categories...")
    cat_embeddings = [get_embedding(cat) for cat in CATEGORIES]
    
    registry = {cat: [] for cat in CATEGORIES}
    
    print(f"Parsing and embedding {len(lines)} journals...")
    for i, line in enumerate(lines):
        parts = line.split(' | ')
        if len(parts) == 2:
            name, url = parts[0].strip(), parts[1].strip()
            # Find best category
            name_emb = get_embedding(name)
            best_cat = CATEGORIES[0]
            best_score = -1.0
            for cat, c_emb in zip(CATEGORIES, cat_embeddings):
                sim = compute_cosine_similarity(name_emb, c_emb)
                if sim > best_score:
                    best_score = sim
                    best_cat = cat
                    
            registry[best_cat].append({"name": name, "url": url})
            
            if i % 500 == 0:
                print(f"Processed {i}/{len(lines)}...")
                
    output_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'journal_registry.json')
    with open(output_path, 'w') as f:
        json.dump(registry, f, indent=2)
        
    print(f"Saved registry to {output_path}")
    
    # Print stats
    for cat in CATEGORIES:
        print(f"{cat}: {len(registry[cat])} journals")

if __name__ == '__main__':
    main()
