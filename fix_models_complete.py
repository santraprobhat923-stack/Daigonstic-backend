with open("app/models.py", "r") as f:
    lines = f.readlines()

# Clean up any leftover script artifact lines
clean_lines = []
for line in lines:
    if "# Find where Base is defined" in line or "code =" in line or "if \"Base = declarative_base()\"" in line:
        break
    clean_lines.append(line)

with open("app/models.py", "w") as f:
    f.writelines(clean_lines)

print("Cleaned trailing artifact lines from app/models.py.")
