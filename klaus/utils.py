# encoding: utf-8

import re
import time
import datetime
import mimetypes

from pygments import highlight
from pygments.lexers import get_lexer_for_filename, guess_lexer, ClassNotFound
from pygments.formatters import HtmlFormatter

from klaus import markup


class SubUri(object):
    """
    WSGI middleware that tweaks the WSGI environ so that it's possible to serve
    the wrapped app (klaus) under a sub-URL and/or to use a different HTTP
    scheme (http:// vs. https://) for proxy communication.

    This is done by making your proxy pass appropriate HTTP_X_SCRIPT_NAME and
    HTTP_X_SCHEME headers.

    For instance if you have klaus mounted under /git/ and your site uses SSL
    (but your proxy doesn't), make it pass ::

        X-Script-Name = '/git'
        X-Scheme = 'https'

    Snippet stolen from http://flask.pocoo.org/snippets/35/
    """
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name.rstrip('/')

        if script_name and environ['PATH_INFO'].startswith(script_name):
            # strip `script_name` from PATH_INFO
            environ['PATH_INFO'] = environ['PATH_INFO'][len(script_name):]

        if 'HTTP_X_SCHEME' in environ:
            environ['wsgi.url_scheme'] = environ['HTTP_X_SCHEME']

        return self.app(environ, start_response)


class KlausFormatter(HtmlFormatter):
    def __init__(self):
        HtmlFormatter.__init__(self, linenos='table', lineanchors='L',
                               anchorlinenos=True)

    def _format_lines(self, tokensource):
        for tag, line in HtmlFormatter._format_lines(self, tokensource):
            if tag == 1:
                # sourcecode line
                line = '<span class=line>%s</span>' % line
            yield tag, line


def pygmentize(code, filename=None, render_markup=True):
    """
    Renders code using Pygments, markup (markdown, rst, ...) using the
    corresponding renderer, if available.
    """
    if render_markup and markup.can_render(filename):
        return markup.render(filename, code)

    try:
        lexer = get_lexer_for_filename(filename)
    except ClassNotFound:
        lexer = guess_lexer(code)

    return highlight(code, lexer, KlausFormatter())


def timesince(when, now=time.time):
    """ Returns the difference between `when` and `now` in human readable form. """
    # TODO: rewrite this mess
    delta = now() - when
    result = []
    break_next = False
    for unit, seconds, break_immediately in [
        ('year', 365*24*60*60, False),
        ('month', 30*24*60*60, False),
        ('week', 7*24*60*60, False),
        ('day', 24*60*60, True),
        ('hour', 60*60, False),
        ('minute', 60, True),
        ('second', 1, False),
    ]:
        if delta > seconds:
            n = int(delta/seconds)
            delta -= n*seconds
            result.append((n, unit))
            if break_immediately:
                break
            if not break_next:
                break_next = True
                continue
        if break_next:
            break

    if not result:
        # 0 seconds
        result = [(1, 'second')]

    if len(result) > 1:
        n, unit = result[0]
        if unit == 'month':
            if n == 1:
                # 1 month, 3 weeks --> 7 weeks
                result = [(result[1][0] + 4, 'week')]
            else:
                # 2 months, 1 week -> 2 months
                result = result[:1]
        elif unit == 'hour' and n > 5:
            result = result[:1]

    return ', '.join('%d %s%s' % (n, unit, 's' if n != 1 else '')
                     for n, unit in result[:2])


def formattimestamp(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).strftime('%b %d, %Y - %H:%M:%S')


def guess_is_binary(dulwich_blob):
    return any('\0' in chunk for chunk in dulwich_blob.chunked)


def guess_is_image(filename):
    mime, _ = mimetypes.guess_type(filename)
    if mime is None:
        return False
    return mime.startswith('image/')


def force_unicode(s):
    """ Does all kind of magic to turn `s` into unicode """
    if isinstance(s, unicode):
        return s
    try:
        return s.decode('utf-8')
    except UnicodeDecodeError as exc:
        pass
    try:
        return s.decode('iso-8859-1')
    except UnicodeDecodeError:
        pass
    try:
        import chardet
        encoding = chardet.detect(s)['encoding']
        if encoding is not None:
            return s.decode(encoding)
    except (ImportError, UnicodeDecodeError):
        raise exc


def extract_author_name(email):
    """
    Extracts the name from an email address...
    >>> extract_author_name("John <john@example.com>")
    "John"

    ... or returns the address if none is given.
    >>> extract_author_name("noname@example.com")
    "noname@example.com"
    """
    match = re.match('^(.*?)<.*?>$', email)
    if match:
        return match.group(1).strip()
    return email


def shorten_sha1(sha1):
    if re.match('[a-z\d]{20,40}', sha1):
        sha1 = sha1[:10]
    return sha1


def subpaths(path):
    """
    Yields a `(last part, subpath)` tuple for all possible sub-paths of `path`.

    >>> list(subpaths("foo/bar/spam"))
    [('foo', 'foo'), ('bar', 'foo/bar'), ('spam', 'foo/bar/spam')]
    """
    seen = []
    for part in path.split('/'):
        seen.append(part)
        yield part, '/'.join(seen)


def shorten_message(msg):
    return msg.split('\n')[0]


def get_mimetype_and_encoding(blob, filename):
    mime, encoding = mimetypes.guess_type(filename)
    if mime and mime.startswith('text/'):
        mime = 'text/plain'
    return mime, encoding


try:
    from subprocess import check_output
except ImportError:
    # Python < 2.7 fallback, stolen from the 2.7 stdlib
    def check_output(*popenargs, **kwargs):
        from subprocess import Popen, PIPE, CalledProcessError
        if 'stdout' in kwargs:
            raise ValueError('stdout argument not allowed, it will be overridden.')
        process = Popen(stdout=PIPE, *popenargs, **kwargs)
        output, _ = process.communicate()
        retcode = process.poll()
        if retcode:
            cmd = kwargs.get("args")
            if cmd is None:
                cmd = popenargs[0]
            raise CalledProcessError(retcode, cmd, output=output)
        return output
