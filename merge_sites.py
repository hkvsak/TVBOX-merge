#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import requests
import base64

# ======================
# 配置（全部走环境变量，带默认值）
# ======================
SOURCES_JSON_PATH = os.environ.get("SOURCES_JSON_PATH", "sources.json")
TARGET_JSON_PATH = os.environ.get("TARGET_JSON_PATH", "青龙.json")

# 注意：GitHub Actions 会自动提供 GITHUB_TOKEN 环境变量
# 但在 Secrets 中我们不能用 GITHUB_TOKEN 这个名称
# 所以我们用自定义名称，然后通过工作流传递
MY_GITHUB_TOKEN = os.environ.get("MY_GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "leexuben/TVBOX-merge")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

# 打印调试信息
print(f"[调试] MY_GITHUB_TOKEN 长度: {len(MY_GITHUB_TOKEN)}")
print(f"[调试] GITHUB_REPO: {GITHUB_REPO}")
print(f"[调试] GITHUB_BRANCH: {GITHUB_BRANCH}")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TVBoxMerge/1.0)"
}

# ======================
# 拉取站点
# ======================
def get_sites_from_url(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = json.loads(r.text)
            if isinstance(data, dict) and "sites" in data:
                return data["sites"]
            elif isinstance(data, list):
                return data
    except Exception as e:
        print(f"[拉取失败] {url} | {e}")
    return []

# ======================
# 修复路径
# ======================
def fix_site_paths(site, base):
    if not base:
        return site
    base = base.rstrip("/")
    for k, v in site.items():
        if isinstance(v, str) and v.startswith("./"):
            site[k] = base + "/" + v[2:]
    return site

# ======================
# GitHub 推送
# ======================
def push_to_github(path, content, repo, token, branch):
    print(f"[推送] 准备推送到 GitHub: {repo}/{path} (分支: {branch})")
    
    # 检查 token 是否有效
    if not token or len(token) < 10:
        print("[错误] Token 无效或太短")
        return False
    
    api = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 尝试获取文件现有 SHA
    sha = None
    try:
        r = requests.get(api, headers=headers, params={"ref": branch}, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
            print(f"[推送] 文件已存在，SHA: {sha[:8]}...")
        elif r.status_code == 404:
            print(f"[推送] 文件不存在，将创建新文件")
        else:
            print(f"[推送] 检查文件失败: {r.status_code}")
    except Exception as e:
        print(f"[推送] 检查文件异常: {e}")

    # 准备推送数据
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("ascii")
    data = {
        "message": f"🔄 自动更新站点 ({time.strftime('%Y-%m-%d %H:%M:%S')})",
        "content": encoded_content,
        "branch": branch
    }
    if sha:
        data["sha"] = sha

    # 推送文件
    try:
        r = requests.put(api, headers=headers, json=data, timeout=15)
        if r.status_code in (200, 201):
            print(f"[成功] 文件已推送到 GitHub")
            return True
        else:
            print(f"[失败] 推送失败: {r.status_code}")
            print(f"响应: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"[异常] 推送过程出错: {e}")
        return False

# ======================
# 主流程
# ======================
def main():
    print("=" * 60)
    print("TVBox 站点合并脚本")
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. 检查源配置文件
    if not os.path.exists(SOURCES_JSON_PATH):
        print(f"[错误] 找不到源配置文件: {SOURCES_JSON_PATH}")
        sys.exit(1)
    
    # 2. 读取源配置
    try:
        with open(SOURCES_JSON_PATH, "r", encoding="utf-8") as f:
            sources = json.load(f)
        print(f"[读取] 加载了 {len(sources)} 个源")
    except Exception as e:
        print(f"[错误] 读取源配置失败: {e}")
        sys.exit(1)
    
    # 3. 读取现有目标文件（如果存在）
    sites = []
    keys = set()
    
    if os.path.exists(TARGET_JSON_PATH):
        try:
            with open(TARGET_JSON_PATH, "r", encoding="utf-8") as f:
                old = json.load(f)
                sites = old.get("sites", [])
                keys = {s.get("key") for s in sites if s.get("key")}
            print(f"[读取] 现有文件包含 {len(sites)} 个站点")
        except Exception as e:
            print(f"[警告] 读取目标文件失败，将新建: {e}")
    else:
        print(f"[提示] 目标文件不存在，将创建新文件")
    
    # 4. 合并站点
    added_count = 0
    for i, src in enumerate(sources, 1):
        url = src.get("url")
        base = src.get("base", "")
        if not url:
            continue
        
        print(f"[{i}/{len(sources)}] 处理: {url}")
        new_sites = get_sites_from_url(url)
        for s in new_sites:
            key = s.get("key")
            if key and key not in keys:
                sites.append(fix_site_paths(s, base))
                keys.add(key)
                added_count += 1
    
    # 5. 生成结果
    result = {
        "sites": sites,
        "updateTime": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(sites)
    }
    
    # 6. 写入本地文件
    with open(TARGET_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"[完成] 共 {len(sites)} 个站点，新增 {added_count} 个，已写入 {TARGET_JSON_PATH}")
    
    # 7. 推送到 GitHub
    if MY_GITHUB_TOKEN and GITHUB_REPO:
        print(f"[推送] 开始推送到 GitHub 仓库: {GITHUB_REPO}")
        with open(TARGET_JSON_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        ok = push_to_github(TARGET_JSON_PATH, content, GITHUB_REPO, MY_GITHUB_TOKEN, GITHUB_BRANCH)
        if ok:
            print("[完成] ✅ 推送成功！")
        else:
            print("[失败] ❌ 推送失败")
    else:
        print(f"[提示] 未配置 GitHub Token 或仓库信息，仅本地生成")
        print(f"       MY_GITHUB_TOKEN: {'已设置' if MY_GITHUB_TOKEN else '未设置'}")
        print(f"       GITHUB_REPO: {GITHUB_REPO}")

if __name__ == "__main__":
    main()
