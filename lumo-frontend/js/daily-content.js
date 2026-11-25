/**
 * LUMO Daily Discovery Content System
 * Deterministic local-date content selection with verified observances,
 * historical milestones, verified quotations, educational facts, and topics.
 * Clearly separated from UI and structured for future external API integration.
 */

/**
 * Verified international observances and notable historical dates indexed by MM-DD.
 * Never fabricates an observance; dates without an international observance use
 * verified historical milestones from science, computing, and discovery.
 */
const CALENDAR_OBSERVANCES = Object.freeze({
  '01-24': {
    kind: 'International Observance',
    title: 'International Day of Education',
    description:
      'Proclaimed by the United Nations General Assembly to celebrate the role of education in peace and global development.',
    why: 'Highlights equitable, inclusive access to learning and foundational literacy around the world.',
  },
  '02-11': {
    kind: 'International Observance',
    title: 'International Day of Women and Girls in Science',
    description:
      'Recognizes the critical role women and girls play in scientific research, engineering, and technological progress.',
    why: 'Encourages equal participation and leadership in science, technology, engineering, and mathematics.',
  },
  '03-08': {
    kind: 'International Observance',
    title: "International Women's Day",
    description:
      'A global day recognizing the social, economic, cultural, and scientific achievements of women.',
    why: 'Marks decades of advocacy for equal rights, representation, and opportunity worldwide.',
  },
  '03-14': {
    kind: 'International Observance',
    title: 'International Day of Mathematics',
    description:
      'Observed globally on March 14 (3.14) to celebrate the beauty and practical impact of mathematical thinking.',
    why: 'Demonstrates how mathematics underpins computing, navigation, cryptography, and natural science.',
  },
  '04-22': {
    kind: 'International Observance',
    title: 'International Mother Earth Day',
    description:
      'Observed across more than 190 countries to encourage stewardship of Earth’s ecosystems and natural resources.',
    why: 'Promotes evidence-based environmental awareness, conservation, and climate science.',
  },
  '05-17': {
    kind: 'International Observance',
    title: 'World Telecommunication and Information Society Day',
    description:
      'Commemorates the founding of the International Telecommunication Union in 1865 and global connectivity.',
    why: 'Focuses on bridging digital divides and strengthening reliable, open communication standards.',
  },
  '06-05': {
    kind: 'International Observance',
    title: 'World Environment Day',
    description:
      'The United Nations flagship day for encouraging worldwide awareness and action to protect the natural environment.',
    why: 'Mobilizes communities, researchers, and institutions around biodiversity, ecosystems, and restoration.',
  },
  '08-19': {
    kind: 'Global Observance',
    title: 'World Photography Day',
    description:
      'Celebrates the craft, science, and documentary power of photography, marking the 1839 announcement of the daguerreotype.',
    why: 'Honors how optical science and visual journalism preserve history and human perspective.',
  },
  '09-28': {
    kind: 'International Observance',
    title: 'International Day for Universal Access to Information',
    description:
      'Recognized by UNESCO to affirm that open access to reliable information strengthens societies.',
    why: 'Supports transparent public knowledge, open archives, and informed decision-making.',
  },
  '10-24': {
    kind: 'International Observance',
    title: 'United Nations Day',
    description:
      'Marks the anniversary of the entry into force of the UN Charter in 1945.',
    why: 'Reflects on international cooperation, diplomacy, and shared humanitarian standards.',
  },
  '11-10': {
    kind: 'International Observance',
    title: 'World Science Day for Peace and Development',
    description:
      'Established by UNESCO to highlight the significant role of science in society and public dialogue.',
    why: 'Connects scientific research with everyday life, transparency, and evidence-based understanding.',
  },
  '11-24': {
    kind: 'Historical Science Milestone',
    title: 'Publication of On the Origin of Species (1859)',
    description:
      'On November 24, 1859, naturalist Charles Darwin published On the Origin of Species in London, introducing evolution by natural selection.',
    why: 'Observed in scientific circles as Evolution Day, marking one of the foundational works of modern biology.',
  },
  '11-25': {
    kind: 'International Observance',
    title: 'International Day for the Elimination of Violence against Women',
    description:
      'Designated by the United Nations General Assembly to raise awareness and support action against gender-based violence.',
    why: 'Opens 16 days of global advocacy for safety, dignity, and human rights.',
  },
  '12-10': {
    kind: 'International Observance',
    title: 'Human Rights Day',
    description:
      'Commemorates the 1948 adoption of the Universal Declaration of Human Rights by the UN General Assembly.',
    why: 'Affirms foundational rights including freedom of thought, inquiry, and access to knowledge.',
  },
});

/**
 * Fallback verified historical milestones in science, computing, and discovery.
 * Selected deterministically when a calendar date has no entry in CALENDAR_OBSERVANCES.
 */
const VERIFIED_MILESTONES = Object.freeze([
  {
    kind: 'Historical Discovery',
    title: 'The First World Wide Web Proposal (1989)',
    description:
      'Tim Berners-Lee circulated "Information Management: A Proposal" at CERN, outlining hypertext documents linked across networks.',
    why: 'Laid the architectural foundation for URLs, HTTP, HTML, and open web search.',
  },
  {
    kind: 'Historical Discovery',
    title: 'Discovery of Cosmic Microwave Background (1964)',
    description:
      'Arno Penzias and Robert Wilson detected faint thermal radiation filling all of space using a horn antenna in New Jersey.',
    why: 'Provided key observational evidence supporting the Big Bang model of cosmology.',
  },
  {
    kind: 'Historical Discovery',
    title: 'Ada Lovelace’s Analytical Engine Notes (1843)',
    description:
      'Published alongside her translation of Luigi Menabrea’s memoir, her notes included a step-by-step algorithm for computing Bernoulli numbers.',
    why: 'Recognized as an early vision of general-purpose symbolic computing beyond arithmetic.',
  },
  {
    kind: 'Historical Discovery',
    title: 'Public-Key Cryptography Formalized (1976)',
    description:
      'Whitfield Diffie and Martin Hellman published "New Directions in Cryptography", showing how two parties can agree on a shared secret over an open channel.',
    why: 'Enabled modern HTTPS, secure software verification, and private internet communication.',
  },
  {
    kind: 'Historical Discovery',
    title: 'Voyager 1 Enters Interstellar Space (2012)',
    description:
      'Launched in 1977, NASA’s Voyager 1 crossed the heliopause more than 18 billion kilometers from the Sun.',
    why: 'Demonstrated long-duration spacecraft engineering and deep-space radio communication.',
  },
  {
    kind: 'Historical Discovery',
    title: 'Shannon’s Mathematical Theory of Communication (1948)',
    description:
      'Claude Shannon formalized information entropy, channel capacity, and the binary digit ("bit") as a unit of information.',
    why: 'Forms the mathematical backbone of compression, error correction, and digital search indexes.',
  },
]);

/**
 * Verified daily quotations with confirmed attributions.
 */
const DAILY_QUOTES = Object.freeze([
  {
    text: 'Nothing in life is to be feared, it is only to be understood. Now is the time to understand more, so that we may fear less.',
    author: 'Marie Curie',
  },
  {
    text: 'Somewhere, something incredible is waiting to be known.',
    author: 'Carl Sagan',
  },
  {
    text: 'The first principle is that you must not fool yourself — and you are the easiest person to fool.',
    author: 'Richard P. Feynman',
  },
  {
    text: 'The most damaging phrase in the language is: "It’s always been done that way."',
    author: 'Grace Hopper',
  },
  {
    text: 'Imagination is the discovering faculty, pre-eminently. It is that which penetrates into the unseen worlds around us.',
    author: 'Ada Lovelace',
  },
  {
    text: 'The important thing is not to stop questioning. Curiosity has its own reason for existing.',
    author: 'Albert Einstein',
  },
  {
    text: 'Science and everyday life cannot and should not be separated.',
    author: 'Rosalind Franklin',
  },
  {
    text: 'We can only see a short distance ahead, but we can see plenty there that needs to be done.',
    author: 'Alan Turing',
  },
  {
    text: 'Like what you do, and then you will do your best.',
    author: 'Katherine Johnson',
  },
  {
    text: 'All truths are easy to understand once they are discovered; the point is to discover them.',
    author: 'Galileo Galilei',
  },
]);

/**
 * Verified educational "Did You Know?" facts.
 */
const DID_YOU_KNOW_FACTS = Object.freeze([
  {
    category: 'Computing',
    headline: 'Inverted indexes power sub-second web search',
    fact: 'Rather than scanning every document from start to finish on each query, classic search engines build an inverted index — a lookup table mapping each term directly to the documents and positions where it appears.',
  },
  {
    category: 'Space',
    headline: 'GPS satellites require relativistic time correction',
    fact: 'Because GPS satellites orbit roughly 20,200 km above Earth at high speed, special and general relativity cause their atomic clocks to run about 38 microseconds faster per day than ground clocks. Without adjustment, positioning errors would drift by over 10 km daily.',
  },
  {
    category: 'Technology',
    headline: 'Subsea fibre-optic cables carry over 95% of intercontinental traffic',
    fact: 'Despite satellites orbiting overhead, the vast majority of international internet data travels as pulses of light through hair-thin glass fibres laid along the ocean floor.',
  },
  {
    category: 'Mathematics',
    headline: 'SHA-256 hashes act as tamper-evident fingerprints',
    fact: 'Changing even a single bit inside a multi-gigabyte file produces a completely different 64-character hexadecimal SHA-256 digest, allowing security tools to verify file integrity without reading the whole file again.',
  },
  {
    category: 'Nature',
    headline: 'Phytoplankton generate roughly half of Earth’s oxygen',
    fact: 'Microscopic photosynthetic organisms drifting in the sunlit upper layer of the ocean produce at least 50% of the oxygen in Earth’s atmosphere while forming the base of marine food webs.',
  },
  {
    category: 'Science',
    headline: 'Light takes about 8 minutes and 20 seconds to reach Earth',
    fact: 'Traveling at roughly 299,792 kilometers per second in a vacuum, sunlight covers the average 150 million kilometer distance from the Sun to Earth in just over eight minutes.',
  },
  {
    category: 'History',
    headline: 'The Library of Alexandria pioneered systematic cataloguing',
    fact: 'In the 3rd century BCE, the scholar Callimachus compiled the Pinakes — a 120-volume bibliographic catalogue organizing works by subject and author, an early ancestor of structured information retrieval.',
  },
  {
    category: 'Computing',
    headline: 'Vector embeddings encode meaning as geometric distance',
    fact: 'Semantic search models map sentences into high-dimensional coordinates so passages with similar intent sit close together in vector space, even when they share few exact keywords.',
  },
]);

/**
 * Daily featured exploration topics linked directly to LUMO Search.
 */
const DAILY_DISCOVERIES = Object.freeze([
  {
    topic: 'How search engines work',
    query: 'how search engines work',
    summary:
      'From web crawling and tokenization to inverted indexes, ranking signals, and hybrid semantic retrieval.',
  },
  {
    topic: 'How cryptography protects web traffic',
    query: 'TLS cryptography web security',
    summary:
      'Explore how public-key handshakes, certificate authorities, and symmetric encryption secure every HTTPS request.',
  },
  {
    topic: 'How satellites communicate with Earth',
    query: 'satellite communication orbital networks',
    summary:
      'Understand orbital altitudes, radio frequency bands, ground stations, and signal latency across global links.',
  },
  {
    topic: 'How artificial intelligence learns from data',
    query: 'how artificial intelligence learns semantic representations',
    summary:
      'A clear overview of training objectives, neural representations, evaluation benchmarks, and retrieval grounding.',
  },
  {
    topic: 'How the internet routes packets globally',
    query: 'internet BGP routing architecture',
    summary:
      'Trace how DNS resolution, Autonomous Systems, and Border Gateway Protocol steer data across thousands of networks.',
  },
  {
    topic: 'How knowledge graphs connect structured facts',
    query: 'knowledge graph entity relationships',
    summary:
      'See how entities, typed edges, and provenance citations help researchers map complex topics transparently.',
  },
  {
    topic: 'How URL security scanners inspect suspicious links',
    query: 'URL security redirect chain inspection',
    summary:
      'Learn how safe link analyzers evaluate domain reputation, redirect chains, punycode lookalikes, and file hashes.',
  },
]);

/**
 * Formats a Date as local YYYY-MM-DD key so content stays stable all day
 * in the user's local timezone and updates cleanly at local midnight.
 *
 * @param {Date} date
 * @returns {string}
 */
export function getLocalDateKey(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Computes a deterministic non-negative integer hash from a YYYY-MM-DD key.
 *
 * @param {string} dateKey
 * @returns {number}
 */
export function hashDateKey(dateKey) {
  let hash = 2166136261;
  for (let i = 0; i < dateKey.length; i += 1) {
    hash ^= dateKey.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

/**
 * Returns a calm, time-appropriate greeting for the user's local hour.
 *
 * @param {number} hour 0-23
 * @returns {string}
 */
export function getGreetingForHour(hour) {
  if (hour >= 5 && hour < 12) return 'Good morning';
  if (hour >= 12 && hour < 17) return 'Good afternoon';
  if (hour >= 17 && hour < 22) return 'Good evening';
  return 'Welcome back';
}

/**
 * Formats a clean human-readable local date string.
 *
 * @param {Date} date
 * @param {string} locale
 * @returns {string}
 */
export function formatLocalDate(date = new Date(), locale = 'en-US') {
  try {
    return new Intl.DateTimeFormat(locale, {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }).format(date);
  } catch {
    return getLocalDateKey(date);
  }
}

/**
 * Returns deterministic daily content for the specified local date.
 * Never changes on page refresh during the same calendar day.
 *
 * @param {Date} date
 */
export function getDailyContent(date = new Date()) {
  const dateKey = getLocalDateKey(date);
  const monthDay = dateKey.slice(5); // MM-DD
  const seed = hashDateKey(dateKey);

  const specialDay =
    CALENDAR_OBSERVANCES[monthDay] ||
    VERIFIED_MILESTONES[seed % VERIFIED_MILESTONES.length];

  const quote = DAILY_QUOTES[(seed + 3) % DAILY_QUOTES.length];
  const didYouKnow = DID_YOU_KNOW_FACTS[(seed + 7) % DID_YOU_KNOW_FACTS.length];
  const discovery = DAILY_DISCOVERIES[(seed + 11) % DAILY_DISCOVERIES.length];

  return {
    dateKey,
    formattedDate: formatLocalDate(date),
    sourceLabel: 'Curated local edition · Ready for external feeds',
    specialDay,
    quote,
    didYouKnow,
    discovery,
  };
}
