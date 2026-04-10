import re
from context import ProjectContext


class PromptResolver:
    def __init__(self, context: ProjectContext):
        self.context = context
        self.re_project = re.compile(r"\[@project\]")
        self.re_dir = re.compile(r"<@dir:([^>]+)>")
        self.re_file = re.compile(r"<@file:([^>]+)>")
        self.re_type = re.compile(r"<@type:([^>]+)>")

    def resolve(self, text: str, visited: set = None) -> str:
        if visited is None:
            visited = set()

        if self.re_project.search(text):
            call_sig = "[@project]"
            if call_sig in visited:
                text = self.re_project.sub(f"<!-- Loop detected: {call_sig} -->", text)
            else:
                new_visited = visited.copy()
                new_visited.add(call_sig)
                tree_content = self.context.generate_tree()
                text = self.re_project.sub(lambda m: tree_content, text)

        def dir_repl(match):
            path = match.group(1)
            call_sig = f"<@dir:{path}>"
            if call_sig in visited:
                return f"<!-- Loop detected: {call_sig} -->"
            new_visited = visited.copy()
            new_visited.add(call_sig)
            content = self.context.get_dir_contents(path)
            return self.resolve(content, new_visited)

        text = self.re_dir.sub(dir_repl, text)

        def file_repl(match):
            path = match.group(1)
            call_sig = f"<@file:{path}>"
            if call_sig in visited:
                return f"<!-- Loop detected: {call_sig} -->"
            new_visited = visited.copy()
            new_visited.add(call_sig)
            content = self.context.get_file_content(path)
            return self.resolve(content, new_visited)

        text = self.re_file.sub(file_repl, text)

        def type_repl(match):
            ext = match.group(1)
            call_sig = f"<@type:{ext}>"
            if call_sig in visited:
                return f"<!-- Loop detected: {call_sig} -->"
            new_visited = visited.copy()
            new_visited.add(call_sig)
            content = self.context.get_type_contents(ext)
            return self.resolve(content, new_visited)

        text = self.re_type.sub(type_repl, text)

        return text
