#!/usr/bin/env python3
"""Build script for packaging UNMASK as an installable Debian package (.deb)."""

import os
import shutil
import subprocess
from pathlib import Path

def build_deb() -> None:
    repo_dir = Path(__file__).resolve().parent.parent
    dist_dir = repo_dir / "dist"
    build_dir = dist_dir / "deb_build"

    if build_dir.exists():
        shutil.rmtree(build_dir)

    debian_dir = build_dir / "DEBIAN"
    usr_bin = build_dir / "usr" / "bin"
    usr_share = build_dir / "usr" / "share" / "unmask"

    for d in (debian_dir, usr_bin, usr_share):
        d.mkdir(parents=True, exist_ok=True)

    # 1. DEBIAN/control
    control_content = """Package: unmask
Version: 1.0.0
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.11)
Maintainer: Sayantan <sayantan@portfolio.dev>
Description: UNMASK - Professional Universal Code Deobfuscator & Reverse Engineering Engine
 UNMASK is an extensible, multi-language reverse engineering
 and deobfuscation framework for Python, JavaScript, TypeScript, Java, and Go.
 Features include control-flow flattening recovery, string reconstruction,
 decoder unmasking, Common IR optimization, and secure dynamic sandboxing.
"""
    (debian_dir / "control").write_text(control_content)

    # 2. Launcher script in /usr/bin/unmask
    launcher_content = """#!/usr/bin/env bash
exec python3 /usr/share/unmask/main.py "$@"
"""
    unmask_bin = usr_bin / "unmask"
    unmask_bin.write_text(launcher_content)
    unmask_bin.chmod(0o755)

    # Alias /usr/bin/UNMASK
    (usr_bin / "UNMASK").symlink_to("unmask")

    # 3. Copy source trees into /usr/share/unmask
    shutil.copy(repo_dir / "main.py", usr_share / "main.py")
    shutil.copy(repo_dir / "pyproject.toml", usr_share / "pyproject.toml")
    for folder in ("core", "languages", "passes", "decoders", "analysis", "dynamic"):
        dest = usr_share / folder
        shutil.copytree(repo_dir / folder, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # 4. Invoke dpkg-deb
    dist_dir.mkdir(parents=True, exist_ok=True)
    deb_output = dist_dir / "unmask_1.0.0_all.deb"
    cmd = ["dpkg-deb", "--build", "--root-owner-group", str(build_dir), str(deb_output)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error building debian package: {res.stderr}")
        return

    print(f"[+] Successfully built Debian package: {deb_output}")
    print(f"    Install with: sudo apt install {deb_output}")
    print(f"    Or with     : sudo dpkg -i {deb_output}")

if __name__ == "__main__":
    build_deb()
