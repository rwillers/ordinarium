from html.parser import HTMLParser


def parse_fragment(fragment):
    parser = FragmentParser()
    parser.feed(fragment or "")
    parser.close()
    return parser.root


def serialize_children(node):
    return "".join(serialize_node(child) for child in node["children"])


def serialize_node(node):
    if node["type"] == "text":
        return node["text"]
    if node["tag"] == "br":
        return "<br>"
    attrs = "".join(f' {key}="{value}"' for key, value in node["attrs"].items())
    inner = "".join(serialize_node(child) for child in node["children"])
    return f"<{node['tag']}{attrs}>{inner}</{node['tag']}>"


class FragmentParser(HTMLParser):
    VOID_TAGS = {"br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"type": "element", "tag": "root", "attrs": {}, "children": []}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        tag_name = tag.lower()
        node = {
            "type": "element",
            "tag": tag_name,
            "attrs": {key: value for key, value in attrs},
            "children": [],
        }
        self.stack[-1]["children"].append(node)
        if tag_name not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag):
        tag_name = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index]["tag"] == tag_name:
                self.stack = self.stack[:index]
                return

    def handle_data(self, data):
        if data:
            self.stack[-1]["children"].append({"type": "text", "text": data})
