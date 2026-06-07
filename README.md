<div align="center">
  <img src="./publicat_logo.png" width="400" alt="Publicat Logo">
  
  *A personalized AI-powered research feed that cuts through the noise and delivers only the methodology and discoveries you actually care about.*
</div>

---

**PUBLICAT** automatically ingests, scores, and summarizes scientific papers based on your highly specific topics of interest. Stay on top of the latest research without drowning in generic feeds.

## Quick Start & Installation

There are two ways to run Publicat: the **1-Click Launcher** (recommended for most users) or via manual command line setup.

### The 1-Click Launcher Way

We use a modern installation approach to ensure your local AI tools are hardware-accelerated and properly isolated.

**For Mac/Linux:**
1. Download or `git clone` this repository.
2. Open a terminal in the folder and run:
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

**For Windows:**
1. Download or `git clone` this repository.
2. Double-click the `start.bat` file.

*What does this do?*
It automatically checks for and installs `uv` (a blazingly fast Python manager), creates an isolated virtual environment, installs PyTorch optimally for your system (CUDA/MPS), builds the React frontend, and launches the app in your browser at `http://localhost:8001`!

### Manual Installation
Make sure you have Node.js (v18+) and Python (3.11+) with `uv` installed.

1. **Clone the repository:**
   ```bash
   git clone git@github.com:jakob-steuer/eureka.git
   cd eureka
   ```

2. **Start the Backend:**
   ```bash
   cp backend/.env.example backend/.env
   # Tip: Add your S2_API_KEY to the .env file for faster fetching!
   
   cd backend
   uv sync
   uv run uvicorn src.main:app --reload --port 8001
   ```

3. **Start the Frontend:** (In a new terminal window)
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open `http://localhost:5173` in your browser!

---

## Tutorial: Setting Up Your First Topic

Publicat uses advanced AI to semantically match papers to your topics. The better you describe your topic, the better your feed will be!

**Pro Tip for Topic Descriptions:** Don't use a generic list of outcomes (like "predicts 3D structures"). Focus heavily on the *methodology* and the core concepts you want to read about.

### Example LLM Prompt to Generate a Great Topic
If you're unsure how to describe your topic, ask an LLM of your choice:
> *"I want to create a feed for academic papers about [Your Topic]. Write a 2-3 sentence description focusing strictly on the methodology and core technologies involved, avoiding generic outcomes. Then provide a comma-separated list of 3-5 hyper-specific keywords."*

### Example Topic
- **Name:** Foundation Models in Life Sciences
- **Description:** Applications of large language models (LLMs), transformer architectures, foundation models, and self-supervised deep learning architectures applied to biological data.
- **Keywords:** Foundation Models, Protein Language Models, RNA Language Models, DNA Language Models

> **⚠️ Note:** When you create a new topic, Publicat will immediately start fetching and scoring papers from the last 30 days. This **first sync may take a few minutes** depending on your hardware and network speed.

---

## Using the Interface

Publicat uses a simple, swipe-like tri-state system to help you reach Inbox Zero.

- ⭐ **Star:** Save this paper. It will be permanently kept in your "Starred" feed for future reference.
- ✅ **Read (Acknowledge):** You've seen this paper, but don't need to save it. It will be hidden from your main feed unless you toggle "Show Read".
- ❌ **Discard:** Not relevant. Hides the paper entirely so it never clutters your feed again.

### Features at a Glance
- **Follow Authors:** Click the `+` icon next to an author's name on any paper. Every future paper they publish will automatically receive a score boost (+15%) and be highlighted in your feed!
- **Export Citations:** Easily export your starred papers to share or use in manuscripts.

### Zotero Integration
Every topic in Publicat features a dedicated "Zotero RSS URL" button at the top of the dashboard.

**How it works:**
1. Click the button to copy your unique topic URL.
2. In Zotero, go to *New Feed -> From URI* and paste the link.
3. High-confidence, AI-summarized papers will pipe straight into your reference manager!

*(We plan to add direct Zotero API key integration in the future. Pros: Direct PDF injection and two-way syncing. Cons: Requires giving the app full write access to your Zotero library.)*

---

## Semantic Scholar API Key (Highly Recommended)

> [!IMPORTANT]
> Publicat relies heavily on the Semantic Scholar API to discover new papers. While the app will run without an API key, the unauthenticated tier is heavily rate-limited globally. **Without a key, your paper fetching will likely fail with "Too Many Requests" errors.**

**How to get your free key:**
1. Go to [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api)
2. Click "Get an API Key" and fill out the form.
3. Once you have your key, paste it into the **Settings** page inside the Publicat app.

---

## Local vs. Cloud AI

Publicat relies heavily on AI. All semantic embedding and paper matching runs **100% locally** on your machine using optimized PyTorch models. 

For generating the actual text summaries, you have a choice (configurable in Settings):
- **Cloud APIs (Recommended):** By entering a Gemini or Anthropic API key, Publicat can summarize dozens of complex papers in parallel in seconds with state-of-the-art accuracy.
- **Local (Ollama):** If you provide no API keys, Publicat automatically falls back to your local Ollama installation. While highly private, generating 20+ scientific summaries sequentially on a local 8B model will take significantly longer and requires powerful hardware.

---

## Legal & Tech Stack

**Tech Stack:** React, TypeScript, Vite, TailwindCSS • Python, FastAPI, SQLite • Semantic Scholar SPECTER v2, Gemini, Anthropic.

*This software is provided "as is", without warranty of any kind. It relies on third-party APIs (Semantic Scholar, arXiv, bioRxiv). AI-generated summaries may contain inaccuracies and should be verified against original publications.*

Copyright (c) 2026 Jakob Steuer. All rights reserved.
