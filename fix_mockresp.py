with open("test_milestone4_pdf.py", "r") as f:
    code = f.read()

import re

# Match MockResp class and inject context manager methods
pattern = r"class MockResp.*?def __init__\(self, r\):"
replacement = '''class MockResp:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def __init__(self, r):'''

if "def __enter__" not in code:
    code = re.sub(pattern, replacement, code, count=1)
    with open("test_milestone4_pdf.py", "w") as f:
        f.write(code)
    print("MockResp updated with context manager protocol.")
else:
    print("Context manager already present.")
