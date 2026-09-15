with open("test_milestone4_pdf.py", "r") as f:
    code = f.read()

target = "class MockResp:\n    def __init__(self, res):"
replacement = """class MockResp:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def __init__(self, res):"""

if target in code:
    code = code.replace(target, replacement, 1)
    with open("test_milestone4_pdf.py", "w") as f:
        f.write(code)
    print("MockResp updated with context manager support.")
else:
    print("Target not found. Please verify exact formatting.")
