#   Copyright 2015 David Malcolm <dmalcolm@redhat.com>
#   Copyright 2015 Red Hat, Inc.
#
#   This library is free software; you can redistribute it and/or
#   modify it under the terms of the GNU Lesser General Public
#   License as published by the Free Software Foundation; either
#   version 2.1 of the License, or (at your option) any later version.
#
#   This library is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#   Lesser General Public License for more details.
#
#   You should have received a copy of the GNU Lesser General Public
#   License along with this library; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301
#   USA
"""
Scrape a mailing list archive, looking for patches

Caution: this script performs numerous URL GETs on gcc.gnu.org;
it caches everything, but the first time you run it, the cache
will be cold.
"""
from collections import OrderedDict
import os
import re
import unittest
import urllib

from bs4 import BeautifulSoup
import requests

class UrlCache:
    """
    Provide a way to fetch URLs, wrapping behind a cache on the
    filesystem.
    """
    def __init__(self):
        self.cache_dir = '.url-cache'
        self.hits = 0
        self.misses = 0

    def get(self, url, **kwargs):
        path = os.path.join(self.cache_dir, urllib.quote(url, safe=''))
        if os.path.exists(path):
            if 0:
                print('using cache: %r' % path)
            self.hits += 1
            with open(path) as f:
                return f.read()
        else:
            print('GET %r' % url)
            self.misses += 1
            r = requests.get(url, **kwargs)
            if not os.path.exists(self.cache_dir):
                os.mkdir(self.cache_dir)
            with open(path, 'w') as f:
                f.write(r.text.encode('utf-8'))
            return r.text

    def dump_stats(self):
        print('cache misses requiring GET: %i' % self.misses)
        print('cache hits: %i' % self.hits)

class MHonArcScraper:
    """
    Screen-scraper for MHonArc archives (e.g. gcc-patches)
    """
    def __init__(self, url_cache, verify):
        self.url_cache = url_cache
        self.verify = verify

    def scrape_monthly_index(self, url):
        """
        Yield a sequence of URLs for the mails themselves
        """
        html_doc = self.url_cache.get(url, verify=self.verify)
        soup = BeautifulSoup(html_doc, 'html.parser')
        #print(soup.prettify())

        for link in soup.find_all('a'):
            href = link.get('href')
            m = re.match('msg[0-9]+.html', href)
            if m:
                mail_url = url + href
                yield mail_url

    def scrape_html_mail(self, html_mail):
        """
        Given the URL of an HTML archive of an individual mail,
        get it (with caching), and return a
          (subject, body)
        pair.
        """
        state = 'preamble'
        subdivisions = OrderedDict()
        subdivisions[state] = ''
        subject = None
        for line in html_mail.splitlines():
            # Look for lines like this: '<!--X-Head-of-Message-->'
            m = re.match('<!--X-Subject: (.*) -->', line)
            if m:
                subject = m.group(1)
                continue

            m = re.match('<!--X-([A-za-z-]+)-->', line)
            if m:
                state = m.group(1)
                subdivisions[state] = ''
            else:
                subdivisions[state] += line + '\n'
        if 0:
            for k, v in subdivisions.iteritems():
                print(k)
                print(v)

        body = subdivisions.get('Body-of-Message')
        # The body has a <PRE> and </PRE> wrapper.  Strip it
        PREFIX = '<PRE>\n'
        if body.startswith(PREFIX):
            body = body[len(PREFIX):]
        SUFFIX = '\n</PRE>\n\n'
        if body.endswith(SUFFIX):
            body = body[:len(body) - len(SUFFIX)]

        return subject, body

def extract_patch(body):
    """
    Attempt to extract a patch from the body of a mail scraped from a
    mailing-list archive.
    Return a str, or None
    """
    within_patch = False
    patch = None
    for line in body.splitlines():
        if within_patch:
            if line == '':
                # Blank line within a patch
                patch += '\n'
                continue
            if line[0] not in '-+@ ':
                # End of patch
                return patch.rstrip() + '\n'
            patch += line + '\n'
            continue
        else:
            # We're before the patch started
            if line.startswith('--- '):
                within_patch = True
                patch = line + '\n'
                continue
            # Otherwise, discard leading test.
    if within_patch:
        # The patch continued to the end of the body:
        return patch

class Testsuite(unittest.TestCase):
    def setUp(self):
        self.url_cache = UrlCache()

    def make_scraper(self):
        return MHonArcScraper(self.url_cache,
                              verify=False)
        # Disable verification for gcc-patches, otherwise we get a
        # requests.exceptions.SSLError:
        #   hostname 'gcc.gnu.org' doesn't match either of 'cygwin.com', 'www.cygwin.com'

    def test_monthly_index(self):
        scraper = self.make_scraper()
        days_of_yore = 'https://gcc.gnu.org/ml/gcc-patches/1998-05/'
        mail_urls = list(scraper.scrape_monthly_index(days_of_yore))
        self.assertEqual(len(mail_urls), 100)
        self.assertEqual(mail_urls[0],
                         'https://gcc.gnu.org/ml/gcc-patches/1998-05/msg00099.html')
        self.assertEqual(mail_urls[99],
                         'https://gcc.gnu.org/ml/gcc-patches/1998-05/msg00000.html')
        self.url_cache.dump_stats()

    def test_extract_mail_1998_05_msg00053(self):
        mail_url = 'https://gcc.gnu.org/ml/gcc-patches/1998-05/msg00053.html'
        html_mail = self.url_cache.get(mail_url)
        scraper = self.make_scraper()
        subject, body = scraper.scrape_html_mail(html_mail)
        self.assertEqual(subject, 'PATCH: location of "trampolines" paper')
        self.maxDiff = 2000
        self.assertMultiLineEqual(body,
'''The "trampolines" paper is no longer available from the location mentioned
in the documentation. One of the Debian developers obtained a copy and made
it available on the web.

--- egcs-1.0.3a.orig/gcc/extend.texi
+++ egcs-1.0.3a/gcc/extend.texi
@@ -367,8 +367,7 @@
 
 GNU CC implements taking the address of a nested function using a
 technique called @dfn{trampolines}.  A paper describing them is
-available from @samp{maya.idiap.ch} in directory @file{pub/tmb},
-file @file{usenix88-lexic.ps.Z}.
+available as @samp{<A  HREF="http://master.debian.org/~karlheg/Usenix88-lexic.pdf}">http://master.debian.org/~karlheg/Usenix88-lexic.pdf}</A>.
 
 A nested function can jump to a label inherited from a containing
 function, provided the label was explicitly declared in the containing


You might want to consider making it available through a more persistent URL
(e.g. on the cygnus site).

Greetings,
Ray
-- 
Tevens ben ik van mening dat Nederland overdekt dient te worden.
''')
        patch = extract_patch(body)
        self.assertMultiLineEqual(patch,
'''--- egcs-1.0.3a.orig/gcc/extend.texi
+++ egcs-1.0.3a/gcc/extend.texi
@@ -367,8 +367,7 @@
 
 GNU CC implements taking the address of a nested function using a
 technique called @dfn{trampolines}.  A paper describing them is
-available from @samp{maya.idiap.ch} in directory @file{pub/tmb},
-file @file{usenix88-lexic.ps.Z}.
+available as @samp{<A  HREF="http://master.debian.org/~karlheg/Usenix88-lexic.pdf}">http://master.debian.org/~karlheg/Usenix88-lexic.pdf}</A>.
 
 A nested function can jump to a label inherited from a containing
 function, provided the label was explicitly declared in the containing
''')   

    def test_extract_mail_1998_05_msg00063(self):
        mail_url = 'https://gcc.gnu.org/ml/gcc-patches/1998-05/msg00063.html'
        html_mail = self.url_cache.get(mail_url)
        scraper = self.make_scraper()
        subject, body = scraper.scrape_html_mail(html_mail)
        self.assertEqual(subject, 'PATCH for contrib/warn_summary')
        self.maxDiff = 2000
        self.assert_(body.startswith('This patch updates the warn_summary'))
        patch = extract_patch(body)
        self.assert_(patch.startswith(
            '--- egcs-19980529.orig/contrib/warn_summary	Sun May 24 00:35:33 1998\n'))
        self.assert_(patch.endswith(
            ' \t\ts/`\\(inline\\)\'"\'"\'/"\\1"/g;\n'))

unittest.main()
