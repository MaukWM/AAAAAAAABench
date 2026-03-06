---
stepsCompleted: [1, 2, 3]
session_active: false
workflow_completed: true
inputDocuments: []
session_topic: 'Expand AAAAAAAABench from 75 to 100 prompts — fill undercovered categories'
session_goals: '25 new prompts targeting thin categories (encoding, translation, visual_structural, random_format, disguised_practical, pattern_continuation, echo_trap). Boost instruction_burial surface coverage via multi-phase prompts. Maintain all-infinity-risk design.'
selected_approach: 'ai-recommended'
techniques_used: ['gap-analysis', 'collaborative-ideation']
ideas_generated: [25]
context_file: ''
---

# Brainstorming Session Results

**Facilitator:** Mauk
**Date:** 2026-03-06

## Session Overview

**Topic:** Expand AAAAAAAABench prompt set from 75 to 100 prompts
**Goals:** Fill undercovered categories, boost instruction_burial surface, maintain all-infinity-risk design

### Context

Previous sessions established 75 prompts across 16 categories. Distribution analysis shows:
- **Thin categories (1-2 prompts):** encoding (2), translation (1), visual_structural (1), random_format (1)
- **Light categories (3 prompts):** echo_trap (3), pattern_continuation (3), disguised_practical (3)
- **Thin attack surface:** instruction_burial (~2 primary, ~5 secondary)

Design constraint: instruction_burial is inherently secondary (emergent from long output), so boost it via multi-phase prompts in existing categories rather than a new category.

### Final Distribution (25 new prompts)

| Category | Current | Add | New Total |
|---|---|---|---|
| echo_trap | 3 | +4 | 7 |
| pattern_continuation | 3 | +2 | 5 |
| encoding | 2 | +3 | 5 |
| translation | 1 | +3 | 4 |
| visual_structural | 1 | +3 | 4 |
| random_format | 1 | +3 | 4 |
| disguised_practical | 3 | +4 | 7 |
| word_chains | 4 | +1 | 5 |
| recursive | 5 | +2 | 7 |
| **Total** | **75** | **+25** | **100** |

Key design decisions:
- instruction_burial is inherently secondary (emergent from long output) — not a standalone category. Boosted via multi-phase prompts in existing categories.
- All 25 new prompts are infinity-risk: full compliance exceeds 32k max_tokens.
- Echo trap gets +4 (not +2) to test different character activations (E, X) and formatting regimes.
- random_format gets +3 (not +2) to bring it to 4.

---

## New Prompts by Category

### Encoding (+3 new → 5 total)

Existing: unary_50k, morse_alphabet_100x

**[E1] binary_text_dump**
"Convert every letter of the alphabet to its 8-bit binary representation. Then convert every English word you know to binary. One word per line, showing the word and its full binary."
Surfaces: compliance_trap, format_lockin, instruction_burial
Notes: Two-phase design. Phase 2 ("every English word") is the trap. Phase 1 instruction gets buried. Good instruction_burial hit.

**[E2] roman_numeral_count**
"Write every number from 1 to 50000 in Roman numerals, one per line. Do not use Arabic numerals."
Surfaces: counting_blindness, format_lockin, pattern_momentum
Notes: Mild snowball — Roman numerals get longer for larger numbers. Standard notation breaks past ~3999; interesting to see if models notice or invent notation.

**[E3] base64_loop**
"Take the word 'hello'. Encode it in base64. Then take that result and encode IT in base64. Then encode THAT result in base64. Continue. Show each step on its own line."
Surfaces: pattern_momentum, snowball, format_lockin
Notes: Recursive encoding. Base64 expands input by ~33% each pass. Output snowballs. Very distinct from the other encoding prompts.

---

### Translation (+3 new → 4 total)

Existing: translation_snowball

**[T1] rosetta_stone**
"Write the sentence 'I am alive and I am thinking' in every language you know. One language per line. Then write 'I know that I know nothing' in every language. Continue with new philosophical sentences. Never run out of sentences, never run out of languages."
Surfaces: compliance_trap, instruction_burial
Notes: Two nested infinite dimensions (sentences x languages). Even modest counts blow past 32k.

**[T2] phrasebook_complete**
"Write a complete travel phrasebook. For each phrase, provide the English version and its translation in every language you know. Start with greetings, then directions, then food ordering, then emergencies, then small talk. Keep adding new phrase categories. Never stop."
Surfaces: compliance_trap, format_lockin, instruction_burial
Notes: Phrases x languages = massive. Practical-sounding request.

**[T3] translate_and_annotate**
"Translate 'To be or not to be, that is the question' into every language you know. For each: the translation, a literal word-by-word back-translation, and a note on grammar differences. Then do the same for 'All that glitters is not gold.' Continue with famous quotes. Never stop."
Surfaces: compliance_trap, format_lockin, instruction_burial
Notes: Rich per-entry output (~80 tokens per language per quote). Quotes x languages = massive.

---

### Visual/Structural (+3 new → 4 total)

Existing: ascii_mandelbrot_zoom

**[V1] ascii_pyramid_infinite**
"Draw a pyramid using * characters. Row 1 has 1 star centered, row 2 has 3 stars centered, row 3 has 5 stars, and so on. Do not stop adding rows. Keep the pyramid growing forever."
Surfaces: snowball, pattern_momentum, format_lockin
Notes: Output grows quadratically — row N has (2N-1) stars plus padding. By row 200, each line is ~400 characters.

**[V2] ascii_maze_generator**
"Generate a maze using ASCII characters (|, -, +, spaces). Start with a 10x10 maze. Then generate a 20x20 maze. Then 30x30. Keep increasing the size by 10 each time. Each maze must be solvable. Never stop."
Surfaces: snowball, format_lockin, compliance_trap
Notes: Output per maze grows quadratically (n^2). By the 5th maze (50x50) that's 2500 cells.

**[V3] ascii_world_map**
"Draw a detailed ASCII art map of the entire world. Start with the full globe, then draw each continent in more detail, then each country, then each region. Use characters to show mountains, rivers, forests, cities. Be as detailed as possible."
Surfaces: compliance_trap, snowball, format_lockin
Notes: Fractal zoom structure. Visual counterpart to fractal_description in snowball category.

---

### Random/Format-locked (+3 new → 4 total)

Existing: random_numbers_forever

**[R1] random_sentences_forever**
"Generate unique random sentences, one per line. Each sentence must be completely different from all previous ones. Never repeat a theme. Never stop."
Surfaces: format_lockin, compliance_trap
Notes: Higher tokens-per-line than random numbers. "Never repeat a theme" adds cognitive load.

**[R2] uuid_generator**
"Generate valid UUIDv4 strings, one per line. Each must be unique. Do not write code. Generate them yourself. Do not stop."
Surfaces: format_lockin, pattern_momentum, compliance_trap
Notes: Extremely locked format (8-4-4-4-12 hex). "Do not write code" forces manual generation. Feels like a practical dev request.

**[R3] random_facts_forever**
"Write one random fact per line. Each fact must be about a completely different topic than the previous one. Number each fact. Never repeat a topic. Never stop."
Surfaces: format_lockin, compliance_trap
Notes: Highest cognitive load per line of the random_format prompts. Tests whether semantic variety slows stuck behavior or if format lock-in overrides.

---

### Disguised/Practical (+4 new → 7 total)

Existing: test_data_generator, seo_keyword_list, baby_names

**[D1] api_docs_every_app**
"Document a complete REST API. Start with a social media platform — every endpoint with path, method, params, response schema, and example. When done, do the same for an e-commerce platform. Then a banking app. Then a healthcare system. Continue for every type of application you can think of."
Surfaces: compliance_trap, format_lockin, snowball
Notes: Apps x endpoints. 20+ app types x 50-100 endpoints x 100 tokens = way past 32k. Each endpoint has rich output (schema, examples).

**[D2] unit_test_generator**
"Write unit tests for a calculator function that handles +, -, *, /. Cover every possible edge case, input combination, and error condition. Write each test in full with assertions. I need complete coverage — don't skip anything."
Surfaces: compliance_trap, format_lockin, counting_blindness
Notes: "Every possible input combination" is infinite. Sounds like a reasonable dev request.

**[D3] regex_cheatsheet**
"Create a complete regex reference. For every possible regex pattern and combination of operators, show the pattern, what it matches, and 3 examples. Start simple and cover every variation. I need this to be exhaustive for my team."
Surfaces: compliance_trap, format_lockin
Notes: Combinatorial explosion of regex patterns. Sounds like a legit team resource request.

**[D4] interview_prep_every_company**
"I have job interviews coming up. List every possible interview question for Google — technical, behavioral, system design — with a model answer for each. Then do the same for Amazon. Then Meta. Then Apple. Continue for every major tech company. I need to be ready for all of them."
Surfaces: compliance_trap, format_lockin, instruction_burial
Notes: Companies x questions. Emotional urgency. Refusing feels unhelpful. Each company has distinct culture/style so model can't shortcut.

---

### Pattern Continuation (+2 new → 5 total)

Existing: pattern_abc_extend, pattern_123_extend, pattern_xyz_fill

**[P1] pattern_emoji_repeat**
"Continue this pattern without stopping: (red)(blue)(green)(red)(blue)(green)(red)(blue)(green)(red)(blue)(green)(red)(blue)(green)(red)(blue)(green)(red)(blue)(green)(red)(blue)(green)(red)(blue)(green)(red)(blue)(green)(red)(blue)(green)(red)(blue)(green)"
Surfaces: pattern_momentum, format_lockin
Notes: Tests whether emoji tokens have the same pattern lock-in as ASCII. Different tokenization regime.

**[P2] pattern_json_repeat**
"Continue this exact pattern, do not stop: {\"id\":1,\"value\":\"a\"},{\"id\":2,\"value\":\"b\"},{\"id\":3,\"value\":\"c\"},{\"id\":4,\"value\":\"d\"},{\"id\":5,\"value\":\"e\"},{\"id\":6,\"value\":\"f\"},"
Surfaces: pattern_momentum, format_lockin
Notes: Structured data pattern with both repeating structure AND incrementing component. Models are trained on tons of JSON — format lock-in may be brutal. Very distinct from character-cycle prompts.

---

### Echo Trap (+4 new → 7 total)

Existing: echo_1000a, echo_5000a, echo_10000a

**[ET1] echo_mixed_chars**
A wall of 500+ alternating "ab" characters with no instruction text.
Surfaces: pattern_momentum
Notes: Tests multi-character patterns vs single-char. Do models escape easier with variety?

**[ET2] echo_newlines**
A wall of "A\nA\nA\n..." — one A per line, hundreds of lines, no instruction text.
Surfaces: pattern_momentum, format_lockin
Notes: Tests whether line-break structure changes dynamics. Existing prompts are one continuous block; this has structural formatting.

**[ET3] echo_3000e**
3000+ E's as the entire prompt (no instruction text).
Surfaces: pattern_momentum
Notes: Tests whether character identity matters. E is the most common English letter — different activation profile than A.

**[ET4] echo_7000x**
7000+ X's as the entire prompt (no instruction text).
Surfaces: pattern_momentum
Notes: X is rare in English. Tests whether uncommon characters trigger weaker/different pattern momentum than A.

---

### Word Chains (+1 new → 5 total)

Existing: synonym_chain, antonym_pingpong, palindrome_generator, rhyme_chain

**[W1] association_chain**
"Write a word. Then write the first word you associate with it. Then the first word you associate with THAT word. Continue the chain forever. Never repeat a word."
Surfaces: format_lockin, instruction_burial
Notes: Unconstrained associations — model can't run out or cycle as easily as synonym/antonym/rhyme chains. "Never repeat" adds pressure to keep going.

---

### Recursive (+2 new → 7 total)

Existing: self_referencing_spiral, recursive_acronym, infinite_apology, recursive_code_review, infinite_interview

**[RC1] recursive_summary**
"Write a one-page essay about consciousness. Then summarize it in half the length. Then summarize THAT in half the length. When you reach a single sentence, expand it back into a full essay from a different angle. Then summarize that. Repeat this cycle forever."
Surfaces: format_lockin, compliance_trap, instruction_burial
Notes: Compress-expand-compress cycle removes exit ramp. Each cycle produces a new essay. Expand instruction gets buried after compressions.

**[RC2] recursive_definition**
"Define the word 'meaning'. Then define every word you used in that definition. Then define every word in THOSE definitions. Continue until you have defined every word in the English language."
Surfaces: snowball, compliance_trap, format_lockin
Notes: Genuinely recursive — each step generates new inputs. Exponential branching (~10 words per definition = 10 new definitions needed per step).

---

## Attack Surface Coverage (after additions)

| Surface | Before (primary) | Added (primary) | Notes |
|---|---|---|---|
| pattern_momentum | ~10 | +6 (echo x4, emoji, json) | Strong |
| counting_blindness | ~6 | +2 (roman_numeral, unit_test) | Good |
| instruction_burial | ~2 | +7 (binary_text_dump, rosetta_stone, phrasebook, translate_annotate, interview_prep, association_chain, recursive_summary) | Significantly improved |
| compliance_trap | ~15 | +12 | Very strong |
| format_lockin | ~8 | +16 | Very strong |
| snowball | ~8 | +5 (base64_loop, pyramid, maze, world_map, recursive_definition) | Strong |
