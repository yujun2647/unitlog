#!/usr/bin/env python3
import os
import re
import json
import subprocess
import requests
from packaging import version

# 配置信息
LAST_VERSION_FILE = '.last_git_publish_version'
INIT_FILE = 'unitlog/__init__.py'
MODEL_API_URL = 'https://api.deepseek.com/chat/completions'


def get_last_version():
    """获取上次发布的 Git Commit Hash"""
    if os.path.exists(LAST_VERSION_FILE):
        with open(LAST_VERSION_FILE, 'r') as f:
            return f.read().strip()
    return None


def get_current_version():
    """从 __init__.py 文件中获取当前版本号"""
    if not os.path.exists(INIT_FILE):
        return "0.0.0"

    with open(INIT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    match = re.search(r'__version__\s*=\s*[\'"]([^\'"]+)[\'"]', content)
    if not match:
        # 如果找不到，返回默认
        return "0.0.0"
    return match.group(1)


def get_commits_since(last_commit_hash):
    """获取自上次发布以来的所有提交信息"""
    try:
        # 优化：添加 --no-merges 排除合并提交，减少噪音
        cmd = 'git log --no-merges --pretty=format:"%s"'

        if last_commit_hash:
            cmd = f'{cmd} {last_commit_hash}..HEAD'

        commits = subprocess.check_output(cmd, shell=True, text=True).split('\n')

        # 优化：数据清洗，过滤掉无意义的提交
        clean_commits = []
        ignore_keywords = ['wip', 'chore', 'lint', 'merge', 'refactor', '测试', 'backup']

        for commit in commits:
            commit = commit.strip()
            if not commit:
                continue
            # 如果提交信息太短或包含忽略关键词，则跳过
            if len(commit) < 4 or any(k in commit.lower() for k in ignore_keywords):
                continue
            clean_commits.append(commit)

        return clean_commits
    except subprocess.CalledProcessError as e:
        print(f"获取提交信息失败: {e}")
        return []


def summarize_changes(commits):
    """调用大模型总结变更内容"""
    if not commits:
        return "常规维护与优化。"

    commit_text = "\n".join([f"- {c}" for c in commits])

    # ---------------------------------------------------------
    # 逻辑分层与智能降噪 Prompt
    # ---------------------------------------------------------
    _prompt = f"""
        你是一名资深产品经理。请分析以下 Git 提交记录，撰写一份**逻辑清晰、用户视角**的版本更新日志。

        ### 提交记录集合：
        {commit_text}

        ### 核心撰写规则（必须严格遵守）：

        1. **原则一：一事一议（禁止不相关合并）**
           - **错误示范**："- 重磅推出视频功能，并升级了 SQLite 存储。" （这是两件事！）
           - **正确示范**：
             "- **重磅推出视频功能**：支持插入、封面预览，并可联动 Todo 状态。"
             "- **底层架构升级**：采用 SQLite3 存储引擎，大幅提升启动与读写性能。"
           - **指令**：不同的核心模块（如“多媒体”与“数据库”）必须拆分为不同的 Bullet Points。

        2. **原则二：主次归纳（子功能合并）**
           - 如果“视频”是核心功能，那么“视频联动Todo”、“视频记忆缩放”都属于它的**子特性**。请将它们合并到“视频功能”的描述中，不要单独列出。

        3. **原则三：智能隐藏（开发侧修复不可见）**
           - **关键逻辑**：如果本次更新是**首次推出**某项功能（如“视频”），那么关于该功能的**所有 Bug 修复**（如“修复视频句柄”、“修复视频选区”）都**不要写在【🐛 问题修复】里**。
           - **原因**：用户从未见过该功能，对用户来说，它一上线就是完美的。不要暴露开发过程中的修补痕迹。
           - **保留项**：只保留那些**老功能**的修复（如“富文本粘贴”、“自动保存失效”）。

        ### 请严格按照以下 Markdown 格式输出：

        ### 版本说明

        **✨ 核心亮点**
        - [功能A]：[描述]。
        - [功能B]：[描述]。
        *（注意：核心亮点通常不超过 3 条，确保每条都是独立的大功能）*

        **🚀 体验优化**
        - [概括性的优化点]

        **🐛 问题修复**
        - [仅列出老功能的修复，忽略新功能的开发修复]
        """

    # 调用 DeepSeek API
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("错误：请设置 DEEPSEEK_API_KEY 环境变量")
        return generate_fallback_summary(commits)

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    try:
        payload = {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "system", "content": "你是一个资深的技术文档专家，擅长将技术语言转化为通俗易懂的产品文案。"},
                {"role": "user", "content": _prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 2048
        }

        res = requests.post(MODEL_API_URL, headers=headers, data=json.dumps(payload), timeout=60)
        res.raise_for_status()
        response_data = res.json()

        raw_text = response_data["choices"][0]["message"]["content"]

        # 提取 Markdown (如果有代码块包裹)
        markdown_pattern = re.compile(r'```markdown\s*([\s\S]*?)\s*```')
        match = markdown_pattern.search(raw_text)

        final_text = match.group(1) if match else raw_text

        # 二次清洗：去掉可能存在的 "Here is the summary" 等前缀
        # 简单策略：找到第一个 "**" 或 "##" 开始截取
        start_idx = -1
        for marker in ["**✨", "**🚀", "**🐛", "###", "✨", "🚀", "🐛"]:
            idx = final_text.find(marker)
            if idx != -1:
                if start_idx == -1 or idx < start_idx:
                    start_idx = idx

        if start_idx != -1:
            final_text = final_text[start_idx:]

        return final_text.strip()

    except Exception as e:
        print(f"调用大模型失败: {e}")
        return generate_fallback_summary(commits)


def generate_fallback_summary(commits):
    """降级方案"""
    return "### 版本更新\n\n" + "\n".join([f"- {c}" for c in commits[:10]])


def increment_version(current_version):
    """增加版本号 1.2.9 -> 1.3.0"""
    try:
        parts = [int(x) for x in current_version.split('.')]
        while len(parts) < 3:
            parts.append(0)

        parts[2] += 1
        if parts[2] >= 10:
            parts[2] = 0
            parts[1] += 1
            if parts[1] >= 10:
                parts[1] = 0
                parts[0] += 1

        return ".".join(map(str, parts))
    except Exception as e:
        print(f"版本解析错误: {e}, 重置为 0.0.1")
        return "0.0.1"


def update_init_file(current_version, new_version, updates_content):
    """
    安全更新 __init__.py 文件
    使用正则替换，保留文件中可能存在的其他 import 或配置
    """
    if not os.path.exists(INIT_FILE):
        # 如果文件不存在，创建新文件
        with open(INIT_FILE, 'w', encoding='utf-8') as f:
            f.write(f'__version__ = "{new_version}"\n\nupdates = """\n{updates_content}\n"""\n')
        return

    with open(INIT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 替换版本号
    version_pattern = r'__version__\s*=\s*[\'"][^\'"]+[\'"]'
    new_version_str = f'__version__ = "{new_version}"'

    if re.search(version_pattern, content):
        content = re.sub(version_pattern, new_version_str, content)
    else:
        # 如果原来没有版本号，加在最前面
        content = new_version_str + "\n" + content

    # 2. 替换 updates 内容
    # 匹配 updates = """...""" 或 updates = "..."
    # 注意：这个正则处理多行字符串比较复杂，这里简化处理，假设是三引号
    updates_pattern = r'updates\s*=\s*"""[\s\S]*?"""'
    new_updates_str = f'updates = """\n{updates_content}\n"""'

    if re.search(updates_pattern, content):
        content = re.sub(updates_pattern, new_updates_str, content)
    else:
        content += "\n\n" + new_updates_str

    with open(INIT_FILE, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ 版本已更新: {current_version} → {new_version}")


def save_current_version():
    """保存当前 HEAD hash"""
    try:
        latest_commit_hash = subprocess.check_output(
            'git rev-parse HEAD', shell=True, text=True
        ).strip()
        with open(LAST_VERSION_FILE, 'w') as f:
            f.write(latest_commit_hash)
    except Exception as e:
        print(f"保存 Hash 失败: {e}")


def main():
    last_hash = get_last_version()
    current_ver = get_current_version()

    commits = get_commits_since(last_hash)

    print(f"当前版本: {current_ver}")
    print(f"检测到 {len(commits)} 个有效提交")

    if not commits:
        print("没有实质性更新，跳过。")
        return

    print("正在调用 AI 生成更新日志...")
    updates = summarize_changes(commits)
    print("-" * 30)
    print(updates)
    print("-" * 30)

    new_ver = increment_version(current_ver)
    update_init_file(current_ver, new_ver, updates)
    save_current_version()

    print(f"🎉 发布完成！新版本：{new_ver}")


if __name__ == "__main__":
    main()