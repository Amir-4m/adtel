import re

break_line_r = re.compile(r'''<br[^>]*>''')


def filter_escape(html):
    if isinstance(html, str):
        replaced_breakline = ' \n '.join(list(map(str.strip, break_line_r.split(html))))
        return replaced_breakline
    return html
