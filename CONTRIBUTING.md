# Contributing to UNMASK

Thank you for your interest in improving **UNMASK: Universal Code Deobfuscator & Reverse Engineering Engine**!

UNMASK was conceived, architected, and developed by **Sayantan** and is released under the **GNU General Public License v3.0 (GPLv3)**.

---

## 📜 Licensing & Usage Principles

By using, contributing to, or modifying UNMASK, you agree to the following terms enforced by the GNU GPLv3 license:

1. **Free Use:** Anyone is free to download, install, execute, and use UNMASK for security research, malware analysis, reverse engineering, academic study, or personal workflows.
2. **Open Improvements:** If you discover a bug, improve an AST deobfuscation pass, add support for a new programming language, or optimize performance, you are encouraged and allowed to do so! However, **any modifications or improvements MUST remain free, public, and open-source under the GNU General Public License v3.0 (GPLv3)**.
3. **No Closed-Source Derivative Tools:** You may **not** copy, bundle, or incorporate code from UNMASK into a closed-source, proprietary, or commercial product without open-sourcing the entire derivative codebase under GPLv3.
4. **Permanent Attribution:** All original copyright notices (`Copyright (C) 2026 Sayantan`) and attribution banners must remain intact in all copies, modifications, and derivative works.

---

## 🛠️ How to Contribute Improvements

We welcome contributions directly to the upstream UNMASK project!

### 1. Opening Issues
- Found a bug or an unsupported obfuscation pattern? Open an issue on GitHub describing the input snippet, expected deobfuscated output, and actual behavior.

### 2. Submitting Pull Requests
1. **Fork the Repository:** Create a fork of `smazumdar261-IN/UNMASK`.
2. **Create a Feature Branch:**
   ```bash
   git checkout -b feature/my-new-pass
   ```
3. **Adhere to Project Standards:**
   - **Zero Third-Party Dependencies:** All code must run strictly on the standard Python 3.11+ library.
   - **Provenance & Confidence:** Ensure all new AST transformation passes record provenance records with appropriate `ConfidenceLevel`.
   - **Unit Tests:** Add unit tests for your changes under the `tests/` directory.
4. **Run the Test Suite:**
   ```bash
   python3 -m unittest discover tests -p "test_*.py"
   ```
   All tests must pass before submitting a Pull Request.
5. **Open a Pull Request:** Submit your PR against the `main` branch with a clear description of the improvements made.

---

## ⚖️ Legal Agreement

All contributions submitted to this repository are licensed under the **GNU General Public License v3.0**. By submitting a Pull Request, you certify that you have the right to submit the code under the GNU GPLv3 and agree that original project attribution remains with **Sayantan**.
