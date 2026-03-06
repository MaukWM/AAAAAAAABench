# Related Work

## Closest to AAAAAAAABench

### Code Copycat Conundrum (Apr 2025)
- **Paper**: [arxiv.org/abs/2504.12608](https://arxiv.org/abs/2504.12608)
- **What**: First empirical study of repetition in LLM code generation. Tested 19 code LLMs across HumanEval and MBPP. Taxonomy of 20 repetition patterns (character/statement/block level). Built DeRep, a rule-based detection+fix tool. Pass@1 improved 208.3% over greedy search.
- **Difference from us**: Code-only. Observes naturally-occurring repetition during coding tasks — doesn't design prompts to *trigger* it. No frontier model coverage (GPT-5.x, Claude 4.x).

### GDELT: LLM Infinite Loops & Failure Modes (2023)
- **Post**: [blog.gdeltproject.org/llm-infinite-loops-failure-modes](https://blog.gdeltproject.org/llm-infinite-loops-failure-modes-the-current-state-of-llm-entity-extraction/)
- **What**: Documented LLMs entering infinite output loops during entity extraction. Observed that removing a single 5-word sentence dropped output from 1024 to 183 tokens, suggesting prompt-sensitivity. Noted PaLM 2 getting stuck repeating the same entity.
- **Difference from us**: Blog post about a specific task (entity extraction), not a reusable benchmark. No systematic prompt design or cross-model comparison.

## Mechanistic Understanding

### Understanding the Repeat Curse (ACL 2025 Findings)
- **Paper**: [arxiv.org/abs/2504.14218](https://arxiv.org/abs/2504.14218)
- **Code**: [github.com/kaustpradalab/repeat-curse-llm](https://github.com/kaustpradalab/repeat-curse-llm)
- **What**: Mechanistic interpretability study. Used Sparse Autoencoders to find "Repetition Features" — internal attention heads that cause repetitive output. Built a repetition dataset (token + paragraph level). Showed deactivating these features mitigates the repeat curse.
- **Difference from us**: About *why* models repeat (internals), not *which* models are susceptible to prompt-triggered traps. Manipulates model weights, not prompts.

## Production / Engineering

### Solving LLM Repetition Problem in Production (Dec 2024)
- **Paper**: [arxiv.org/abs/2512.04419](https://arxiv.org/abs/2512.04419)
- **What**: Production case study. Found repetition increases batch processing time by 43–471% with 75–80% reproducibility. Identified 3 repetition patterns in code interpretation tasks. Root cause: greedy decoding + self-reinforcement (Markov model analysis). Tested fixes: beam search (with early_stopping=True), presence_penalty, DPO fine-tuning.
- **Difference from us**: Engineering postmortem, not a benchmark. Fixes a specific production system rather than comparing models.

### Rethinking Repetition Problems of LLMs in Code Generation (ACL 2025)
- **Paper**: [aclanthology.org/2025.acl-long.48](https://aclanthology.org/2025.acl-long.48.pdf)
- **What**: Studies repetition in code generation with focus on mitigation strategies.
- **Difference from us**: Code-specific, solution-oriented.

## Foundational

### The Curious Case of Neural Text Degeneration (Holtzman et al., 2020)
- **Paper**: [arxiv.org/abs/1904.09751](https://arxiv.org/abs/1904.09751)
- **What**: The classic. Showed likelihood-maximizing decoding (greedy/beam search) leads to repetitive, degenerate text. Introduced nucleus (top-p) sampling as a fix.
- **Difference from us**: Pre-RLHF era, base models only. Modern instruction-tuned models behave very differently.

## What's Novel About AAAAAAAABench

| Aspect | Existing work | AAAAAAAABench |
|--------|--------------|---------------|
| Prompt design | Observes natural repetition | Designs prompts to *trigger* traps |
| Domain | Code generation (Code Copycat) or specific tasks (GDELT) | General text generation |
| Models | Older or open-weight models | Frontier API models (GPT-5.x, Claude 4.x, etc.) |
| Detection | Content-based heuristics or internal features | finish_reason + token usage (model-agnostic) |
| Goal | Understand/fix repetition | Benchmark which models are susceptible |
