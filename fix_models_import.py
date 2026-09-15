with open("app/models.py", "r") as f:
    content = f.read()

if "JSON" not in content.split("from sqlalchemy import")[1].split("\n")[0]:
    # Replace the sqlalchemy import line to include JSON
    content = content.replace(
        "from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text",
        "from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, JSON"
    )

with open("app/models.py", "w") as f:
    f.write(content)

print("app/models.py imports updated successfully.")
