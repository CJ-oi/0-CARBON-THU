from __future__ import annotations

import unittest

from park_observer.collector import parse_html
from park_observer.utils import canonical_url, parse_date


class CollectorTests(unittest.TestCase):
    def test_html_parser(self) -> None:
        parser = parse_html(b"<html><head><title>Title</title><meta name='description' content='A long public description for a park policy document that is clearly longer than fifty characters.'></head><body><a href='/a'>zero carbon park policy update</a><p>This is a sufficiently long paragraph for the parser and it contains public information about an industrial park project.</p></body></html>")
        self.assertEqual(parser.page_title, "Title")
        self.assertEqual(parser.links[0]["href"], "/a")
        self.assertTrue(parser.paragraphs)

    def test_url_and_date_normalization(self) -> None:
        self.assertEqual(canonical_url("http://EXAMPLE.com/a/?utm_source=x#top"), "https://example.com/a")
        self.assertEqual(parse_date("发布日期：2026年8月17日"), "2026-08-17")


if __name__ == "__main__":
    unittest.main()
