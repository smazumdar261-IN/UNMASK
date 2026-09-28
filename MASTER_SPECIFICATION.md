# Universal Deobfuscator

## Project Status

This document is the master specification for the project.

The goal is to build a professional, extensible, high-accuracy
deobfuscation and code-understanding tool capable of converting
obfuscated source code into simpler, readable, semantically equivalent
source code wherever recovery is possible.

The project must be developed incrementally, tested continuously, and
must never claim to recover information that has been destroyed by
obfuscation.

------------------------------------------------------------------------

# 1. Core Objective

Build a **Universal Deobfuscator** with this conceptual pipeline:

``` text
Input
  |
  v
Language Detection
  |
  v
Language Parser / Loader
  |
  v
Language AST / Bytecode Representation
  |
  v
Common Intermediate Representation (IR)
  |
  +-----------------------------+
  |                             |
  v                             v
Static Analysis              Pattern/Decoder Engine
  |                             |
  +-------------+---------------+
                |
                v
       Symbolic Evaluation
                |
                v
       Deobfuscation Passes
                |
                v
       Control/Data Flow Analysis
                |
                v
        Confidence Analysis
                |
        +-------+-------+
        |               |
        v               v
   Fully known      Unresolved
        |               |
        |               v
        |       Isolated Dynamic
        |          Analysis
        |               |
        +-------+-------+
                |
                v
          Simplified IR
                |
                v
       Language-specific Printer
                |
                v
        Readable Source
                |
                v
       Analysis / Audit Report
```

The system should prioritize:

1.  Correctness
2.  Semantic preservation
3.  Safety
4.  Explainability
5.  Extensibility
6.  Accuracy
7.  Readability
8.  Performance

Do not sacrifice correctness merely to make output look simpler.

------------------------------------------------------------------------

# 2. Important Reality Constraint

The system must NOT promise exact recovery of the original source.

Obfuscation can permanently destroy:

-   Original variable names
-   Original comments
-   Original formatting
-   Original function names
-   Original structure
-   Source-level intent

Therefore the project's objective is:

> Recover the maximum amount of reliable semantic information and
> produce readable, behavior-preserving source code where possible.

Every inferred transformation must have a confidence level or
provenance.

------------------------------------------------------------------------

# 3. Supported Languages

Build support incrementally.

## Phase 1

Python source.

## Phase 2

JavaScript.

## Phase 3

TypeScript.

## Phase 4

Java source and Java bytecode.

## Phase 5

Go source.

## Phase 6

Additional languages through a plugin architecture.

Potential future languages:

-   C
-   C++
-   Rust
-   PHP
-   C#
-   Kotlin
-   Swift
-   Lua
-   Shell
-   WebAssembly

Do NOT attempt all languages simultaneously.

------------------------------------------------------------------------

# 4. Source vs Compiled Input

The architecture must distinguish:

### Source-level input

Examples:

``` text
.py
.js
.ts
.java
.go
```

### Intermediate/compiled input

Examples:

``` text
.class
.jar
.wasm
```

### Native binaries

Examples:

``` text
ELF
PE
Mach-O
```

Native binary decompilation is a separate advanced subsystem and must
not be mixed casually with source-code parsing.

------------------------------------------------------------------------

# 5. Project Architecture

Use this general structure:

``` text
universal-deobfuscator/
│
├── README.md
├── LICENSE
├── pyproject.toml
├── main.py
│
├── core/
│   ├── __init__.py
│   ├── pipeline.py
│   ├── ir.py
│   ├── analyzer.py
│   ├── confidence.py
│   ├── provenance.py
│   └── exceptions.py
│
├── languages/
│   ├── __init__.py
│   │
│   ├── python/
│   │   ├── __init__.py
│   │   ├── parser.py
│   │   ├── analyzer.py
│   │   ├── normalizer.py
│   │   └── printer.py
│   │
│   ├── javascript/
│   ├── typescript/
│   ├── java/
│   └── go/
│
├── decoders/
│   ├── __init__.py
│   ├── registry.py
│   ├── base64_decoder.py
│   ├── hex_decoder.py
│   ├── unicode_decoder.py
│   ├── xor_decoder.py
│   ├── compression_decoder.py
│   └── string_decoder.py
│
├── passes/
│   ├── __init__.py
│   ├── constant_propagation.py
│   ├── expression_folding.py
│   ├── string_reconstruction.py
│   ├── dead_code.py
│   ├── control_flow.py
│   ├── variable_analysis.py
│   └── simplify.py
│
├── analysis/
│   ├── __init__.py
│   ├── cfg.py
│   ├── dataflow.py
│   ├── callgraph.py
│   ├── taint.py
│   └── patterns.py
│
├── dynamic/
│   ├── __init__.py
│   ├── sandbox.py
│   ├── tracer.py
│   └── policy.py
│
├── printers/
│   ├── __init__.py
│   ├── python.py
│   ├── javascript.py
│   ├── typescript.py
│   ├── java.py
│   └── go.py
│
├── cli/
│   ├── __init__.py
│   └── commands.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   └── samples/
│
├── fixtures/
│   ├── python/
│   ├── javascript/
│   ├── java/
│   └── go/
│
├── reports/
└── output/
```

The architecture may evolve, but the separation of concerns must remain.

------------------------------------------------------------------------

# 6. Development Rules for Gemini CLI

You are the primary coding agent for this repository.

Work autonomously, but follow these rules.

## Rule 1 --- Inspect before changing

Before implementing a feature:

1.  Inspect the current repository.
2.  Read existing relevant files.
3.  Determine what already exists.
4.  Do not duplicate functionality.
5.  Preserve working code.

## Rule 2 --- Work phase by phase

Do not implement the entire specification in one giant change.

Implement the currently active phase completely.

After each phase:

1.  Run tests.
2.  Run static checks.
3.  Run representative examples.
4.  Fix regressions.
5.  Update documentation.
6.  Update this project's progress notes.

Then proceed to the next phase only if the phase is stable.

## Rule 3 --- Do not invent dependencies

Prefer Python standard library where practical.

Before adding a dependency:

-   determine whether it is necessary;
-   explain its purpose in the project documentation;
-   pin or constrain the dependency appropriately;
-   avoid unnecessary packages.

## Rule 4 --- No insecure execution shortcut

Never execute arbitrary input code directly on the host.

Do NOT treat:

``` python
subprocess.run(["python", "-c", user_code])
```

as a secure sandbox.

Dynamic analysis must eventually use an explicitly isolated execution
environment.

Until the secure dynamic-analysis subsystem exists, unresolved
expressions should remain unresolved rather than being executed
unsafely.

## Rule 5 --- Never silently alter semantics

Every transformation must be conservative.

If a transformation cannot be proven safe, do not apply it
automatically.

Prefer:

``` text
UNKNOWN
```

over:

``` text
GUESS
```

## Rule 6 --- Preserve provenance

Every important transformation should be traceable.

For example:

``` text
original:
    "SGVsbG8="

transformation:
    Base64Decode

result:
    "Hello"

confidence:
    0.99
```

------------------------------------------------------------------------

# 7. Phase Plan

## Phase 0 --- Foundation

Create:

-   repository structure
-   CLI skeleton
-   configuration
-   logging
-   error handling
-   test framework
-   documentation

Acceptance criteria:

``` text
python main.py --help
```

works.

------------------------------------------------------------------------

# Phase 1 --- Python Static Engine

Start with Python only.

Implement:

### Parser

Use:

``` python
ast
```

for Python 3.11+.

Support:

-   parsing
-   AST traversal
-   source regeneration
-   syntax error reporting

### Constant propagation

Example:

``` python
a = "Hello"
b = a
print(b)
```

should be understood as:

``` text
b -> "Hello"
```

### Expression folding

Handle safe constant expressions such as:

``` python
10 + 20
10 * 5
"hello" + "world"
"abc" * 3
```

Do not execute arbitrary expressions.

### String reconstruction

Support safe static reconstruction of patterns such as:

``` python
"a" + "b"
"".join(["a", "b"])
chr(72) + chr(105)
"abc"[::-1]
```

### Decoder detection

Initially support:

-   Base64
-   hexadecimal
-   Unicode escape sequences
-   URL encoding where appropriate
-   string concatenation
-   character-array reconstruction
-   reversal

Decoders must validate input strictly.

Do not decode every random string as Base64 merely because its length is
divisible by four.

------------------------------------------------------------------------

# 8. Phase 2 --- Advanced Python Obfuscation

Implement:

-   nested decoding
-   multi-stage decoding
-   constant propagation across scopes where safely possible
-   function-level analysis
-   import analysis
-   alias tracking
-   safe simplification
-   dead-code detection
-   unreachable-code detection
-   redundant expression removal
-   variable-use analysis
-   call analysis

Example:

``` python
a = "SGVsbG8="
b = base64.b64decode(a)
c = b.decode()
print(c)
```

should be recognized as a chain:

``` text
a
 ↓
Base64
 ↓
bytes
 ↓
decode
 ↓
"Hello"
```

Do not assume every API call is safe to evaluate.

------------------------------------------------------------------------

# 9. Phase 3 --- Control Flow

Build a Control Flow Graph.

Represent:

-   basic blocks
-   branches
-   loops
-   jumps
-   returns
-   exception paths

Detect patterns such as:

-   dead branches
-   redundant branches
-   opaque predicates
-   simple control-flow flattening
-   unnecessary state variables

The engine must preserve behavior.

Do not rewrite complicated control flow unless the transformation is
well understood.

------------------------------------------------------------------------

# 10. Phase 4 --- Data Flow and Symbolic Analysis

Implement:

-   reaching definitions
-   use-def chains
-   basic symbolic values
-   constant propagation
-   type hints where inferable
-   simple symbolic expressions
-   dependency tracking

Example:

``` python
x = 10
y = x * 2
z = y + 5
```

should produce:

``` text
x = 10
y = 20
z = 25
```

when the expressions are provably constant.

------------------------------------------------------------------------

# 11. Phase 5 --- Confidence System

Every transformation should optionally produce:

``` text
confidence
reason
source location
transformation
```

Use categories:

``` text
CERTAIN
HIGH
MEDIUM
LOW
UNKNOWN
```

Do not invent numerical confidence values without a defined basis.

The report should distinguish:

``` text
Recovered
Inferred
Simplified
Unresolved
```

------------------------------------------------------------------------

# 12. Phase 6 --- JavaScript

Add JavaScript parser and printer.

The JavaScript engine should eventually understand patterns including:

``` javascript
atob(...)
btoa(...)
String.fromCharCode(...)
decodeURIComponent(...)
unescape(...)
array.join(...)
string splitting
string reversal
IIFE patterns
constant propagation
```

Also account for:

-   minification
-   renamed variables
-   nested functions
-   closures
-   dynamic property access
-   computed strings

Do not assume browser APIs exist when analyzing Node.js code, and vice
versa.

------------------------------------------------------------------------

# 13. Phase 7 --- TypeScript

Reuse JavaScript infrastructure where appropriate.

Preserve:

-   interfaces
-   types
-   enums
-   generics
-   decorators where supported

Distinguish TypeScript source from JavaScript output.

------------------------------------------------------------------------

# 14. Phase 8 --- Java

Support two separate modes:

### Java source

Parse and normalize Java source.

### Java bytecode

Use a bytecode/decompiler pipeline.

The common IR should allow the analysis engine to operate independently
of Java-specific syntax.

------------------------------------------------------------------------

# 15. Phase 9 --- Go

Support:

-   Go source parsing
-   constant propagation
-   string reconstruction
-   dead-code detection
-   basic control-flow analysis

Binary Go analysis should remain a separate advanced feature.

------------------------------------------------------------------------

# 16. Common Intermediate Representation

The common IR is one of the most important parts of the project.

It should represent concepts such as:

``` text
Module
Function
Variable
Constant
Expression
Call
Assignment
Branch
Loop
Return
Exception
Import
String
BinaryOperation
UnaryOperation
```

The IR must not depend heavily on one programming language.

Language-specific information may be attached as metadata.

------------------------------------------------------------------------

# 17. Decoder Plugin Architecture

Do not hard-code all decoders into one giant function.

Use a registry.

Conceptually:

``` python
registry.register(Base64Decoder())
registry.register(HexDecoder())
registry.register(XorDecoder())
```

Each decoder should expose:

``` text
name
can_decode()
decode()
confidence()
explain()
```

A decoder should never crash the entire pipeline because an input is
malformed.

------------------------------------------------------------------------

# 18. Dynamic Analysis

Dynamic analysis is an optional fallback.

It must be implemented only after static analysis is mature.

Requirements:

-   no direct execution on host
-   strict resource limits
-   filesystem isolation
-   network isolation
-   process isolation
-   timeout
-   memory limit
-   CPU limit
-   controlled environment
-   syscall restrictions where practical
-   output capture
-   execution trace

Dynamic execution should be opt-in or clearly controlled.

Never assume a subprocess is a security sandbox.

------------------------------------------------------------------------

# 19. Malware and Hostile Input Safety

Treat every analyzed program as potentially hostile.

The tool itself should be safe to run against malicious input.

Never:

-   execute analyzed code on the host;
-   import analyzed modules into the analyzer process;
-   load arbitrary native libraries;
-   trust filenames/extensions;
-   follow arbitrary network requests;
-   write arbitrary attacker-controlled paths.

Prefer parsing and static analysis.

Dynamic analysis belongs in a separate isolated environment.

------------------------------------------------------------------------

# 20. CLI

Eventually support:

``` text
deobfuscator analyze input.py
deobfuscator deobfuscate input.py
deobfuscator deobfuscate input.py -o output.py
deobfuscator report input.py
deobfuscator detect input.py
```

Possible options:

``` text
--language
--output
--format
--verbose
--report
--confidence
--no-dynamic
--dynamic
--max-depth
```

The CLI should provide useful error messages.

------------------------------------------------------------------------

# 21. Output Modes

Support:

### Clean source

``` text
Readable reconstructed source
```

### Annotated source

``` text
Readable source with transformation comments
```

### JSON report

Machine-readable analysis.

### Human-readable report

Example:

``` text
Universal Deobfuscator Report
==============================

Language: Python

Transformations:
  [CERTAIN] Base64 string decoded
  [CERTAIN] Constant expression folded
  [HIGH]    Dead branch removed
  [UNKNOWN] Dynamic value unresolved

Dynamic execution:
  Not performed
```

------------------------------------------------------------------------

# 22. Testing Strategy

Testing is mandatory.

Create tests for every transformation.

For each input:

``` text
Original
Obfuscated
Expected simplified representation
```

Test categories:

-   unit tests
-   integration tests
-   regression tests
-   malformed input tests
-   adversarial input tests
-   performance tests

Never delete a regression test just because implementation changed.

------------------------------------------------------------------------

# 23. Semantic Preservation

For transformations that can be validated safely, compare behavior
without executing untrusted input directly.

Where practical, use:

-   AST equivalence
-   IR equivalence
-   symbolic equivalence
-   controlled test fixtures
-   language-specific parsers

The goal is not merely:

``` text
shorter code
```

The goal is:

``` text
same intended semantics + greater readability
```

------------------------------------------------------------------------

# 24. Code Quality

Use:

-   type hints
-   docstrings
-   clear names
-   small functions
-   modular architecture
-   deterministic behavior
-   structured logging
-   meaningful exceptions

Avoid:

``` python
except:
    pass
```

Use explicit exception handling.

Avoid huge classes.

Avoid one-file implementations once a subsystem becomes complex.

------------------------------------------------------------------------

# 25. Documentation

Maintain:

``` text
README.md
ARCHITECTURE.md
DEVELOPMENT.md
CHANGELOG.md
```

Document:

-   supported languages
-   supported transformations
-   limitations
-   security model
-   installation
-   CLI usage
-   architecture
-   examples
-   test methodology

Never claim 100% deobfuscation.

------------------------------------------------------------------------

# 26. Autonomous Development Protocol

When working autonomously:

1.  Inspect repository.
2.  Determine current completed phase.
3.  Read project documentation.
4.  Select the next incomplete milestone.
5.  Implement it.
6.  Write tests first where practical.
7.  Run tests.
8.  Run lint/type checks if configured.
9.  Fix failures.
10. Review for semantic correctness.
11. Update documentation.
12. Update CHANGELOG.
13. Commit only if explicitly configured/allowed.
14. Continue to the next milestone only when the current milestone
    passes.

Do not repeatedly ask the user for confirmation for ordinary
implementation decisions.

However, STOP and ask the user if:

-   a destructive filesystem operation is required;
-   credentials are required;
-   an external service/account is required;
-   a security boundary must be weakened;
-   the specification contains a genuine contradiction;
-   an irreversible architectural decision cannot reasonably be made
    from this document.

------------------------------------------------------------------------

# 27. Definition of Done

A feature is complete only when:

``` text
[ ] Implementation exists
[ ] Unit tests exist
[ ] Integration test exists where appropriate
[ ] Error handling exists
[ ] Documentation is updated
[ ] Existing tests still pass
[ ] No known semantic regression exists
[ ] Security implications were reviewed
```

------------------------------------------------------------------------

# 28. First Milestone

Start with:

``` text
Phase 0 + Phase 1A
```

Create the repository foundation and Python parser.

Minimum initial structure:

``` text
main.py

core/
    __init__.py

languages/
    __init__.py
    python/
        __init__.py
        parser.py

tests/
    samples/
        simple.py
```

Use Python 3.11+.

Do not add dynamic execution.

Do not add Base64/XOR/etc. yet.

Do not jump to JavaScript.

First make parsing, source regeneration, logging, CLI handling, and
tests reliable.

After that passes, proceed to Phase 1B.

------------------------------------------------------------------------

# 29. Phase Progress Tracking

Maintain this checklist in the project:

``` text
Phase 0  [x] Foundation
Phase 1A [x] Python parser
Phase 1B [x] Constant propagation
Phase 1C [x] String reconstruction
Phase 1D [x] Decoder registry
Phase 1E [x] Python data-flow analysis
Phase 2  [x] Advanced Python obfuscation
Phase 3  [x] Control-flow analysis
Phase 4  [x] Symbolic analysis
Phase 5  [x] Confidence engine
Phase 6  [x] JavaScript
Phase 7  [x] TypeScript
Phase 8  [x] Java
Phase 9  [x] Go
Phase 10 [x] Common IR refinement
Phase 11 [x] Secure dynamic analysis
Phase 12 [x] Production hardening
```

Only mark a phase complete after its acceptance criteria and tests pass.

------------------------------------------------------------------------

# 30. Final Development Principle

Build this as an **analysis framework**, not as a collection of regexes.

Bad architecture:

``` text
if "base64" in code:
    decode()
if "eval" in code:
    execute()
if "hex" in code:
    decode()
```

Desired architecture:

``` text
Parser
  ↓
AST
  ↓
IR
  ↓
Data Flow
  ↓
Symbolic Values
  ↓
Pattern Recognition
  ↓
Transformation
  ↓
Confidence + Provenance
  ↓
IR
  ↓
Printer
```

The system should become progressively more capable without becoming
progressively less safe.

The first objective is not to support every language.

The first objective is to build a **correct, testable, extensible
deobfuscation engine for Python** that can later serve as the foundation
for other languages.
