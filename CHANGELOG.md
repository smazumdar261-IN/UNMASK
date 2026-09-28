# Changelog

All notable changes to the **Universal Deobfuscator** project are documented in this file.
The project adheres to [Semantic Versioning](https://semver.org/).

---

## [1.0.0] - Production Release

### Phase 12: Production Hardening
- **Adversarial & Malformed Input Resilience**:
  - Hardened parsers across all 5 languages (Python, JavaScript, TypeScript, Java, Go) against recursion limits, deeply nested expressions, and null-byte injection.
  - Implemented safe file reader (`read_source_file`) with automatic latin-1 fallback to gracefully ingest corrupted, binary, or non-UTF8 files without unhandled crashes.
  - Added protection in expression evaluation and folding passes against zero-division errors, float overflows, and recursion exhaustion.
- **CLI Enhancements**:
  - Implemented `analyze` subcommand for static code inspection, AST metrics, and obfuscation detection.
  - Implemented `report` subcommand for generating complete provenance audit reports without mutating input source.
- **Packaging & Distribution**:
  - Updated `pyproject.toml` package discovery to include `dynamic*` module.
- **Production Documentation**:
  - Created `ARCHITECTURE.md` detailing the 3-layer architecture, Common IR, CFG, passes, and security model.
  - Created `DEVELOPMENT.md` providing development workflows, testing methodology, and plugin authoring guides.
  - Created `CHANGELOG.md` documenting all project phases from inception to 1.0.0.
- **Hardening Test Suite**:
  - Added `tests/test_hardening.py` covering adversarial syntax errors, deep nesting, binary corrupt payloads, divide-by-zero, semantic preservation, and CLI subcommands.

---

## [0.11.0] - Phase 11: Secure Dynamic Analysis

- **Process Isolation**:
  - Implemented subprocess sandbox in `dynamic/sandbox.py` ensuring untrusted code is never imported or executed inside the host analyzer process.
- **Resource Limits**:
  - Enforced POSIX resource boundaries via `resource.setrlimit` (`RLIMIT_CPU`, `RLIMIT_AS` memory ceiling 64MB, `RLIMIT_FSIZE`, `RLIMIT_NPROC`).
- **Filesystem & Network Isolation**:
  - Implemented ephemeral directory jail and network unsharing / dummy routing to prevent arbitrary network and disk writes.
- **Step Tracing & Dynamic Unmasking**:
  - Added deterministic execution tracer (`dynamic/tracer.py`) capped at 10,000 steps.
  - Implemented `DynamicDecoderUnmasker` pass (`dynamic/unmasker.py`) for safe runtime decoding of complex multi-stage payload wrappers.
  - Integrated `--dynamic` and `--no-dynamic` flags into CLI.

---

## [0.10.0] - Phase 10: Common IR Refinement

- **Universal Intermediate Representation**:
  - Built `core/ir.py` defining language-neutral IR AST nodes (`IRModule`, `IRFunction`, `IRBranch`, `IRLoop`, `IRAssignment`, `IRCall`, `IRBinaryOperation`, etc.).
  - Added `IRPrinter` and `IRValidator` for structural validation.
- **IR Control Flow Graph**:
  - Built `core/ir_cfg.py` featuring basic block construction, edge classification, reachability analysis, cycle detection, and ASCII graph visualization.
- **Universal IR Passes**:
  - Implemented `IRConstantFoldingPass`, `IRDeadCodeEliminationPass`, and `IRControlFlowSimplificationPass` in `core/ir_passes/`.
  - Added `IRPipeline` in `core/ir_pipeline.py`.
- **CLI Subcommand**:
  - Added `deobfuscator ir` subcommand with `-O` (optimize), `--cfg` (visualize), and `--roundtrip` modes.

---

## [0.9.0] - Phase 9: Go Language Support

- **Go Frontend & Printer**:
  - Implemented pure stdlib recursive-descent Go lexer, parser, and printer (`languages/go/`).
  - Supports Go packages, imports, structs, functions, channels (`chan`), goroutines (`go`), `select`, `defer`, and multi-variable assignments.
- **Go Passes & IR Converter**:
  - Added constant propagation, dead code elimination, and string reconstruction passes for Go.
  - Added bidirectional `GoIRConverter` to lower Go AST to Common IR and raise Common IR to Go AST.

---

## [0.8.0] - Phase 8: Java & Bytecode Support

- **Java Source Parser**:
  - Implemented pure stdlib recursive-descent Java lexer, parser, and printer (`languages/java/`).
  - Supports classes, interfaces, methods, fields, control flow, casts, annotations, and generic signatures.
- **JVM Bytecode Decompiler**:
  - Implemented binary JVM `.class` and `.jar` parser (`languages/java/bytecode.py`) decompiling bytecode to Java AST.
- **Java Passes & IR Converter**:
  - Implemented Java constant propagation, expression folding, and decoder detection passes.
  - Built bidirectional `JavaIRConverter` for Common IR interoperability.

---

## [0.7.0] - Phase 7: TypeScript Support

- **TypeScript Parser & Type Preservation**:
  - Extended JavaScript frontend to parse TypeScript constructs: `interface`, `type` aliases, `enum`, variable type annotations, generics, type assertions (`as`), and decorators.
- **Dual Unparsing Engine**:
  - Preserves full TypeScript constructs by default.
  - Supports compilation/unparsing to clean JavaScript via `--target-js` flag.
- **Common IR Integration**:
  - Built bidirectional `TSIRConverter` retaining type metadata across IR transformations.

---

## [0.6.0] - Phase 6: JavaScript Support

- **JavaScript Frontend**:
  - Built pure stdlib recursive-descent ECMAScript lexer, parser, and ESTree-compatible AST (`languages/javascript/`).
- **JavaScript Deobfuscation Passes**:
  - Constant propagation, expression folding, string reconstruction, property access normalization (`obj['prop']` $\rightarrow$ `obj.prop`), and IIFE normalization.
- **JS Decoders**:
  - Unmasked `atob()`, `btoa()`, `decodeURIComponent()`, and `unescape()`.
- **JS Common IR**:
  - Implemented bidirectional `JSIRConverter`.

---

## [0.5.0] - Phase 5: Confidence & Provenance Engine

- **Confidence System**:
  - Defined `ConfidenceLevel` (`CERTAIN`, `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`) and `TransformationCategory` (`RECOVERED`, `INFERRED`, `SIMPLIFIED`, `UNRESOLVED`).
  - Implemented mathematical scoring and weighted average confidence computation.
- **Provenance Audit System**:
  - Tracked source locations (file, line, column), original snippet, transformed snippet, and pass rationale for every modification.
  - Implemented multi-format report generator (`text`, `json`, `markdown`).

---

## [0.4.0] - Phase 4: Symbolic Analysis

- **Symbolic Execution**:
  - Implemented symbolic expression solver evaluating arithmetic identities, bitwise cancellations (`x ^ x` $\rightarrow$ `0`), and algebraic reductions.
  - Added `SymbolicEvaluationPass` integrated into Python deobfuscation pipeline.

---

## [0.3.0] - Phase 3: Control-Flow Analysis

- **Control-Flow Graph**:
  - Implemented AST-level CFG builder, basic block extraction, edge analysis, and dominator tree computation.
- **CFG Reduction**:
  - Added unreachable branch pruning and dead code elimination based on reachability invariants.

---

## [0.2.0] - Phase 2: Advanced Python Obfuscation

- **Control-Flow Flattening (CFF) Recovery**:
  - Reconstructed linear statement sequences and structured `if`/`else` branches from dispatcher loops and state machines.
- **Inlining & Normalization**:
  - Added trivial proxy function inlining, import alias normalization, and dead assignment elimination.

---

## [0.1.0] - Phases 0 & 1: Foundation & Static Engine

- **Core Framework**:
  - Initialized CLI skeleton (`main.py`), logging, language registry, and error handling hierarchy (`core/exceptions.py`).
- **Python Static Engine**:
  - Implemented Python AST parsing, unparsing, constant propagation, string reconstruction (`chr`/`ord`/concatenation), and decoder plugin registry (Base64, Hex, URL, Unicode, XOR, Compression).
