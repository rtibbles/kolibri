#!/usr/bin/env python
"""
Benchmark script to compare html5lib vs regex-based HTML script injection.

Validates performance claims from commit 750c24a33c:
- Small HTML (45B):  ~1,500 µs → ~2.3 µs (claimed ~650x speedup)
- Medium HTML (1.7KB): ~5,000 µs → ~2.7 µs (claimed ~1,850x speedup)
- Large HTML (57KB): ~60,000 µs → ~5.4 µs (claimed ~11,000x speedup)

Usage:
    python benchmark_parse_html.py
"""
import logging
import re
import statistics
import timeit

import html5lib

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# =============================================================================
# Common Constants
# =============================================================================

INITIALIZE_SANDBOX_FROM_IFRAME = (
    "if (window.parent && window.parent.sandbox) "
    "{try {window.parent.sandbox.initializeIframe(window);} catch (e) {}}"
)


# =============================================================================
# OLD IMPLEMENTATION (html5lib-based)
# =============================================================================


def parse_html_html5lib(content):
    """Original html5lib-based implementation."""
    try:
        document = html5lib.parse(content, namespaceHTMLElements=False)

        if not document:
            return content

        head = document.find("head")

        script_tag = head.makeelement("script", {"type": "text/javascript"})
        script_tag.text = INITIALIZE_SANDBOX_FROM_IFRAME

        head.insert(0, script_tag)

        # Parse for doctype
        doctype = None
        try:
            tree_builder_dom = html5lib.treebuilders.getTreeBuilder("dom")
            parser_dom = html5lib.HTMLParser(
                tree_builder_dom, namespaceHTMLElements=False
            )
            tree = parser_dom.parse(content)
            doctype_node = tree.childNodes[0]

            if doctype_node.nodeType == doctype_node.DOCUMENT_TYPE_NODE:
                doctype = doctype_node.toxml().replace("'", '"')
        except Exception:
            pass

        html = html5lib.serialize(
            document,
            quote_attr_values="always",
            omit_optional_tags=False,
            minimize_boolean_attributes=False,
            use_trailing_solidus=True,
            space_before_trailing_solidus=False,
        )

        if doctype:
            html = doctype + html

        return html
    except html5lib.html5parser.ParseError:
        return content


# =============================================================================
# NEW IMPLEMENTATION (regex-based)
# =============================================================================

# Pre-compiled regex patterns
_HEAD_PATTERN = re.compile(rb"(<head(?:\s[^>]*)?>)", re.IGNORECASE)
_HTML_PATTERN = re.compile(rb"(<html(?:\s[^>]*)?>)", re.IGNORECASE)
_SCRIPT_OPEN_PATTERN = re.compile(rb"<script(?:\s[^>]*)?>", re.IGNORECASE)
_SCRIPT_CLOSE_PATTERN = re.compile(rb"</script\s*>", re.IGNORECASE)
_STYLE_OPEN_PATTERN = re.compile(rb"<style(?:\s[^>]*)?>", re.IGNORECASE)
_STYLE_CLOSE_PATTERN = re.compile(rb"</style\s*>", re.IGNORECASE)

_SCRIPT_TAG = '<script type="text/javascript">{}</script>'.format(
    INITIALIZE_SANDBOX_FROM_IFRAME
)
_SCRIPT_TAG_BYTES = _SCRIPT_TAG.encode("utf-8")
_HEAD_WITH_SCRIPT = b"<head>" + _SCRIPT_TAG_BYTES + b"</head>"


def _is_inside_comment(content, position):
    before = content[:position]
    last_open = before.rfind(b"<!--")
    if last_open == -1:
        return False
    close_after_open = before.find(b"-->", last_open + 4)
    return close_after_open == -1


def _is_inside_cdata(content, position):
    before = content[:position]
    last_open = before.rfind(b"<![CDATA[")
    if last_open == -1:
        return False
    close_after_open = before.find(b"]]>", last_open + 9)
    return close_after_open == -1


def _is_inside_unclosed_tag(before, open_pattern, close_pattern):
    """Check if position is inside an unclosed tag (script or style)."""
    last_open = -1
    for match in open_pattern.finditer(before):
        last_open = match.end()

    if last_open == -1:
        return False

    last_close = -1
    for match in close_pattern.finditer(before):
        if match.start() >= last_open:
            last_close = match.end()

    return last_close == -1 or last_close < last_open


def _is_inside_script_or_style(content, position):
    before = content[:position]
    if _is_inside_unclosed_tag(before, _SCRIPT_OPEN_PATTERN, _SCRIPT_CLOSE_PATTERN):
        return True
    if _is_inside_unclosed_tag(before, _STYLE_OPEN_PATTERN, _STYLE_CLOSE_PATTERN):
        return True
    return False


def _is_inside_tag_brackets(content, position):
    before = content[:position]
    last_open = before.rfind(b"<")
    if last_open == -1:
        return False
    between = before[last_open:]
    return b">" not in between


def _is_valid_injection_point(content, position):
    return (
        not _is_inside_comment(content, position)
        and not _is_inside_cdata(content, position)
        and not _is_inside_script_or_style(content, position)
        and not _is_inside_tag_brackets(content, position)
    )


def parse_html_regex(content):
    """New regex-based implementation."""
    if isinstance(content, str):
        content = content.encode("utf-8")

    for head_match in _HEAD_PATTERN.finditer(content):
        if _is_valid_injection_point(content, head_match.start()):
            insert_pos = head_match.end()
            return content[:insert_pos] + _SCRIPT_TAG_BYTES + content[insert_pos:]

    for html_match in _HTML_PATTERN.finditer(content):
        if _is_valid_injection_point(content, html_match.start()):
            insert_pos = html_match.end()
            return content[:insert_pos] + _HEAD_WITH_SCRIPT + content[insert_pos:]

    return _HEAD_WITH_SCRIPT + content


# =============================================================================
# Test Data
# =============================================================================

# Small HTML (~45 bytes) - minimal valid HTML
HTML_SMALL = b"<html><head></head><body>Hello</body></html>"

# Medium HTML (~1.7KB) - typical simple webpage
HTML_MEDIUM = b"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sample Page</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { color: #333; }
        p { line-height: 1.6; }
        .button { background: #007bff; color: white; padding: 10px 20px; border: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Welcome to Our Website</h1>
        <p>This is a sample paragraph with some text content.</p>
        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>
        <button class="button">Click Me</button>
        <script>
            document.querySelector('.button').addEventListener('click', function() {
                alert('Button clicked!');
            });
        </script>
    </div>
</body>
</html>
"""

LOREM_IPSUM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris "
    "nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in "
    "reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur."
)


def generate_large_html():
    """Generate a large HTML document (~57KB)."""
    paragraphs = []

    # Generate enough content to reach ~57KB
    for i in range(150):
        paragraphs.append(f"<p id='para-{i}'>{LOREM_IPSUM}</p>")

    content = "\n".join(paragraphs)
    table_rows = "".join(
        f"<tr><td>{i}</td><td>Item {i}</td><td>{i * 100}</td><td>Active</td></tr>"
        for i in range(50)
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Large Document</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 40px; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        p {{ line-height: 1.8; color: #555; margin-bottom: 15px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background: #3498db; color: white; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Large Document for Performance Testing</h1>
        <h2>Introduction</h2>
        {content}
        <h2>Data Table</h2>
        <table>
            <tr><th>ID</th><th>Name</th><th>Value</th><th>Status</th></tr>
            {table_rows}
        </table>
        <script>
            console.log('Page loaded');
            document.querySelectorAll('p').forEach(function(p, i) {{
                p.dataset.index = i;
            }});
        </script>
    </div>
</body>
</html>
"""
    return html.encode("utf-8")


HTML_LARGE = generate_large_html()


# =============================================================================
# Benchmark Functions
# =============================================================================


def benchmark(func, data, iterations=100, warmup=10):
    """
    Run a benchmark with warmup iterations.
    Returns mean, stdev, min, max times in microseconds.
    """
    # Warmup
    for _ in range(warmup):
        func(data)

    # Actual timing
    times = []
    for _ in range(iterations):
        start = timeit.default_timer()
        func(data)
        end = timeit.default_timer()
        times.append((end - start) * 1_000_000)  # Convert to microseconds

    return {
        "mean": statistics.mean(times),
        "stdev": statistics.stdev(times) if len(times) > 1 else 0,
        "min": min(times),
        "max": max(times),
        "iterations": iterations,
    }


def format_time(us):
    """Format microseconds for display."""
    if us >= 1000:
        return f"{us/1000:.1f} ms"
    return f"{us:.1f} µs"


def verify_implementations(test_cases):
    """Verify both implementations produce correct output."""
    logger.info("Verifying implementations produce correct output...")
    for name, data, _, _, _ in test_cases:
        result_html5lib = parse_html_html5lib(data)
        result_regex = parse_html_regex(data)

        # Check that the script was injected
        script_check = INITIALIZE_SANDBOX_FROM_IFRAME.encode("utf-8")

        # html5lib returns string, regex returns bytes
        if isinstance(result_html5lib, str):
            html5lib_has_script = INITIALIZE_SANDBOX_FROM_IFRAME in result_html5lib
        else:
            html5lib_has_script = script_check in result_html5lib

        regex_has_script = script_check in result_regex

        status = "OK" if (html5lib_has_script and regex_has_script) else "FAIL"
        logger.info("  %s: %s", name, status)

        if not html5lib_has_script:
            logger.warning("    WARNING: html5lib did not inject script!")
        if not regex_has_script:
            logger.warning("    WARNING: regex did not inject script!")
    logger.info("")


def run_benchmarks(test_cases):
    """Run benchmarks and return results."""
    logger.info("Running benchmarks (100 iterations each with 10 warmup)...")
    logger.info("")

    results = []
    for name, data, claimed_old, claimed_new, claimed_speedup in test_cases:
        logger.info("Benchmarking %s HTML (%s bytes)...", name, f"{len(data):,}")

        html5lib_result = benchmark(parse_html_html5lib, data)
        regex_result = benchmark(parse_html_regex, data)
        speedup = html5lib_result["mean"] / regex_result["mean"]

        results.append(
            {
                "name": name,
                "size": len(data),
                "html5lib": html5lib_result,
                "regex": regex_result,
                "speedup": speedup,
                "claimed_old": claimed_old,
                "claimed_new": claimed_new,
                "claimed_speedup": claimed_speedup,
            }
        )
    return results


def print_results_table(results):
    """Print results summary table."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("RESULTS")
    logger.info("=" * 80)
    logger.info("")

    header = (
        f"{'Size':<10} {'html5lib':<20} {'regex':<20} {'Speedup':<15} {'Claimed':<10}"
    )
    logger.info(header)
    logger.info("-" * 75)

    for r in results:
        html5lib_time = format_time(r["html5lib"]["mean"])
        regex_time = format_time(r["regex"]["mean"])
        speedup = f"{r['speedup']:.0f}x"
        claimed = f"~{r['claimed_speedup']:,}x"
        row = (
            f"{r['name']:<10} {html5lib_time:<20} {regex_time:<20} "
            f"{speedup:<15} {claimed:<10}"
        )
        logger.info(row)


def print_detailed_results(results):
    """Print detailed results for each test case."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("DETAILED RESULTS")
    logger.info("=" * 80)

    for r in results:
        logger.info("")
        logger.info("%s HTML (%s bytes)", r["name"], f"{r['size']:,}")
        logger.info("-" * 40)

        logger.info("  html5lib:")
        logger.info("    Mean:   %s", format_time(r["html5lib"]["mean"]))
        logger.info("    Stdev:  %s", format_time(r["html5lib"]["stdev"]))
        logger.info("    Min:    %s", format_time(r["html5lib"]["min"]))
        logger.info("    Max:    %s", format_time(r["html5lib"]["max"]))
        logger.info("    Claimed: ~%s µs", f"{r['claimed_old']:,}")

        logger.info("  regex:")
        logger.info("    Mean:   %s", format_time(r["regex"]["mean"]))
        logger.info("    Stdev:  %s", format_time(r["regex"]["stdev"]))
        logger.info("    Min:    %s", format_time(r["regex"]["min"]))
        logger.info("    Max:    %s", format_time(r["regex"]["max"]))
        logger.info("    Claimed: ~%s µs", r["claimed_new"])

        logger.info(
            "  Speedup: %.0fx (claimed: ~%sx)",
            r["speedup"],
            f"{r['claimed_speedup']:,}",
        )

        # Compare to claimed values
        html5lib_ratio = r["html5lib"]["mean"] / r["claimed_old"]
        regex_ratio = r["regex"]["mean"] / r["claimed_new"]
        speedup_ratio = r["speedup"] / r["claimed_speedup"]

        logger.info("  Claim validation:")
        logger.info("    html5lib: %.2fx claimed value", html5lib_ratio)
        logger.info("    regex:    %.2fx claimed value", regex_ratio)
        logger.info("    speedup:  %.2fx claimed speedup", speedup_ratio)


def print_summary(results):
    """Print summary and validation status."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info("")

    all_speedups_validated = True
    for r in results:
        # Consider claim validated if actual speedup is at least 50% of claimed
        if r["speedup"] < r["claimed_speedup"] * 0.5:
            all_speedups_validated = False
            logger.warning(
                "WARNING: %s speedup (%.0fx) is less than 50%% of claimed (%sx)",
                r["name"],
                r["speedup"],
                f"{r['claimed_speedup']:,}",
            )

    if all_speedups_validated:
        logger.info("All performance claims are within acceptable range!")
        logger.info("")
        logger.info(
            "The regex-based implementation provides significant performance "
            "improvements over the html5lib-based implementation across all test cases."
        )
    else:
        logger.info("")
        logger.info("Some performance claims could not be validated.")
        logger.info("This may be due to differences in hardware or Python version.")


def main():
    """Main benchmark entry point."""
    logger.info("=" * 80)
    logger.info("HTML Script Injection Benchmark: html5lib vs Regex")
    logger.info("=" * 80)
    logger.info("")

    test_cases = [
        ("Small", HTML_SMALL, 1500, 2.3, 650),
        ("Medium", HTML_MEDIUM, 5000, 2.7, 1850),
        ("Large", HTML_LARGE, 60000, 5.4, 11000),
    ]

    # Print test data sizes
    logger.info("Test Data Sizes:")
    logger.info("  Small:  %s bytes", f"{len(HTML_SMALL):,}")
    logger.info("  Medium: %s bytes", f"{len(HTML_MEDIUM):,}")
    logger.info("  Large:  %s bytes", f"{len(HTML_LARGE):,}")
    logger.info("")

    verify_implementations(test_cases)
    results = run_benchmarks(test_cases)
    print_results_table(results)
    print_detailed_results(results)
    print_summary(results)


if __name__ == "__main__":
    main()
