#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import requests
from pathlib import Path

# ======================
# 配置区
# ======================
# 从环境变量读取配置，使用默认值
SOURCES_JSON_PATH = os.environ.get("SOURCES_JSON_PATH", "sources.json")
TARGET_JSON_PATH = os.environ.get("TARGET_JSON_PATH", "青龙.json")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ======================
# 工具函数：从 URL 获取 sites 列表
# ======================
def get_sites_from_url(url):
    """
    从给定 URL 获取 JSON 数据，并尝试提取其中的 'sites' 数组
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            content = resp.text.strip()
            try:
                data = json.loads(content)
                if isinstance(data, dict) and "sites" in data:
                    return data["sites"]
                elif isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                # 容错处理：尝试提取 JSON
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end != 0:
                    try:
                        data = json.loads(content[start:end])
                        if isinstance(data, dict) and "sites" in data:
                            return data["sites"]
                    except:
                        pass
        print(f"[失败] 状态码: {resp.status_code} | URL: {url}")
        return []
    except Exception as e:
        print(f"[异常] {url} | 错误: {e}")
        return []

# ======================
# 工具函数：修复站点路径与 jar
# ======================
def fix_site_paths(site, base_url, jar_url):
    """
    对单个站点字典进行路径修复
    """
    if not base_url:
        return site
        
    base = base_url.rstrip("/")
    
    # 遍历所有键值，修复以 "./" 开头的路径
    for k, v in site.items():
        if isinstance(v, str) and v.startswith("./"):
            site[k] = base + "/" + v[2:]
    
    # 如果站点没有 jar 且提供了 jar_url，则添加
    if "jar" not in site and jar_url and jar_url.strip():
        site["jar"] = jar_url.rstrip("/")
    
    return site

# ======================
# 工具函数：推送文件到 GitHub
# ======================
def push_to_github(file_path, content, repo, token, branch, commit_message=None):
    """
    通过 GitHub API 推送文件到仓库
    """
    if not commit_message:
        commit_message = f"Auto update: {file_path} at {time.strftime('%Y-%m-%d %H:%M:%S')}"
    
    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    
    # 获取文件当前 SHA（如果存在）
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 检查文件是否已存在
    get_resp = requests.get(api_url, headers=headers, params={"ref": branch}, timeout=10)
    sha = None
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")
        print(f"[GitHub] 文件已存在，准备更新")
    else:
        print(f"[GitHub] 创建新文件")
    
    # 构建请求数据
    data = {
        "message": commit_message,
        "content": content,
        "branch": branch
    }
    if sha:
        data["sha"] = sha
    
    # 发送请求
    resp = requests.put(api_url, headers=headers, json=data, timeout=15)
    
    if resp.status_code in (200, 201):
        print(f"[成功] 文件已推送到 GitHub: {file_path}")
        return True
    else:
        print(f"[失败] 推送失败: {resp.status_code}")
        print(f"响应: {resp.text[:200]}")
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
    
    print(f"[配置] 源文件: {SOURCES_JSON_PATH}")
    print(f"[配置] 目标文件: {TARGET_JSON_PATH}")
    
    # 2. 读取源配置
    try:
        with open(SOURCES_JSON_PATH, "r", encoding="utf-8") as f:
            sources = json.load(f)
        print(f"[读取] 加载了 {len(sources)} 个源")
    except Exception as e:
        print(f"[错误] 读取源配置失败: {e}")
        sys.exit(1)
    
    # 3. 读取现有目标文件（如果存在）
    target_sites = []
    if os.path.exists(TARGET_JSON_PATH):
        try:
            with open(TARGET_JSON_PATH, "r", encoding="utf-8") as f:
                target_data = json.load(f)
                if isinstance(target_data, dict) and "sites" in target_data:
                    target_sites = target_data["sites"]
                elif isinstance(target_data, list):
                    target_sites = target_data
            print(f"[读取] 现有目标文件包含 {len(target_sites)} 个站点")
        except Exception as e:
            print(f"[警告] 读取目标文件失败，将新建: {e}")
            target_sites = []
    else:
        print(f"[提示] 目标文件不存在，将创建新文件")
    
    # 4. 收集现有站点的 key
    existing_keys = {site.get("key", "").strip() for site in target_sites if site.get("key")}
    added_count = 0
    
    # 5. 遍历所有源，合并站点
    for i, src in enumerate(sources, 1):
        url = src.get("url", "").strip()
        jar = src.get("jar", "").strip()
        base = src.get("base", "").strip()
        
        if not url:
            print(f"[跳过] 源 #{i}: 缺少 URL")
            continue
        
        print(f"[{i}/{len(sources)}] 处理: {url}")
        
        # 获取站点列表
        sites = get_sites_from_url(url)
        if not sites:
            print(f"  [警告] 未获取到站点数据")
            continue
        
        print(f"  [成功] 获取到 {len(sites)} 个站点")
        
        # 处理每个站点
        for site in sites:
            if not isinstance(site, dict):
                continue
                
            # 修复路径
            if base:
                site = fix_site_paths(site.copy(), base, jar)
            
            # 检查是否已存在
            key = site.get("key", "").strip()
            if not key or key in existing_keys:
                continue
            
            # 添加到结果
            target_sites.append(site)
            existing_keys.add(key)
            added_count += 1
    
    print(f"\n[统计] 新增站点: {added_count}")
    print(f"[统计] 总计站点: {len(target_sites)}")
    
    # 6. 构建最终输出
    output_data = {
        "sites": target_sites,
        "updateTime": time.strftime("%Y-%m-%d %H:%M:%S"),
        "totalSites": len(target_sites)
    }
    
    # 7. 写入本地文件
    try:
        with open(TARGET_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2, separators=(",", ":"))
        print(f"[保存] 已保存到本地: {TARGET_JSON_PATH}")
    except Exception as e:
        print(f"[错误] 保存文件失败: {e}")
        sys.exit(1)
    
    # 8. 如果配置了 GitHub 信息，则推送
    if GITHUB_TOKEN and GITHUB_REPO:
        print(f"\n[GitHub] 准备推送到仓库: {GITHUB_REPO}")
        
        # 读取文件内容并编码为 base64
        try:
            with open(TARGET_JSON_PATH, "r", encoding="utf-8") as f:
                file_content = f.read()
            
            import base64
            encoded_content = base64.b64encode(file_content.encode("utf-8")).decode("ascii")
            
            # 推送文件
            success = push_to_github(
                file_path=TARGET_JSON_PATH,
                content=encoded_content,
                repo=GITHUB_REPO,
                token=GITHUB_TOKEN,
                branch=GITHUB_BRANCH,
                commit_message=f"Auto update sites ({len(target_sites)} sites) at {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            if success:
                print(f"[完成] 任务执行成功！")
            else:
                print(f"[警告] 文件保存成功，但推送 GitHub 失败")
        except Exception as e:
            print(f"[错误] GitHub 推送异常: {e}")
    else:
        print(f"\n[提示] 未配置 GitHub 推送，仅在本地保存")
        print(f"[完成] 任务执行完成！")

# ======================
# 程序入口
# ======================
if __name__ == "__main__":
    main()
