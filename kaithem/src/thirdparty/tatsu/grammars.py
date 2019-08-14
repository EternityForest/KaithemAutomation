# -*- coding: utf-8 -*-
from __future__ import generator_stop

import os
import functools
from collections.abc import Mapping
from collections import defaultdict
from copy import copy
from itertools import takewhile

from tatsu.util import (
    indent, trim, compress_seq, chunks,
    re, notnone,
)
from tatsu.exceptions import FailedRef, GrammarError
from tatsu.ast import AST
from tatsu.contexts import ParseContext
from tatsu.objectmodel import Node
from tatsu.bootstrap import EBNFBootstrapBuffer
from tatsu.infos import RuleInfo
from tatsu.leftrec import Nullable, find_left_recursion


PEP8_LLEN = 72


COMMENTS_RE = r'\(\*((?:.|\n)*?)\*\)'
EOL_COMMENTS_RE = r'#([^\n]*?)$'
PRAGMA_RE = r'^\s*#include.*$'


def dot(x, y, k):
    return {(a + b)[:k] for a in x for b in y}


def pythonize_name(name):
    return ''.join('_' + c.lower() if c.isupper() else c for c in name)


class EBNFBuffer(EBNFBootstrapBuffer):
    def __init__(
            self, text, filename=None, comments_re=None, eol_comments_re=None, **kwargs):
        super().__init__(
            text,
            filename=filename,
            memoize_lookaheads=False,
            comment_recovery=True,
            comments_re=comments_re or COMMENTS_RE,
            eol_comments_re=eol_comments_re or EOL_COMMENTS_RE,
            **kwargs
        )

    def process_block(self, name, lines, index, **kwargs):
        i = 0
        while i < len(lines):
            line = lines[i]
            if re.match(PRAGMA_RE, line):
                directive, arg = line.split('#', 1)[1], ''
                if '::' in directive:
                    directive, arg = directive.split('::', 1)
                directive, arg = directive.strip(), arg.strip()
                i = self.pragma(name, directive, arg, lines, index, i)
            else:
                i += 1
        return lines, index

    def pragma(self, source, name, arg, lines, index, i):
        # we only recognize the 'include' pragama
        if name == 'include':
            filename = arg.strip('\'"')
            return self.include_file(source, filename, lines, index, i, i + 1)
        else:
            return i + 1  # will be treated as a directive by the parser


class ModelContext(ParseContext):
    def __init__(self, rules, semantics=None, trace=False, **kwargs):
        super().__init__(
            semantics=semantics,
            trace=trace,
            **kwargs
        )
        self.rules = {rule.name: rule for rule in rules}

    @property
    def pos(self):
        return self._tokenizer.pos

    def _find_rule(self, name):
        return functools.partial(self.rules[name].parse, self)


class Model(Node):
    @staticmethod
    def classes():
        return [
            c for c in globals().values()
            if isinstance(c, type) and issubclass(c, Model)
        ]

    def __init__(self, ast=None, ctx=None):
        super().__init__(ast=ast, ctx=ctx)
        self._lookahead = None
        self._first_set = None
        self._follow_set = set()
        self.value = None
        self._nullability = self._nullable()
        if isinstance(self._nullability, int):  # Allow simple boolean values
            if self._nullability:
                self._nullability = Nullable.yes()
            else:
                self._nullability = Nullable.no()

    def parse(self, ctx):
        ctx.last_node = None
        return None

    def defines(self):
        return []

    def lookahead(self, k=1):
        if self._lookahead is None:
            self._lookahead = dot(self.firstset(k), self.followset(k), k)
        return self._lookahead

    def firstset(self, k=1):
        if self._first_set is None:
            self._first_set = self._first(k, {})
        return self._first_set

    def followset(self, k=1):
        return self._follow_set

    def missing_rules(self, rules):
        return set()

    def _used_rule_names(self):
        return set()

    def _first(self, k, f):
        return set()

    def _follow(self, k, fl, a):
        return a

    def is_nullable(self, ctx=None):
        return self._nullability.nullable

    def _nullable(self):
        return False

    # list of rules that can be invoked at the same position
    def at_same_pos(self, ctx):
        return []

    def comments_str(self):
        comments, eol = self.comments
        if not comments:
            return ''

        return '\n'.join(
            '(* %s *)\n' % '\n'.join(c).replace('(*', '').replace('*)', '').strip()
            for c in comments
        )

    def nodecount(self):
        return 1

    def pretty(self):
        return self._to_str()

    def pretty_lean(self):
        return self._to_str(lean=True)

    def _to_str(self, lean=False):
        return '%s:%d' % (type(self).__name__, id(self))

    def __str__(self):
        return self._to_str()


class Void(Model):
    def parse(self, ctx):
        return ctx._void()

    def _to_str(self, lean=False):
        return '()'

    def _nullable(self):
        return True


class Any(Model):
    def parse(self, ctx):
        return ctx._any()

    def _to_str(self, lean=False):
        return '/./'


class Fail(Model):
    def parse(self, ctx):
        return ctx._fail()

    def _to_str(self, lean=False):
        return '!()'


class Comment(Model):
    def __init__(self, ast=None, **kwargs):
        self.comment = None
        super().__init__(ast=AST(comment=ast))

    def _to_str(self, lean=False):
        return '(* %s *)' % self.comment


class EOLComment(Comment):
    def _to_str(self, lean=False):
        return '  # %s\n' % self.comment


class EOF(Model):
    def parse(self, ctx):
        ctx._check_eof()

    def _to_str(self, lean=False):
        return '$'


class Decorator(Model):
    def __init__(self, ast=None, exp=None, **kwargs):
        if exp is not None:
            self.exp = exp
        elif not isinstance(ast, AST):
            # Patch to avoid bad interactions with attribute setting in Model.
            # Also a shortcut for subexpressions that are not ASTs.
            ast = AST(exp=ast)
        super().__init__(ast)
        assert isinstance(self.exp, Model)

    def parse(self, ctx):
        return self.exp.parse(ctx)

    def defines(self):
        return self.exp.defines()

    def missing_rules(self, rules):
        return self.exp.missing_rules(rules)

    def _used_rule_names(self):
        return self.exp._used_rule_names()

    def _first(self, k, f):
        return self.exp._first(k, f)

    def _follow(self, k, fl, a):
        return self.exp._follow(k, fl, a)

    def nodecount(self):
        return 1 + self.exp.nodecount()

    def _to_str(self, lean=False):
        return self.exp._to_str(lean=lean)

    def _nullable(self):
        return Nullable.of(self.exp)

    def at_same_pos(self, ctx):
        return [self.exp]


# NOTE: backwards compatibility
_Decorator = Decorator


class Group(Decorator):
    def parse(self, ctx):
        with ctx._group():
            self.exp.parse(ctx)
            return ctx.last_node

    def _to_str(self, lean=False):
        exp = self.exp._to_str(lean=lean)
        if len(exp.splitlines()) > 1:
            return '(\n%s\n)' % indent(exp)
        else:
            return '(%s)' % trim(exp)


class Token(Model):
    def __postinit__(self, ast):
        super().__postinit__(ast)
        self.token = ast

    def parse(self, ctx):
        return ctx._token(self.token)

    def _first(self, k, f):
        return {(self.token,)}

    def _to_str(self, lean=False):
        return repr(self.token)


class Constant(Model):
    def __postinit__(self, ast):
        super().__postinit__(ast)
        self.literal = ast

    def parse(self, ctx):
        return self.literal

    def _to_str(self, lean=False):
        return '`%s`' % repr(self.literal)

    def _nullable(self):
        return True


class Pattern(Model):
    def __postinit__(self, ast):
        super().__postinit__(ast)
        if not isinstance(ast, list):
            ast = [ast]
        self.patterns = ast
        self.regex = re.compile(self.pattern)

    @property
    def pattern(self):
        return ''.join(self.patterns)

    def parse(self, ctx):
        return ctx._pattern(self.pattern)

    def _first(self, k, f):
        return {(self.pattern,)}

    def _to_str(self, lean=False):
        parts = []
        for pat in (str(p) for p in self.patterns):
            template = '/%s/'
            if '/' in pat:
                template = '?"%s"'
                pat = pat.replace('"', r'\"')
            parts.append(template % pat)
        return '\n+ '.join(parts)

    def _nullable(self):
        return bool(self.regex.match(""))


class Lookahead(Decorator):
    def parse(self, ctx):
        with ctx._if():
            return super().parse(ctx)

    def _to_str(self, lean=False):
        return '&' + self.exp._to_str(lean=lean)

    def _nullable(self):
        return True


class NegativeLookahead(Decorator):
    def parse(self, ctx):
        with ctx._ifnot():
            return super().parse(ctx)

    def _to_str(self, lean=False):
        return '!' + str(self.exp._to_str(lean=lean))

    def _nullable(self):
        return True


class SkipTo(Decorator):
    def parse(self, ctx):
        super_parse = super().parse
        return ctx._skip_to(lambda: super_parse(ctx))

    def _to_str(self, lean=False):
        return '->' + self.exp._to_str(lean=lean)


class Sequence(Model):
    def __init__(self, ast, **kwargs):
        assert ast.sequence
        self.sequence = ()
        super().__init__(ast=ast)

    def parse(self, ctx):
        ctx.last_node = [s.parse(ctx) for s in self.sequence]
        return ctx.last_node

    def defines(self):
        return [d for s in self.sequence for d in s.defines()]

    def missing_rules(self, rules):
        return set().union(*[s.missing_rules(rules) for s in self.sequence])

    def _used_rule_names(self):
        return set().union(*[s._used_rule_names() for s in self.sequence])

    def _first(self, k, f):
        result = {()}
        for s in self.sequence:
            result = dot(result, s._first(k, f), k)
        return result

    def _follow(self, k, fl, a):
        fs = a
        for x in reversed(self.sequence):
            if isinstance(x, RuleRef):
                fl[x.name] |= fs
            x._follow(k, fl, fs)
            fs = dot(x.firstset(k=k), fs, k)
        return a

    def nodecount(self):
        return 1 + sum(s.nodecount() for s in self.sequence)

    def _to_str(self, lean=False):
        comments = self.comments_str()
        seq = [str(s._to_str(lean=lean)) for s in self.sequence]
        single = ' '.join(seq)
        if len(single) <= PEP8_LLEN and len(single.splitlines()) <= 1:
            return comments + single
        else:
            return comments + '\n'.join(seq)

    def _nullable(self):
        return Nullable.all(self.sequence)

    def at_same_pos(self, ctx):
        head = list(takewhile(lambda c: c.is_nullable(ctx), self.sequence))
        if len(head) < len(self.sequence):
            head.append(self.sequence[len(head)])
        return head


class Choice(Model):
    def __init__(self, ast=None, **kwargs):
        self.options = []
        super().__init__(ast=AST(options=ast))
        assert isinstance(self.options, list), repr(self.options)

    def parse(self, ctx):
        with ctx._choice():
            for o in self.options:
                with ctx._option():
                    ctx.last_node = o.parse(ctx)
                    return ctx.last_node

            lookahead = ' '.join(str(repr(f[0])) for f in self.lookahead() if str(f))
            if lookahead:
                ctx._error('expecting one of {%s}' % lookahead)
            ctx._error('no available options')

    def defines(self):
        return [d for o in self.options for d in o.defines()]

    def missing_rules(self, rules):
        return set().union(*[o.missing_rules(rules) for o in self.options])

    def _used_rule_names(self):
        return set().union(*[o._used_rule_names() for o in self.options])

    def _first(self, k, f):
        result = set()
        for o in self.options:
            result |= o._first(k, f)
        return result

    def _follow(self, k, fl, a):
        for o in self.options:
            o._follow(k, fl, a)
        return a

    def nodecount(self):
        return 1 + sum(o.nodecount() for o in self.options)

    def _to_str(self, lean=False):
        options = [str(o._to_str(lean=lean)) for o in self.options]

        multi = any(len(o.splitlines()) > 1 for o in options)
        single = ' | '.join(o for o in options)

        if multi:
            return '\n|\n'.join(indent(o) for o in options)
        elif len(options) and len(single) > PEP8_LLEN:
            return '| ' + '\n| '.join(o for o in options)
        else:
            return single

    def _nullable(self):
        return Nullable.any(self.options)

    def at_same_pos(self, ctx):
        return self.options


class Closure(Decorator):
    def parse(self, ctx):
        return ctx._closure(lambda: self.exp.parse(ctx))

    def _first(self, k, f):
        efirst = self.exp._first(k, f)
        result = {()}
        for _i in range(k):
            result = dot(result, efirst, k)
        return {()} | result

    def _to_str(self, lean=False):
        sexp = str(self.exp._to_str(lean=lean))
        if len(sexp.splitlines()) <= 1:
            return '{%s}' % sexp
        else:
            return '{\n%s\n}' % indent(sexp)

    def _nullable(self):
        return True


class PositiveClosure(Closure):
    def parse(self, ctx):
        return ctx._positive_closure(lambda: self.exp.parse(ctx))

    def _first(self, k, f):
        efirst = self.exp._first(k, f)
        result = {()}
        for _i in range(k):
            result = dot(result, efirst, k)
        return result

    def _to_str(self, lean=False):
        return super()._to_str(lean=lean) + '+'

    def _nullable(self):
        return Nullable.of(self.exp)


class Join(Decorator):
    JOINOP = '%'

    def __init__(self, ast=None, **kwargs):
        super().__init__(ast.exp)
        self.sep = ast.sep

    def parse(self, ctx):
        def sep():
            return self.sep.parse(ctx)

        def exp():
            return self.exp.parse(ctx)

        return self._do_parse(ctx, exp, sep)

    def _do_parse(self, ctx, exp, sep):
        return ctx._join(exp, sep)

    def _to_str(self, lean=False):
        ssep = self.sep._to_str(lean=lean)
        sexp = str(self.exp._to_str(lean=lean))
        if len(sexp.splitlines()) <= 1:
            return '%s%s{%s}' % (ssep, self.JOINOP, sexp)
        else:
            return '%s%s{\n%s\n}' % (ssep, self.JOINOP, sexp)

    def _nullable(self):
        return True


class PositiveJoin(Join):
    def _do_parse(self, ctx, exp, sep):
        return ctx._positive_join(exp, sep)

    def _to_str(self, lean=False):
        return super()._to_str(lean=lean) + '+'

    def _nullable(self):
        return Nullable.of(self.exp)


class LeftJoin(PositiveJoin):
    JOINOP = '<'

    def _do_parse(self, ctx, exp, sep):
        return ctx._left_join(exp, sep)


class RightJoin(PositiveJoin):
    JOINOP = '>'

    def _do_parse(self, ctx, exp, sep):
        return ctx._right_join(exp, sep)


class Gather(Join):
    JOINOP = '.'

    def _do_parse(self, ctx, exp, sep):
        return ctx._gather(exp, sep)


class PositiveGather(Gather):
    def _do_parse(self, ctx, exp, sep):
        return ctx._positive_gather(exp, sep)

    def _to_str(self, lean=False):
        return super()._to_str(lean=lean) + '+'

    def _nullable(self):
        return Nullable.of(self.exp)


class EmptyClosure(Model):
    def parse(self, ctx):
        return ctx._empty_closure()

    def _to_str(self, lean=False):
        return '{}'

    def _nullable(self):
        return True


class Optional(Decorator):
    def parse(self, ctx):
        ctx.last_node = None
        with ctx._optional():
            return self.exp.parse(ctx)

    def _first(self, k, f):
        return {()} | self.exp._first(k, f)

    def _to_str(self, lean=False):
        exp = str(self.exp._to_str(lean=lean))
        template = '[%s]'
        if isinstance(self.exp, Choice):
            template = trim(self.str_template)
        elif isinstance(self.exp, Group):
            exp = self.exp.exp
        return template % exp

    str_template = '''
            [
            %s
            ]
            '''

    def _nullable(self):
        return True


class Cut(Model):
    def parse(self, ctx):
        ctx._cut()
        return None

    def _first(self, k, f):
        return {('~',)}

    def _to_str(self, lean=False):
        return '~'

    def _nullable(self):
        return True


class Named(Decorator):
    def __init__(self, ast=None, **kwargs):
        super().__init__(ast.exp)
        self.name = ast.name

    def parse(self, ctx):
        value = self.exp.parse(ctx)
        ctx.ast[self.name] = value
        return value

    def defines(self):
        return [(self.name, False)] + super().defines()

    def _to_str(self, lean=False):
        if lean:
            return self.exp._to_str(lean=True)
        return '%s:%s' % (self.name, self.exp._to_str(lean=lean))


class NamedList(Named):
    def parse(self, ctx):
        value = self.exp.parse(ctx)
        ctx.ast._setlist(self.name, value)
        return value

    def defines(self):
        return [(self.name, True)] + super().defines()

    def _to_str(self, lean=False):
        if lean:
            return self.exp._to_str(lean=True)
        return '%s+:%s' % (self.name, str(self.exp._to_str(lean=lean)))


class Override(Named):
    def __init__(self, ast=None, **kwargs):
        super().__init__(ast=AST(name='@', exp=ast))

    def defines(self):
        return []


class OverrideList(NamedList):
    def __init__(self, ast=None, **kwargs):
        super().__init__(ast=AST(name='@', exp=ast))

    def defines(self):
        return []


class Special(Model):
    def _first(self, k, f):
        return {(self.value,)}

    def _to_str(self, lean=False):
        return '?%s?' % self.value

    def _nullable(self):
        return True


class RuleRef(Model):
    def __postinit__(self, ast):
        super().__postinit__(ast)
        self.name = ast

    def parse(self, ctx):
        try:
            rule = ctx._find_rule(self.name)
        except KeyError:
            ctx._error(self.name, exclass=FailedRef)
        else:
            return rule()

    def missing_rules(self, rules):
        if self.name not in rules:
            return {self.name}
        return set()

    def _used_rule_names(self):
        return {self.name}

    def _first(self, k, f):
        self._first_set = f.get(self.name, set())
        return self._first_set

    def firstset(self, k=1):
        if self._first_set is None:
            self._first_set = {('<%s>' % self.name,)}
        return self._first_set

    def _to_str(self, lean=False):
        return self.name

    def is_nullable(self, ctx=None):
        return ctx[self.name].is_nullable(ctx)


class RuleInclude(Decorator):
    def __init__(self, rule):
        assert isinstance(rule, Rule), str(rule.name)
        super().__init__(rule.exp)
        self.rule = rule

    def _to_str(self, lean=False):
        return '>%s' % (self.rule.name)


class Rule(Decorator):
    def __init__(self, ast, name, exp, params, kwparams, decorators=None):
        assert kwparams is None or isinstance(kwparams, Mapping), kwparams
        super().__init__(exp=exp, ast=ast)
        self.name = name
        self.params = params
        self.kwparams = kwparams
        self.decorators = decorators or []
        self._adopt_children([params, kwparams])

        self.is_name = 'name' in self.decorators
        self.base = None
        self.is_leftrec = False  # Starts a left recursive cycle
        self.is_memoizable = 'nomemo' not in self.decorators

    def parse(self, ctx):
        result = self._parse_rhs(ctx, self.exp)
        self._add_defined_attributes(result)
        if self.is_name:
            ctx._check_name()
        return result

    def _parse_rhs(self, ctx, exp):
        ruleinfo = RuleInfo(
            self.name, exp.parse,
            self.is_leftrec, self.is_memoizable, self.params, self.kwparams
        )
        result = ctx._call(ruleinfo)
        return result

    def _add_defined_attributes(self, ast):
        defines = compress_seq(self.defines())
        if not isinstance(ast, (AST, Node)):
            return
        for d, l in defines:
            if not hasattr(ast, d):
                setattr(ast, d, [] if l else None)

    def _first(self, k, f):
        if self._first_set:
            return self._first_set
        return self.exp._first(k, f)

    def _follow(self, k, fl, a):
        return self.exp._follow(k, fl, fl[self.name])

    def _nullable(self):
        return Nullable.of(self.exp)

    @staticmethod
    def param_repr(p):
        if isinstance(p, (int, float)):
            return str(p)
        elif isinstance(p, str) and p.isalnum():
            return str(p)
        else:
            return repr(p)

    def _to_str(self, lean=False):
        comments = self.comments_str()
        if lean:
            params = ''
        else:
            params = ', '.join(
                self.param_repr(p) for p in self.params
            ) if self.params else ''

            kwparams = ''
            if self.kwparams:
                kwparams = ', '.join(
                    '%s=%s' % (k, self.param_repr(v)) for (k, v)
                    in self.kwparams.items()
                )

            if params and kwparams:
                params = '(%s, %s)' % (params, kwparams)
            elif kwparams:
                params = '(%s)' % (kwparams)
            elif params:
                if len(self.params) == 1:
                    params = '::%s' % params
                else:
                    params = '(%s)' % params

        base = ' < %s' % str(self.base.name) if self.base else ''

        return trim(self.str_template).format(
            name=self.name,
            base=base,
            params=params,
            exp=indent(self.exp._to_str(lean=lean)),
            comments=comments,
            is_name='@name\n' if self.is_name else '',
        )

    str_template = '''\
                {is_name}{comments}{name}{base}{params}
                    =
                {exp}
                    ;
                '''


class BasedRule(Rule):
    def __init__(self, ast, name, exp, base, params, kwparams, decorators=None):
        super().__init__(
            ast,
            name,
            exp,
            params or base.params,
            kwparams or base.kwparams,
            decorators=decorators
        )
        self.base = base
        ast = AST(sequence=[self.base.exp, self.exp])
        ast.set_parseinfo(self.base.parseinfo)
        self.rhs = Sequence(ast)

    def parse(self, ctx):
        return self._parse_rhs(ctx, self.rhs)

    def defines(self):
        return self.rhs.defines()


class Grammar(Model):
    def __init__(self,
                 name,
                 rules,
                 semantics=None,
                 filename='Unknown',
                 whitespace=None,
                 nameguard=None,
                 namechars=None,
                 left_recursion=None,
                 comments_re=None,
                 eol_comments_re=None,
                 directives=None,
                 parseinfo=None,
                 keywords=None):
        super().__init__()
        assert isinstance(rules, list), str(rules)

        self.rules = rules

        directives = directives or {}
        self.directives = directives

        if name is None:
            name = self.directives.get('grammar')
        if name is None:
            name = os.path.splitext(os.path.basename(filename))[0]
        self.name = name

        self.semantics = semantics

        if whitespace is None:
            whitespace = directives.get('whitespace')
        self.whitespace = whitespace

        if nameguard is None:
            nameguard = directives.get('nameguard')
        self.nameguard = nameguard

        if namechars is None:
            namechars = directives.get('namechars')
        self.namechars = namechars

        if left_recursion is None:
            left_recursion = directives.get('left_recursion', True)
        self.left_recursion = left_recursion

        if parseinfo is None:
            parseinfo = directives.get('parseinfo')
        self._use_parseinfo = parseinfo

        if comments_re is None:
            comments_re = directives.get('comments')
        self.comments_re = comments_re

        if eol_comments_re is None:
            eol_comments_re = directives.get('eol_comments')
        self.eol_comments_re = eol_comments_re

        self.keywords = keywords or set()

        self._adopt_children(rules)

        missing = self.missing_rules({r.name for r in self.rules})
        if missing:
            msg = '\n'.join([''] + list(sorted(missing)))
            raise GrammarError('Unknown rules, no parser generated:' + msg)

        self._calc_lookahead_sets()
        if left_recursion:
            find_left_recursion(self)

    def missing_rules(self, rules):
        return set().union(*[rule.missing_rules(rules) for rule in self.rules])

    def _used_rule_names(self):
        if not self.rules:
            return {}

        used = {'start', self.rules[0].name}
        prev = {}
        while used != prev:
            prev = used
            used = used | set().union(*[
                rule._used_rule_names()
                for rule in self.rules
                if rule.name in used
            ])
        return used

    def used_rules(self):
        used = self._used_rule_names()
        return [rule for rule in self.rules if rule.name in used]

    @property
    def first_sets(self):
        return self._first_set

    def _calc_lookahead_sets(self, k=1):
        self._calc_first_sets()
        self._calc_follow_sets()

    def _calc_first_sets(self, k=1):
        f = defaultdict(set)
        f1 = None
        while f1 != f:
            f1 = copy(f)
            for rule in self.rules:
                f[rule.name] |= rule._first(k, f)

        for rule in self.rules:
            rule._first_set = f[rule.name]

    def _calc_follow_sets(self, k=1):
        fl = defaultdict(set)
        fl1 = None
        while fl1 != fl:
            fl1 = copy(fl)
            for rule in self.rules:
                rule._follow(k, fl, set())

        for rule in self.rules:
            rule._follow_set = fl[rule.name]

    def parse(self,
              text,
              rule_name=None,
              start=None,
              filename=None,
              semantics=None,
              trace=False,
              context=None,
              whitespace=None,
              left_recursion=None,
              comments_re=None,
              eol_comments_re=None,
              parseinfo=None,
              nameguard=None,
              namechars=None,
              **kwargs):  # pylint: disable=W0221
        start = start if start is not None else rule_name
        start = start if start is not None else self.rules[0].name

        ctx = context or ModelContext(
            self.rules,
            trace=trace,
            keywords=self.keywords,
            **kwargs)

        semantics = notnone(semantics, self.semantics)
        left_recursion = notnone(left_recursion, self.left_recursion)
        parseinfo = notnone(parseinfo, self._use_parseinfo)
        comments_re = notnone(comments_re, self.comments_re)
        eol_comments_re = notnone(eol_comments_re, self.eol_comments_re)
        nameguard = notnone(nameguard, self.nameguard)
        namechars = notnone(namechars, self.namechars)
        whitespace = notnone(whitespace, self.whitespace)
        if whitespace:
            whitespace = re.compile(whitespace)

        return ctx.parse(
            text,
            rule_name=start,
            filename=filename,
            semantics=semantics,
            trace=trace,
            whitespace=whitespace,
            comments_re=comments_re,
            eol_comments_re=eol_comments_re,
            left_recursion=left_recursion,
            parseinfo=parseinfo,
            nameguard=nameguard,
            namechars=namechars,
            **kwargs
        )

    def nodecount(self):
        return 1 + sum(r.nodecount() for r in self.rules)

    def _to_str(self, lean=False):
        regex_directives = {'comments', 'eol_comments', 'whitespace'}
        ustr_directives = {'comments', 'grammar'}
        string_directives = {'namechars'}

        directives = ''
        for directive, value in self.directives.items():
            fmt = dict(
                name=directive,
                frame='/' if directive in regex_directives else '',
                value=(
                    repr(value) if directive in string_directives
                    else str(value) if directive in ustr_directives
                    else value
                ),
            )
            directives += '@@{name} :: {frame}{value}{frame}\n'.format(**fmt)
        if directives:
            directives += '\n'

        keywords = '\n'.join(
            '@@keyword :: ' + ' '.join(repr(k) for k in c if k is not None)
            for c in chunks(sorted(self.keywords), 8)
        ).strip()
        keywords = '\n\n' + keywords + '\n' if keywords else ''

        rules = (
            '\n\n'.join(str(rule._to_str(lean=lean))
                        for rule in self.rules)
        ).rstrip() + '\n'
        return directives + keywords + rules
