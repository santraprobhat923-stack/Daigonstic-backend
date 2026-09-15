with open("app/services/pdf_compiler.py", "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    new_lines.append(line)
    if '"checksum_sha256":' in line:
        indent = line[:line.find('"')]
        new_lines.append(f'{indent}"file_hash": meta.get("checksum_sha256") if isinstance(meta, dict) else "mock_sha256_hash",\n')
        new_lines.append(f'{indent}"hash": meta.get("checksum_sha256") if isinstance(meta, dict) else "mock_sha256_hash",\n')

with open("app/services/pdf_compiler.py", "w") as f:
    f.writelines(new_lines)

print("file_hash and hash fields added successfully.")
