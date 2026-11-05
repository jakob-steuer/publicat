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
        {/* Section 1: Voting system */}
        <section>
          <h2 className="text-2xl font-semibold mb-4 text-primary flex items-center gap-2">
            1. Using the Feed (Inbox Zero)
          </h2>
          <p className="text-foreground/80 mb-4 leading-relaxed">
            The inbox is a ranked list. Move with <kbd className="px-1 border rounded font-mono text-xs">j</kbd>/<kbd className="px-1 border rounded font-mono text-xs">k</kbd>, open a paper with <kbd className="px-1 border rounded font-mono text-xs">Enter</kbd>, vote with <kbd className="px-1 border rounded font-mono text-xs">s</kbd> <kbd className="px-1 border rounded font-mono text-xs">u</kbd> <kbd className="px-1 border rounded font-mono text-xs">n</kbd> <kbd className="px-1 border rounded font-mono text-xs">d</kbd>, undo with <kbd className="px-1 border rounded font-mono text-xs">z</kbd>. Press <kbd className="px-1 border rounded font-mono text-xs">?</kbd> for the full list. Every vote trains the topic shown on the card, and only that topic.
          </p>
          <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-muted/30 border border-border/50 p-4 rounded-xl">
              <div className="text-2xl mb-2 text-yellow-500">⭐</div>
              <h3 className="font-semibold mb-1">Star (+2)</h3>
              <p className="text-sm text-muted-foreground">Save permanently. Heavily boosts similar papers.</p>
            </div>
            <div className="bg-muted/30 border border-border/50 p-4 rounded-xl">
              <div className="text-2xl mb-2 text-green-500">👍</div>
              <h3 className="font-semibold mb-1">Upvote (+1)</h3>
              <p className="text-sm text-muted-foreground">Relevant, but don't save. Boosts similar papers.</p>
            </div>
            <div className="bg-muted/30 border border-border/50 p-4 rounded-xl">
              <div className="text-2xl mb-2 text-blue-500">➖</div>
              <h3 className="font-semibold mb-1">Neutral (0)</h3>
              <p className="text-sm text-muted-foreground">Clear it from the inbox. Counts as a slight "not for me", a quarter of an upvote, so use it freely for papers you cannot judge yet.</p>
            </div>
            <div className="bg-muted/30 border border-border/50 p-4 rounded-xl">
              <div className="text-2xl mb-2 text-red-500">👎</div>
              <h3 className="font-semibold mb-1">Downvote (-1)</h3>
              <p className="text-sm text-muted-foreground">Not relevant. Penalizes similar papers.</p>
            </div>
          </div>
          <div className="bg-primary/5 border border-primary/20 rounded-xl p-4 mt-4">
            <h3 className="font-semibold text-primary mb-1">Automatic Database Cleanup</h3>
            <p className="text-sm text-foreground/80">
              To prevent your local database from becoming bloated, any publication older than 60 days that you haven't explicitly starred is automatically removed during background syncs. Starred papers are kept forever!
            </p>
          </div>
        </section>

        {/* Section 2: Setting up topics */}
        <section>
          <h2 className="text-2xl font-semibold mb-4 text-primary flex items-center gap-2">
            2. Creating Great Topics & Active Learning
          </h2>
          <p className="text-foreground/80 mb-4 leading-relaxed">
            The AI initially matches papers based on the semantic meaning of your topic description and strict keyword boosting. For the best initial results, focus heavily on the <strong>methodology and core concepts</strong>, and avoid generic statements.
          </p>
          <div className="bg-primary/5 border border-primary/20 rounded-xl p-5 mb-4">
            <h3 className="font-semibold text-primary mb-2">Continuous Active Learning 🧠</h3>
            <p className="text-sm text-foreground/80 mb-2">
              Each topic has its own small ranking model. Before you vote it ranks by similarity to your <strong>seed papers</strong> (or to Semantic Scholar search results for the topic). Every <strong>Star</strong>, <strong>Upvote</strong>, <strong>Neutral</strong> or <strong>Downvote</strong> retrains that model within seconds and rescores the topic's papers.
            </p>
            <p className="text-sm text-foreground/80">
              Click the score number on any paper to see why it scored the way it did. The Settings page shows how many votes each ranker has and its cross-validated accuracy; below roughly 30 votes it mostly follows the seed papers and keywords.
            </p>
          </div>
          <div className="bg-muted/30 border border-border/50 p-5 rounded-xl mb-4">
            <h3 className="font-semibold mb-2">Tip: Use an LLM to write your topic</h3>
            <p className="text-sm text-muted-foreground italic mb-2">
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
            3. Following Authors
          </h2>
          <p className="text-foreground/80 mb-4 leading-relaxed">
            If you see a paper by an author you want to track, simply click the <span className="font-mono bg-muted px-1 rounded text-xs">+</span> icon next to their name. 
          </p>
          <p className="text-foreground/80 leading-relaxed">
            Any future paper published by a followed author automatically receives a <strong>+15% score boost</strong>, guaranteeing it rises to the top of your "Do Not Miss" feed. You can manage your followed authors in the <Link to="/settings" className="text-primary hover:underline">Settings</Link> page.
          </p>
          <div className="bg-primary/5 border border-primary/20 rounded-xl p-4 mt-4">
            <h3 className="font-semibold text-primary mb-1">Automatic Journal Boosts</h3>
            <p className="text-sm text-foreground/80">
              Papers published in major high-impact life science and medical journals (like Nature, Science, Cell, NEJM) automatically receive a semantic score boost to ensure they surface in your feed.
            </p>
          </div>
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
                Select papers and use the bar at the bottom to export BibTeX or save them into the running Zotero desktop app with one click (the AI summary goes along as a note). The Starred Library can be exported as BibTeX in full.
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
            Publicat relies heavily on the Semantic Scholar API to discover new papers. While the app will run without an API key, the unauthenticated tier is heavily rate-limited globally. <strong className="text-red-500 dark:text-red-400">It is highly recommended to register for a free Semantic Scholar API Key. Without a key, your paper fetching will likely fail with "Too Many Requests" errors.</strong>
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
              <h3 className="font-semibold mb-1 text-primary">Cloud APIs</h3>
              <p className="text-sm text-foreground/80">Using a Gemini or Anthropic API key allows Publicat to use fast, cost-effective models (like Gemini Flash or Claude Haiku) to summarize dozens of complex papers in parallel in seconds with state-of-the-art accuracy.</p>
            </div>
            <div className="bg-muted/30 border border-border/50 p-4 rounded-xl">
              <h3 className="font-semibold mb-1">Local (Ollama)</h3>
              <p className="text-sm text-muted-foreground">If you provide no API keys, Publicat falls back to a local model. This is highly private, but generating many scientific summaries sequentially can take significantly longer, depending on your local hardware.</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
