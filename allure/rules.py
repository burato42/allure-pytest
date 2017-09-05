# -*- coding: utf-8 -*-
"""
Simple object-to-XML binding mechanism.

@author: pupssman
"""

import re
import sys

from six import u, unichr
from lxml import objectify
from namedlist import namedlist

from allure.utils import unicodify


def element_maker(name, namespace):
    return getattr(objectify.ElementMaker(annotate=False, namespace=namespace,), name)


class Rule(object):
    _check = None

    def value(self, name, what):
        raise NotImplemented()

    def if_(self, check):
        self._check = check
        return self

    def check(self, what):
        if self._check:
            return self._check(what)
        else:
            return True


# see http://en.wikipedia.org/wiki/Valid_characters_in_XML#Non-restricted_characters

# We need to get the subset of the invalid unicode ranges according to
# XML 1.0 which are valid in this python build.  Hence we calculate
# this dynamically instead of hardcoding it.  The spec range of valid
# chars is: Char ::= #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD]
# | [#x10000-#x10FFFF]
_legal_chars = (0x09, 0x0A, 0x0d)
_legal_ranges = (
    (0x20, 0x7E),
    (0x80, 0xD7FF),
    (0xE000, 0xFFFD),
    (0x10000, 0x10FFFF),
)
_legal_xml_re = [u("%s-%s") % (unichr(low), unichr(high)) for (low, high) in _legal_ranges if low < sys.maxunicode]
_legal_xml_re = [unichr(x) for x in _legal_chars] + _legal_xml_re
illegal_xml_re = re.compile(u('[^%s]') % u('').join(_legal_xml_re))


def legalize_xml(arg):
    def repl(matchobj):
        i = ord(matchobj.group())
        if i <= 0xFF:
            return u('#x%02X') % i
        else:
            return u('#x%04X') % i
    return illegal_xml_re.sub(repl, arg)


class Ignored(Rule):
    def if_(self, check):
        return False


class Element(Rule):

    def __init__(self, name='', namespace=''):
        self.name = name
        self.namespace = namespace

    def value(self, name, what):
        from _pytest._code.code import (
            ReprEntry,
            ReprEntryNative,
            ReprExceptionInfo,
            ReprFileLocation,
            ReprFuncArgs,
            ReprLocals,
            ReprTraceback
        )
        if not isinstance(what, str):
            unserialized_entries = []
            reprentry = None
            for entry_data in what.reprtraceback.reprentries:
                data = entry_data['data']
                entry_type = entry_data['type']
                if entry_type == 'ReprEntry':
                    reprfuncargs = None
                    reprfileloc = None
                    reprlocals = None
                    if data['reprfuncargs']:
                        reprfuncargs = ReprFuncArgs(
                            **data['reprfuncargs'])
                    if data['reprfileloc']:
                        reprfileloc = ReprFileLocation(
                            **data['reprfileloc'])
                    if data['reprlocals']:
                        reprlocals = ReprLocals(
                            data['reprlocals']['lines'])

                    reprentry = ReprEntry(
                        lines=data['lines'],
                        reprfuncargs=reprfuncargs,
                        reprlocals=reprlocals,
                        filelocrepr=reprfileloc,
                        style=data['style']
                    )
                elif entry_type == 'ReprEntryNative':
                    reprentry = ReprEntryNative(data['lines'])
                else:
                    report_unserialization_failure(
                        entry_type, name, reportdict)
                unserialized_entries.append(reprentry)

            what.reprtraceback.reprentries = unserialized_entries
        return element_maker(self.name or name, self.namespace)(legalize_xml(unicodify(what)))


class Attribute(Rule):

    def value(self, name, what):
        return legalize_xml(unicodify(what))


class Nested(Rule):

    def value(self, name, what):
        return what.toxml()


class Many(Rule):

    def __init__(self, rule, name='', namespace=''):
        self.rule = rule
        self.name = name
        self.namespace = namespace

    def value(self, name, what):
        return [self.rule.value(name, x) for x in what]


class WrappedMany(Many):

    def value(self, name, what):
        values = super(WrappedMany, self).value(name, what)
        return element_maker(self.name or name, self.namespace)(*values)


def xmlfied(el_name, namespace='', fields=[], **kw):
    items = fields + sorted(kw.items())

    class MyImpl(namedlist('XMLFied', [(item[0], None) for item in items])):

        def toxml(self):
            el = element_maker(el_name, namespace)

            def entries(clazz):
                return [(name, rule.value(name, getattr(self, name)))
                        for (name, rule) in items
                        if isinstance(rule, clazz) and rule.check(getattr(self, name))]

            elements = entries(Element)
            attributes = entries(Attribute)
            nested = entries(Nested)
            manys = sum([[(m[0], v) for v in m[1]] for m in entries(Many)], [])

            return el(*([element for (_, element) in elements + nested + manys]),
                      **dict(attributes))

    return MyImpl
