import re

break_line_r = re.compile(r'''<br[^>]*>''')


def filter_escape(html):
    if not isinstance(html, str):
        return html

    replaced_breakline = ' \n '.join(list(map(str.strip, break_line_r.split(html))))
    return replaced_breakline
