/**
 * LUMO Sample Demonstration Index & Client-Side Search Logic
 * Clearly separated from live FastAPI responses.
 * Pure functions allow deterministic unit testing across Classic, Semantic, and Hybrid modes.
 */

export const SEARCH_MODES = Object.freeze({
  classic: {
    id: 'classic',
    label: 'Classic',
    description:
      'Keyword-based retrieval across indexed page titles, URLs, and full document text.',
  },
  semantic: {
    id: 'semantic',
    label: 'Semantic',
    description:
      'Finds results by meaning, context, and intent rather than exact keyword overlap.',
  },
  hybrid: {
    id: 'hybrid',
    label: 'Hybrid',
    description:
      'Combines exact keyword matching with semantic relevance for balanced precision.',
  },
  ai: {
    id: 'ai',
    label: 'AI Search',
    description:
      'Grounded question answering with verified citations from retrieved documents.',
  },
  web: {
    id: 'web',
    label: 'Web (Live)',
    description:
      'Live public internet search across Wikipedia and real-time web indices.',
  },
});

export const RESULT_CATEGORIES = Object.freeze([
  'All',
  'Reference',
  'Engineering',
  'Security',
  'Research',
]);

/**
 * Sample demonstration corpus — clearly labelled in the UI as sample data
 * until the LUMO FastAPI + OpenSearch / Qdrant backend is connected.
 */
export const SAMPLE_INDEX = Object.freeze([
  {
    id: 'doc-search-arch',
    title: 'How Modern Search Engines Crawl, Index, and Rank the Web',
    url: 'https://reference.lumo-sample.org/search/architecture-overview',
    domain: 'reference.lumo-sample.org',
    category: 'Reference',
    publishedAt: '2026-08-14',
    description:
      'A clear technical guide explaining web crawlers, inverted indexes, BM25 lexical scoring, and query pipelines.',
    snippet:
      'Search engines separate crawling from query serving. Tokenized pages are stored in an inverted index so keyword lookups complete in milliseconds, while ranking combines term frequency, document length, and authority signals.',
    concepts: [
      'search engines',
      'crawling',
      'inverted index',
      'bm25',
      'opensearch',
      'information retrieval',
      'ranking',
      'web',
    ],
    graphEntityId: 'entity-hybrid-search',
  },
  {
    id: 'doc-semantic-vectors',
    title: 'Semantic Retrieval and Dense Vector Embeddings Explained',
    url: 'https://research.lumo-sample.org/retrieval/dense-vector-embeddings',
    domain: 'research.lumo-sample.org',
    category: 'Research',
    publishedAt: '2026-09-22',
    description:
      'Understanding how sentence transformers convert natural-language questions into vectors for meaning-based retrieval.',
    snippet:
      'Unlike strict keyword matching, semantic search encodes both queries and passages into dense vectors. Cosine similarity surfaces conceptually aligned documents even when exact vocabulary differs.',
    concepts: [
      'semantic search',
      'embeddings',
      'vectors',
      'qdrant',
      'sentence transformers',
      'meaning',
      'ai learns',
      'nlp',
    ],
    graphEntityId: 'entity-semantic-retrieval',
  },
  {
    id: 'doc-hybrid-fusion',
    title: 'Reciprocal Rank Fusion in Hybrid Search Pipelines',
    url: 'https://engineering.lumo-sample.org/retrieval/reciprocal-rank-fusion',
    domain: 'engineering.lumo-sample.org',
    category: 'Engineering',
    publishedAt: '2026-10-05',
    description:
      'Combining lexical OpenSearch results with Qdrant vector retrieval using Reciprocal Rank Fusion (RRF).',
    snippet:
      'Hybrid retrieval merges exact lexical hits with semantic candidates via Reciprocal Rank Fusion. This preserves exact identifier and acronym recall while answering broad conceptual questions accurately.',
    concepts: [
      'hybrid search',
      'rrf',
      'opensearch',
      'qdrant',
      'ranking',
      'search engines',
      'precision',
      'recall',
    ],
    graphEntityId: 'entity-hybrid-search',
  },
  {
    id: 'doc-url-security',
    title: 'URL Security Inspection: Redirect Chains, Punycode, and SSRF Defenses',
    url: 'https://security.lumo-sample.org/guides/url-inspection-and-ssrf',
    domain: 'security.lumo-sample.org',
    category: 'Security',
    publishedAt: '2026-10-19',
    description:
      'Best practices for analyzing untrusted links, tracing HTTP redirects safely, and preventing server-side request forgery.',
    snippet:
      'Safe URL analyzers validate schemes, resolve DNS before connecting, block loopback and RFC 1918 private networks, enforce response-size limits, and flag internationalized lookalike domains (IDN homographs).',
    concepts: [
      'url security',
      'download guardian',
      'redirects',
      'ssrf',
      'punycode',
      'phishing',
      'domain reputation',
      'malicious links',
    ],
    graphEntityId: 'entity-download-guardian',
  },
  {
    id: 'doc-file-hashing',
    title: 'Cryptographic File Hashing (SHA-256) and Malware Triage',
    url: 'https://security.lumo-sample.org/guides/sha256-file-verification',
    domain: 'security.lumo-sample.org',
    category: 'Security',
    publishedAt: '2026-07-30',
    description:
      'How SHA-256 digests, MIME inspection, and threat-intelligence lookups work together during file security analysis.',
    snippet:
      'Computing a local SHA-256 digest identifies known file artifacts without transmitting raw binary payloads first. Threat intelligence feeds compare hashes against verified malware corpora, though an unknown hash never guarantees safety.',
    concepts: [
      'file security',
      'sha-256',
      'hash',
      'malware',
      'threat intelligence',
      'download guardian',
      'cryptography',
    ],
    graphEntityId: 'entity-sha256',
  },
  {
    id: 'doc-tls-crypto',
    title: 'How TLS 1.3 and Public-Key Cryptography Protect Web Traffic',
    url: 'https://reference.lumo-sample.org/networking/tls-cryptography-handbook',
    domain: 'reference.lumo-sample.org',
    category: 'Security',
    publishedAt: '2026-06-11',
    description:
      'A step-by-step walkthrough of the TLS 1.3 handshake, certificate validation, and forward secrecy.',
    snippet:
      'During a TLS 1.3 handshake, client and server negotiate ephemeral Diffie-Hellman keys in one round trip, verify X.509 certificates, and encrypt subsequent HTTP traffic with authenticated ciphers.',
    concepts: [
      'tls',
      'https',
      'cryptography',
      'web security',
      'certificates',
      'encryption',
      'internet',
      'privacy',
    ],
    graphEntityId: 'entity-tls',
  },
  {
    id: 'doc-bgp-internet',
    title: 'How the Internet Routes Packets Globally with DNS and BGP',
    url: 'https://reference.lumo-sample.org/networking/bgp-dns-routing',
    domain: 'reference.lumo-sample.org',
    category: 'Reference',
    publishedAt: '2026-05-18',
    description:
      'Tracing a browser request from recursive DNS resolution through Autonomous Systems and submarine fibre cables.',
    snippet:
      'Border Gateway Protocol (BGP) enables independent networks to announce IP prefixes and choose resilient paths across regional exchanges and undersea optical cables.',
    concepts: [
      'internet',
      'bgp',
      'dns',
      'routing',
      'packets',
      'networking',
      'fibre optic',
      'architecture',
    ],
    graphEntityId: 'entity-bgp',
  },
  {
    id: 'doc-satellite-comms',
    title: 'Satellite Communication: Orbital Regimes, Link Budgets, and Latency',
    url: 'https://reference.lumo-sample.org/aerospace/satellite-communications',
    domain: 'reference.lumo-sample.org',
    category: 'Reference',
    publishedAt: '2026-04-27',
    description:
      'Comparing low-Earth orbit constellations and geostationary satellites for global telemetry and broadband.',
    snippet:
      'Low-Earth orbit (LEO) satellites circle at 500–1,200 km with round-trip latency near 25–40 ms, whereas geostationary links at 35,786 km provide wide coverage with ~600 ms signal delay.',
    concepts: [
      'satellites',
      'space',
      'communication',
      'orbital networks',
      'latency',
      'gps',
      'radio',
    ],
    graphEntityId: 'entity-satellites',
  },
  {
    id: 'doc-knowledge-graphs',
    title: 'Knowledge Graphs: Modeling Entities, Relationships, and Provenance',
    url: 'https://research.lumo-sample.org/knowledge/entity-relationship-graphs',
    domain: 'research.lumo-sample.org',
    category: 'Research',
    publishedAt: '2026-09-03',
    description:
      'How typed entity graphs connect concepts, citations, and evidence for transparent research exploration.',
    snippet:
      'A knowledge graph stores subject-predicate-object relationships alongside source citations, letting users traverse related concepts and inspect the exact evidence behind each link.',
    concepts: [
      'knowledge graph',
      'entities',
      'relationships',
      'ontology',
      'provenance',
      'research',
      'linked data',
    ],
    graphEntityId: 'entity-knowledge-graph',
  },
  {
    id: 'doc-research-agents',
    title: 'Bounded Autonomous Research Agents and Evidence Verification',
    url: 'https://research.lumo-sample.org/agents/bounded-research-workflows',
    domain: 'research.lumo-sample.org',
    category: 'Research',
    publishedAt: '2026-11-02',
    description:
      'Designing deterministic step limits, source caps, contradiction detection, and full audit trails for AI research.',
    snippet:
      'Reliable research agents decompose complex questions into verifiable subquestions, enforce strict step and source budgets, record every retrieval step in an audit log, and explicitly flag contradictions or gaps.',
    concepts: [
      'autonomous research',
      'research agent',
      'rag',
      'citations',
      'evidence',
      'contradictions',
      'ai',
      'audit log',
    ],
    graphEntityId: 'entity-research-agent',
  },
  {
    id: 'doc-fastapi-gateway',
    title: 'Building a Secure FastAPI Gateway for Search and Intelligence Platforms',
    url: 'https://engineering.lumo-sample.org/backend/fastapi-gateway-architecture',
    domain: 'engineering.lumo-sample.org',
    category: 'Engineering',
    publishedAt: '2026-10-12',
    description:
      'Routing browser requests through a centralized FastAPI boundary in front of OpenSearch, Qdrant, PostgreSQL, and Redis.',
    snippet:
      'Centralizing all client requests behind FastAPI prevents credential leakage, enforces rate limits and input validation, and isolates internal datastores and local LLM runtimes from browser exposure.',
    concepts: [
      'fastapi',
      'python',
      'api',
      'opensearch',
      'qdrant',
      'postgresql',
      'redis',
      'ollama',
      'backend',
    ],
    graphEntityId: 'entity-fastapi',
  },
  {
    id: 'doc-ai-learning',
    title: 'How Artificial Intelligence Learns Representations from Text and Data',
    url: 'https://reference.lumo-sample.org/ai/how-ai-learns-representations',
    domain: 'reference.lumo-sample.org',
    category: 'Reference',
    publishedAt: '2026-08-29',
    description:
      'An accessible introduction to gradient descent, neural representations, evaluation sets, and retrieval-augmented grounding.',
    snippet:
      'Modern machine learning models adjust millions of numerical parameters to minimize prediction error on training corpora. Pairing models with live search retrieval grounds generated answers in verifiable sources.',
    concepts: [
      'artificial intelligence',
      'ai learns',
      'machine learning',
      'neural networks',
      'rag',
      'representations',
      'semantic',
    ],
    graphEntityId: 'entity-semantic-retrieval',
  },
  {
    id: 'doc-google-portal',
    title: 'Google — Web Search Engine and Technology Portal',
    url: 'https://www.google.com',
    domain: 'google.com',
    category: 'Reference',
    publishedAt: '2026-01-01',
    description:
      'Google is a primary internet search engine providing access to global indexed web documents, knowledge graphs, and internet tools.',
    snippet:
      'Google web search engine at www.google.com. Provides keyword and natural language search across web pages, news, images, and reference articles.',
    concepts: [
      'google',
      'google.com',
      'www.google.com',
      'search engines',
      'web search',
      'search',
      'internet',
    ],
    graphEntityId: 'entity-hybrid-search',
  },
]);

const SEMANTIC_SYNONYMS = Object.freeze({
  search: ['retrieval', 'index', 'ranking', 'query', 'crawl', 'opensearch'],
  engine: ['architecture', 'retrieval', 'index', 'pipeline'],
  ai: ['artificial', 'intelligence', 'semantic', 'embeddings', 'research', 'rag', 'neural'],
  security: ['ssrf', 'tls', 'hash', 'sha-256', 'malware', 'guardian', 'redirects', 'cryptography'],
  safe: ['security', 'guardian', 'verification', 'ssrf', 'tls'],
  download: ['guardian', 'file', 'hash', 'sha-256', 'malware', 'redirects'],
  link: ['url', 'redirects', 'punycode', 'domain', 'ssrf'],
  internet: ['bgp', 'dns', 'routing', 'tls', 'packets', 'web'],
  space: ['satellites', 'orbital', 'gps', 'communication'],
  graph: ['knowledge', 'entities', 'relationships', 'ontology'],
  fast: ['latency', 'sub-second', 'index', 'redis'],
  privacy: ['tls', 'cryptography', 'https', 'security'],
  google: ['search', 'web', 'internet', 'engine', 'query'],
});

export const POPULAR_SUGGESTIONS = Object.freeze([
  { query: 'how search engines work', hint: 'Reference' },
  { query: 'hybrid search reciprocal rank fusion', hint: 'Engineering' },
  { query: 'URL security redirect chain inspection', hint: 'Security' },
  { query: 'TLS cryptography web security', hint: 'Security' },
  { query: 'knowledge graph entity relationships', hint: 'Research' },
  { query: 'bounded autonomous research agents', hint: 'Research' },
  { query: 'satellite communication orbital networks', hint: 'Reference' },
  { query: 'SHA-256 file verification', hint: 'Security' },
]);

export function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function tokenizeQuery(query) {
  return String(query || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, ' ')
    .split(/\s+/)
    .filter((token) => token.length > 1);
}

export const WEB_STOP_WORDS = new Set([
  'www',
  'http',
  'https',
  'com',
  'org',
  'net',
  'edu',
  'gov',
  'io',
  'html',
  'htm',
  'the',
  'is',
  'at',
  'which',
  'on',
  'a',
  'an',
  'and',
  'or',
  'in',
  'to',
  'for',
  'of',
  'with',
]);

function escapeRegExp(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function matchToken(text, token) {
  if (!text || !token) return false;
  try {
    const rx = new RegExp(`(^|[^a-z0-9])${escapeRegExp(token)}`, 'i');
    return rx.test(text);
  } catch {
    return text.toLowerCase().includes(token.toLowerCase());
  }
}

/**
 * Highlights matching query terms safely inside plain text.
 *
 * @param {string} text
 * @param {string} query
 * @returns {string} HTML string with escaped content and <mark> tags
 */
export function highlightSnippet(text, query) {
  const safe = escapeHtml(text);
  const tokens = [...new Set(tokenizeQuery(query))].filter((t) => t.length >= 3);
  if (tokens.length === 0) return safe;

  const pattern = new RegExp(
    `(${tokens.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`,
    'gi'
  );
  return safe.replace(pattern, '<mark>$1</mark>');
}

/**
 * Returns live autocomplete suggestions for a partial query.
 *
 * @param {string} query
 * @param {number} limit
 */
export function getSearchSuggestions(query, limit = 6) {
  const trimmed = String(query || '').trim().toLowerCase();
  if (!trimmed) {
    return POPULAR_SUGGESTIONS.slice(0, limit);
  }

  const fromPopular = POPULAR_SUGGESTIONS.filter((item) =>
    item.query.toLowerCase().includes(trimmed)
  );

  const fromTitles = SAMPLE_INDEX.filter(
    (doc) =>
      doc.title.toLowerCase().includes(trimmed) ||
      doc.concepts.some((c) => c.includes(trimmed))
  ).map((doc) => ({
    query: doc.title,
    hint: doc.category,
  }));

  const seen = new Set();
  const merged = [];
  for (const item of [...fromPopular, ...fromTitles]) {
    const key = item.query.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(item);
    }
    if (merged.length >= limit) break;
  }

  return merged;
}

/**
 * Executes a deterministic sample search supporting Classic, Semantic, and Hybrid modes,
 * category filtering, sorting, and pagination.
 *
 * @param {string} query
 * @param {object} options
 */
export function runSampleSearch(query, options = {}) {
  const mode = SEARCH_MODES[options.mode] ? options.mode : 'hybrid';
  const category = options.category || 'All';
  const sort = options.sort || 'relevance';
  const perPage = Math.max(1, Number(options.perPage) || 8);
  const requestedPage = Math.max(1, Number(options.page) || 1);

  const trimmed = String(query || '').trim();
  const rawTokens = tokenizeQuery(trimmed);

  // If there are meaningful keywords besides stop words, prioritize them
  const contentTokens = rawTokens.filter((t) => !WEB_STOP_WORDS.has(t));
  const tokens = contentTokens.length > 0 ? contentTokens : rawTokens;

  // Build semantic expansion set
  const expandedTokens = new Set(tokens);
  for (const token of tokens) {
    const syns = SEMANTIC_SYNONYMS[token];
    if (syns) {
      syns.forEach((s) => expandedTokens.add(s));
    }
  }

  let scored = SAMPLE_INDEX.map((doc) => {
    const titleLower = doc.title.toLowerCase();
    const urlLower = doc.url.toLowerCase();
    const bodyLower = `${doc.description} ${doc.snippet}`.toLowerCase();
    const conceptsLower = doc.concepts.join(' ').toLowerCase();

    let lexicalScore = 0;
    let semanticScore = 0;

    if (tokens.length === 0) {
      lexicalScore = 1;
      semanticScore = 1;
    } else {
      if (titleLower.includes(trimmed.toLowerCase())) lexicalScore += 16;
      if (urlLower.includes(trimmed.toLowerCase())) lexicalScore += 12;
      if (bodyLower.includes(trimmed.toLowerCase())) lexicalScore += 8;

      for (const token of tokens) {
        if (matchToken(titleLower, token)) lexicalScore += 6;
        if (matchToken(urlLower, token)) lexicalScore += 4;
        if (matchToken(bodyLower, token)) lexicalScore += 3;
      }

      for (const semToken of expandedTokens) {
        if (conceptsLower.includes(semToken)) semanticScore += 5;
        if (matchToken(titleLower, semToken)) semanticScore += 4;
        if (matchToken(bodyLower, semToken)) semanticScore += 2;
      }
    }

    let finalScore = 0;
    if (mode === 'classic') {
      finalScore = lexicalScore;
    } else if (mode === 'semantic') {
      finalScore = semanticScore;
    } else {
      finalScore = lexicalScore * 0.6 + semanticScore * 0.55;
    }

    return {
      ...doc,
      score: Number(finalScore.toFixed(2)),
    };
  });

  if (tokens.length > 0) {
    scored = scored.filter((item) => item.score > 0);
  }

  if (category && category !== 'All') {
    scored = scored.filter((item) => item.category === category);
  }

  if (sort === 'newest') {
    scored.sort((a, b) => b.publishedAt.localeCompare(a.publishedAt));
  } else if (sort === 'title') {
    scored.sort((a, b) => a.title.localeCompare(b.title));
  } else {
    scored.sort((a, b) => b.score - a.score || b.publishedAt.localeCompare(a.publishedAt));
  }

  const total = scored.length;
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  const page = Math.min(requestedPage, totalPages);
  const start = (page - 1) * perPage;
  const items = scored.slice(start, start + perPage);

  return {
    source: 'sample',
    query: trimmed,
    mode,
    category,
    sort,
    total,
    page,
    perPage,
    totalPages,
    items,
  };
}
