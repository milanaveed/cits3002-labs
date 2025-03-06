    def test_different_lengths(self):
        """Test when inputs have different lengths (should raise ValueError)."""
        with self.assertRaises(ValueError):
            hamming_distance("1010", "101")