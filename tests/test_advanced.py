# -*- coding: utf-8 -*-

from .context import CoolPlot

import unittest


class AdvancedTestSuite(unittest.TestCase):
    """Advanced test cases."""

    def test_thoughts(self):
        self.assertIsNone(CoolPlot.hmm())


if __name__ == '__main__':
    unittest.main()
