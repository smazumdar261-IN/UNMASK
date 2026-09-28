# Developer Guide & Contributing

This document details development workflows, testing methodology, architectural patterns, and coding standards for extending the **Universal Deobfuscator**.

---

## 1. Environment & Prerequisites

The Universal Deobfuscator is built to run entirely on **Python 3.11+ standard library**.

- **Python Version**: `>= 3.11`
- **External Dependencies**: None. All parsers, analyzers, sandboxes, and printers are implemented in pure Python stdlib.
- **Operating Systems**: Linux (primary for namespace sandboxing), macOS, Windows.

### Installation for Development
Clone the repository and install in editable mode:
```bash
git clone <repo-url> universal-deobfuscator
cd universal-deobfuscator
pip install -e .
```

---

## 2. Running Tests

Testing is mandatory for every feature, bug fix, or transformation pass.

### Run All Tests
```bash
python3 -m unittest discover -s tests -v
```

### Run Specific Test Modules
```bash
# Run hardening & adversarial tests
python3 -m unittest tests/test_hardening.py -v

# Run Python pipeline tests
python3 -m unittest tests/test_pipeline.py -v

# Run Common IR tests
python3 -m unittest tests/test_common_ir.py -v

# Run JavaScript passes tests
python3 -m unittest tests/test_javascript_passes.py -v

# Run Sandbox security tests
python3 -m unittest tests/test_sandbox.py -v
```

---

## 3. Repository Architecture

```text
universal-deobfuscator/
├── core/               # Language-neutral foundation
│   ├── ir.py           # Common IR AST node definitions & validator
│   ├── ir_cfg.py       # Control Flow Graph engine for Common IR
│   ├── ir_pipeline.py  # IR transformation runner & pass coordinator
│   ├── ir_passes/      # Universal IR passes (const fold, dead code)
│   ├── confidence.py   # Confidence scoring engine (CERTAIN, HIGH, ...)
│   ├── provenance.py   # Provenance tracker and audit report generator
│   └── exceptions.py   # Exception hierarchy (DeobfuscatorError, ParseError)
│
├── languages/          # Language-specific frontends and printers
│   ├── python/         # Python stdlib AST frontend & transformer
│   ├── javascript/     # Recursive-descent JS parser, AST & printer
│   ├── typescript/     # TypeScript frontend with type preservation
│   ├── java/           # Java source parser & JVM bytecode decompiler
│   └── go/             # Go source parser, AST & printer
│
├── passes/             # High-level AST deobfuscation passes (Python)
│   ├── constant_propagation.py
│   ├── expression_folding.py
│   ├── string_reconstruction.py
│   ├── decoder_detection.py
│   ├── cff_recovery.py
│   └── symbolic_evaluation.py
│
├── decoders/           # Pure decoding primitives (base64, hex, xor, etc.)
├── dynamic/            # Opt-in isolated dynamic analysis sandbox
├── tests/              # Test suite (unit, integration, hardening)
├── main.py             # CLI entry point (detect, parse, analyze, report, deobfuscate, ir)
└── pyproject.toml      # Packaging & distribution configuration
```

---

## 4. Coding Standards

1. **Zero Third-Party Dependencies**: Never introduce external packages without strict architectural justification.
2. **Type Hints**: All functions and methods must have comprehensive type annotations:
   ```python
   def transform_node(node: IRNode, context: Dict[str, Any]) -> IRNode:
   ```
3. **Explicit Exception Handling**: Bare `except:` is strictly banned. Catch specific exceptions:
   ```python
   # Correct
   try:
       result = int(val, 16)
   except ValueError:
       return None

   # Prohibited
   except:
       pass
   ```
4. **Deterministic Behavior**: Output must be 100% reproducible. When iterating over dictionaries or sets in code generators, sort keys to guarantee deterministic emitted code.
5. **Preserve Node Locations**: Always copy source locations to transformed nodes (`ast.copy_location(new_node, old_node)`).

---

## 5. Adding a New Language Plugin

To add support for a new programming language (e.g., `Ruby` or `Rust`):

1. **Create Package Directory**:
   Create `languages/<lang_name>/` containing `__init__.py`, `ast_nodes.py`, `lexer.py`, `parser.py`, `printer.py`, and `ir_converter.py`.

2. **Implement `BaseLanguage`**:
   Subclass `languages.BaseLanguage` in `languages/<lang_name>/__init__.py`:
   ```python
   from languages import BaseLanguage, registry

   class NewLanguage(BaseLanguage):
       name = "newlang"
       extensions = [".nl"]

       def parse(self, source: str, filename: Optional[str] = None) -> Any:
           ...
       def unparse(self, ast_tree: Any) -> str:
           ...
       def to_ir(self, ast_tree: Any) -> IRModule:
           ...
       def from_ir(self, ir_module: IRModule) -> Any:
           ...

   registry.register(NewLanguage())
   ```

3. **Implement Common IR Conversion**:
   Implement bidirectional lowering from Language AST $\rightarrow$ `IRNode` and raising from `IRNode` $\rightarrow$ Language AST. This allows your language to immediately benefit from all universal IR optimization passes!

4. **Register in CLI**:
   Import `languages.<lang_name>` in `main.py`.

---

## 6. Implementing Transformation Passes

Transformation passes can be implemented either at the **Language AST level** or at the **Common IR level**.

### Common IR Pass (Recommended for Language-Neutral Transformations)
Subclass `core.ir_pipeline.IRPass`:
```python
from core.ir import IRModule, IRTransformer
from core.ir_pipeline import IRPass
from core.provenance import ProvenanceTracker
from core.confidence import Confidence, TransformationCategory

class RedundantOpRemovalPass(IRPass):
    name = "RedundantOpRemoval"
    description = "Removes redundant identity operations from IR."

    def run(self, module: IRModule, tracker: ProvenanceTracker) -> IRModule:
        class IdentityTransformer(IRTransformer):
            ...
        return IdentityTransformer().transform(module)
```

### Language AST Pass
Subclass `core.pipeline.Pass`:
```python
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from core.confidence import Confidence, TransformationCategory

class CustomAstPass(Pass):
    name = "CustomAstPass"
    description = "Performs language-specific AST transformations."

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        # Perform AST mutation
        ...
        tracker.record(
            pass_name=self.name,
            original=orig_str,
            transformed=new_str,
            confidence=Confidence.certain("Simplified constant", TransformationCategory.SIMPLIFIED),
            location=loc,
        )
        return target
```

---

## 7. Testing Methodology & Definition of Done

A feature is only considered complete when:
- [x] Implementation exists with full type annotations.
- [x] Unit tests verify happy-path and edge-case behavior.
- [x] Malformed and adversarial input handling is verified (no crashes or unhandled tracebacks).
- [x] Semantic preservation is verified (behavior of deobfuscated code equals original).
- [x] Provenance and confidence records are accurately emitted.
- [x] All existing tests in the suite continue to pass (zero regressions).
