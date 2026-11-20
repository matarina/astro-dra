"""Convert API abstract markup without interpreting scientific '<' as a tag."""
from html.parser import HTMLParser


class AbstractText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag.casefold() in {"h4", "p", "div", "br"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag.casefold() in {"h4", "p", "div"}:
            self.parts.append(" ")


def abstract_text(markup):
    parser = AbstractText()
    parser.feed(markup)
    parser.close()
    return "".join(parser.parts)
