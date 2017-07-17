# -*- coding: utf-8 -*-
"""
The Buffer class provides the functionality required by a parser-driven lexer.

Line analysis and caching are done so the parser can freely move with goto(p)
to any position in the parsed text, and still recover accurate information
about source lines and content.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
from itertools import takewhile, repeat

from tatsu.util import identity, imap, ustr, strtype
from tatsu.util import extend_list, contains_sublist
from tatsu.util import re as regexp
from tatsu.util import WHITESPACE_RE
from tatsu.exceptions import ParseError
from tatsu.infos import PosLine, LineIndexInfo, LineInfo, CommentInfo

RETYPE = type(regexp.compile('.'))

# for backwards compatibility with existing parsers
LineIndexEntry = LineIndexInfo


class Buffer(object):
    def __init__(self,
                 text,
                 filename=None,
                 whitespace=None,
                 comments_re=None,
                 eol_comments_re=None,
                 ignorecase=False,
                 nameguard=None,
                 comment_recovery=False,
                 namechars='',
                 **kwargs):
        text = ustr(text)
        self.text = self.original_text = text
        self.filename = filename or ''

        self.whitespace = whitespace

        self.comments_re = comments_re
        self.eol_comments_re = eol_comments_re
        self.ignorecase = ignorecase
        self.nameguard = (nameguard
                          if nameguard is not None
                          else bool(self.whitespace_re))
        self.comment_recovery = comment_recovery
        self.namechars = namechars
        self._namechar_set = set(namechars)
        if namechars:
            self.nameguard = True

        self._pos = 0
        self._len = 0
        self._linecount = 0
        self._lines = []
        self._line_index = []
        self._line_cache = []
        self._comment_index = []
        self._re_cache = {}

        self._preprocess()
        self._postprocess()

    @property
    def whitespace(self):
        return self._whitespace

    @whitespace.setter
    def whitespace(self, value):
        self._whitespace = value
        self.whitespace_re = self.build_whitespace_re(value)

    @staticmethod
    def build_whitespace_re(whitespace):
        if whitespace is None:
            return WHITESPACE_RE
        elif isinstance(whitespace, RETYPE):
            return whitespace
        elif whitespace:
            if not isinstance(whitespace, strtype):
                # a list or a set?
                whitespace = ''.join(c for c in whitespace)
            return regexp.compile(
                '[%s]+' % regexp.escape(whitespace),
                regexp.MULTILINE | regexp.UNICODE
            )
        else:
            return None

    def _preprocess(self, *args, **kwargs):
        lines, index = self._preprocess_block(self.filename, self.text)
        self._lines = lines
        self._line_index = index
        self.text = self.join_block_lines(lines)

    def _postprocess(self):
        cache, count = PosLine.build_line_cache(self._lines)
        self._line_cache = cache
        self._linecount = count
        self._len = len(self.text)

    def _preprocess_block(self, name, block, **kwargs):
        lines = self.split_block_lines(block)
        index = LineIndexInfo.block_index(name, len(lines))
        return self.process_block(name, lines, index, **kwargs)

    def split_block_lines(self, block):
        return block.splitlines(True)

    def join_block_lines(self, lines):
        return ''.join(lines)

    def process_block(self, name, lines, index, **kwargs):
        return lines, index

    def include(self, lines, index, i, j, name, block, **kwargs):
        blines, bindex = self._preprocess_block(name, block, **kwargs)
        assert len(blines) == len(bindex)
        lines[i:j] = blines
        index[i:j] = bindex
        assert len(lines) == len(index)
        return j + len(blines) - 1

    def include_file(self, source, name, lines, index, i, j):
        text, filename = self.get_include(source, name)
        return self.include(lines, index, i, j, filename, text)

    def get_include(self, source, filename):
        source = os.path.abspath(source)
        base = os.path.dirname(source)
        include = os.path.join(base, filename)
        try:
            with open(include) as f:
                return f.read(), include
        except IOError:
            raise ParseError('include not found: %s' % include)

    def replace_lines(self, i, j, name, block):
        lines = self.split_block_lines(self.text)
        index = list(self._line_index)

        endline = self.include(lines, index, i, j, name, block)

        self.text = self.join_block_lines(lines)
        self._line_index = index
        self._postprocess()

        newtext = self.join_block_lines(lines[j + 1:endline + 2])
        return endline, newtext

    @property
    def pos(self):
        return self._pos

    @pos.setter
    def pos(self, p):
        self.goto(p)

    @property
    def line(self):
        return self.posline()

    @property
    def col(self):
        return self.poscol()

    def posline(self, pos=None):
        if pos is None:
            pos = self._pos
        return self._line_cache[pos].line

    def poscol(self, pos=None):
        if pos is None:
            pos = self._pos
        start = self._line_cache[pos].start
        return pos - start

    def atend(self):
        return self._pos >= self._len

    def ateol(self):
        return self.atend() or self.current() in '\r\n'

    def current(self):
        if self._pos >= self._len:
            return None
        return self.text[self._pos]

    def at(self, p):
        if p >= self._len:
            return None
        return self.text[p]

    def peek(self, n=1):
        return self.at(self._pos + n)

    def next(self):
        if self._pos >= self._len:
            return None
        c = self.text[self._pos]
        self._pos += 1
        return c

    def goto(self, p):
        self._pos = max(0, min(len(self.text), p))

    def move(self, n):
        self.goto(self.pos + n)

    def comments(self, p, clear=False):
        if not self.comment_recovery or not self._comment_index:
            return CommentInfo([], [])

        n = self.posline(p)
        if n >= len(self._comment_index):
            return CommentInfo([], [])

        eolcmm = []
        if n < len(self._comment_index):
            eolcmm = self._comment_index[n].eol
            if clear:
                self._comment_index[n].eol = []

        cmm = []
        while n >= 0 and self._comment_index[n].inline:
            cmm.insert(0, self._comment_index[n].inline)
            if clear:
                self._comment_index[n].inline = []
            n -= 1

        return CommentInfo(cmm, eolcmm)

    def _index_comments(self, comments, selector):
        if comments and self.comment_recovery:
            n = self.line
            extend_list(self._comment_index, n, default=CommentInfo.new_comment)
            previous = selector(self._comment_index[n])
            if not contains_sublist(previous, comments):  # FIXME: will discard repeated comments
                previous.extend(comments)

    def _eat_regex(self, regex):
        if regex is not None:
            return list(takewhile(identity, imap(self.matchre, repeat(regex))))

    def eat_whitespace(self):
        return self._eat_regex(self.whitespace_re)

    def eat_comments(self):
        comments = self._eat_regex(self.comments_re)
        self._index_comments(comments, lambda x: x.inline)

    def eat_eol_comments(self):
        comments = self._eat_regex(self.eol_comments_re)
        self._index_comments(comments, lambda x: x.eol)

    def next_token(self):
        p = None
        while self._pos != p:
            p = self._pos
            self.eat_eol_comments()
            self.eat_comments()
            self.eat_whitespace()

    def skip_to(self, c):
        p = self._pos
        le = self._len
        while p < le and self.text[p] != c:
            p += 1
        self.goto(p)
        return self.pos

    def skip_past(self, c):
        self.skip_to(c)
        self.next()
        return self.pos

    def skip_to_eol(self):
        return self.skip_to('\n')

    def scan_space(self, offset=0):
        return (
            self.whitespace_re and
            self._scanre(self.whitespace_re, offset=offset) is not None
        )

    def is_space(self):
        return self.scan_space()

    def is_name_char(self, c):
        return c is not None and c.isalnum() or c in self._namechar_set

    def match(self, token, ignorecase=None):
        ignorecase = ignorecase if ignorecase is not None else self.ignorecase

        if token is None:
            return self.atend()

        p = self.pos
        if ignorecase:
            is_match = self.text[p:p + len(token)].lower() == token.lower()
        else:
            is_match = self.text[p:p + len(token)] == token

        if is_match:
            self.move(len(token))
            if not self.nameguard:
                return token

            partial_match = (
                token.isalnum() and
                token[0].isalpha() and
                self.is_name_char(self.current())
            )
            if not partial_match:
                return token
        self.goto(p)

    def matchre(self, pattern, ignorecase=None):
        matched = self._scanre(pattern, ignorecase=ignorecase)
        if matched:
            token = matched.group()
            self.move(len(token))
            return token

    def _scanre(self, pattern, ignorecase=None, offset=0):
        if isinstance(pattern, RETYPE):
            re = pattern
        elif pattern in self._re_cache:
            re = self._re_cache[pattern]
        else:
            re = regexp.compile(pattern, regexp.MULTILINE | regexp.UNICODE)
            self._re_cache[pattern] = re
        return re.match(self.text, self.pos + offset)

    @property
    def linecount(self):
        return self._linecount

    def line_info(self, pos=None):
        if pos is None:
            pos = self._pos

        if pos >= len(self._line_cache):
            return LineInfo(self.filename, self.linecount, 0, self._len, self._len, '')

        start, line, length = self._line_cache[pos]
        end = start + length
        col = pos - start

        text = self.text[start:end]
        n = min(len(self._line_index) - 1, line)
        filename, line = self._line_index[n]

        return LineInfo(filename, line, col, start, end, text)

    def lookahead_pos(self):
        if self.atend():
            return ''
        info = self.line_info()
        return '~%d:%d' % (info.line + 1, info.col + 1)

    def lookahead(self):
        if self.atend():
            return ''
        info = self.line_info()
        text = info.text[info.col:info.col + 1 + 80]
        text = self.split_block_lines(text)[0].rstrip()
        return '%s' % (text)

    def get_line(self, n=None):
        if n is None:
            n = self.line
        return self._lines[n]

    def get_lines(self, start=None, end=None):
        if start is None:
            start = 0
        if end is None:
            end = len(self._lines)
        return self._lines[start:end + 1]

    def line_index(self, start=0, end=None):
        if end is None:
            end = len(self._line_index)
        return self._line_index[start:1 + end]

    def __repr__(self):
        return '%s@%d' % (type(self).__name__, self.pos)

    def __json__(self):
        return None
