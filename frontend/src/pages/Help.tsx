import { Link } from 'react-router-dom'

export default function Help() {
  return (
    <div className="max-w-4xl mx-auto py-8 px-4 sm:px-6 lg:px-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="mb-8 border-b border-border/50 pb-6">
        <h1 className="text-3xl font-bold tracking-tight mb-2">Help & Tutorial</h1>
        <p className="text-muted-foreground text-lg">
          Learn how to get the most out of your personalized AI research feed.
        </p>
      </div>

      <div className="space-y-12">
        {/* Section 1: Tri-state system */}
        <section>
          <h2 className="text-2xl font-semibold mb-4 text-primary flex items-center gap-2">
            1. Using the Feed (Inbox Zero)
          </h2>
          <p className="text-foreground/80 mb-4 leading-relaxed">
            Publicat uses a simple tri-state system to help you quickly process new papers and achieve "Inbox Zero".
          </p>
          <div className="grid sm:grid-cols-3 gap-4">
            <div className="bg-muted/30 border border-border/50 p-4 rounded-xl">
              <div className="text-2xl mb-2">⭐</div>
              <h3 className="font-semibold mb-1">Star</h3>
              <p className="text-sm text-muted-foreground">Save this paper permanently to your Starred Library for future reading or export.</p>
            </div>
            <div className="bg-muted/30 border border-border/50 p-4 rounded-xl">
              <div className="text-2xl mb-2">✅</div>
              <h3 className="font-semibold mb-1">Read / Acknowledge</h3>
              <p className="text-sm text-muted-foreground">Mark as seen. It will be hidden from your main feed unless you toggle "Show Read".</p>
            </div>
            <div className="bg-muted/30 border border-border/50 p-4 rounded-xl">
              <div className="text-2xl mb-2">❌</div>
              <h3 className="font-semibold mb-1">Discard</h3>
              <p className="text-sm text-muted-foreground">Not relevant. Hides the paper entirely so it never clutters your feed again.</p>
            </div>
          </div>
        </section>

        {/* Section 2: Setting up topics */}
        <section>
          <h2 className="text-2xl font-semibold mb-4 text-primary flex items-center gap-2">
            2. Creating Great Topics
          </h2>
          <p className="text-foreground/80 mb-4 leading-relaxed">
            The AI matches papers based on the semantic meaning of your topic description and strict keyword boosting. For the best results, focus heavily on the <strong>methodology and core concepts</strong>, and avoid generic statements.
          </p>
          <div className="bg-primary/5 border border-primary/20 rounded-xl p-5 mb-4">
            <h3 className="font-semibold text-primary mb-2">Tip: Use an LLM to write your topic</h3>
            <p className="text-sm text-foreground/80 italic mb-2">
              "I want to create a feed for academic papers about [Your Topic]. Write a 2-3 sentence description focusing strictly on the methodology and core technologies involved, avoiding generic outcomes. Then provide a comma-separated list of 3-5 specific keywords."
            </p>
          </div>
          <div className="bg-muted/30 border border-border/50 p-5 rounded-xl text-sm">
            <p className="mb-2"><strong>Example Topic:</strong></p>
            <ul className="space-y-2">
              <li><span className="text-muted-foreground">Name:</span> Foundation Models in Life Sciences</li>
              <li><span className="text-muted-foreground">Description:</span> Applications of large language models (LLMs), transformer architectures, foundation models, and self-supervised deep learning architectures applied to biological data.</li>
              <li><span className="text-muted-foreground">Keywords:</span> Foundation Models, Protein Language Models, RNA Language Models, DNA Language Models</li>
            </ul>
          </div>
          <p className="text-xs text-muted-foreground mt-3 flex items-center gap-1">
            <span>Note:</span> When you create a new topic, the first sync fetches 30 days of history and may take a few minutes!
          </p>
        </section>

        {/* Section 3: Following Authors */}
        <section>
          <h2 className="text-2xl font-semibold mb-4 text-primary flex items-center gap-2">
            3. Following Authors & Venues
          </h2>
          <p className="text-foreground/80 mb-4 leading-relaxed">
            If you see a paper by an author you want to track, simply click the <span className="font-mono bg-muted px-1 rounded text-xs">+</span> icon next to their name. 
          </p>
          <p className="text-foreground/80 leading-relaxed">
            Any future paper published by a followed author automatically receives a <strong>+15% score boost</strong>, guaranteeing it rises to the top of your "Do Not Miss" feed. You can manage your followed authors in the <Link to="/settings" className="text-primary hover:underline">Settings</Link> page.
          </p>
        </section>

        {/* Section 4: Integrations */}
        <section>
          <h2 className="text-2xl font-semibold mb-4 text-primary flex items-center gap-2">
            4. Zotero & Exports
          </h2>
          <div className="grid md:grid-cols-2 gap-6">
            <div className="space-y-3">
              <h3 className="font-semibold text-lg flex items-center gap-2">Zotero RSS</h3>
              <p className="text-sm text-foreground/80 leading-relaxed">
                Every topic has a dedicated Zotero RSS URL button at the top of the feed. Click it to copy the link, then in Zotero go to <strong>New Feed → From URI</strong>. High-scoring, AI-summarized papers will automatically pipe into Zotero!
              </p>
            </div>
            <div className="space-y-3">
              <h3 className="font-semibold text-lg flex items-center gap-2">Export Citations</h3>
              <p className="text-sm text-foreground/80 leading-relaxed">
                In your Starred Library, you can export all your saved papers as a JSON file, or copy their citations to share with colleagues or use in your manuscripts.
              </p>
            </div>
          </div>
        </section>

        {/* Section 5: Semantic Scholar API Key */}
        <section>
          <h2 className="text-2xl font-semibold mb-4 text-primary flex items-center gap-2">
            5. Semantic Scholar API Key
          </h2>
          <p className="text-foreground/80 leading-relaxed mb-4">
            Publicat relies heavily on the Semantic Scholar API to discover new papers. While the app will run without an API key, the unauthenticated tier is heavily rate-limited globally. <strong className="text-red-500 dark:text-red-400">Without a key, your paper fetching will likely fail with "Too Many Requests" errors. This is highly recommended.</strong>
          </p>
          <div className="bg-primary/5 border border-primary/20 p-5 rounded-xl">
            <h3 className="font-semibold text-primary mb-2">How to get your free key:</h3>
            <ol className="list-decimal pl-5 space-y-1 text-sm text-foreground/80">
              <li>Go to <a href="https://www.semanticscholar.org/product/api" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">semanticscholar.org/product/api</a></li>
              <li>Click "Get an API Key" and fill out the form.</li>
              <li>Once you receive your key, paste it into the <strong>Settings</strong> page inside the Publicat app.</li>
            </ol>
          </div>
        </section>

        {/* Section 6: LLM Architecture */}
        <section>
          <h2 className="text-2xl font-semibold mb-4 text-primary flex items-center gap-2">
            6. Local vs. Cloud AI
          </h2>
          <p className="text-foreground/80 leading-relaxed mb-4">
            Publicat runs all semantic matching and paper scoring <strong>100% locally</strong> on your machine. However, for generating the actual text summaries, you can configure your LLM preference in the <Link to="/settings" className="text-primary hover:underline">Settings</Link> page.
          </p>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="bg-primary/5 border border-primary/20 p-4 rounded-xl">
              <h3 className="font-semibold mb-1 text-primary">Cloud APIs (Recommended)</h3>
              <p className="text-sm text-foreground/80">Using a Gemini or Anthropic API key allows Publicat to summarize dozens of complex papers in parallel in seconds with state-of-the-art accuracy.</p>
            </div>
            <div className="bg-muted/30 border border-border/50 p-4 rounded-xl">
              <h3 className="font-semibold mb-1">Local (Ollama)</h3>
              <p className="text-sm text-muted-foreground">If you provide no API keys, Publicat falls back to your local Ollama installation. This is highly private, but generating 20+ scientific summaries sequentially takes significantly longer.</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
