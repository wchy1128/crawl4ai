"""
Generate c4ai-code-context.md and c4ai-doc-context.md for the MCP ask endpoint.

Usage:
    python deploy/docker/generate_context.py [--output-dir deploy/docker]

The generated files are plain concatenations of source files, identical in format
to the originals. File lists are hard-coded to match the original selection.
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

# ── File lists (same as the original context files) ────────────────

CODE_FILES = [
    "crawl4ai/async_configs.py",
    "crawl4ai/async_webcrawler.py",
    "crawl4ai/cli.py",
    "crawl4ai/extraction_strategy.py",
    "crawl4ai/models.py",
    "crawl4ai/content_filter_strategy.py",
    "crawl4ai/markdown_generation_strategy.py",
    "crawl4ai/browser_manager.py",
    "docs/examples/quickstart.py",
    "docs/examples/quickstart_examples_set_1.py",
    "docs/examples/dispatcher_example.py",
    "docs/examples/hello_world.py",
    "docs/examples/hooks_example.py",
    "crawl4ai/deep_crawling/__init__.py",
    "crawl4ai/deep_crawling/base_strategy.py",
    "crawl4ai/deep_crawling/bff_strategy.py",
    "crawl4ai/deep_crawling/bfs_strategy.py",
    "crawl4ai/deep_crawling/filters.py",
    "crawl4ai/deep_crawling/scorers.py",
    "docs/examples/deepcrawl_example.py",
]

DOC_FILES = [
    "docs/md_v2/core/ask-ai.md",
    "docs/md_v2/core/browser-crawler-config.md",
    "docs/md_v2/core/cache-modes.md",
    "docs/md_v2/core/cli.md",
    "docs/md_v2/core/content-selection.md",
    "docs/md_v2/core/crawler-result.md",
    "docs/md_v2/core/deep-crawling.md",
    "docs/md_v2/core/self-hosting.md",
    "docs/md_v2/core/fit-markdown.md",
    "docs/md_v2/core/installation.md",
    "docs/md_v2/core/link-media.md",
    "docs/md_v2/core/local-files.md",
    "docs/md_v2/core/markdown-generation.md",
    "docs/md_v2/core/page-interaction.md",
    "docs/md_v2/core/quickstart.md",
    "docs/md_v2/core/simple-crawling.md",
    "docs/md_v2/advanced/advanced-features.md",
    "docs/md_v2/advanced/crawl-dispatcher.md",
    "docs/md_v2/advanced/file-downloading.md",
    "docs/md_v2/advanced/hooks-auth.md",
    "docs/md_v2/advanced/identity-based-crawling.md",
    "docs/md_v2/advanced/lazy-loading.md",
    "docs/md_v2/advanced/multi-url-crawling.md",
    "docs/md_v2/advanced/network-console-capture.md",
    "docs/md_v2/advanced/proxy-security.md",
    "docs/md_v2/advanced/session-management.md",
    "docs/md_v2/advanced/ssl-certificate.md",
    "docs/md_v2/extraction/chunking.md",
    "docs/md_v2/extraction/clustring-strategies.md",
    "docs/md_v2/extraction/llm-strategies.md",
    "docs/md_v2/extraction/no-llm-strategies.md",
]


def resolve_code_ext(path: str) -> str:
    """Return the markdown code-block language tag for a file."""
    if path.endswith(".py"):
        return "py"
    if path.endswith(".md"):
        return "md"
    if path.endswith((".js", ".mjs")):
        return "js"
    if path.endswith((".ts", ".tsx")):
        return "ts"
    return ""


def generate_context(
    title: str,
    file_list: list[str],
    project_root: Path,
) -> str:
    """Build the concatenated context string for one output file."""
    today = datetime.now().strftime("%Y-%m-%d")
    parts: list[str] = [f"# {title}\n", f"Generated on {today}\n"]

    missing = []
    for rel in file_list:
        full = project_root / rel
        if not full.exists():
            missing.append(rel)
            continue
        content = full.read_text(encoding="utf-8")
        ext = resolve_code_ext(rel)
        parts.append(f"\n## File: {rel}\n")
        parts.append(f"\n```{ext}\n{content}\n```\n")

    if missing:
        print(f"WARNING: {len(missing)} file(s) not found, skipped:")
        for m in missing:
            print(f"  - {m}")

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description="Generate Crawl4AI context files for the MCP ask endpoint"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write the output files (default: same as this script)",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="Project root directory (default: auto-detected from this script's location)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    project_root = Path(args.project_root).resolve() if args.project_root else script_dir.parent.parent
    output_dir = Path(args.output_dir).resolve() if args.output_dir else script_dir

    if not project_root.exists():
        print(f"ERROR: project root not found: {project_root}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate code context
    code_path = output_dir / "c4ai-code-context.md"
    print(f"Generating {code_path} ...")
    code_content = generate_context("Crawl4AI Code Context", CODE_FILES, project_root)
    code_path.write_text(code_content, encoding="utf-8")
    size_kb = len(code_content.encode("utf-8")) / 1024
    print(f"  -> {size_kb:.0f} KB, {len(CODE_FILES)} files")

    # Generate doc context
    doc_path = output_dir / "c4ai-doc-context.md"
    print(f"Generating {doc_path} ...")
    doc_content = generate_context("Crawl4AI Doc Context", DOC_FILES, project_root)
    doc_path.write_text(doc_content, encoding="utf-8")
    size_kb = len(doc_content.encode("utf-8")) / 1024
    print(f"  -> {size_kb:.0f} KB, {len(DOC_FILES)} files")

    total_kb = (len(code_content.encode("utf-8")) + len(doc_content.encode("utf-8"))) / 1024
    print(f"\nDone. Total: {total_kb:.0f} KB")


if __name__ == "__main__":
    main()
