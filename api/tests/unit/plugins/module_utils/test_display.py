import unittest

from .....plugins.module_utils.display import Display

class DisplayTester(unittest.TestCase):

    def test_display_set_correctly_on_init(self):
        # Display is not available by default
        display = Display()

        assert display.display == None
