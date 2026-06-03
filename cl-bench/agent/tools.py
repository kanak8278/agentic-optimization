"""Context search and read tools for the agent."""

import re


class ContextTools:
    """Tools that operate on a context file."""

    def __init__(self, file_path):
        self.file_path = file_path
        with open(file_path, "r", encoding="utf-8") as f:
            self.lines = f.readlines()
        self.total_lines = len(self.lines)

    def search_context(self, pattern, context_lines=2, max_matches=10):
        """
        Regex search over the context file.

        Args:
            pattern: Regex pattern to search for
            context_lines: Lines of context around each match (max 5)
            max_matches: Max matches to return (max 20)

        Returns:
            dict with status and message
        """
        context_lines = min(context_lines, 5)
        max_matches = min(max_matches, 20)

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return {"status": "error", "message": f"Invalid regex: {e}"}

        # Find ALL matches first to report total count
        all_matches = []
        for i, line in enumerate(self.lines):
            if regex.search(line):
                all_matches.append(i)

        if not all_matches:
            return {"status": "not_found", "message": f"No matches for '{pattern}'."}

        # Show only up to max_matches, but report total
        shown_matches = all_matches[:max_matches]

        sections = []
        for match_idx in shown_matches:
            start = max(0, match_idx - context_lines)
            end = min(self.total_lines, match_idx + context_lines + 1)

            section = []
            for j in range(start, end):
                marker = ">>>" if j == match_idx else "   "
                line_text = self.lines[j].rstrip("\n")
                if len(line_text) > 200:
                    line_text = line_text[:200] + "..."
                section.append(f"{j + 1:5d} {marker}| {line_text}")
            sections.append("\n".join(section))

        # Header with total count and all match line numbers
        match_lines_str = ", ".join(str(m + 1) for m in all_matches)
        header = (
            f"Found {len(all_matches)} total match(es) for '{pattern}' "
            f"at lines: [{match_lines_str}]\n"
            f"Showing {len(shown_matches)} of {len(all_matches)}:"
        )

        output = header + "\n\n" + "\n\n---\n\n".join(sections)

        if len(output) > 10000:
            output = output[:10000] + "\n\n[OUTPUT TRUNCATED]"

        return {"status": "success", "message": output}

    def read_lines(self, start_line, end_line):
        """
        Read a range of lines from the context file.

        Args:
            start_line: Start line number (1-indexed, inclusive)
            end_line: End line number (1-indexed, inclusive)

        Returns:
            dict with status and message
        """
        if end_line - start_line + 1 > 200:
            return {"status": "error", "message": f"Max 200 lines per call. Requested {end_line - start_line + 1}."}

        start = max(0, start_line - 1)
        end = min(self.total_lines, end_line)

        if start >= self.total_lines:
            return {"status": "error", "message": f"Start line {start_line} out of range. File has {self.total_lines} lines."}

        result = []
        for i in range(start, end):
            result.append(f"{i + 1:5d}| {self.lines[i].rstrip(chr(10))}")

        return {
            "status": "success",
            "message": f"Lines {start + 1}-{end} of {self.total_lines}:\n\n" + "\n".join(result),
        }

    def execute(self, tool_name, tool_input):
        """Execute a tool by name."""
        # Coerce string-typed integers (some models return "2" instead of 2)
        coerced = {}
        for k, v in tool_input.items():
            if isinstance(v, str) and k in ("context_lines", "max_matches", "start_line", "end_line"):
                try:
                    v = int(v)
                except ValueError:
                    pass
            coerced[k] = v

        if tool_name == "search_context":
            return self.search_context(**coerced)
        elif tool_name == "read_lines":
            return self.read_lines(**coerced)
        else:
            return {"status": "error", "message": f"Unknown tool: {tool_name}"}


# Anthropic tool definitions
TOOL_DEFINITIONS = [
    {
        "name": "search_context",
        "description": (
            "Search the context document using a regex pattern. "
            "Returns matching lines with surrounding context and line numbers. "
            "Use this to find specific rules, definitions, data points, or procedures in the document."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for (case-insensitive)",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Lines of context around each match (default 2, max 5)",
                    "default": 2,
                },
                "max_matches": {
                    "type": "integer",
                    "description": "Maximum matches to return (default 10, max 20)",
                    "default": 10,
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "read_lines",
        "description": (
            "Read a specific range of lines from the context document. "
            "Use this when you know the approximate location and need to read a section in detail. "
            "Max 200 lines per call."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_line": {
                    "type": "integer",
                    "description": "Start line number (1-indexed, inclusive)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line number (1-indexed, inclusive)",
                },
            },
            "required": ["start_line", "end_line"],
        },
    },
]


# OpenAI-format tool definitions (used by litellm for all providers)
TOOLS_OPENAI_FORMAT = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in TOOL_DEFINITIONS
]
