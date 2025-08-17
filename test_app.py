import unittest
import io
from PIL import Image
from app import _validate_image_bytes, _get_logo_bytes

class TestImageHandling(unittest.TestCase):
    def test_validate_image_bytes(self):
        # Valid PNG
        img = Image.new('RGB', (128, 128), color='blue')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        self.assertTrue(_validate_image_bytes(buf.getvalue()))

        # Invalid data
        self.assertFalse(_validate_image_bytes(b"invalid_data"))

        # Valid GIF (unsupported)
        img = Image.new('RGB', (128, 128), color='blue')
        buf = io.BytesIO()
        img.save(buf, format='GIF')
        self.assertFalse(_validate_image_bytes(buf.getvalue()))

    def test_get_logo_bytes(self):
        # Test with valid uploaded logo
        img = Image.new('RGB', (128, 128), color='blue')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        class MockUploader:
            def read(self):
                buf.seek(0)
                return buf.getvalue()
        logo_bytes = _get_logo_bytes(MockUploader(), "02-1234567")
        self.assertTrue(_validate_image_bytes(logo_bytes))

        # Test with invalid uploaded logo
        class MockInvalidUploader:
            def read(self):
                return b"invalid_data"
        logo_bytes = _get_logo_bytes(MockInvalidUploader(), "02-1234567")
        self.assertTrue(_validate_image_bytes(logo_bytes))  # Should return placeholder

if __name__ == '__main__':
    unittest.main()
