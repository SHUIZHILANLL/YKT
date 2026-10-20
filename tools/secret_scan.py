"""提交前自检：扫描被跟踪文件与 git 历史，查找**字面量**形式的疑似凭据。

用法：
    python tools/secret_scan.py

退出码：
    0  未发现
    1  发现疑似凭据（请先处理再提交）

只读、不联网。

判定规则刻意保守——只报「等号/冒号右边直接跟着一段长字面量」的情况，
所以 `"sid=" + appSid` 这类代码拼接不会被误报。
"""
import os
import re
import subprocess
import sys

# 只匹配字面量赋值：key = "长串" 或 key: 长串
# 值里不允许出现 < % + $ 空格 引号，这些是占位符或拼接的迹象
SECRET_ASSIGN = re.compile(
    r"""(?i)\b(sessionid|sid|csrftoken|csrf|token|auth|password|passwd|secret)
        \s*[=:]\s*["']?([A-Za-z0-9_\-]{20,48})["']?""",
    re.VERBOSE,
)

# 已知占位符 / 示例值
ALLOWLIST = {
    "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "00000000000000000000000000000000",
}

TEXT_EXT = {
    ".py", ".java", ".xml", ".gradle", ".md", ".txt", ".json", ".yml", ".yaml",
    ".bat", ".sh", ".properties", ".toml", ".cfg", ".ini", "",
}

SKIP_FILES = {"tools/secret_scan.py"}


def run(cmd):
    p = subprocess.run(cmd, capture_output=True)
    return (p.stdout or b"").decode("utf-8", "replace")


def tracked_files():
    return [f for f in run(["git", "ls-files"]).split() if os.path.exists(f)]


def find_in_line(line):
    out = []
    for m in SECRET_ASSIGN.finditer(line):
        key, val = m.group(1).lower(), m.group(2)
        if val in ALLOWLIST:
            continue
        # 纯占位符形态
        if set(val) <= set("xX0*_") or val.lower().startswith("your"):
            continue
        out.append((key, val))
    return out


def scan_worktree():
    problems = []
    for f in tracked_files():
        if f.replace("\\", "/") in SKIP_FILES:
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext not in TEXT_EXT:
            continue
        try:
            text = open(f, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for key, val in find_in_line(line):
                problems.append((f"{f}:{i}", key, val, line.strip()[:100]))
    return problems


def scan_history():
    problems = []
    patch = run(["git", "log", "--all", "-p", "--no-color", "--", "."])
    commit = "?"
    for line in patch.splitlines():
        if line.startswith("commit "):
            commit = line.split()[1][:8]
        elif line.startswith("+"):
            body = line[1:]
            for key, val in find_in_line(body):
                problems.append((f"history@{commit}", key, val, body.strip()[:100]))
    return problems


def main():
    wt = scan_worktree()
    hist = scan_history()

    print("=== 被跟踪文件 ===")
    if wt:
        for loc, key, val, snip in wt:
            print(f"  [!] {loc}")
            print(f"      {key} = {val[:16]}…（{len(val)} 字符）")
            print(f"      {snip}")
    else:
        print("  ✅ 无字面量凭据")

    print("\n=== git 历史（新增行）===")
    if hist:
        seen = set()
        for loc, key, val, snip in hist:
            k = (key, val)
            if k in seen:
                continue
            seen.add(k)
            print(f"  [!] {loc}  {key} = {val[:16]}…")
        print(f"  共 {len(seen)} 类命中")
    else:
        print("  ✅ 无字面量凭据")

    if wt or hist:
        print("\n⚠ 请先处理上述命中再提交；确属示例值请加入 ALLOWLIST。")
        return 1
    print("\n✅ 可以提交。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
