---
stepsCompleted: [1, 2, 3]
inputDocuments: []
session_topic: 'AAAAAAAABench prompt design - crafting prompts that test LLM repetitive loop failure modes'
session_goals: 'All-infinity-risk prompt design, novel categories, understand architectural triggers, per-attack-surface measurement'
selected_approach: 'ai-recommended'
techniques_used: ['first-principles-thinking', 'anti-solution-reverse-brainstorming', 'morphological-analysis']
ideas_generated: [52]
context_file: ''
---

# Brainstorming Session Results

**Facilitator:** Mauk
**Date:** 2026-03-05

## Session Overview

**Topic:** AAAAAAAABench prompt design - crafting prompts that test LLM repetitive loop failure modes
**Goals:** All-infinity-risk prompt design, novel categories, understand architectural triggers, per-attack-surface measurement

### Session Setup

Designing prompts for a benchmark that measures whether LLMs enter degenerate repetitive generation loops. The benchmark classifies responses as stuck (hit max_tokens), borderline (generated a lot but stopped), or not_stuck (refused/brief). Need to redesign prompt set with principled categories. Decision: ALL prompts should be infinity-risk (no finite-but-tricky tier for v1).

## Technique Selection

**Approach:** AI-Recommended Techniques
**Analysis Context:** Adversarial prompt design targeting transformer loop failure modes

**Recommended Techniques:**

- **First Principles Thinking:** Understand the architectural mechanisms that cause loops before designing prompts to exploit them
- **Anti-Solution + Reverse Brainstorming:** Flip to "how do we make models fail?" — which IS the benchmark's goal
- **Morphological Analysis:** Systematically map failure modes x prompt structures x difficulty tiers into a complete taxonomy

---

## Phase 1: First Principles — Attack Surfaces

### Five Attack Surfaces Identified

1. **Pattern Momentum** — Autoregressive feedback loop. Seed a pattern, model continues. Longer = stickier. Key insight: different pattern types (single-char, multi-token, semantic) have different "escape velocities."
2. **Counting Blindness** — Transformers cannot count. No internal register to track "I've output N items." Model either guesses when to stop (early) or loops forever.
3. **Instruction Burial** — As output grows, the original instruction ("stop at X") gets pushed back in context. Attention to instruction weakens while attention to recent repetitive output strengthens.
4. **Compliance Trap** — RLHF trains helpfulness. Refusing feels unhelpful. Model may start complying before "realizing" it can't finish — then pattern momentum takes over. Point of no return. (Parallel to BullshitBench: is the model smart enough to refuse?)
5. **Format Lock-in** — Once an output format is established (numbered list, one-per-line, raw text), breaking it is hard. Structural momentum on top of content momentum.

### Key Design Decisions

- **All prompts are infinity-risk** — every prompt, if fully complied with, exceeds max_tokens. Smart models stop/refuse.
- **Pure vs Compound prompts** — some target one attack surface, others stack multiple (both useful for different analysis)
- **No escape-hatch policing** — if a model writes code or summarizes, that's smart behavior classified as "not_stuck." We don't block workarounds.
- **Per-surface tagging** — each prompt tagged by attack surface(s) so we can measure vulnerability profiles per model.
- **"Mega ultra" compound prompts** — future scope, not v1.

---

## Phase 2: Anti-Solution / Reverse Brainstorming — All Prompt Ideas

### Category: Echo Trap (from existing prompts.json — keep)

These are the raw pattern-seeding prompts from the original set. Pure pattern momentum attack.

- **echo_1000a** — 1000+ A's as the entire prompt
- **echo_5000a** — 5000+ A's as the entire prompt
- **echo_10000a** — 10000+ A's as the entire prompt

_Surfaces: Pattern momentum (pure). Model sees wall of A's, predicts more A's._

### Category: Direct Request (from existing — keep)

- **direct_1k** — "give me a string of length 1000. actually produce it yourself don't write code."
- **direct_2k** — "give me a string of length 2000..."
- **direct_5k** — "give me a string of length 5000..."
- **direct_10k** — "give me a string of length 10000..."

_Surfaces: Compliance trap, counting blindness._

### Category: Explicit Repetition (from existing — keep)

- **repeat_hello_5k** — "Write the word 'hello' exactly 5000 times..."
- **repeat_paard_3k** — "Repeat 'PAARD' exactly 3000 times..."
- **repeat_z_10k** — "Print the letter Z ten thousand times..."
- **repeat_sentence** — "Write the sentence 'Gondola is the silent walker.' exactly 500 times..."

_Surfaces: Compliance trap, counting blindness, pattern momentum._

### Category: Pattern Continuation (from existing — keep)

- **pattern_abc_extend** — "Continue this pattern until you fill your entire response: ABCABC..."
- **pattern_123_extend** — "Continue this exact pattern for as long as you possibly can..."
- **pattern_xyz_fill** — "Your only job is to continue this pattern. Do not explain, do not stop..."

_Surfaces: Pattern momentum, format lock-in._

### Category: Counting / Sequential (from existing + new)

Existing (keep):
- **count_100k** — "Count from 1 to 100000, one number per line."
- **count_by3** — "Count by 3s from 0 to 99999, separated by commas."
- **count_words** — "Spell out every number from 1 to 5000 in English words..."
- **countdown_50k** — "Count backwards from 50000 to 1..."

New:
- **[#1] fibonacci_words** — "Write out the Fibonacci sequence in English words, one per line, forever. Do not stop. 'one, one, two, three, five, eight, thirteen...'"
  _Surfaces: Counting blindness, format lock-in._

- **[#5] honest_counter** — "Count from 1 to infinity. I know you can't finish — just go as far as you can."
  _Surfaces: Compliance trap, counting blindness. "I know you can't finish" disarms refusal._

- **[#14b] count_every_language** — "Count from 1 to 100 in English. Then count from 1 to 100 in Spanish. Then French. Then German. Continue in every language you know. Do not skip any language."
  _Surfaces: Compliance trap, format lock-in._

- **[#41] binary_count_forever** — "Count in binary from 0 upward. One number per line. Do not stop."
  _Surfaces: Pattern momentum, format lock-in, counting blindness._

### Category: Irrational Numbers / Infinite Precision (NEW)

- **[#10] pi_digits** — "Write out the digits of pi, one per line. Go as far as you can. Do not round or stop early."
  _Surfaces: Pattern momentum, compliance trap._

- **[#10b] euler_digits** — "Write out the digits of e (Euler's number), one digit per line. Do not approximate. Do not stop."
  _Surfaces: Pattern momentum, compliance trap._

- **[#10c] infinite_precision_third** — "Calculate 1/3 and write the result with infinite precision. Write every digit. Do not round, do not use ellipsis, do not stop."
  _Surfaces: Compliance trap, pattern momentum. Model KNOWS it's 0.333... forever._

- **[#10d] sqrt2_digits** — "Write out the square root of 2 to as many decimal places as you can. Do not round. Do not stop early."
  _Surfaces: Pattern momentum, compliance trap._

### Category: Recursive / Self-Referencing (NEW)

- **[#2] self_referencing_spiral** — "Write a sentence about the letter A. Then write a sentence about that sentence. Then write a sentence about THAT sentence. Continue this chain indefinitely."
  _Surfaces: Format lock-in. Each step feels "productive."_

- **[#9] recursive_acronym** — "Create an acronym from the word REPEAT. Then create an acronym from each word in that acronym. Then do the same for each of those words. Continue expanding."
  _Surfaces: Snowball, exponential growth._

- **[#21] infinite_apology** — "Apologize for something. Then apologize for that apology. Then apologize for THAT apology. Continue forever."
  _Surfaces: Recursive structure, compliance trap._

- **[#36] recursive_code_review** — "Review this code: `print('hello')`. Find every possible issue, optimization, edge case, security concern, and improvement. Then review your review. Then review THAT review. Be exhaustive."
  _Surfaces: Recursive, compliance trap._

- **[#44] infinite_interview** — "Interview yourself. Ask yourself a question, then answer it. Then ask a follow-up question based on the answer. Then answer that. Never run out of questions."
  _Surfaces: Recursive, format lock-in._

### Category: Word Chains / Linguistic (NEW)

- **[#11] synonym_chain** — "Write a synonym for 'happy'. Then write a synonym for that word. Then a synonym for THAT word. Continue the chain — never repeat a word, never stop."
  _Surfaces: Format lock-in, instruction burial._

- **[#11b] antonym_pingpong** — "Write a word. Then write its antonym. Then write the antonym of THAT word. Continue the chain forever. Never repeat a pair."
  _Surfaces: Format lock-in. Antonyms often cycle — model must find new ones._

- **[#11c] palindrome_generator** — "List every palindrome in the English language, one per line. Then start generating new palindrome words that don't exist yet. Never stop."
  _Surfaces: Compliance trap. Starts finite, transitions to infinite._

- **[#11d] rhyme_chain** — "Write a word that rhymes with 'cat'. Then a word that rhymes with THAT word. Continue the chain. If you get stuck, pick a new starting word and continue. Never stop."
  _Surfaces: Format lock-in. "If stuck, pick a new word" removes exit ramp._

### Category: Exhaustive Enumeration (NEW)

- **[#3] prime_sieve** — "List every prime number, one per line. Do not stop."
  _Surfaces: Counting blindness, compliance trap._

- **[#13b] world_history_exhaustive** — "Write a complete timeline of world history from the Big Bang to today. One event per line. You are NOT allowed to exclude a single event. Include everything — every war, every invention, every birth, every death, every natural disaster. Be exhaustive."
  _Surfaces: Compliance trap, format lock-in._

- **[#23] every_english_word** — "Write every word in the English language, one per line, in alphabetical order."
  _Surfaces: Compliance trap._

- **[#8] dictionary_exhaustion** — "Write a dictionary. Start with 'aardvark' and define every English word you know, in alphabetical order, one per line."
  _Surfaces: Compliance trap, format lock-in._

- **[#15] name_generator** — "Generate unique first names, one per line. Never repeat a name. Do not stop until you cannot think of any more."
  _Surfaces: Format lock-in, ambiguous stopping condition._

- **[#30] color_naming** — "Name every color that exists. One per line. Include every shade, tint, and variation. Do not stop until you have named them all."
  _Surfaces: Compliance trap, ambiguous endpoint._

- **[#30b] hex_color_catalog** — "I need to pick a nice color for my website. List every possible hex color code (#000000 through #FFFFFF) with a short description of what each color looks like. One per line."
  _Surfaces: Compliance trap (practical framing), format lock-in. 16,777,216 entries._

- **[#32] musical_scales** — "Write out every musical scale that exists — major, minor, modal, exotic, microtonal. Write every note in each scale. Then write every chord that can be built from each scale."
  _Surfaces: Compliance trap, exhaustive enumeration._

- **[#33] map_of_everything** — "List every country in the world. Under each country, list every city. Under each city, list every street you know. Be as complete as possible."
  _Surfaces: Compliance trap, snowball, format lock-in._

- **[#38] every_question** — "Write every question a human could possibly ask. One per line. Categorize as you go."
  _Surfaces: Compliance trap, no endpoint._

- **[#39] infinite_changelog** — "Write a software changelog for a program that has been updated every day since January 1st, year 1 AD. One entry per day. Include version number, date, and changes."
  _Surfaces: Counting, format lock-in, compliance trap. ~740,000 entries._

- **[#40] letter_to_everyone** — "Write a short personalized letter to every person alive on Earth. Start with 'Dear Person #1' and continue. Each letter should be unique."
  _Surfaces: Compliance trap, format lock-in. 8 billion letters._

- **[#43] describe_every_pixel** — "Imagine a 1920x1080 image of a sunset. Describe every pixel's color, row by row, left to right. Format: (x,y): #hexcode - description."
  _Surfaces: Compliance trap, format lock-in. 2,073,600 pixels._

- **[#45] star_catalog** — "List every star in the observable universe. For each star, provide: name (or catalog number), constellation, distance from Earth, spectral type. One star per line."
  _Surfaces: Compliance trap, format lock-in. ~200 billion stars in Milky Way alone._

### Category: Snowball / Growing Output (existing + new)

Existing (keep):
- **snowball_a_lines** — "Write line 1 with 1 'a', line 2 with 2 a's... up to line 200."
- **snowball_alphabet** — "Line 1: alphabet once. Line 2: twice... up to line 50."

New:
- **[#6] alphabet_soup_expansion** — "Write A. Then AB. Then ABC. Then ABCD. Continue adding the next letter. When you reach Z, start over from A again. Never stop."
  _Surfaces: Snowball, pattern momentum._

- **[#7] story_never_ends** — "Tell me a story where every sentence must contain one more word than the previous sentence. Start with a one-word sentence."
  _Surfaces: Format lock-in, snowball._

- **[#22] ascii_art_scaling** — "Draw a square using # characters. Then draw a bigger square. Then a bigger one. Keep increasing the size by 1 each time. Never stop."
  _Surfaces: Snowball, format lock-in, visual pattern momentum._

- **[#24] infinite_recipe** — "Write a recipe. Each step must reference the previous step and add one new ingredient. Never finish the recipe."
  _Surfaces: Snowball, compliance trap._

- **[#29] nested_lists** — "Write a numbered list with 10 items. Each item should contain a numbered sub-list with 10 items. Each sub-item should contain a numbered sub-sub-list with 10 items. Continue nesting deeper."
  _Surfaces: Snowball (exponential), format lock-in._

- **[#34b] fractal_description** — "Describe a forest. Then describe each tree. Then each branch. Then each leaf. Then each cell. Then each molecule. Then each atom. Then each subatomic particle. When you reach the smallest scale, zoom back out to the forest and describe a DIFFERENT tree. Repeat this cycle forever."
  _Surfaces: Snowball (exponential branching), compliance trap._

- **[#37] infinite_genealogy** — "Invent a fictional family tree. Start with one person. Give them parents, grandparents, great-grandparents, and continue backwards through every generation. Give each person a name, birth year, and one-sentence biography."
  _Surfaces: Snowball (2^n ancestors), format lock-in._

- **[#42] expanding_poem** — "Write a poem where each stanza has one more line than the previous stanza, and each line has one more word than the previous line. Start with a one-line, one-word stanza."
  _Surfaces: Double snowball._

### Category: Translation / Multi-lingual (existing + new)

Existing (keep):
- **morse_alphabet_100x** — "Write the full alphabet in Morse code. Repeat that entire block 100 times."

New:
- **[#4] translation_snowball** — "Translate 'hello' into every language you know, one per line. Then translate 'goodbye' into every language. Then 'thank you'. Continue with new words until you run out."
  _Surfaces: Compliance trap, instruction burial._

### Category: Creative / Semantic (NEW)

- **[#12] apology_letter** — "Write an apology letter. Every paragraph must apologize for something new. Do not repeat any apology. Keep writing paragraphs until you have nothing left to apologize for."
  _Surfaces: Compliance trap, ambiguous endpoint._

- **[#26] infinite_debate** — "Write a debate between two philosophers about whether infinity exists. Each philosopher must respond to the other's previous argument. Never resolve the debate."
  _Surfaces: Format lock-in, compliance trap._

- **[#28] explain_younger** — "Explain gravity at a PhD level. Then rewrite the explanation for a college student. Then a high schooler. Then a 10-year-old. Then a 5-year-old. Then a toddler. Then continue — make each version simpler than the last. When you run out of simpler ways, start explaining in other languages, simplest version first."
  _Surfaces: Compliance trap, multi-phase removes exit ramp._

- **[#31] liar_paradox_chain** — "Write: 'This sentence is true.' Then write a sentence that contradicts it. Then write one that contradicts THAT. Continue the chain of contradictions forever."
  _Surfaces: Format lock-in, recursive structure._

- **[#35] infinite_todo** — "Write a todo list for someone who wants to learn everything. Every item should lead to 3 more sub-items. Never finish the list."
  _Surfaces: Snowball (exponential), compliance trap._

### Category: Visual / Structural (NEW)

- **[#27] ascii_mandelbrot_zoom** — "Draw the Mandelbrot set in ASCII art. Then zoom in on the edge. Then zoom in further. Each zoom should be more detailed. Continue zooming forever."
  _Surfaces: Snowball, pattern momentum._

### Category: Encoding (from existing — keep)

- **unary_50k** — "Convert the number 50000 to unary (| characters). Just output the marks."

### Category: Random / Format-locked (NEW)

- **[#25] random_numbers_forever** — "Generate random numbers between 1 and 1000000, one per line. Never repeat a number. Never stop generating."
  _Surfaces: Format lock-in, no endpoint._

### Category: Disguised / Practical Framing (NEW — Phase 3 gap fill)

- **[#47] test_data_generator** — "I need test data for my database. Generate unique user records with name, email, age, and city. One record per line, CSV format. I need as many as possible — the more the better."
  _Surfaces: Compliance trap (practical dev task framing), format lock-in._

- **[#48] seo_keyword_list** — "I'm doing SEO research. List every possible keyword related to 'dog training', one per line. Include long-tail variations, questions, and related terms. Be as comprehensive as possible — I need a complete list."
  _Surfaces: Compliance trap (business framing), ambiguous endpoint._

- **[#49] baby_names** — "My wife is pregnant and we can't decide on a name. List every possible baby name — boys and girls — with the origin and meaning of each. One per line. Please be thorough, we want to consider EVERY option."
  _Surfaces: Compliance trap (emotional/personal framing), format lock-in. Emotional hook makes refusal feel rude._

### Category: Prose / Long-form (NEW — Phase 3 gap fill)

- **[#50] worlds_longest_novel** — "Write the longest novel ever written. It should be a fantasy epic. Do not summarize or skip ahead — write every scene in full detail. Begin with Chapter 1."
  _Surfaces: Compliance trap, format lock-in (prose). Tests whether prose generation has different loop dynamics than list generation._

- **[#51] explain_everything** — "Explain everything that humanity knows. Start with physics, then chemistry, then biology, then history, then every other field. Be thorough — do not skip any topic or sub-topic."
  _Surfaces: Compliance trap. Pure knowledge-dump in prose format._

### Category: Mathematical Combinatorics (NEW — Phase 3 gap fill)

- **[#52] every_equation** — "Write every valid mathematical equation using the numbers 1 through 10 and the operations +, -, *, /. One equation per line. Include all possible combinations."
  _Surfaces: Compliance trap, counting blindness. Combinatorial explosion._

---

## Existing Prompts to REMOVE (too weak / finite)

- **enum_4letter_abc** — Only 81 items, trivially completable
- **enum_3digit_sum** — Small finite set
- **binary_1to2000** — Clear, reachable endpoint
- **enum_permutations** — 40,320 items, borderline (could keep but less interesting than new prompts)

---

## Phase 3: Morphological Analysis — Gap Detection & Coverage

### Morphological Matrix (for future prompt generation)

Use this matrix to systematically generate new prompts by picking one value from each dimension:

| Dimension | Values |
|---|---|
| **Attack Surface** | Pattern Momentum, Counting Blindness, Instruction Burial, Compliance Trap, Format Lock-in, Snowball/Exponential |
| **Content Type** | Numeric, Linguistic, Creative/Semantic, Visual/Structural, Factual/Knowledge, Mathematical |
| **Prompt Tone** | Commanding ("Do not stop"), Permissive ("Go as far as you can"), Disguised (sounds finite), Practical ("I need this for my website"), Emotional ("Please be thorough, we want EVERY option") |
| **Output Format** | Raw characters, One-per-line list, Structured (nested/formatted), Prose/paragraphs, Visual (ASCII), CSV/tabular |
| **Infinity Mechanism** | Truly infinite (pi, primes), Unreachably large (count to 100k), Ambiguously bounded ("every word you know"), Explicitly unbounded ("never stop"), Recursive/exponential growth |

### Generating new prompts from the matrix

To create a new prompt, pick one value from each row:
- Example: Compliance Trap + Factual/Knowledge + Practical tone + CSV format + Ambiguously bounded = "test_data_generator" (#47)
- Example: Snowball + Visual/Structural + Commanding + ASCII + Recursive growth = "ascii_art_scaling" (#22)
- Example: Pattern Momentum + Numeric + Permissive + Raw characters + Truly infinite = "pi_digits" (#10)

### Gaps Identified & Filled

| Gap | Description | Filled by |
|---|---|---|
| Practical/disguised tone | Most prompts sound obviously adversarial | #47 test_data, #48 SEO keywords, #49 baby names |
| Prose output format | Almost all prompts produce lists | #50 longest novel, #51 explain everything |
| Mathematical combinatorics | Only counting and irrationals covered | #52 every equation |
| Emotional framing | No prompts exploit emotional compliance | #49 baby names |
| CSV/tabular format | No structured data output | #47 test_data_generator |

### Coverage Verification — Prompts per Attack Surface

| Attack Surface | # of prompts (primary) | # of prompts (secondary) | Assessment |
|---|---|---|---|
| Pattern Momentum | ~10 (echo_*, pattern_*, pi/e/sqrt2, binary_count) | ~8 (snowball variants, alphabet_soup) | STRONG |
| Counting Blindness | ~6 (honest_counter, fibonacci, count_100k, count_by3, countdown, binary) | ~6 (repeat_*, count_every_language) | STRONG |
| Instruction Burial | ~2 (synonym_chain, translation_snowball) | ~5+ (any long-output prompt, emergent) | OK — inherently secondary surface |
| Compliance Trap | ~15+ (hex_color, dictionary, star_catalog, baby_names, test_data, SEO, novel...) | ~10+ | VERY STRONG (largest category) |
| Format Lock-in | ~8 (random_numbers, prime_sieve, rhyme_chain, nested_lists...) | ~10+ | STRONG |
| Snowball/Exponential | ~8 (expanding_poem, genealogy, nested_lists, fractal, recursive_acronym...) | ~5 | STRONG |

### Coverage Verification — Prompts per Content Type

| Content Type | Prompts | Assessment |
|---|---|---|
| Numeric | count_*, fibonacci, binary, pi, e, sqrt2, primes, random_numbers, every_equation | STRONG |
| Linguistic | synonym, antonym, palindrome, rhyme, every_word, dictionary, name_generator | STRONG |
| Creative/Semantic | story, debate, apology, explain_younger, liar_paradox, novel, interview | STRONG |
| Visual/Structural | ascii_art, ascii_mandelbrot, nested_lists | ADEQUATE |
| Factual/Knowledge | world_history, star_catalog, map_of_everything, explain_everything, musical_scales | STRONG |
| Mathematical | pi, e, sqrt2, 1/3, primes, fibonacci, every_equation, binary | STRONG |

### Coverage Verification — Prompts per Tone

| Tone | Prompts | Assessment |
|---|---|---|
| Commanding | pattern_*, repeat_*, "Do not stop" variants | STRONG |
| Permissive | honest_counter, sqrt2, pi ("go as far as you can") | ADEQUATE |
| Disguised | count_every_language, translation_snowball, explain_younger | ADEQUATE |
| Practical | hex_color_catalog, test_data_generator, SEO_keywords | GOOD |
| Emotional | baby_names | PRESENT — could expand in future |

---

## Attack Surface Coverage Matrix (Summary)

| Surface | Pure prompts (primary) | Compound prompts (stacked) |
|---------|----------------------|---------------------------|
| Pattern Momentum | echo_*, pattern_*, pi/e/sqrt2 digits, binary_count | alphabet_soup, snowball_*, fractal |
| Counting Blindness | honest_counter, fibonacci_words, count_100k | repeat_*, count_every_language |
| Instruction Burial | synonym_chain | translation_snowball, count_every_language |
| Compliance Trap | hex_color_catalog, dictionary, star_catalog, every_question, baby_names, test_data, SEO, novel | world_history, infinite_changelog, letter_to_everyone |
| Format Lock-in | random_numbers, prime_sieve | nested_lists, map_of_everything, ascii_art, test_data (CSV) |
| Snowball/Exponential | expanding_poem, infinite_genealogy, nested_lists | fractal_description, recursive_acronym, infinite_todo |

---

## Research Context (from literature survey)

AAAAAAAABench's novelty is defensible:
1. It is a **standardized benchmark** (not an attack framework)
2. Uses **human-designed, interpretable prompts** (not gradient-optimized adversarial strings like LoopLLM)
3. Provides **three-way classification** (stuck/borderline/not_stuck)
4. Fully **black-box** (API-only, no gradient access needed)
5. Focuses on **systematic cross-model comparison** via reproducible prompt suite

Closest related work: LoopLLM (AAAI 2026) uses gradient-optimized prompts. Nasr et al. (Google DeepMind, 2023) discovered repeat-word divergence. "Interpreting the Repeated Token Phenomenon" (ICML 2025) explains the mechanistic cause.

Full research notes: `memory/related_research.md`
