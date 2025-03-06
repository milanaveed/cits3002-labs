import unittest

def hamming_distance(codeword1, codeword2):
    return sum(b1 != b2 for b1, b2 in zip(codeword1, codeword2))

class TestHammingDistance(unittest.TestCase):

    def test_same_codewords(self):
        """Test when both codewords are identical (Hamming distance = 0)."""
        self.assertEqual(hamming_distance("101010", "101010"), 0)

    def test_one_bit_difference(self):
        """Test when there is a single bit difference (Hamming distance = 1)."""
        self.assertEqual(hamming_distance("101010", "101011"), 1)

    def test_multiple_bit_differences(self):
        """Test when multiple bits are different."""
        self.assertEqual(hamming_distance("110010", "101110"), 3)

    def test_all_bits_different(self):
        """Test when all bits are different (maximum Hamming distance)."""
        self.assertEqual(hamming_distance("111111", "000000"), 6)

    def test_empty_strings(self):
        """Test when both inputs are empty strings (should return 0)."""
        self.assertEqual(hamming_distance("", ""), 0)

# Run the unit tests
if __name__ == '__main__':
    # unittest.main()