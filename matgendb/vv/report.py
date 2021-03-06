"""
Description.
"""
__author__ = 'Dan Gunter <dkgunter@lbl.gov>'
__date__ = '2/21/13'


import bson
from email.mime.text import MIMEText
import json
from operator import itemgetter
import smtplib

from pymatgen import PMGJSONEncoder
from .util import DoesLogging
from ..util import MongoJSONEncoder

class Report:
    def __init__(self, header):
        """Create blank report, with a header.

        :param header: Report header
        :type header: ReportHeader
        """
        self._hdr = header
        self._sections = []

    def add_section(self, section):
        self._sections.append(section)

    @property
    def header(self):
        return self._hdr

    def is_empty(self):
        return len(self._sections) == 0

    def __iter__(self):
        return iter(self._sections)


class ReportSection(Report):
    """Section within a report, with data.
    """
    def __init__(self, header, body=None):
        """Create new report section, initialized with header and body.

        :param header: The header for the section
        :type header: SectionHeader
        :param body: The body of the section, or None if this is a container for sub-sections
        :type body: Table
        """
        Report.__init__(self, header)
        self._body = body

    @property
    def body(self):
        return self._body

class Header:
    """Base header class.
    """
    def __init__(self, title=''):
        self._kv = []
        self.title = title

    def add(self, key, value):
        self._kv.append((key, value))

    def get(self, key):
        return (v for k, v in self._kv if k == key)

    def __iter__(self):
        return iter(self._kv)

    def to_dict(self):
        return {k:v for k, v in self._kv}

class ReportHeader(Header):
    """Header for entire report.
    """
    pass


class SectionHeader(Header):
    """Header for one section of a report.
    """
    pass


class Table:
    """Table of values.
    """
    def __init__(self, colnames):
        self._colnames = colnames
        self._rows = []
        self._width = len(colnames)
        self._max_col_widths = map(len, colnames)

    def add(self, values):
        if len(values) != self._width:
            raise ValueError('expected {:d} values, got {:d}'.format(self._width, len(values)))
        self._rows.append(values)
        for i, v in enumerate(values):
            n = len(str(v))
            if self._max_col_widths[i] < n:
                self._max_col_widths[i] = n

    def sortby(self, name_or_index):
        name, index = None, None
        if isinstance(name_or_index, int):
            index = name_or_index
        else:
            name = name_or_index
        if name is not None:
            try:
                colnum = self._colnames.index(name)
            except ValueError:
                raise ValueError('column {} not in {}'.format(name, self._colnames))
        else:
            if index < 0 or index >= self._width:
                raise ValueError('index out of range 0..{:d}'.format(self._width - 1))
            colnum = index
        self._rows.sort(key=itemgetter(colnum))

    def __iter__(self):
        return iter(self._rows)

    @property
    def values(self):
        return [{self._colnames[i]: r[i] for i in range(self._width)}
                for r in self._rows]

    @property
    def column_names(self):
        return self._colnames

    @property
    def column_widths(self):
        return self._max_col_widths

    @property
    def ncol(self):
        return self._width

    @property
    def nrow(self):
        return len(self._rows)


## Exceptions

class ReportBackupError(Exception): pass

## Formatting

# CSS for HTML report output
DEFAULT_CSS = """
html {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
}
body {
    margin: 2em;
}
table { margin-top: 1em; clear: both; border: 1px solid grey; }
dl, dt, dd { float: left; }
dl, dt { clear: both; }
dt { width: 8em; font-weight: 700; }
dd { width: 32em; }
tr.even { background-color: #F2F2FF; }
tr.odd { background-color: white; }
th, td {
    padding: 0.2em 0.5em;
}
th {
    text-align: left;
    color: #000066;
    border-bottom: 1px solid #000066;
    margin: 0;
}
h1, h2, h3 { clear: both; margin: 0; padding: 0; }
h1 { color: #FE5300; }
h2 { color: #004489; }
""".replace('\n', ' ').replace('  ', ' ')


class HTMLFormatter:
    """Format a report as HTML.
    """
    def __init__(self, line_sep='\n', id_column=0, css=DEFAULT_CSS):
        self._sep = line_sep
        self._idcol = id_column
        self._css = css

    def format(self, report):
        text = []
        text.append('<!DOCTYPE html>')
        text.append('<html>')
        text.append('<title>{}</title>'.format(report.header.title))
        text.append('<head>')
        if self._css:
            text.append('<style>')
            text.append(self._css)
            text.append('</style>')
        text.append('</head>')
        text.append('<body>')
        text.append('<h1>{}</h1>'.format(report.header.title))
        text.append('<dl class="rptmeta">')
        for key, value in report.header:
            text.append('<dt>{}</dt>'.format(key))
            text.append('<dd>{}</dd>'.format(value))
        text.append('</dl>')
        for section in report:
            text.append('<h2>{}</h2>'.format(section.header.title))
            text.append('<dl class="sectmeta">')
            for key, value in section.header:
                text.append('<dt>{}</dt>'.format(key))
                text.append('<dd>{}</dd>'.format(value))
            text.append('</dl>')
            for cond_section in section:
                text.append('<h3>{}</h3>'.format(cond_section.header.title))
                text.append('<dl class="subsectmeta">')
                for key, value in cond_section.header:
                    text.append('<dt>{}</dt>'.format(key))
                    text.append('<dd>{}</dd>'.format(value))
                text.append('</dl>')
                text.append('<table>')
                text.append('<tr>')
                for name in cond_section.body.column_names:
                    text.append('<th>{}</th>'.format(name))
                text.append('</tr>')
                prev_key, i = None, 0
                for row in cond_section.body:
                    row = list(row)
                    key = row[self._idcol]
                    if prev_key and key == prev_key:
                        row[self._idcol] = ''
                    else:
                        prev_key = key
                        i += 1
                    rclass = ('even', 'odd')[i % 2]
                    text.append('<tr class="{}">'.format(rclass))
                    for value in row:
                        text.append('<td>{}</td>'.format(value))
                    text.append('</tr>')
                text.append('</table>')
        text.append('</body>')
        text.append('</html>')
        return self._sep.join(text)


class JSONFormatter:
    """Format a report as JSON.
    """
    def __init__(self, id_column=0, indent=2):
        self._indent = indent
        self._idcol = id_column

    def format(self, report):
        obj = dict(
            title=report.header.title,
            info=report.header,
            sections=[
                dict(title=s.header.title,
                     info=s.header,
                     conditions=[
                        dict(title=cs.header.title,
                             info=cs.header,
                             violations=cs.body)
                        for cs in s
                     ]
                )
                for s in report
            ]
        )
        return json.dumps(obj, indent=self._indent, cls=MongoJSONEncoder)

class ReportJSONEncoder(MongoJSONEncoder):
    def default(self, o):
        if isinstance(o, Header):
            return o.to_dict()
        elif isinstance(o, Table):
            return o.values
        return MongoJSONEncoder.default(self, o)


class MarkdownFormatter:
    """Format a report as markdown
    """
    def __init__(self, id_column=0):
        self._idcol = id_column

    def _mapdump(self, d):
        return ', '.join((('{}={}'.format(k, v) for k, v in d.iteritems())))

    def _fixed_width(self, values, widths):
        s = ''.join(["{{:{:d}s}}".format(w+1).format(str(v))
                       for w, v in zip(widths, values)])
        return s

    def format(self, report):
        lines = []
        lines.append('# {} #\n'.format(report.header.title))
        lines.append('Info: {}'.format(self._mapdump(report.header.to_dict())))
        for section in report:
            lines.append('\n## {} ##\n'.format(section.header.title))
            if section.header:
                lines.append('Info: {}'.format(self._mapdump(section.header.to_dict())))
            for cond in section:
                lines.append('\n### {} ###\n'.format(cond.header.title))
                if cond.header:
                    lines.append('Info: {}'.format(self._mapdump(cond.header.to_dict())))
                lines.append('\nViolations:\n')
                indent = '    '
                tbl = cond.body
                lines.append(indent + self._fixed_width(tbl.column_names, tbl.column_widths))
                for row in tbl:
                    lines.append(indent + self._fixed_width(row, tbl.column_widths))
        return '\n'.join(lines)


class Emailer(DoesLogging):
    """Send a report to an email recipient.
    """
    def __init__(self, sender='me@localhost', recipients=('you@remote.host',),
                 subject='Report', server='localhost', port=None, **kwargs):
        """Send reports as email.

        :param: sender Sender of the email
        :param: recipients List of _recipients of the email
        :param: subject Email _subject line
        :param: server SMTP server host
        :param: port SMTP server port (None for default)
        """
        DoesLogging.__init__(self, 'mg.emailer')
        self._sender, self._recipients, self._subject = sender, recipients, subject
        self._server, self._port = server, port
        self._message = ""

    def send(self, text, fmt):
        """Send the email message.

        :param text: The text to send
        :type text: str
        :param fmt: The name of the format of the text
        :type fmt: str
        :return: Number of recipients it was sent to
        :rtype: int
        """
        num_recip = 0
        main_fmt, sub_fmt = fmt.split('/')
        mime_class = dict(text=MIMEText).get(main_fmt, MIMEText)
        msg = mime_class(text, sub_fmt)
        msg['Subject'] = self._subject
        msg['From'] = self._sender
        msg['To'] = ', '.join(self._recipients)
        if self._port is None:
            conn_kwargs = dict(host=self._server)
        else:
            conn_kwargs = dict(host=self._server, port=self._port)
        self._log.info("connect to email server {}".format(conn_kwargs))
        try:
            s = smtplib.SMTP(**conn_kwargs)
            s.sendmail(self._sender, self._recipients, msg.as_string())
            s.quit()
            n_recip = len(self._recipients)
        except Exception, err:
            self._log.error("connection to SMTP server failed: {}".format(err))
            n_recip = 0
        return n_recip