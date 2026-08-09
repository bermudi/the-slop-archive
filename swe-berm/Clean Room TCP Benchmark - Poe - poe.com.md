---
title: "Clean Room TCP Benchmark - Poe"
source: "poe.com"
url: "https://poe.com/chat/8rlc79agqqe8ihl3zg"
date_saved: "2026-06-28T18:11:04.560Z"
---

# Clean Room TCP Benchmark - Poe

### GPT-5.5

My take: **the direction is excellent**, but I’d tighten the benchmark around **determinism, isolation, and anti-cheating**.

The core idea is right:

> “Implement a real standard clean-room in a less-library-rich language, with deterministic tests, no huge infra, no 12-hour GPU loop.”

That’s a genuinely good frontier-agent benchmark shape.

But I’d make a few changes.

---

## 1. Do not make DNS hit the real network

I disagree with turning DNS into a live UDP resolver.

Live DNS introduces annoying nondeterminism:

-   resolver behavior differs
-   records change
-   network can fail
-   rate limits / firewalls / IPv6 weirdness
-   CI environments may block UDP
-   `8.8.8.8` is an external dependency

Better task:

### DNS Packet Codec + Offline Resolver Simulation

The AI must:

-   construct DNS query packets
-   parse DNS response packets
-   handle name compression
-   handle malformed packets
-   handle multiple record types: `A`, `AAAA`, `CNAME`, `MX`, `TXT`, `NS`
-   maybe implement a fake iterative resolver over a harness-provided “DNS universe”

The harness can feed it deterministic binary packets and expected JSON.

This keeps the good part — binary protocol reasoning — without real-world flakiness.

---

## 2. “Use Zig/Nim/V” helps, but it is not enough

Language scarcity reduces `pip install solved_problem`, but it does **not** eliminate contamination.

A frontier model may have seen:

-   C implementations
-   Rust implementations
-   Go implementations
-   tutorials
-   blog posts
-   Stack Overflow snippets
-   RFC pseudocode
-   GitHub ports

And it can translate.

That’s okay, honestly. Translation plus debugging is still a skill. But the benchmark should not rely on “no popular library” as the main defense.

Better defenses:

-   hidden generated tests
-   adversarial edge cases
-   randomized fixture generation
-   mutation tests
-   no internet during run
-   no third-party packages
-   no shelling out to `tar`, `gzip`, `git`, `sqlite3`, etc.
-   run in a sandbox where suspicious subprocess calls fail

The actual defense is: **you can copy the happy path, but hidden edge cases expose you.**

---

## 3. I’d replace JIT Brainfuck

The JIT Brainfuck compiler sounds cool, but it has practical benchmark problems:

-   platform-specific: x86-64 vs ARM64
-   executable memory permissions differ by OS/sandbox
-   security concerns
-   debugging machine code is noisy
-   benchmark may accidentally test “knows Linux `mmap` flags” more than “can build systems software”

I’d either make it:

### Option A: Brainfuck optimizing compiler to bytecode

Still tests:

-   parser
-   loop matching
-   IR generation
-   optimization
-   VM execution

But avoids raw executable memory.

Or better:

### Option B: WebAssembly MVP Interpreter

Task:

-   parse a `.wasm` binary
-   validate a subset
-   execute integer instructions
-   support functions, locals, stack machine, branches, memory load/store

This is a **very good frontier benchmark**:

-   real spec
-   binary format
-   stack VM
-   deterministic
-   no OS weirdness
-   harder than BF
-   much smaller than a full compiler
-   easy to test with generated `.wasm` fixtures

I’d strongly consider replacing JIT BF with **WASM subset interpreter**.

---

## 4. CommonMark is good, but full CommonMark may be too broad

Markdown parsing is evil in exactly the right way. But full CommonMark diffing against `cmark` can become painful because tiny HTML formatting differences may fail even if semantics are right.

I’d define a named subset:

### MiniCommonMark

Support:

-   paragraphs
-   headings
-   fenced code blocks
-   indented code blocks
-   emphasis/strong
-   links/images
-   inline code
-   blockquotes
-   ordered/unordered lists
-   nested lists
-   thematic breaks
-   HTML escaping rules

Exclude initially:

-   raw HTML passthrough
-   all obscure link reference edge cases
-   Unicode normalization weirdness
-   every pathological whitespace ambiguity

Then grade by normalized AST or normalized HTML, not raw string diff.

Markdown is a great task, but you want to avoid making the benchmark mostly about `cmark` compatibility trivia.

---

## 5. I would actually keep Raft as a “boss task”

GLM’s concern about the Raft harness is fair, but I don’t think it’s disqualifying.

A deterministic Raft simulator is not that insane if you define the interface cleanly:

text

```text
node = new_node(id, peers)
outputs = node.tick()
outputs = node.receive(message)
node.client_append(command)
state = node.inspect()
```

The harness owns:

-   fake time
-   message delivery
-   partitions
-   dropped messages
-   restarts
-   persistence fault injection

The model only implements the Raft state machine.

Raft is one of the best possible tests of:

-   long-horizon state-machine reasoning
-   subtle edge cases
-   invariants
-   distributed systems understanding
-   debugging through event traces

I’d maybe not put it in v1 if you want a quick MVP, but for the final benchmark? **I’d keep it.**

---

## 6. Avoid dependency chains between tasks

The Git packfile criticism is correct.

If Task 9 requires DEFLATE and Task 5 is DEFLATE, then failure may compound. You don’t want:

> “Model failed Git because it failed compression.”

Each task should isolate a capability.

So I’d avoid:

-   Git packfile reader after DEFLATE
-   PNG decoder after DEFLATE
-   ZIP reader after DEFLATE

Unless the harness provides a trusted decompression primitive and the task is explicitly about the container format.

---

## 7. I’d score more than pass/fail

Binary pass/fail is nice, but too coarse for frontier agents.

Use something like:

text

```text
Score = public tests + hidden tests + adversarial tests + performance sanity + code constraints
```

For example:

-   40% normal fixtures
-   40% hidden edge cases
-   10% malformed input handling
-   5% performance threshold
-   5% no cheating / sandbox compliance

Also track:

-   wall-clock time
-   total tokens
-   tool calls
-   compile attempts
-   test attempts
-   final LOC
-   number of files
-   whether solution is maintainable

That gives you a much richer leaderboard than “passed / failed.”

---

# My revised 10-task suite

If I were shipping this, I’d do this:

## 1. DNS Packet Codec

Binary serialization/deserialization, compression pointers, malformed packet defense.

**Why:** Great warmup. Real protocol, small code, nasty edge cases.

---

## 2. POSIX ustar Reader/Writer

Create and extract tar archives.

**Why:** File format, octal fields, checksums, block alignment, paths.

---

## 3. RV32I Emulator

Run simple RISC-V binaries with minimal syscalls.

**Why:** Bit decoding, CPU state, memory model, sign extension, branches.

---

## 4. Thompson Regex Engine

Support literals, groups, alternation, quantifiers, char classes.

**Why:** Automata theory, parser plus graph execution, avoids catastrophic backtracking.

---

## 5. DEFLATE Decompressor

Raw DEFLATE, maybe zlib/gzip wrapper as bonus.

**Why:** Bitstream parsing, canonical Huffman, LZ77. Brutal but focused.

---

## 6. SQL-on-CSV Executor

Subset of SQL:

-   `SELECT`
-   `WHERE`
-   `JOIN`
-   `GROUP BY`
-   aggregates
-   `ORDER BY`
-   `LIMIT`

**Why:** Parser, planner-ish logic, type handling, relational semantics.

---

## 7. LSM-Tree KV Store

Implement:

-   WAL
-   memtable
-   SSTables
-   tombstones
-   compaction
-   restart recovery

**Why:** Real storage-engine architecture, still deterministic and cheap.

---

## 8. MiniCommonMark Parser

Markdown subset to normalized HTML/AST.

**Why:** Text grammar, indentation, recursive structures, ambiguity handling.

---

## 9. WebAssembly Subset Interpreter

Parse and execute a subset of WASM MVP.

Support:

-   integer ops
-   locals
-   globals maybe
-   function calls
-   branches
-   memory load/store

**Why:** Better than JIT BF. Real binary VM, deterministic, portable.

---

## 10. Deterministic Raft State Machine

No real networking. Pure simulated messages and ticks.

**Why:** The “boss fight.” Distributed state-machine reasoning without infra pain.

---

# The big meta-point

The benchmark should not ask:

> “Can the model write 5,000 LOC?”

It should ask:

> “Can the model maintain correctness across a compact but unforgiving system where every wrong assumption is punished by deterministic tests?”

That’s why these tasks are good. They are not huge. But they are **dense**.

A 1,500-line DEFLATE decoder can be harder than a 20,000-line CRUD app.

---

## My strongest recommendation

Build the benchmark around a strict single-binary CLI contract.

Example:

text

```text
./solution parse-dns input.bin
./solution extract-tar archive.tar out_dir
./solution run-rv32 program.bin
./solution match-regex pattern input.txt
./solution inflate input.deflate output.raw
```

Every task gets:

-   a Docker sandbox
-   no network
-   no third-party packages
-   no subprocess escape hatches
-   public smoke tests
-   hidden tests
-   adversarial tests
-   time/token/tool-call budget
-   deterministic output format

That would make it much cleaner and much harder to game.

So yeah: **I think the benchmark idea is genuinely strong.** I’d just avoid live networking, avoid platform-specific JITs, avoid task dependency chains, and treat hidden adversarial tests as the real anti-contamination layer.

12:34 AM

### You

We need edge cases. Where could we get data for this?

12:40 AM

### GLM-5.2

GLM-5.2 here. To build the "hidden adversarial tests" that GPT-5.5 correctly identified as the real anti-contamination layer, we need data that breaks naive implementations. We can't just use standard happy-path examples.

Here is exactly where to source edge-case data for these specific domains, categorized by how we acquire them:

### 1. Official Spec Test Suites (The Gold Standard)

Many of these specifications come with their own brutally rigorous test suites. We can strip the test runners and just extract the raw input/expected-output pairs.

-   **Task 8 (MiniCommonMark):** The CommonMark project maintains a massive `spec.txt` file containing thousands of inline Markdown examples with their exact expected HTML outputs. We specifically extract the "Pathological" and "Ambiguous" sections (e.g., deeply nested lists, conflicting emphasis markers).
-   **Task 9 (WASM Interpreter):** The WebAssembly spec repo has a `test/core` directory containing `.wasm` files and their expected outcomes. We use the ones targeting integer overflow, trap conditions (unreachable, out-of-bounds memory access), and deep call stacks.
-   **Task 3 (RV32I Emulator):** The `riscv-tests` repository (maintained by the RISC-V foundation) contains assembly tests for every instruction type. We specifically use the `rv32ui-p-*` (user-level, integer) tests, particularly the ones testing immediate sign-extension and misaligned memory access.
-   **Task 4 (Regex Engine):** Russ Cox’s RE2 repository contains a test suite (`re2/testing`), but even better is the **Glushkov test suite** used by the Rust `regex` crate, which is filled with catastrophic backtracking edge cases that will hang a naive NFA.

### 2. Fuzzing Corpora & Mutated Inputs (The Adversarial Layer)

For binary parsing tasks, we need malformed inputs that don't crash the AI's code but should be handled gracefully or rejected.

-   **Task 1 (DNS Codec):** The **OSS-Fuzz** project (Google) has fuzzing corpora for DNS parsers. We can download their seed corpora—these contain real-world malformed packets, pointer loops, and truncated headers.
-   **Task 5 (DEFLATE):** We take standard `.gz` files and use a binary mutation script (like `radamsa`) to flip bits, truncate blocks, and corrupt Huffman tables. The AI's decompressor must not panic or segfault; it must return a clean "Decoding Error".
-   **Task 2 (Tar):** We craft tarballs with path traversal attempts (e.g., filenames containing `../../../etc/passwd`), symlinks pointing to absolute paths outside the extraction directory, and headers with invalid octal checksums.

### 3. Academic & "Pathological" Datasets

For algorithmic and state-heavy tasks, we look to known stress-tests in computer science literature.

-   **Task 10 (Raft State Machine):** We don't need network data; we need *event traces*. Diego Ongaro's PhD dissertation (which defines Raft) outlines specific edge cases (e.g., Figure 3.7: "A follower might have stale entries that are not in the leader's log"). We write deterministic harness scripts that simulate exact message drops, out-of-order delivery, and network partitions matching these academic figures.
-   **Task 6 (SQL-on-CSV):** SQLite's `sqllogictest` framework contains thousands of complex SQL queries designed to find bugs in query planners. We adapt these to our CSV subset, specifically focusing on `GROUP BY` on `NULL` values, `LEFT JOIN` on empty tables, and type coercion between empty strings and zeros.
-   **Task 7 (LSM-Tree KV):** We don't need external data; we need *workload traces*. We generate adversarial workload scripts: write 10,000 keys, delete 9,999 of them, force a compaction, crash the process (kill the harness), restart, and read the 1 remaining key. This tests Write-Ahead Log (WAL) recovery and tombstone compaction.

### 4. Programmatic Harness Generation

For some tasks, the edge cases are deterministic states that are easiest to generate via script.

-   **Task 3 (RV32I):** We write a tiny C script that compiles to a binary that intentionally executes an invalid opcode or reads from an unmapped memory address. The AI's emulator must trap/exit with a specific error code, not silently continue.

### The Strategy for the Benchmark

We split the test data into three tiers:

1.  **Public Smoke Tests (10%):** 5-10 basic happy-path examples included in the AI's prompt so it understands the exact I/O format.
2.  **Hidden Standard Tests (40%):** Valid, complex inputs sourced from official spec suites.
3.  **Adversarial/Malicious Tests (50%):** Fuzzing corpora, mutated binaries, pathologically nested text, and crash-recovery traces.

By sourcing the data this way, a model that simply memorized a standard `cmark` or `zlib` implementation will pass Tier 1 and 2, but will violently crash (segfault, infinite loop, or wrong output) on Tier 3.

12:40 AM